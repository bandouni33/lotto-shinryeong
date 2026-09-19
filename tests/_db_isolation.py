"""테스트용 DB 격리 — 진짜 운영 Turso를 절대 건드리지 않게 하는 단일 구현.

왜 이 파일이 필요한가 (2026-09-19):
  db_turso.connect()는 TURSO_DATABASE_URL/TURSO_AUTH_TOKEN(env 또는 st.secrets)으로
  항상 원격 Turso에 붙고, 테스트용 로컬 파일로 우회하는 분기가 아예 없다. 그래서
  각 테스트는 `some_db.DB_PATH = <임시경로>`로 격리하려 했지만 — DB_PATH는 어디서도
  읽히지 않는 죽은 변수였다(wallet_db·marketing_db·birthday_db·zero_phone_db 모두
  자기 _connect()에서 db_turso.connect()를 그대로 부른다). 그 결과 이 테스트들은
  격리되지 않고 운영 DB에 시험 데이터를 실제로 썼다(실측 확인: userBirthdays에
  guest_local/m_101/m_202/m_555/m_1001/m_2002 행, lotto_combinations에 시험 회차,
  sms_queue에 시험 번호).

  확실한 차단점은 하나뿐이다 — db_turso.connect 자체. 앱 모듈들은
  `from db_turso import connect`를 쓰지 않고 전부 `db_turso.connect()`로 모듈 속성을
  호출하므로(grep 확인), 이 한 곳만 임시 sqlite 파일로 바꿔치기하면
  wallet_db·marketing_db·birthday_db·zero_phone_db·feedback_db·security_log·
  draw_results_db·app_settings가 전부 동시에 격리된다.

사용법:
  · pytest   → tests/conftest.py의 autouse fixture가 모든 테스트에 자동 적용
  · 단독 실행 → 테스트가 isolated_db()를 직접 감싼다(setUp/tearDown 또는 runner).
  두 경로 모두 이 파일 하나를 타야 한다 — 격리 구현이 두 벌이면 반드시 어긋난다.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import db_turso  # noqa: E402

# 연결이 원격으로 나가는 DB 모듈들 — 진단·문서용 목록. 실제 차단은 위 설명대로
# db_turso.connect 한 곳에서 일어나므로, 새 모듈이 추가돼도 여기를 고칠 필요 없이
# 자동으로 격리된다(그게 이 방식의 요점이다).
DB_MODULES = (
    "wallet_db",
    "marketing_db",
    "birthday_db",
    "zero_phone_db",
    "feedback_db",
    "security_log",
    "draw_results_db",
    "app_settings",
)

# 각 모듈의 "테이블 준비 완료" 1회성 플래그(init_*()가 한 번만 실행되게 하는 것).
# 임시 DB는 테스트마다 새 파일이므로 이 플래그를 되돌리지 않으면 두 번째 테스트부터
# init_*()가 스킵돼 "테이블이 없는 DB에 쿼리"하게 된다 — wallet 테스트가 수동으로
# `wdb._WALLET_TABLES_READY = False`를 하던 일과 같은 이유다.
READY_FLAGS = {
    "wallet_db": "_WALLET_TABLES_READY",
    "marketing_db": "_MARKETING_TABLES_READY",
    "birthday_db": "_BIRTHDAY_TABLE_READY",
    "zero_phone_db": "_ZERO_PHONE_TABLES_READY",
    "feedback_db": "_FEEDBACK_TABLES_READY",
    "security_log": "_SECURITY_TABLES_READY",
    "draw_results_db": "_TABLE_READY",
    "app_settings": "_SETTINGS_TABLE_READY",
}

_current_path: str | None = None


def current_path() -> str | None:
    """지금 격리돼 있는 임시 sqlite 파일 경로(테스트가 sqlite3로 직접 열어볼 때).

    예전처럼 테스트가 자기가 만든 경로를 따로 들고 있으면, 실제로 앱이 쓴 DB와
    다른 파일을 검사하는 헛수고가 된다(무효 DB_PATH 패턴이 정확히 그거였다).
    """
    return _current_path


def isolation_active() -> bool:
    """db_turso.connect가 지금 격리용으로 바뀌어 있는지."""
    return bool(getattr(db_turso.connect, "_db_isolation", False))


def reset_ready_flags() -> None:
    """이미 import된 DB 모듈의 테이블 준비 플래그를 되돌린다(아직 import 안 된
    모듈은 어차피 기본값 False라 건드릴 필요가 없다)."""
    for module_name, flag in READY_FLAGS.items():
        module = sys.modules.get(module_name)
        if module is not None and hasattr(module, flag):
            setattr(module, flag, False)


class _LocalCursor:
    """db_turso._CursorWrapper와 같은 계약(lastrowid/rowcount/fetchone/fetchall/iter).

    행은 db_turso.Row로 감싼다 — 앱 코드가 row["컬럼"], row[0], .get(), dict(row)를
    섞어 쓰는데, sqlite3.Row는 .get()이 없어 운영과 동작이 달라진다(db_turso 쪽은
    _CursorWrapper가 항상 db_turso.Row를 돌려주고 `conn.row_factory = sqlite3.Row`
    대입은 무시된다 — 그 동작까지 그대로 흉내낸다).
    """

    def __init__(self, cursor: sqlite3.Cursor):
        self._cur = cursor

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    @property
    def rowcount(self):
        return self._cur.rowcount

    def _wrap(self, raw):
        cols = [d[0] for d in (self._cur.description or [])]
        return db_turso.Row(zip(cols, raw))

    def fetchone(self):
        row = self._cur.fetchone()
        return None if row is None else self._wrap(row)

    def fetchall(self):
        return [self._wrap(row) for row in self._cur.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class _LocalConnection:
    """임시 sqlite 파일에 붙는 db_turso._ConnectionWrapper 대역.

    commit/close는 진짜 커밋/종료를 하지만 close는 db_turso와 동일하게 아무 것도
    하지 않는다(운영에서 close()는 no-op이다 — 앱 수백 곳이 함수 끝마다 close()를
    부르도록 짜여 있어, 그 차이를 테스트에서 새로 만들면 운영과 다른 코드를
    검증하게 된다). 실제 정리는 isolated_db()가 끝날 때 한꺼번에 한다.
    """

    def __init__(self, path: str, registry: list):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        # Streamlit AppTest는 앱 스크립트를 별도 스레드에서 돌린다 — 그때를 위해
        # check_same_thread=False가 필요하다.
        self._registry = registry
        registry.append(self._conn)

    # db_turso 래퍼와 동일하게 이 속성은 있어도 결과 행에는 영향이 없다.
    row_factory = None

    def execute(self, sql, params=()):
        return _LocalCursor(self._conn.execute(sql, tuple(params) if params else ()))

    def executemany(self, sql, params_list):
        params_list = [tuple(p) for p in params_list]
        if params_list:
            self._conn.executemany(sql, params_list)

    def executescript(self, script):
        self._conn.executescript(script)

    def batch_execute(self, statements):
        """db_turso에 있는 것과 같은 이름 — wallet_db._batch_execute()가
        hasattr로 분기하므로, 여기 있으면 앱과 같은 경로(batch)로 실행된다."""
        return [
            _LocalCursor(self._conn.execute(sql, tuple(params) if params else ()))
            for sql, params in statements
        ]

    def commit(self):
        self._conn.commit()

    def close(self):
        pass


def _local_connect_factory(path: str, registry: list):
    def _connect():
        return _LocalConnection(path, registry)

    _connect._db_isolation = True
    return _connect


def _install(path: str, registry: list):
    """db_turso의 원격 출구를 전부 막고 connect()만 임시 파일로 돌린다."""
    original = {
        "connect": db_turso.connect,
        "make_client": db_turso._make_client,
        "shared_client": db_turso._shared_client,
    }
    db_turso.connect = _local_connect_factory(path, registry)

    def _no_remote(*_args, **_kwargs):
        raise AssertionError(
            "테스트가 운영 Turso 클라이언트를 만들려 했다(_make_client/_shared_client) "
            "— db_turso.connect()를 거치지 않는 격리 밖 경로다. 격리 누수를 조용히 "
            "운영 쓰기로 넘기지 않으려고 즉시 실패시킨다."
        )

    db_turso._make_client = _no_remote
    db_turso._shared_client = _no_remote
    return original


def _uninstall(original):
    db_turso.connect = original["connect"]
    db_turso._make_client = original["make_client"]
    db_turso._shared_client = original["shared_client"]


@contextlib.contextmanager
def isolated_db(path: str | None = None):
    """이 블록 안에서는 모든 DB 접근이 임시 sqlite 파일로 간다(yields: 그 경로).

    진짜 Turso로 나가는 출구를 db_turso 단계에서 막으므로, 어떤 앱 모듈이
    어떤 함수를 부르든 운영 DB는 건드려지지 않는다.
    """
    global _current_path

    owns_dir = path is None
    tmpdir = tempfile.mkdtemp(prefix="lotto_test_db_") if owns_dir else None
    db_path = path or os.path.join(tmpdir, "test_lotto.db")

    registry: list[sqlite3.Connection] = []
    original = _install(db_path, registry)
    previous_path = _current_path
    _current_path = db_path
    reset_ready_flags()
    try:
        yield db_path
    finally:
        reset_ready_flags()
        _current_path = previous_path
        _uninstall(original)
        # Windows에서는 열린 핸들이 하나라도 있으면 임시 파일/폴더를 못 지운다 —
        # db_turso와 달리 close()가 no-op이므로 여기서 실제로 닫아준다.
        for conn in registry:
            try:
                conn.close()
            except Exception:
                pass
        if owns_dir and tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)
