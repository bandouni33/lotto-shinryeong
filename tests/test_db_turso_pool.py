"""db_turso 클라이언트 풀 불변식 테스트 (2026-09-19, 동시접속 처리량 개선).

배경: 앱 전체가 Turso 클라이언트(ClientSync) 1개를 공유하면, 그 내부의 전용
스레드 1개 큐에 모든 세션·모든 쿼리가 직렬로 서서 DB 처리량 상한이
"1 / 왕복지연"으로 고정된다(관측된 동시접속 30~50명 한계). 그래서 클라이언트를
N개 풀로 만들어 라운드로빈으로 나눠 쓰도록 바꿨다 — 이 파일은 그 변경이 모든
유효 입력에서 지켜야 하는 성질을 검증한다.

불변식:
  P1. acquire()는 항상 [0, size) 범위의 슬롯번호와 그 슬롯의 클라이언트를 준다.
  P2. 라운드로빈은 균등하다 — 슬롯 수의 배수만큼 뽑으면 정확히 같은 횟수,
      배수가 아니어도 슬롯 간 편차가 1 이하다.
  P3. 동시 실행 수는 풀 크기를 넘지 않는다(풀 1 = 반드시 직렬, 풀 4 = 2~4).
  P4. 같은 부하에서 풀 4가 풀 1보다 실제로 빠르다(병렬화가 일어난다).
  P5. 연속 타임아웃이 임계치 미만이면 어떤 클라이언트도 교체되지 않는다.
  P6. 임계치에 처음 닿은 순간에만 True를 돌려주고, 그때 교체 대상 슬롯만
      바뀐다 — 다른 슬롯의 클라이언트 객체는 그대로이고 풀 크기도 그대로다.
  P7. 성공 한 번이 그 슬롯의 연속 카운터를 0으로 되돌린다(간헐 타임아웃으로
      멀쩡한 클라이언트가 교체되지 않는다).
  P8. 재생성 실패는 예외를 밖으로 던지지 않고 기존 클라이언트를 유지한다
      (타임아웃 처리 도중이라, 예외가 새면 원래 신호가 덮인다).
  P9. 실제 타임아웃 경로(_guarded)가 그 슬롯에만 기록된다/비타임아웃 예외는
      타임아웃으로 세지 않는다.
  P10. 풀 크기 환경변수는 어떤 쓰레기 값에도 안전한 정수를 낸다(경계 포함).
  P11. connect()는 풀 슬롯을 라운드로빈으로 쓰는 래퍼를 주고, 그 래퍼로 실제
       쿼리가 끝까지 동작한다.
  P12. 한 번의 batch_execute는 반드시 클라이언트 1개에서만 실행된다(원자성
       전제 유지 — 문장이 여러 클라이언트로 흩어지지 않는다).

pytest 없이도 돌도록 표준 assert + __main__ 러너를 둔다(다른 테스트와 동일 규칙).
"""

from __future__ import annotations

import os
import sqlite3
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import libsql_client  # noqa: E402

import db_turso  # noqa: E402

LATENCY = 0.06


class FakeResultSet:
    def __init__(self, rows=None, columns=("ok",)):
        self.columns = columns
        self.rows = rows if rows is not None else [(1,)]
        self.last_insert_rowid = 0
        self.rows_affected = 1


