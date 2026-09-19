"""
Turso(libsql_client, 순수 Python HTTP 클라이언트) 연결을
기존 sqlite3 스타일 코드와 호환되게 감싸는 공통 모듈.
"""

from __future__ import annotations

import concurrent.futures
import os
import re
import sqlite3
import threading
import time

import libsql_client
import streamlit as st

# 2026-09-03: 어제 앱이 12시간 동안 먹통이었던 사고 이후 원인 조사 —
# libsql_client 라이브러리 전체(sync.py의 _AsyncExecutor.submit_coro가
# fut.result()를 타임아웃 없이 호출)에 타임아웃 보호장치가 전혀 없다는 걸
# 발견했다. Turso 서버가 응답을 안 주는 상황이 오면(네트워크 문제 등) 그
# 요청을 기다리는 스레드가 "예외조차 안 던지고" 영원히 멈춰버려서, try/except
# 로도 못 잡고 그 요청을 처리하던 세션이 그대로 죽는다 — 여러 세션이 동시에
# 이러면 앱 전체가 먹통이 된 것처럼 보일 수 있다. 아래 _EXECUTOR로 모든 Turso
# 호출을 감싸서 강제 타임아웃을 걸어준다 — 타임아웃 나면 TimeoutError를
# 던지고, 이건 기존에 이미 코드 곳곳(draw_results_db 등)에 있던 try/except가
# 그대로 잡아서 안전하게 폴백(캐시된 값 사용 등)하도록 설계돼 있다.
_DEFAULT_POOL_SIZE = 4
_MAX_POOL_SIZE = 16


def _safe_log(message: str) -> None:
    """복구/장애 경로 전용 로그 — 절대 예외를 밖으로 던지지 않는다.

    이 로그들은 타임아웃을 처리하는 도중에 불린다. print 자체가 실패하면
    (예: cp949 콘솔에서 em-dash를 못 쎄 UnicodeEncodeError) 그 예외가
    방금 만든 TimeoutError를 덮어써 호출부의 폴백 로직이 깨진다 — 테스트에서
    실제로 재현됐다."""
    try:
        print(message)
    except Exception:
        pass


def _pool_size_from_env() -> int:
    """TURSO_CLIENT_POOL_SIZE (기본 4). 잘못된 값은 조용히 기본값으로
    폴백한다 — 환경변수를 0/음수/문자로 잘못 넣었다고 클라이언트가 0개가 되어
    모든 DB 호출이 실패하면 안 된다."""
    raw = os.getenv("TURSO_CLIENT_POOL_SIZE", "")
    try:
        size = int(str(raw).strip())
    except (TypeError, ValueError):
        return _DEFAULT_POOL_SIZE
    if size < 1:
        return _DEFAULT_POOL_SIZE
    return min(size, _MAX_POOL_SIZE)


def _executor_workers(pool_size: int) -> int:
    """가드 워커 수 — _guarded()는 호출이 끝날 때까지 워커 하나를 붙잡고
    future.result()를 기다리므로, 풀을 늘린 만큼 동시에 대기하는 호출 수도
    늘어난다(16 고정이면 풀을 키운 뒤 여기가 새 병목이 된다)."""
    return max(16, 4 * pool_size)


def _new_executor(pool_size: int) -> concurrent.futures.ThreadPoolExecutor:
    return concurrent.futures.ThreadPoolExecutor(
        max_workers=_executor_workers(pool_size), thread_name_prefix="turso-guard"
    )


# ─────────────────────────────────────────────────────────────
# 2026-09-19: Turso 클라이언트 풀 (동시접속 처리량)
#
# libsql_client의 ClientSync는 내부에 전용 스레드 1개 + 이벤트루프 1개
# (libsql_client/sync.py의 _AsyncExecutor)를 두고 그 큐에서 요청을 "하나씩"
# 처리한다. 앱 전체가 그 클라이언트를 1개만 공유하면 모든 세션·모든 쿼리가
# 같은 한 줄에 서서 처리량 상한이 "1 / 왕복지연"으로 고정된다 — 왕복 100ms면
# 초당 10쿼리, 메인 렌더 한 번에 15~20왕복이면 초당 0.5~0.7렌더(분당 30~40)로,
# 실측된 동시접속 30~50명 한계와 일치한다.
#
# 그래서 큐를 _POOL_SIZE개로 갈라 쓴다(기본 4). 슬롯마다 자기 전용 스레드·큐를
# 가진 독립 클라이언트라 DB 처리량이 슬롯 수에 거의 비례해 늘어난다.
# 위 _EXECUTOR는 "이 요청 하나를 포기시키는" 가드일 뿐이고(2026-09-03 사고
# 대응), 실제 직렬화 지점은 각 클라이언트 내부 큐라는 점이 핵심이다.
#
# 재생성도 슬롯 단위로 바뀐다: 연속 타임아웃이 _TIMEOUT_RECYCLE_THRESHOLD번
# 쌓인 슬롯만 교체하고 멀쩡한 슬롯은 건드리지 않는다(예전에는 한 줄이 막히면
# 클라이언트 캐시 전체를 비워 나머지 연결까지 버렸다). 막힌 옛 클라이언트/
# 스레드는 강제로 죽일 수 없어 버려두지만 블록된 채 CPU를 쓰지 않으므로
# 무해하다 — 정상 경로(성공하는 호출)는 전혀 건드리지 않는다.
# ─────────────────────────────────────────────────────────────
_TIMEOUT_RECYCLE_THRESHOLD = 5
_POOL_SIZE = _pool_size_from_env()
_EXECUTOR = _new_executor(_POOL_SIZE)
_QUERY_TIMEOUT_SEC = 10


