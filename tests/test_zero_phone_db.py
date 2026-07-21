"""zero_phone_db tests."""

import os
import tempfile

import zero_phone_db as zdb


def test_test_user_signup_bonus_once():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "test.db")
        old = zdb.DB_PATH
        zdb.DB_PATH = path
        try:
            zdb.init_zero_phone_tables()
            u1, new1 = zdb.login_test_user("test_user_01")
            assert new1
            assert u1["point_balance"] == 5000
            u2, new2 = zdb.login_test_user("test_user_01")
            assert not new2
            assert u2["point_balance"] == 5000
        finally:
            zdb.DB_PATH = old


def test_msg_queue_no_phone():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "test.db")
        old = zdb.DB_PATH
        zdb.DB_PATH = path
        try:
            zdb.init_zero_phone_tables()
            zdb.login_test_user("kakao_hash_abc")
            msg_id = zdb.enqueue_msg("kakao_hash_abc", "일반구매", "WAIT")
            assert msg_id > 0
            import sqlite3

            conn = sqlite3.connect(path)
            cols = {row[1] for row in conn.execute("PRAGMA table_info(msg_queue)").fetchall()}
            conn.close()
            assert "phone" not in cols
            assert "user_id" in cols
        finally:
            zdb.DB_PATH = old
