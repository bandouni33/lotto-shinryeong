"""로그인 유지 확인을 세션당 30초에 한 번으로 (2026-10-08 사용자 승인 — 로딩 시간).

auth_providers.restore_member_from_guest 는 화면마다 유휴 시간 조회 + 마지막 접속 기록(DB 2회)을
했다. 같은 기기(guest_id)가 RESTORE_RECHECK_SECONDS(30초) 안에 이미 확인됐으면 건너뛴다(화면 이동
때마다 새 세션이 열리므로 기기 단위).

  R1 30초 안의 다음 렌더(같은 세션·화면 이동으로 생긴 새 세션 모두)는 DB 를 다시 보지 않는다 —
     그 사이 DB 의 마지막 접속을 121초 전으로 바꿔 놓아도 로그아웃되지 않는다(= 조회를 안 했다).
     새 세션도 기억해 둔 연결로 회원이 이어진다.
  R2 30초가 지나면 다시 확인해 유휴 120초 이상이면 로그아웃된다(자동 로그아웃 기능은 그대로).
  R3 쿠키 도달 계측(cookie_reachable)은 더 이상 기록되지 않는다.
  R4 로그아웃·연결 맺기는 기억해 둔 칸을 즉시 비운다.

실행: venv312\\Scripts\\python.exe -X utf8 tests\\test_restore_recheck_throttle.py
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _p in (str(ROOT), str(TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import _db_isolation as iso  # noqa: E402

KST = timezone(timedelta(hours=9))
GUEST = "restore_throttle_guest_1"
MEMBER = 900_202


class RestoreRecheckThrottleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._ctx = iso.isolated_db()
        cls._ctx.__enter__()
        import combo_gen_trigger
        import draw_results_db

        draw_results_db.init_draw_results_table()
        draw_results_db.upsert_draw_result(1245, [3, 11, 19, 27, 35, 44], 7)
        draw_results_db.sync_latest_from_dhlottery = lambda: None
        combo_gen_trigger.maybe_trigger_weekly_generation = lambda: None

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)

    def _set_last_seen(self, age_seconds: int) -> None:
        import wallet_db

        wallet_db.init_wallet_tables()
        wallet_db.link_guest_to_member(GUEST, MEMBER, None)
        stamp = (datetime.now(KST) - timedelta(seconds=age_seconds)).strftime("%Y-%m-%d %H:%M:%S.%f")
        conn = wallet_db._connect()
        conn.execute("UPDATE guest_member_links SET last_seen_at = ? WHERE guest_id = ?", (stamp, GUEST))
        conn.commit()
        conn.close()

    def _linked(self) -> bool:
        import wallet_db

        conn = wallet_db._connect()
        row = conn.execute("SELECT 1 FROM guest_member_links WHERE guest_id = ?", (GUEST,)).fetchone()
        conn.close()
        return row is not None

    def _cookie_events(self) -> int:
        import security_log

        security_log.init_security_tables()
        conn = security_log._connect()
        row = conn.execute("SELECT COUNT(*) FROM security_events WHERE event_type = 'cookie_reachable'").fetchone()
        conn.close()
        return int(row[0])

    def _render(self, member_in_session: bool):
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
        at.query_params["page"] = "main"
        at.query_params["gid"] = GUEST
        if member_in_session:
            at.session_state["member_id"] = MEMBER
        at.run()
        self.assertFalse(at.exception, [str(e)[:120] for e in at.exception])
        return at

    def test_R1_R2_R3(self):
        import auth_providers

        auth_providers._forget_guest_recheck(GUEST)
        self._set_last_seen(5)
        at = self._render(member_in_session=True)
        self.assertTrue(self._linked())
        self.assertIn(GUEST, auth_providers._GUEST_SEEN)

        # R1-a: 같은 세션, 30초 안 — DB 를 121초 전으로 바꿔도 다시 보지 않는다
        self._set_last_seen(121)
        at.run()
        self.assertFalse(at.exception)
        self.assertTrue(self._linked(), "30초 안인데 다시 조회해 로그아웃했다(건너뛰기가 안 됨)")

        # R1-b: 화면 이동(새 세션, 세션엔 회원 없음) — 기억해 둔 연결로 회원이 이어진다
        at2 = self._render(member_in_session=False)
        self.assertTrue(self._linked())
        self.assertEqual(at2.session_state["member_id"], MEMBER, "새 세션에서 회원이 이어지지 않았다")

        # R2: 30초가 지난 것으로 만들면 다시 확인 → 로그아웃
        with auth_providers._GUEST_RECHECK_LOCK:
            for d in (auth_providers._GUEST_SEEN,):
                d[GUEST] = d[GUEST] - auth_providers.RESTORE_RECHECK_SECONDS - 1
        at.run()
        self.assertFalse(at.exception)
        self.assertFalse(self._linked(), "30초가 지났는데 유휴 121초를 확인하지 않았다")

        # R3
        self.assertEqual(self._cookie_events(), 0, "쿠키 도달 계측이 아직 기록된다")

    def test_R4_logout_and_link_forget(self):
        import auth_providers

        with auth_providers._GUEST_RECHECK_LOCK:
            auth_providers._GUEST_SEEN[GUEST] = 1e12
            auth_providers._GUEST_LINK[GUEST] = (1e12, MEMBER, None)
        auth_providers._link_guest_to_member_safe(GUEST, MEMBER, None)
        self.assertNotIn(GUEST, auth_providers._GUEST_SEEN)
        self.assertNotIn(GUEST, auth_providers._GUEST_LINK)
        src = (ROOT / "auth_providers.py").read_text(encoding="utf-8")
        logout_src = src[src.index("def logout()"):][:900]
        self.assertIn("_forget_guest_recheck(", logout_src)
        up = (ROOT / "user_page.py").read_text(encoding="utf-8")
        fresh = up[up.index('if st.query_params.get("fresh_start") == "1":'):][:1200]
        self.assertIn("_forget_guest_recheck(", fresh, "fresh_start 연결 끊기 뒤에 기억 칸을 안 비운다")

if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(RestoreRecheckThrottleTests))
    sys.exit(0 if result.wasSuccessful() else 1)
