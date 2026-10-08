# -*- coding: utf-8 -*-
"""동행복권 새 회차 확인이 화면 그리기를 붙잡지 않는다 (2026-10-08 운영 실측 대응).

운영 실측: 앱 재실행 첫 메인 화면 서버 처리 11.1초. 1시간 캐시가 만료된 뒤 처음 들어온 이용자가
동행복권 사이트 응답(최대 8초 타임아웃)을 화면 그리는 도중 그대로 기다리는 구조였다.

  G1 _draw_results_cache_key 는 확인이 3초 걸려도 즉시 돌아온다(백그라운드 스레드).
  G2 1시간 안에는 다시 확인하지 않는다(진행 중이어도 중복 시작 안 함).
  G3 1시간이 지나면 다시 시작한다.
  G4 호출 시점의 함수(테스트 대역 포함)를 스레드가 그대로 쓴다.
"""
from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import draw_results_db  # noqa: E402
import lotto_stats  # noqa: E402


class DrawSyncBackgroundTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        saved = (draw_results_db.sync_latest_from_dhlottery, draw_results_db.init_draw_results_table,
                 draw_results_db.get_cache_key)

        def restore():
            (draw_results_db.sync_latest_from_dhlottery, draw_results_db.init_draw_results_table,
             draw_results_db.get_cache_key) = saved

        self.addCleanup(restore)

        def slow():
            self.calls.append(time.time())
            time.sleep(1.5)

        draw_results_db.sync_latest_from_dhlottery = slow
        draw_results_db.init_draw_results_table = lambda: None
        draw_results_db.get_cache_key = lambda: (1245, 1245)
        lotto_stats._auto_sync_state.update(last=0.0, running=False)

    def _wait_idle(self):
        for _ in range(40):
            if not lotto_stats._auto_sync_state["running"]:
                return
            time.sleep(0.1)

    def test_G1_G2_G3_G4(self):
        t = time.time()
        self.assertEqual(lotto_stats._draw_results_cache_key(), (1245, 1245))
        self.assertLess(time.time() - t, 0.5, "화면이 동행복권 확인을 기다렸다")
        self.assertEqual(lotto_stats._draw_results_cache_key(), (1245, 1245))  # 진행 중 → 중복 시작 없음
        self._wait_idle()
        self.assertEqual(len(self.calls), 1, "대역 함수가 정확히 1번 불려야 한다")
        lotto_stats._draw_results_cache_key()  # 1시간 안 → 다시 확인 안 함
        time.sleep(0.2)
        self.assertEqual(len(self.calls), 1)
        lotto_stats._auto_sync_state["last"] -= lotto_stats._AUTO_SYNC_INTERVAL_SECONDS + 1
        lotto_stats._draw_results_cache_key()
        self._wait_idle()
        self.assertEqual(len(self.calls), 2, "1시간이 지나면 다시 확인해야 한다")


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(DrawSyncBackgroundTests))
    sys.exit(0 if result.wasSuccessful() else 1)