class _ClientPool:
    """Turso 클라이언트 N개를 라운드로빈으로 나눠 쓰는 풀.

    Streamlit 캐시(_client_pool)와 분리해 둔다 — 그래야 테스트가 가짜 팩토리로
    라운드로빈·임계치·슬롯 단위 재생성 규칙을 그대로 검증할 수 있다. 슬롯 수가
    곧 앱 전체의 동시 DB 처리 줄 수다.

    범위를 벗어난 인덱스가 들어와도 예외를 던지지 않는다 — note_timeout()은
    TimeoutError를 처리하는 도중에 불리므로, 여기서 예외가 새면 호출부가
    원래의 타임아웃 신호를 잃고 폴백 로직이 깨진다.
    """

    def __init__(self, size: int, factory=None):
        self._factory = factory or _make_client
        self._lock = threading.Lock()
        self._clients = [self._factory() for _ in range(max(1, int(size)))]
        self._timeouts = [0] * len(self._clients)
        self._next = 0

    @property
    def size(self) -> int:
        return len(self._clients)

    def acquire(self):
        """(슬롯번호, 클라이언트) — 라운드로빈. 슬롯번호는 타임아웃 집계와
        재생성 대상 지정에 쓴다."""
        with self._lock:
            idx = self._next % len(self._clients)
            self._next += 1
            return idx, self._clients[idx]

    def client_at(self, idx: int):
        return self._clients[idx]

    def note_timeout(self, idx: int) -> bool:
        """이 슬롯의 연속 타임아웃을 1 늘린다. 임계치에 처음 닿은 순간에만
        True를 돌려주고 카운터를 0으로 되돌린다(교체는 호출부가 한다)."""
        with self._lock:
            if idx < 0 or idx >= len(self._timeouts):
                return False
            self._timeouts[idx] += 1
            if self._timeouts[idx] < _TIMEOUT_RECYCLE_THRESHOLD:
                return False
            self._timeouts[idx] = 0
            return True

    def note_success(self, idx: int) -> None:
        with self._lock:
            if 0 <= idx < len(self._timeouts) and self._timeouts[idx]:
                self._timeouts[idx] = 0

    def replace_slot(self, idx: int) -> bool:
        """그 슬롯만 새 클라이언트로 교체한다(나머지 슬롯은 그대로). 생성이
        실패하면 기존 클라이언트를 유지하고 False — 이 함수도 타임아웃 처리
        경로에서 불리므로 예외를 밖으로 던지지 않는다."""
        if idx < 0 or idx >= self.size:
            return False
        with self._lock:
            try:
                new_client = self._factory()
            except Exception as e:
                _safe_log(
                    f"[db_turso] 슬롯 {idx} 클라이언트 재생성 실패"
                    f"({type(e).__name__}: {e}) — 기존 클라이언트 유지"
                )
                return False
            self._clients[idx] = new_client
            self._timeouts[idx] = 0
            return True


def _recycle_after_timeouts(slot: int) -> bool:
    """슬롯 하나를 새 클라이언트로 교체하고, 그때만 가드 워커풀도 새로 만든다
    (막힌 클라이언트를 기다리느라 눌러앉은 워커를 정리하기 위함)."""
    global _EXECUTOR
    replaced = False
    try:
        replaced = _client_pool().replace_slot(slot)
    except Exception as e:
        _safe_log(f"[db_turso] 슬롯 {slot} 교체 실패({type(e).__name__}: {e})")
    old_executor = _EXECUTOR
    _EXECUTOR = _new_executor(_POOL_SIZE)
    old_executor.shutdown(wait=False)
    _safe_log(
        f"[db_turso] 슬롯 {slot} 연속 타임아웃 {_TIMEOUT_RECYCLE_THRESHOLD}회 — "
        f"클라이언트 재생성(replaced={replaced})"
    )
    return replaced


