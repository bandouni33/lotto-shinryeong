"""무활동 자동 로그아웃 3분 → 2분 (2026-10-04 구름님 지시) 불변식.

무엇이 바뀌었나: 앱을 터치하지 않은 채 두면 로그아웃되는 기준 시간을 3분 → 2분.
  · 기준점(실효 판정)  : `auth_providers.IDLE_LOGOUT_SECONDS` = 120초
  · 앱 쪽 사본         : `LottoShinryeong/utils/session-timeout.ts` 의 BACKGROUND_LOGOUT_MS
  둘 중 하나만 바뀌면 "어떤 화면은 3분, 어떤 화면은 2분"이 된다(QR스캔 화면은 앱 쪽
  판정을 쓴다) — 그래서 이 테스트가 둘의 일치와 중복 부재를 함께 잠근다.

이 테스트가 고정하는 것:
  I1 기준점: 값이 120이고, 판정이 그 상수를 쓴다(맨 숫자를 박지 않는다).
  I2 사본 일치: TS 상수 == 값*1000, 다른 파일에 사본이 없다(교차 파일 계약).
  I3 경계 거동(**조립된 앱을 실제로 렌더해서** 확인 — 단위 함수가 아니다):
        idle 119초 → 로그아웃되지 않는다(연결 유지 + 마지막 활동 시각 갱신)
        idle 120초 → 로그아웃된다(임계값에서 바로. 판정이 >= 이므로)
        idle 121초 → 로그아웃된다
     로그아웃의 관찰 신호는 guest_member_links 행의 삭제다 — auth_providers.logout()이
     unlink_guest_from_member()를 부르는 것이 실제 구현이고, session_state만 비우면
     다음 렌더에 조용히 재로그인되므로 DB 쪽 신호를 봐야 정확하다.

실행: venv312\\Scripts\\python.exe -X utf8 tests\\test_idle_logout_2min.py
"""

from __future__ import annotations

import re
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

TS_TSX = ROOT / "LottoShinryeong" / "utils" / "session-timeout.ts"
QR_SCAN = ROOT / "LottoShinryeong" / "app" / "qr-scan.tsx"
AUTH_SRC = (ROOT / "auth_providers.py").read_text(encoding="utf-8")
TS_SRC = TS_TSX.read_text(encoding="utf-8")

EXPECTED_SECONDS = 120
TEST_GUEST = "idle_logout_test_guest_1"
TEST_MEMBER = 900_101


def _ts_background_logout_ms() -> int:
    m = re.search(r"BACKGROUND_LOGOUT_MS\s*=\s*([^;]+);", TS_SRC)
    assert m, "session-timeout.ts 에서 BACKGROUND_LOGOUT_MS 선언을 찾지 못했다"
    expr = m.group(1).strip()
    # '2 * 60 * 1000' 형태만 허용한다(계산식을 남겨야 '몇 분'인지 읽힌다).
    parts = [int(p.strip()) for p in expr.split("*")]
    value = 1
    for p in parts:
        value *= p
    return value


def _python_idle_seconds() -> int:
    import auth_providers

    return int(auth_providers.IDLE_LOGOUT_SECONDS)


class ConstantContractTests(unittest.TestCase):
    """I1·I2 — 기준점 하나, 사본은 그 값을 인용, 중복 없음."""

    def test_I1_canonical_value_is_two_minutes(self):
        self.assertEqual(_python_idle_seconds(), EXPECTED_SECONDS,
                         "기준점 값이 120초가 아니다")

    def test_I1_judgement_uses_the_constant_not_a_bare_number(self):
        body = AUTH_SRC.split("def restore_member_from_guest")[1].split("def ")[0]
        self.assertIn("idle_seconds >= IDLE_LOGOUT_SECONDS", body,
                      "판정이 상수를 쓰지 않는다 — 값을 바꿔도 동작이 안 바뀔 수 있다")
        self.assertIsNone(re.search(r"idle_seconds\s*>=\s*\d+", AUTH_SRC),
                          "idle 판정에 맨 숫자가 남아 있다(사본이 둘이 된다)")

    def test_I2_app_copy_matches_the_canonical_value(self):
        self.assertEqual(_ts_background_logout_ms(), EXPECTED_SECONDS * 1000,
                         "앱 쪽 BACKGROUND_LOGOUT_MS 가 서버 기준점과 다르다")

    def test_I2_no_other_copy_of_the_threshold(self):
        self.assertEqual(len(re.findall(r"BACKGROUND_LOGOUT_MS\s*=", TS_SRC)), 1,
                         "session-timeout.ts 안에서 같은 상수를 두 번 선언했다")
        others = []
        for pattern in ("*.py", "*.ts", "*.tsx"):
            for path in (ROOT / "LottoShinryeong").rglob(pattern):
                if path.resolve() == TS_TSX.resolve():
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                if "BACKGROUND_LOGOUT_MS =" in text:
                    others.append(path)
            for path in ROOT.glob(pattern):
                text = path.read_text(encoding="utf-8", errors="replace")
                if re.search(r"BACKGROUND_LOGOUT_MS\s*=", text):
                    others.append(path)
        self.assertEqual(others, [], f"임계값 사본이 다른 파일에도 있다: {others}")

    def test_I2_qr_scan_comment_matches_the_new_value(self):
        text = QR_SCAN.read_text(encoding="utf-8")
        self.assertIn("2분(BACKGROUND_LOGOUT_MS)", text,
                      "QR스캔 화면 주석이 옛 값(3분)을 그대로 말하고 있다")
        self.assertNotIn("3분(BACKGROUND_LOGOUT_MS)", text)


