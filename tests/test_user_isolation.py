"""사용자별 데이터 격리 — 시뮬레이션 테스트."""

import os
import tempfile
import unittest
from unittest.mock import patch

import birthday_db as bdb


class UserIsolationTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmpdir.name, "test_lotto.db")
        self.users_root = os.path.join(self._tmpdir.name, "users")
        os.makedirs(self.users_root, exist_ok=True)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_birthday_scopes_isolated(self):
        with patch.object(bdb, "DB_PATH", self.db_path):
            bdb.init_birthday_table()
            bdb.upsert_birthday("guest_local", 1, "게스트", "0315")
            bdb.upsert_birthday("m_101", 1, "회원A", "1225")
            bdb.upsert_birthday("m_202", 1, "회원B", "0707")

            guest = bdb.get_user_birthdays("guest_local")
            a = bdb.get_user_birthdays("m_101")
            b = bdb.get_user_birthdays("m_202")

        self.assertEqual(guest[0]["mmdd"], "0315")
        self.assertEqual(a[0]["mmdd"], "1225")
        self.assertEqual(b[0]["mmdd"], "0707")
        self.assertNotEqual(a[0]["mmdd"], b[0]["mmdd"])

    def test_simulation_two_users_same_device_sequential(self):
        """A 저장 → B 저장 시 생일 데이터 혼선 없음."""
        with patch.object(bdb, "DB_PATH", self.db_path):
            bdb.init_birthday_table()
            bdb.upsert_birthday("m_1001", 1, "A", "0101")
            bdb.upsert_birthday("m_2002", 1, "B", "0202")

            a_data = bdb.get_user_birthdays("m_1001")
            b_data = bdb.get_user_birthdays("m_2002")

        self.assertEqual(a_data[0]["label"], "A")
        self.assertEqual(b_data[0]["label"], "B")

    def test_guest_does_not_see_member_birthdays(self):
        with patch.object(bdb, "DB_PATH", self.db_path):
            bdb.init_birthday_table()
            bdb.upsert_birthday("m_555", 1, "회원전용", "1111")
            guest = bdb.get_user_birthdays("guest_local")

        self.assertEqual(guest, [])

    def test_get_user_birthdays_creates_table_if_missing(self):
        """번개조합 등 — init 없이 조회해도 Cloud 신규 DB에서 OperationalError 방지."""
        with patch.object(bdb, "DB_PATH", self.db_path):
            rows = bdb.get_user_birthdays("guest_local")
        self.assertEqual(rows, [])
        with patch.object(bdb, "DB_PATH", self.db_path):
            bdb.upsert_birthday("guest_local", 1, "T", "0315")
            rows = bdb.get_user_birthdays("guest_local")
        self.assertEqual(rows[0]["mmdd"], "0315")

    def test_per_user_filter_file_paths(self):
        with patch("admin_filter.USERS_DATA_ROOT", self.users_root):
            from admin_filter import get_combo_final_path, get_combo_step1_path, get_user_data_dir

            guest_dir = get_user_data_dir("guest_local")
            member_a = get_user_data_dir("member_11")
            member_b = get_user_data_dir("member_22")

            self.assertNotEqual(guest_dir, member_a)
            self.assertNotEqual(member_a, member_b)
            self.assertNotEqual(
                get_combo_step1_path("member_11"),
                get_combo_step1_path("member_22"),
            )
            self.assertTrue(get_combo_final_path("member_11").endswith("final_combinations.csv"))

    def test_scope_key_helpers(self):
        from user_scope import (
            GUEST_SCOPE,
            birthday_scope_for,
            data_dir_key_for,
            session_key_for,
        )

        self.assertEqual(birthday_scope_for(None), GUEST_SCOPE)
        self.assertEqual(birthday_scope_for(42), "m_42")
        self.assertEqual(data_dir_key_for(42), "member_42")
        self.assertEqual(session_key_for("auto_purchase_history", 42), "auto_purchase_history_m_42")
        self.assertEqual(session_key_for("auto_purchase_history", None), f"auto_purchase_history_{GUEST_SCOPE}")


if __name__ == "__main__":
    unittest.main()