class FakeClient:
    """execute()가 latency만큼 자는 가짜 Turso 클라이언트.

    중요: 실제 libsql_client의 ClientSync는 클라이언트마다 전용 스레드 1개 큐로
    요청을 "하나씩" 처리한다(libsql_client/sync.py의 _AsyncExecutor). 가짜가
    이 성질을 흉내내지 않으면 "풀 1개 = 직렬"이라는 전제 자체가 테스트에서
    사라진다 — 그래서 self._serial 락으로 클라이언트 내부 직렬화를 재현한다.

    앱 전체 동시 실행 수는 전역으로 세어 관측한다(풀 크기가 곧 상한이라는
    P3의 관측 수단)."""

    _lock = threading.Lock()
    _inflight = 0
    _max_inflight = 0

    def __init__(self, latency=0.0):
        self.latency = latency
        self.calls = 0
        self.batch_calls = 0
        self.fail_on = None  # callable(sql) -> Exception | None
        self._serial = threading.Lock()
        self.max_inflight_in_client = 0

    def execute(self, sql, args=None):
        with self._serial:  # 클라이언트 내부 큐 = 한 번에 하나
            self.max_inflight_in_client = max(self.max_inflight_in_client, 1)
            with FakeClient._lock:
                FakeClient._inflight += 1
                FakeClient._max_inflight = max(
                    FakeClient._max_inflight, FakeClient._inflight
                )
            try:
                if self.latency:
                    time.sleep(self.latency)
                self.calls += 1
                if self.fail_on is not None:
                    exc = self.fail_on(sql)
                    if exc is not None:
                        raise exc
                return FakeResultSet()
            finally:
                with FakeClient._lock:
                    FakeClient._inflight -= 1

    def batch(self, stmts):
        self.batch_calls += 1
        return [FakeResultSet() for _ in stmts]

    def close(self):
        pass

    @classmethod
    def reset(cls):
        with cls._lock:
            cls._inflight = 0
            cls._max_inflight = 0


def _pool(size: int, latency: float = 0.0):
    """가짜 팩토리로 만든 풀 + 슬롯 순서대로 생성된 클라이언트 목록."""
    created: list[FakeClient] = []

    def factory():
        client = FakeClient(latency=latency)
        created.append(client)
        return client

    return db_turso._ClientPool(size, factory=factory), created


# ── P1~P2: 라운드로빈 ────────────────────────────────────────────


def test_acquire_is_in_range_and_points_at_that_slot():
    pool, created = _pool(4)
    assert pool.size == 4, f"풀 크기가 요청과 다르다: {pool.size}"
    assert len(created) == 4, f"슬롯 수만큼 클라이언트를 만들지 않았다: {len(created)}"
    for _ in range(17):  # 슬롯 수와 서로소인 횟수까지
        idx, client = pool.acquire()
        assert 0 <= idx < pool.size, f"슬롯번호가 범위 밖이다: {idx}"
        assert client is pool.client_at(idx), "acquire가 슬롯과 다른 클라이언트를 돌려줬다"


def test_round_robin_is_even():
    size = 4
    pool, _ = _pool(size)
    seen = [pool.acquire()[0] for _ in range(size * 5)]
    counts = [seen.count(i) for i in range(size)]
    assert counts == [5] * size, f"배수만큼 뽑았는데 균등하지 않다: {counts}"

    for extra in range(1, size):
        seen = [pool.acquire()[0] for _ in range(size * 3 + extra)]
        counts = [seen.count(i) for i in range(size)]
        assert max(counts) - min(counts) <= 1, f"슬롯 편차가 1을 넘었다: {counts}"


# ── P3~P4: 실제 동시성 ───────────────────────────────────────────


def _run_load(pool_size: int, workers: int):
    FakeClient.reset()
    pool, clients = _pool(pool_size, latency=LATENCY)
    barrier = threading.Barrier(workers)
    errors: list[str] = []
    lock = threading.Lock()

    def work():
        try:
            barrier.wait(timeout=5)
        except Exception:
            pass
        try:
            slot, client = pool.acquire()
            db_turso._ConnectionWrapper(client, pool, slot).execute("SELECT 1")
        except Exception as e:  # noqa: BLE001
            with lock:
                errors.append(f"{type(e).__name__}: {e}")

    threads = [threading.Thread(target=work) for _ in range(workers)]
    started = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
    # 가짜 클라이언트가 실제 직렬화를 흉내내는지도 함께 확인한다(불변식 P3의 전제)
    for c in clients:
        assert c.max_inflight_in_client <= 1, "가짜 클라이언트 내부 직렬화가 깨졌다"
    return time.perf_counter() - started, FakeClient._max_inflight, errors