class Row(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class _CursorWrapper:
    def __init__(self, result_set):
        self._rs = result_set
        self._idx = 0

    @property
    def lastrowid(self):
        return self._rs.last_insert_rowid

    @property
    def rowcount(self):
        return self._rs.rows_affected

    def _wrap(self, raw):
        return Row(zip(self._rs.columns, raw))

    def fetchone(self):
        if self._idx >= len(self._rs.rows):
            return None
        row = self._wrap(self._rs.rows[self._idx])
        self._idx += 1
        return row

    def fetchall(self):
        rows = [self._wrap(r) for r in self._rs.rows[self._idx:]]
        self._idx = len(self._rs.rows)
        return rows

    def __iter__(self):
        return iter(self.fetchall())


class _ConnectionWrapper:
    def __init__(self, client, pool: _ClientPool | None = None, slot: int | None = None):
        self._client = client
        self._pool = pool
        self._slot = slot
        self.row_factory = None

    @property
    def slot(self) -> int | None:
        """이 연결이 잡고 있는 풀 슬롯 번호(진단/테스트용)."""
        return self._slot

    def _note_timeout(self):
        """타임아웃을 그 슬롯에만 기록하고, 임계치에 닿으면 그 슬롯만 재생성한다.
        예외를 밖으로 던지지 않는다 — 여기서 예외가 새면 방금 만든
        TimeoutError가 다른 예외로 덮여 호출부의 폴백이 깨진다."""
        if self._pool is None or self._slot is None:
            return
        try:
            due = self._pool.note_timeout(self._slot)
        except Exception:
            return
        if due:
            _recycle_after_timeouts(self._slot)

    def _note_success(self):
        if self._pool is None or self._slot is None:
            return
        try:
            self._pool.note_success(self._slot)
        except Exception:
            pass

    def _guarded(self, func, *args):
        """모든 Turso 호출의 공통 관문 — _QUERY_TIMEOUT_SEC 안에 안 끝나면
        TimeoutError를 던진다(무한정 멈추는 것 방지). 백그라운드 스레드 자체는
        (라이브러리 구조상 강제로 못 죽이므로) 계속 남아있을 수 있지만, 최소한
        "이 요청을 기다리던 세션"은 살아나서 폴백 로직으로 넘어갈 수 있다."""
        future = _EXECUTOR.submit(func, *args)
        try:
            result = future.result(timeout=_QUERY_TIMEOUT_SEC)
        except concurrent.futures.TimeoutError as e:
            self._note_timeout()
            raise TimeoutError(
                f"Turso 쿼리가 {_QUERY_TIMEOUT_SEC}초 안에 응답하지 않았습니다"
                "(네트워크 문제로 추정, 자동 폴백됨)"
            ) from e
        self._note_success()
        return result

    def execute(self, sql, params=()):
        # 2026-09-11: libsql_client/http.py가 에러/부분 응답을 받으면
        # response["result"] 접근에서 KeyError('result')를 던지는 게 실측 확인됐다
        # (일시적 서버·네트워크 문제로 추정, 재시도하면 대개 성공). 읽기 쿼리는
        # 재시도해도 안전하므로 SELECT에 한해 짧게 몇 번 다시 시도한다. 쓰기는
        # 부분 적용 위험이 있어 재시도하지 않는다(기존 동작 유지).
        is_read = sql.lstrip()[:6].upper() == "SELECT"
        attempts = 4 if is_read else 1
        for i in range(attempts):
            try:
                rs = self._guarded(self._client.execute, sql, list(params) if params else [])
                return _CursorWrapper(rs)
            except libsql_client.LibsqlError as e:
                msg = str(e)
                if "UNIQUE" in msg or "CONSTRAINT" in msg.upper():
                    raise sqlite3.IntegrityError(msg) from e
                raise
            except KeyError:
                if i + 1 < attempts:
                    time.sleep(0.35 * (i + 1))
                    continue
                raise

    def executemany(self, sql, params_list):
        stmts = [(sql, list(p)) for p in params_list]
        if not stmts:
            return
        try:
            self._guarded(self._client.batch, stmts)
        except libsql_client.LibsqlError as e:
            msg = str(e)
            if "UNIQUE" in msg or "CONSTRAINT" in msg.upper():
                raise sqlite3.IntegrityError(msg) from e
            raise

    def batch_execute(self, statements):
        """2026-09-19: 잔액 차감/충전 UPDATE와 wallet_ledger INSERT처럼 "둘 다
        성공하거나 둘 다 실패해야" 하는 서로 다른 SQL 여러 개를 한 번의 원격
        왕복으로 원자적으로 실행한다. executemany()와 달리 statements는
        [(sql, params), ...] 형태로 서로 다른 SQL을 섞을 수 있다.

        libsql_client의 batch()는 Hrana 배치 API(v1/batch)를 쓰는데, 이 배치는
        서버에서 하나의 트랜잭션으로 실행된다 — 이미 executemany()/executescript()가
        같은 _client.batch()에 기대고 있는 것과 동일한 보장이다. RETURNING이 있는
        SELECT/UPDATE는 각 결과를 순서대로 반환하므로, 호출부는 statements와 같은
        순서의 _CursorWrapper 리스트를 받는다.

        _guarded()의 10초 타임아웃에 걸리면(TimeoutError) 서버가 이 배치를 실제로
        커밋했는지 클라이언트는 알 수 없다 — 이건 batch로 묶어도 근본적으로
        없앨 수 없는, 네트워크 왕복 자체의 한계다(db_turso.py 상단 2026-09-03
        사고 주석 참고). 다만 최소한 "UPDATE는 반영됐는데 INSERT는 안 됨" 같은
        절반만 적용되는 상태는 batch 자체가 원자적이라 발생하지 않는다."""
        stmts = [(sql, list(params) if params else []) for sql, params in statements]
        if not stmts:
            return []
        try:
            result_sets = self._guarded(self._client.batch, stmts)
        except libsql_client.LibsqlError as e:
            msg = str(e)
            if "UNIQUE" in msg or "CONSTRAINT" in msg.upper():
                raise sqlite3.IntegrityError(msg) from e
            raise
        return [_CursorWrapper(rs) for rs in result_sets]

    def executescript(self, script):
        stmts = [s.strip() for s in re.split(r";\s*\n|;\s*$", script, flags=re.M) if s.strip()]
        self._guarded(self._client.batch, stmts)

    def commit(self):
        pass

    def close(self):
        # 이 클라이언트는 st.cache_resource로 앱 전체(모든 세션)가 공유하는
        # 자원이다 — 기존 코드 수백 곳이 "매번 새로 열고 쓰고 닫는다"는 전제로
        # 함수 끝마다 conn.close()를 호출하고 있는데, 여기서 진짜로 닫아버리면
        # 그 사용자 하나의 요청이 끝나는 순간 다른 모든 세션의 DB 연결까지
        # 통째로 끊겨버린다(2026-08-22, 동시접속 대비 점검 중 발견). 그래서
        # 아무 동작도 하지 않는다 — 실제 종료는 프로세스 자체가 끝날 때
        # 자연스럽게 정리된다.
        pass


def _make_client() -> libsql_client.sync.ClientSync:
    """Turso 클라이언트 1개 생성 — 풀의 슬롯 수만큼 호출된다."""
    url = os.getenv("TURSO_DATABASE_URL")
    token = os.getenv("TURSO_AUTH_TOKEN")
    if not url or not token:
        try:
            url = url or st.secrets.get("TURSO_DATABASE_URL", None)
            token = token or st.secrets.get("TURSO_AUTH_TOKEN", None)
        except Exception:
            pass
    if not url or not token:
        raise RuntimeError(
            "TURSO_DATABASE_URL / TURSO_AUTH_TOKEN 환경변수가 설정되지 않았습니다."
        )
    return libsql_client.create_client_sync(url=url, auth_token=token)


@st.cache_resource(show_spinner=False)
def _client_pool() -> _ClientPool:
    # 예전엔 원격 클라이언트를 요청마다 새로 만들다가(생성 비용), 그 다음엔
    # 1개만 만들어 앱 전체가 공유했다(모든 쿼리가 그 클라이언트 내부의 단일
    # 스레드 큐 한 줄에 서는 처리량 상한). 이제 _POOL_SIZE개를 프로세스 전역으로
    # 만들어 라운드로빈으로 나눠 쓴다 — 위 _ClientPool 주석 참고.
    return _ClientPool(_POOL_SIZE)


def _shared_client() -> libsql_client.sync.ClientSync:
    """(호환용) 예전 단일 공유 클라이언트 접근자 — 이제 풀의 첫 슬롯을 준다.
    신규 코드는 connect()를 쓴다."""
    return _client_pool().client_at(0)


def connect() -> _ConnectionWrapper:
    pool = _client_pool()
    slot, client = pool.acquire()
    return _ConnectionWrapper(client, pool, slot)
