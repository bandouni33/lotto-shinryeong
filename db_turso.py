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
_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=16, thread_name_prefix="turso-guard"
)
_QUERY_TIMEOUT_SEC = 10

# P1(2026-09-17, 비동기 스레드 누적 대응): 위 _EXECUTOR는 "이 요청 하나
# 포기시키기"만 해줄 뿐이다 — 실제 네트워크 요청은 _shared_client()(프로세스
# 전체가 공유하는 ClientSync 인스턴스 1개, 아래 st.cache_resource 참고)의
# 내부 전용 스레드 1개(libsql_client/sync.py의 _AsyncExecutor)가 처리한다.
# 그 내부 스레드가 한 번 멈추면 _EXECUTOR로 새 워커를 몇 개를 쓰든 전부 같은
# "막힌 내부 줄"에 다시 서게 되므로 사실상 무의미하다 — 이게 9/3 사고(위
# 주석)의 정확한 재발 패턴. 연속 타임아웃이 _TIMEOUT_RECYCLE_THRESHOLD번
# 쌓이면 _shared_client()의 캐시를 지워 다음 호출이 완전히 새 클라이언트(새
# 내부 스레드)를 만들게 하고, 동시에 _EXECUTOR도 새로 교체한다. 막힌 옛
# 클라이언트/스레드는 강제로 죽일 방법이 없어 그냥 버려두지만, 블록된 채
# CPU를 쓰지 않으므로 무해하다 — 기존 정상 동작 경로(성공하는 호출)는 전혀
# 건드리지 않는다.
_RECOVERY_LOCK = threading.Lock()
_TIMEOUT_RECYCLE_THRESHOLD = 5
_consecutive_timeouts = 0


def _note_turso_timeout():
    global _consecutive_timeouts
    with _RECOVERY_LOCK:
        _consecutive_timeouts += 1
        should_recycle = _consecutive_timeouts >= _TIMEOUT_RECYCLE_THRESHOLD
        if should_recycle:
            _consecutive_timeouts = 0
    if should_recycle:
        _recycle_after_timeouts()


def _note_turso_success():
    global _consecutive_timeouts
    if _consecutive_timeouts:
        with _RECOVERY_LOCK:
            _consecutive_timeouts = 0


def _recycle_after_timeouts():
    global _EXECUTOR
    old_executor = _EXECUTOR
    _EXECUTOR = concurrent.futures.ThreadPoolExecutor(
        max_workers=16, thread_name_prefix="turso-guard"
    )
    old_executor.shutdown(wait=False)
    try:
        _shared_client.clear()
    except Exception:
        pass
    print(
        f"[db_turso] 연속 타임아웃 {_TIMEOUT_RECYCLE_THRESHOLD}회 누적 — "
        "Turso 클라이언트/워커풀 재생성"
    )


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
    def __init__(self, client):
        self._client = client
        self.row_factory = None

    def _guarded(self, func, *args):
        """모든 Turso 호출의 공통 관문 — _QUERY_TIMEOUT_SEC 안에 안 끝나면
        TimeoutError를 던진다(무한정 멈추는 것 방지). 백그라운드 스레드 자체는
        (라이브러리 구조상 강제로 못 죽이므로) 계속 남아있을 수 있지만, 최소한
        "이 요청을 기다리던 세션"은 살아나서 폴백 로직으로 넘어갈 수 있다."""
        future = _EXECUTOR.submit(func, *args)
        try:
            result = future.result(timeout=_QUERY_TIMEOUT_SEC)
        except concurrent.futures.TimeoutError as e:
            _note_turso_timeout()
            raise TimeoutError(
                f"Turso 쿼리가 {_QUERY_TIMEOUT_SEC}초 안에 응답하지 않았습니다"
                "(네트워크 문제로 추정, 자동 폴백됨)"
            ) from e
        _note_turso_success()
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


@st.cache_resource(show_spinner=False)
def _shared_client() -> libsql_client.sync.ClientSync:
    # 요청마다(=Streamlit 재실행마다) 원격 Turso로 새 HTTP 클라이언트를
    # 매번 새로 만들고 있던 게 확인됐다 — 동시접속이 몰리는 시점(예: 토요일
    # 저녁 로또 구매 마감 직전)에 가장 먼저 병목이 될 지점이라 캐싱한다.
    # ClientSync는 내부적으로 전용 스레드+락으로 요청을 큐잉해 처리하도록
    # 만들어져 있어(libsql_client/sync.py의 _AsyncExecutor) 여러 세션이 이
    # 인스턴스 하나를 동시에 써도 안전하다 — st.cache_resource로 프로세스
    # 전체가 공유하는 게 의도된 설계와 맞는다.
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


def connect() -> _ConnectionWrapper:
    return _ConnectionWrapper(_shared_client())