def test_concurrency_is_bounded_by_pool_size():
    workers = 8
    _, max_one, errors_one = _run_load(1, workers)
    _, max_four, errors_four = _run_load(4, workers)
    assert not errors_one and not errors_four, f"부하 중 예외: {errors_one} {errors_four}"
    assert max_one == 1, f"풀 1인데 동시 실행이 1을 넘었다(직렬화 전제 위반): {max_one}"
    assert 2 <= max_four <= 4, f"풀 4의 동시 실행 수가 범위 밖이다: {max_four}"


def test_pool_four_is_faster_than_pool_one_on_same_load():
    workers = 8
    serial, serial_max, _ = _run_load(1, workers)  # 8 x LATENCY (직렬)
    parallel, parallel_max, _ = _run_load(4, workers)  # 2 x LATENCY (4줄)
    print(
        f"    [timing] pool1={serial:.3f}s(max_inflight={serial_max}) "
        f"pool4={parallel:.3f}s(max_inflight={parallel_max}) "
        f"LATENCY={LATENCY}s workers={workers}"
    )
    assert parallel_max >= 2, (
        f"풀 4인데 동시 실행이 관측되지 않았다: pool1={serial_max} pool4={parallel_max}"
    )
    assert parallel < serial / 2, (
        f"병렬화 이득이 없다: pool1={serial:.3f}s(max={serial_max}) "
        f"pool4={parallel:.3f}s(max={parallel_max}) LATENCY={LATENCY}s"
    )


# ── P5~P7: 임계치와 카운터 ───────────────────────────────────────


def test_below_threshold_nothing_is_replaced():
    pool, _ = _pool(3)
    before = [pool.client_at(i) for i in range(3)]
    for _ in range(db_turso._TIMEOUT_RECYCLE_THRESHOLD - 1):
        assert pool.note_timeout(2) is False, "임계치 미만에서 교체 신호를 냈다"
    assert pool.client_at(2) is before[2], "임계치 미만인데 클라이언트가 바뀌었다"


def test_recycle_replaces_only_that_slot_and_only_at_threshold():
    pool, _ = _pool(4)
    before = [pool.client_at(i) for i in range(4)]
    original_pool_fn = db_turso._client_pool

    for _ in range(db_turso._TIMEOUT_RECYCLE_THRESHOLD - 1):
        assert pool.note_timeout(1) is False, "임계치 미만에서 교체 신호를 냈다"
    assert pool.client_at(1) is before[1], "임계치 미만인데 클라이언트가 바뀌었다"
    try:
        # 계약: note_timeout이 "임계치에 닿았다"를 정확히 한 번 알리고,
        # 실제 교체는 그 신호를 받은 호출부(_recycle_after_timeouts)가 한다.
        assert pool.note_timeout(1) is True, "임계치에 닿았는데 교체 신호를 안 냈다"
        db_turso._client_pool = lambda: pool
        assert db_turso._recycle_after_timeouts(1) is True
    finally:
        db_turso._client_pool = original_pool_fn

    assert pool.client_at(1) is not before[1], "임계치에 닿았는데 교체되지 않았다"
    for i in (0, 2, 3):
        assert pool.client_at(i) is before[i], f"무관한 슬롯 {i}가 교체됐다"
    assert pool.size == 4, f"교체가 풀 크기를 바꿨다: {pool.size}"

    # 교체 직후 카운터는 0 — 다시 임계치만큼 쌓여야 다음 교체가 일어난다
    for _ in range(db_turso._TIMEOUT_RECYCLE_THRESHOLD - 1):
        assert pool.note_timeout(1) is False, "교체 후 카운터가 초기화되지 않았다"
    assert pool.note_timeout(-1) is False and pool.note_timeout(99) is False, (
        "범위 밖 슬롯번호가 교체 신호를 냈다"
    )


def test_success_resets_consecutive_counter():
    pool, _ = _pool(2)
    for _ in range(db_turso._TIMEOUT_RECYCLE_THRESHOLD - 1):
        pool.note_timeout(0)
    pool.note_success(0)
    for _ in range(db_turso._TIMEOUT_RECYCLE_THRESHOLD - 1):
        assert pool.note_timeout(0) is False, "성공이 연속 카운터를 리셋하지 않았다"
    pool.note_success(1)  # 관계없는 슬롯의 성공은 0번 슬롯에 영향이 없어야 한다


