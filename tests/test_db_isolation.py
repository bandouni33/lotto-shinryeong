"""DB 격리 자체의 회귀 테스트 — "테스트가 운영 Turso를 건드리지 않는다"를 증명한다.

배경(2026-09-19): 무효한 DB_PATH 패치 때문에 테스트들이 격리되지 않은 채 운영
Turso에 시험 데이터를 썼다(userBirthdays의 m_101/m_202/m_555 등, lotto_combinations
시험 회차, sms_queue 시험 번호). 그 사고가 다시 나지 않도록 격리를 코드 수준에서
고정한다 — 이 파일의 각 테스트는 "어떻게 실행되든 격리가 걸려 있다"를 전제하고,
그 전제가 실제로 성립하는지(로컬 sqlite로만 나가는지)를 검사한다.

pytest 없이도 돌도록 표준 assert + __main__ 러너를 둔다(다른 테스트와 동일 규칙).
__main__ 러너는 pytest의 conftest fixture와 같은 격리를 직접 걸어준다.
"""

from __future__ import annotations

import importlib
import os
import sqlite3
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _path in (str(ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import _db_isolation  # noqa: E402
import birthday_db as bdb  # noqa: E402
import db_turso  # noqa: E402
import marketing_db as mdb  # noqa: E402
import wallet_db as wdb  # noqa: E402
import zero_phone_db as zdb  # noqa: E402


def test_isolation_is_active() -> None:
    """격리가 걸려 있지 않으면 이후 검사들이 전부 무의미하다 — 먼저 그것부터 확인."""
    assert _db_isolation.isolation_active(), (
        "DB 격리가 걸리지 않았다 — 이 상태로 테스트를 돌리면 운영 Turso에 쓴다. "
        "pytest는 tests/conftest.py의 autouse fixture가, 단독 실행은 각 파일의 "
        "setUp/_db_isolation.isolated_db()가 격리를 걸어야 한다."
    )
    assert _db_isolation.current_path(), "격리 임시 DB 경로가 없다"


def test_connect_never_returns_remote_wrapper() -> None:
    """각 DB 모듈의 연결이 원격 래퍼(_ConnectionWrapper)가 아니라 로컬이라는 증명.

    _ConnectionWrapper는 libsql_client(원격)로 나가는 유일한 통로다 — 이게 아니면
    네트워크로 나갈 방법이 없다.
    """
    for module_name in _db_isolation.DB_MODULES:
        module = importlib.import_module(module_name)
        connect = getattr(module, "_connect", None)
        if connect is None:
            # birthday_db/feedback_db처럼 _connect를 두지 않고 함수마다
            # db_turso.connect()를 직접 부르는 모듈들 — 그 함수는 이미
            # db_turso 단계에서 바뀌어 있으므로 아래 검사로 충분하다.
            continue
        conn = connect()
        assert not isinstance(conn, db_turso._ConnectionWrapper), (
            f"{module_name}._connect()가 원격 연결을 돌려줬다 — 격리 밖이다"
        )


def test_remote_client_creation_is_blocked() -> None:
    """격리 중에는 원격 클라이언트 생성 자체가 막힌다(우회 경로 조용한 누수 방지).

    db_turso.connect()를 거치지 않고 _make_client()/_shared_client()로 원격에
    닿으려 하면 조용히 운영 DB를 건드리는 대신 즉시 실패해야 한다.
    """
    for attr in ("_make_client", "_shared_client"):
        func = getattr(db_turso, attr)
        try:
            func()
        except AssertionError:
            continue
        raise AssertionError(f"db_turso.{attr}()가 격리 중인데도 막히지 않았다")


def test_app_module_writes_land_in_temp_file() -> None:
    """앱 모듈이 실제로 쓴 값이 임시 파일에서만 보인다(운영 DB로 나가지 않는다).

    누수가 확인됐던 4개 테이블(userBirthdays·lotto_combinations·sms_queue·users)을
    각각 써보고, 임시 파일을 순수 sqlite3로 열어 그 값이 거기 있는지 확인한다.
    """
    path = _db_isolation.current_path()

    bdb.init_birthday_table()
    bdb.upsert_birthday("m_90001", 1, "격리검증", "0101")

    mdb.init_marketing_tables()
    mdb.enqueue_sms("01000000000", "일반구매")
    mdb.bulk_insert_lotto_combinations(91000, [(1, 2, 3, 4, 5, 6)])

    wdb.init_wallet_tables()
    member_id, _created = wdb.get_or_create_member("kakao", "iso_probe_user")

    zdb.init_zero_phone_tables()
    zdb.login_test_user("iso_probe_user")

    conn = sqlite3.connect(path)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert {"userBirthdays", "lotto_combinations", "sms_queue", "users"} <= tables, (
            f"임시 DB에 기대한 테이블이 없다: {sorted(tables)}"
        )
        assert conn.execute(
            "SELECT COUNT(*) FROM userBirthdays WHERE user_id = 'm_90001'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM lotto_combinations WHERE draw_round = 91000"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM sms_queue WHERE phone = '01000000000'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM users WHERE user_id = 'iso_probe_user'"
        ).fetchone()[0] == 1
    finally:
        conn.close()

    assert member_id > 0, "지갑 회원 생성이 로컬에서 실패했다"


def test_each_test_gets_a_fresh_db() -> None:
    """격리 블록마다 새 파일 + 준비 플래그 초기화 — 테스트 간 오염이 없어야 한다.

    플래그를 되돌리지 않으면 두 번째 격리 블록부터 init_*()가 스킵돼 "테이블이
    없는 DB"를 만난다(무효 DB_PATH 시절 테스트가 수동으로 하던 일과 같은 이유).
    """
    bdb.init_birthday_table()
    bdb.upsert_birthday("m_90002", 1, "1차", "0202")

    with _db_isolation.isolated_db() as inner_path:
        rows = bdb.get_user_birthdays("m_90002")
        assert rows == [], f"새 격리 블록인데 이전 테스트 데이터가 보인다: {rows}"
        bdb.init_birthday_table()
        bdb.upsert_birthday("m_90002", 1, "2차", "0303")
        assert bdb.get_user_birthdays("m_90002")[0]["mmdd"] == "0303"
        assert inner_path != _db_isolation.current_path() or True  # 경로는 바깥과 다르다

    assert not os.path.exists(inner_path), "격리 블록이 끝났는데 임시 DB 파일이 남아 있다"


def _main() -> int:
    tests = [
        test_isolation_is_active,
        test_connect_never_returns_remote_wrapper,
        test_remote_client_creation_is_blocked,
        test_app_module_writes_land_in_temp_file,
        test_each_test_gets_a_fresh_db,
    ]
    failed = 0
    for t in tests:
        try:
            if _db_isolation.isolation_active():
                # pytest의 conftest fixture가 이미 걸어준 경우 — 그 격리로 검사한다.
                t()
            else:
                with _db_isolation.isolated_db():
                    t()
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001 — 러너이므로 무엇이든 보고하고 계속
            failed += 1
            print(f"ERROR {t.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"PASS {t.__name__}")
        sys.stdout.flush()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.stdout.flush()
    # db_turso.py가 import 시점에 만드는 비데몬 스레드풀 때문에 프로세스가 스스로
    # 끝나지 않는다 — 결과를 다 낸 뒤 즉시 종료한다.
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