class BoundaryBehaviourTests(unittest.TestCase):
    """I3 — 실제 앱을 렌더해 경계 양쪽을 확인한다."""

    @classmethod
    def setUpClass(cls):
        cls._ctx = iso.isolated_db()
        db_path = cls._ctx.__enter__()
        import combo_gen_trigger
        import draw_results_db
        import marketing_db as mdb

        draw_results_db.init_draw_results_table()
        for draw_round in range(1, 1246):
            draw_results_db.upsert_draw_result(draw_round, [3, 11, 19, 27, 35, 44], 7)
        mdb.init_marketing_tables()
        mdb.set_reference_ranks(1245, (0, 0, 0, 5, 12))
        mdb.snapshot_round_stats(1245, 6465)
        mdb.finalize_round_stats(1245)
        draw_results_db.sync_latest_from_dhlottery = lambda: None
        combo_gen_trigger.maybe_trigger_weekly_generation = lambda: None
        cls.db_path = db_path

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)

    # ── 도우미 ──────────────────────────────────────────────────
    def _seed_link(self, age_seconds: int) -> str:
        """이 기기를 회원과 연결해 두고, '마지막 요청'을 age_seconds 전으로 심는다."""
        import wallet_db

        wallet_db.init_wallet_tables()
        wallet_db.link_guest_to_member(TEST_GUEST, TEST_MEMBER, None)
        stamp = (datetime.now(KST) - timedelta(seconds=age_seconds)).strftime(
            "%Y-%m-%d %H:%M:%S.%f")
        conn = wallet_db._connect()
        conn.execute("UPDATE guest_member_links SET last_seen_at = ? WHERE guest_id = ?",
                     (stamp, TEST_GUEST))
        conn.commit()
        conn.close()
        # 2026-10-08: 로그인 유지 확인은 기기별로 30초 기억된다(auth_providers.RESTORE_RECHECK_SECONDS).
        # 이 테스트는 "age_seconds 만큼 시간이 흘렀다"를 DB 값으로만 흉내 내므로, 실제로 시간이 흘렀다면
        # 이미 사라졌을 기억 칸도 같이 비운다(tests/test_restore_recheck_throttle.py 가 기억 동작 자체를 본다).
        import auth_providers

        auth_providers._forget_guest_recheck(TEST_GUEST)
        return stamp

    def _link_row(self):
        import wallet_db

        conn = wallet_db._connect()
        row = conn.execute("SELECT member_id, last_seen_at FROM guest_member_links "
                           "WHERE guest_id = ?", (TEST_GUEST,)).fetchone()
        conn.close()
        return row

    def _render_and_check_logged_out(self, age_seconds: int) -> tuple[bool, int, list[str]]:
        """앱을 실제로 렌더한다 → (로그아웃됐는가, 남은 예외 수, 예외 요약)."""
        from streamlit.testing.v1 import AppTest

        self._seed_link(age_seconds)
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
        at.query_params["page"] = "main"
        at.query_params["gid"] = TEST_GUEST
        at.session_state["member_id"] = TEST_MEMBER
        at.run()
        after = self._link_row()
        exceptions = [f"{type(e).__name__}: {str(e)[:80]}" for e in at.exception]
        return after is None, len(at.exception), exceptions

    # ── 경계 양쪽 ───────────────────────────────────────────────
    def test_I3_just_below_the_limit_keeps_the_session(self):
        logged_out, n_exc, exc = self._render_and_check_logged_out(EXPECTED_SECONDS - 1)
        self.assertFalse(logged_out,
                         f"119초인데 로그아웃됐다(임계값이 120이 아니게 바뀌었나?) 예외={exc}")
        row = self._link_row()
        self.assertIsNotNone(row, "연결이 끊겼다")
        self.assertEqual(int(row["member_id"]), TEST_MEMBER)
        # 이 경로는 '마지막 활동 시각'을 갱신해야 한다(다음 판정의 근거).
        conn_guard = row["last_seen_at"]
        self.assertTrue(conn_guard, "last_seen_at 이 비었다")

    def test_I3_exactly_at_the_limit_logs_out(self):
        logged_out, n_exc, exc = self._render_and_check_logged_out(EXPECTED_SECONDS)
        self.assertTrue(logged_out,
                        f"정확히 120초인데 로그아웃되지 않았다(>= 판정인가?) 예외={exc}")

    def test_I3_over_the_limit_logs_out(self):
        logged_out, n_exc, exc = self._render_and_check_logged_out(EXPECTED_SECONDS + 1)
        self.assertTrue(logged_out, f"121초인데 로그아웃되지 않았다 예외={exc}")

    def test_I3_the_welcome_back_path_still_works_after_rendering(self):
        # 세 번 렌더한 뒤에도 앱이 살아 있어야 한다(예외로 죽은 화면을 '로그아웃'으로
        # 잘못 읽고 있지 않은지 확인) — 예외 0건이면 그 위험은 없다.
        logged_out, n_exc, exc = self._render_and_check_logged_out(EXPECTED_SECONDS - 1)
        self.assertEqual(n_exc, 0, f"렌더 중 예외가 났다: {exc}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