# ── P8: 재생성 실패 ─────────────────────────────────────────────


def test_replacement_failure_keeps_old_client_and_never_raises():
    attempts = {"n": 0}
    first = FakeClient()

    def factory():
        attempts["n"] += 1
        if attempts["n"] == 1:
            return first
        raise RuntimeError("네트워크 없음")

    pool = db_turso._ClientPool(1, factory=factory)
    assert pool.client_at(0) is first
    assert pool.replace_slot(0) is False, "생성 실패인데 성공을 반환했다"
    assert pool.client_at(0) is first, "생성 실패인데 기존 클라이언트가 사라졌다"
    assert pool.size == 1, "생성 실패가 풀 크기를 바꿨다"
    assert pool.replace_slot(-1) is False and pool.replace_slot(5) is False, (
        "범위 밖 슬롯번호가 예외/성공을 냈다"
    )


def test_recycle_after_timeouts_never_raises_and_rebinds_executor():
    pool, _ = _pool(2)
    original_pool_fn = db_turso._client_pool
    original_executor = db_turso._EXECUTOR
    try:
        db_turso._client_pool = lambda: pool
        assert db_turso._recycle_after_timeouts(1) is True
        assert db_turso._EXECUTOR is not original_executor, (
            "재생성 시 가드 워커풀을 새로 만들지 않았다"
        )
        assert db_turso._recycle_after_timeouts(99) is False, (
            "범위 밖 슬롯으로도 예외 없이 False를 내야 한다"
        )
    finally:
        db_turso._client_pool = original_pool_fn


# ── P9: 실제 타임아웃 경로 배선 ───────────────────────────────────


def test_real_timeout_marks_only_that_slot():
    original_timeout = db_turso._QUERY_TIMEOUT_SEC
    original_pool_fn = db_turso._client_pool
    db_turso._QUERY_TIMEOUT_SEC = 0.02
    try:
        pool, _ = _pool(2, latency=0.5)  # 모든 호출이 타임아웃 나도록
        db_turso._client_pool = lambda: pool
        before = [pool.client_at(i) for i in range(2)]
        conn = db_turso._ConnectionWrapper(pool.client_at(1), pool, 1)

        for _ in range(db_turso._TIMEOUT_RECYCLE_THRESHOLD):
            try:
                conn.execute("SELECT 1")
                raise AssertionError("타임아웃이 나야 하는데 성공했다")
            except TimeoutError:
                pass

        assert pool.client_at(1) is not before[1], (
            "실제 타임아웃이 임계치까지 쌓였는데 그 슬롯이 교체되지 않았다"
        )
        assert pool.client_at(0) is before[0], "무관한 슬롯이 함께 교체됐다"
        assert pool.size == 2
    finally:
        db_turso._QUERY_TIMEOUT_SEC = original_timeout
        db_turso._client_pool = original_pool_fn


def test_non_timeout_error_is_not_counted_as_timeout():
    pool, _ = _pool(1)
    slot, client = pool.acquire()
    client.fail_on = lambda sql: libsql_client.LibsqlError(
        "UNIQUE constraint failed: wallet.member_id", "SQLITE_CONSTRAINT"
    )
    conn = db_turso._ConnectionWrapper(client, pool, slot)

    raised = None
    try:
        conn.execute("INSERT INTO t VALUES (1)")
    except Exception as e:  # noqa: BLE001
        raised = e
    assert isinstance(raised, sqlite3.IntegrityError), (
        f"기존 UNIQUE 예외 매핑이 깨졌다: {raised!r}"
    )

    client.fail_on = None
    for _ in range(db_turso._TIMEOUT_RECYCLE_THRESHOLD - 1):
        assert pool.note_timeout(slot) is False, (
            "비타임아웃 예외가 타임아웃으로 집계됐다"
        )


# ── P10: 풀 크기 파싱 ────────────────────────────────────────────


