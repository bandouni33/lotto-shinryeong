"""사용자별 데이터 격리 — 시뮬레이션 테스트.

2026-09-19 수정(중요): 이 파일은 원래 `patch.object(bdb, "DB_PATH", 임시경로)`로
격리한다고 돼 있었지만, birthday_db는 DB_PATH를 어디서도 읽지 않고 모든 함수가
db_turso.connect()를 직접 부른다 — 즉 그 패치는 no-op이었고, 이 테스트들은
격리되지 않은 채 **운영 Turso의 userBirthdays에 시험 생일을 실제로 썼다**
(guest_local/m_101/m_202/m_555/m_1001/m_2002 스코프, 실행할 때마다 upsert로
덮어씀). 스코프 형식이 실회원과 같은 `m_<회원번호>`라 그 번호의 실회원 생일을
덮어쓸 수 있는 상태였다.

이제 tests/_db_isolation.py가 db_turso.connect() 자체를 임시 sqlite 파일로
바꿔치기하므로 운영 DB는 절대 건드리지 않는다. 아래 회귀 테스트
(test_writes_land_in_isolated_file)가 그 사실을 직접 증명한다.
"""

import os
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _path in (str(ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import _db_isolation  # noqa: E402
import birthday_db as bdb  # noqa: E402


class UserIsolationTests(unittest.TestCase):
    def setUp(self):
        # pytest로 돌든 `python tests/test_user_isolation.py`로 돌든 격리가 걸리게
        # 여기서 직접 건다(conftest는 pytest에서만 로드된다 — 이 프로젝트의 실제
        # 러너는 __main__/unittest 쪽이라 conftest만으로는 부족하다).
        self._iso = _db_isolation.isolated_db()
        self.db_path = self._iso.__enter__()
        self.addCleanup(self._iso.__exit__, None, None, None)
        self.users_root = os.path.join(os.path.dirname(self.db_path), "users")
        os.makedirs(self.users_root, exist_ok=True)

    def test_writes_land_in_isolated_file(self):
        """격리 자체의 회귀 테스트 — 생일 쓰기가 임시 파일에만 보여야 한다.

        이 파일이 격리되지 않던 사고(운영 userBirthdays에 시험 행 기록)를 다시는
        못 내도록, "앱이 쓴 값"을 격리 파일에서 직접 읽어 확인한다.
        """
        self.assertTrue(
            _db_isolation.isolation_active(), "DB 격리가 걸리지 않았다 — 운영 DB로 샐 수 있다"
        )
        bdb.init_birthday_table()
        bdb.upsert_birthday("m_7777", 1, "격리확인", "0101")

        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT user_id, slot, label, mmdd FROM userBirthdays WHERE user_id = 'm_7777'"
        ).fetchall()
        conn.close()
        self.assertEqual(rows, [("m_7777", 1, "격리확인", "0101")])

    def test_birthday_scopes_isolated(self):
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
        bdb.init_birthday_table()
        bdb.upsert_birthday("m_1001", 1, "A", "0101")
        bdb.upsert_birthday("m_2002", 1, "B", "0202")

        a_data = bdb.get_user_birthdays("m_1001")
        b_data = bdb.get_user_birthdays("m_2002")

        self.assertEqual(a_data[0]["label"], "A")
        self.assertEqual(b_data[0]["label"], "B")

    def test_guest_does_not_see_member_birthdays(self):
        bdb.init_birthday_table()
        bdb.upsert_birthday("m_555", 1, "회원전용", "1111")
        guest = bdb.get_user_birthdays("guest_local")
        self.assertEqual(guest, [])

    def test_get_user_birthdays_creates_table_if_missing(self):
        """번개조합 등 — init 없이 조회해도 Cloud 신규 DB에서 OperationalError 방지."""
        rows = bdb.get_user_birthdays("guest_local")
        self.assertEqual(rows, [])
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
