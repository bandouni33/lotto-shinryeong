"""자동조합 이용 시간(2026-10-12 사용자 지시) — 다음 회차 조합 준비 즉시 ~ 토 19:55, 그 밖 '준비중입니다'.

  W1 날짜 → 판매 회차: 1245=2026-10-10, 토 19:55 전/후 경계, 일·월은 다음 토요일 회차
  W2 열림 = 앱의 다음 회차 == 판매 회차 and 조합 있음
  W3 토 19:55 이후 당첨번호 반영 전(앱 다음 회차가 옛 회차) → 닫힘
  W4 반영 뒤 조합 생성 전 → 닫힘, 생성 직후(일요일·월요일·화 09시 전 포함) → 열림
  W5 조회 실패 → 닫힘, 안내 문구 '준비중입니다' 하나로 통일
실행: python tests/test_sales_window.py
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sales_window as sw  # noqa: E402

KST = ZoneInfo("Asia/Seoul")


def t(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=KST)


class SalesWindowTest(unittest.TestCase):
    def test_W1_target_round(self):
        self.assertEqual(sw.target_round_for(t(2026, 10, 10, 19, 54)), 1245)
        self.assertEqual(sw.target_round_for(t(2026, 10, 10, 19, 55)), 1246)
        self.assertEqual(sw.target_round_for(t(2026, 10, 11, 14, 0)), 1246)   # 일
        self.assertEqual(sw.target_round_for(t(2026, 10, 12, 9, 0)), 1246)    # 월
        self.assertEqual(sw.target_round_for(t(2026, 10, 17, 12, 0)), 1246)   # 토 낮

    def test_W2_open(self):
        self.assertTrue(sw.is_sales_window_open(t(2026, 10, 14, 10, 0), next_round=1246, pool_ready=True))

    def test_W3_after_cutoff_before_sync(self):
        self.assertFalse(sw.is_sales_window_open(t(2026, 10, 10, 20, 30), next_round=1245, pool_ready=True))

    def test_W4_ready_immediately(self):
        self.assertFalse(sw.is_sales_window_open(t(2026, 10, 11, 9, 0), next_round=1246, pool_ready=False))
        self.assertTrue(sw.is_sales_window_open(t(2026, 10, 11, 13, 45), next_round=1246, pool_ready=True))
        self.assertTrue(sw.is_sales_window_open(t(2026, 10, 12, 8, 0), next_round=1246, pool_ready=True))
        self.assertTrue(sw.is_sales_window_open(t(2026, 10, 13, 8, 59), next_round=1246, pool_ready=True))

    def test_W5_failure_closed_and_text(self):
        import auto_purchase_service as aps

        with mock.patch.object(aps, "check_next_draw_pool_ready", side_effect=RuntimeError("db")):
            self.assertFalse(sw.is_sales_window_open(t(2026, 10, 14, 10, 0)))
        self.assertEqual(sw.SALES_WINDOW_BANNER, "준비중입니다")
        self.assertEqual(aps.NEXT_DRAW_POOL_BANNER, "준비중입니다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