def test_pool_size_env_is_always_safe():
    original = os.environ.get("TURSO_CLIENT_POOL_SIZE")
    cases = {
        "": db_turso._DEFAULT_POOL_SIZE,
        "   ": db_turso._DEFAULT_POOL_SIZE,
        "abc": db_turso._DEFAULT_POOL_SIZE,
        "4.5": db_turso._DEFAULT_POOL_SIZE,
        "0": db_turso._DEFAULT_POOL_SIZE,
        "-3": db_turso._DEFAULT_POOL_SIZE,
        "1": 1,
        "4": 4,
        "16": db_turso._MAX_POOL_SIZE,
        "17": db_turso._MAX_POOL_SIZE,
        "9999": db_turso._MAX_POOL_SIZE,
    }
    try:
        for raw, expected in cases.items():
            os.environ["TURSO_CLIENT_POOL_SIZE"] = raw
            actual = db_turso._pool_size_from_env()
            assert actual == expected, f"{raw!r} → {actual} (기대 {expected})"
            assert 1 <= actual <= db_turso._MAX_POOL_SIZE, f"범위 밖: {actual}"
        os.environ.pop("TURSO_CLIENT_POOL_SIZE", None)
        assert db_turso._pool_size_from_env() == db_turso._DEFAULT_POOL_SIZE
    finally:
        if original is None:
            os.environ.pop("TURSO_CLIENT_POOL_SIZE", None)
        else:
            os.environ["TURSO_CLIENT_POOL_SIZE"] = original


def test_executor_workers_never_undersize_the_pool():
    assert db_turso._executor_workers(1) >= 16
    for size in range(1, db_turso._MAX_POOL_SIZE + 1):
        workers = db_turso._executor_workers(size)
        assert workers >= 4 * size, f"풀 {size} 대비 워커가 부족하다: {workers}"
        assert workers >= db_turso._executor_workers(size - 1), "풀을 키웠는데 워커가 줄었다"


# ── P11~P12: 조립된 경로(connect/batch) ──────────────────────────


def test_connect_round_robins_over_pool_slots():
    original_factory = db_turso._make_client
    original_pool_fn = db_turso._client_pool
    try:
        db_turso._make_client = lambda: FakeClient()
        pool = db_turso._ClientPool(4)  # 팩토리 미지정 → 위 패치를 쓴다
        db_turso._client_pool = lambda: pool

        slots = [db_turso.connect().slot for _ in range(8)]
        assert slots == [0, 1, 2, 3, 0, 1, 2, 3], f"connect가 슬롯을 고르게 쓰지 않는다: {slots}"

        conn = db_turso.connect()
        assert conn.row_factory is None
        assert conn.execute("SELECT 1") is not None, "래퍼가 쿼리를 끝까지 처리하지 못했다"
        conn.commit()  # no-op 이지만 예외가 나면 안 된다
        conn.close()  # 풀 공유 자원이므로 닫히면 안 된다
        assert pool.size == 4, f"close()가 풀을 건드렸다: {pool.size}"
        assert db_turso.connect().slot in range(4)
    finally:
        db_turso._make_client = original_factory
        db_turso._client_pool = original_pool_fn


def test_batch_execute_stays_on_one_client():
    pool, created = _pool(4)
    slot, client = pool.acquire()
    conn = db_turso._ConnectionWrapper(client, pool, slot)

    results = conn.batch_execute(
        [("UPDATE wallet SET balance = balance - 1", []), ("INSERT INTO ledger VALUES (1)", [])]
    )
    assert len(results) == 2, f"문장 2개에 결과가 2개가 아니다: {len(results)}"
    used = [c.batch_calls for c in created]
    assert used.count(1) == 1 and sum(used) == 1, (
        f"배치가 여러 클라이언트로 흩어졌다(원자성 전제 위반): {used}"
    )


def _main() -> int:
    try:  # cp949 콘솔에서도 결과가 읽히고, 로그가 예외로 바뀌지 않게
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        started = time.perf_counter()
        try:
            t()
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"ERROR {t.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"PASS {t.__name__} ({time.perf_counter() - started:.2f}s)")
        sys.stdout.flush()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.stdout.flush()
    # db_turso가 import 시점에 만드는 비데몬 워커 스레드 때문에 프로세스가
    # 스스로 끝나지 않는다 — 다른 테스트와 같은 방식으로 즉시 종료한다.
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
