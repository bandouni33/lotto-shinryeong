"""zero_phone_db tests.

2026-09-19 수정: 예전엔 zdb.DB_PATH를 임시경로로 바꿔 격리하려 했지만
zero_phone_db._connect()가 DB_PATH를 안 보고 db_turso.connect()(=진짜 운영
Turso)를 그대로 부르는 탓에 그 패치는 no-op이었다 — 이 테스트는 운영 DB의
users/msg_queue에 시험 사용자(test_user_01, kakao_hash_abc)를 실제로 남겼다.

같은 이유로 테스트 자신도 조용히 망가져 있었다: 임시 파일을 sqlite3로 직접 열어
컬럼을 검사했기 때문에, 실제 테이블이 만들어진 곳(운영 DB)이 아니라 아무것도
없는 빈 파일을 보고 있었다(test_msg_queue_no_phone의 "user_id in cols"가 실패했을
것이다). 이제는 격리된 DB 경로를 _db_isolation.current_path()로 받아 검사한다.
"""

import sqlite3
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _path in (str(ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import _db_isolation  # noqa: E402
import zero_phone_db as zdb  # noqa: E402


def test_test_user_signup_bonus_once():
    with _db_isolation.isolated_db():
        zdb.init_zero_phone_tables()
        u1, new1 = zdb.login_test_user("test_user_01")
        assert new1
        assert u1["point_balance"] == 5000
        u2, new2 = zdb.login_test_user("test_user_01")
        assert not new2
        assert u2["point_balance"] == 5000


def test_msg_queue_no_phone():
    with _db_isolation.isolated_db() as db_path:
        zdb.init_zero_phone_tables()
        zdb.login_test_user("kakao_hash_abc")
        msg_id = zdb.enqueue_msg("kakao_hash_abc", "일반구매", "WAIT")
        assert msg_id > 0

        conn = sqlite3.connect(db_path)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(msg_queue)").fetchall()}
        conn.close()
        assert "phone" not in cols
        assert "user_id" in cols
