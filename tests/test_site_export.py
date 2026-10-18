"""홈페이지 공개 데이터(site_data/data.json) 내보내기 — 2026-10-18.

  E1 회차·날짜·정렬 번호·보너스, 최신 회차
  E2 조합 성적은 확정된 회차만, 1~4등만(앱 배출 표와 같은 범위)
  E3 공개 값만: 허용된 최상위 키 외에는 없음(회원·주문·토큰 등 새지 않게)
  E4 링크는 social_links 기준점(UTM homepage), 볼 색은 ball_style 기준점
실행: python tests/test_site_export.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import ball_style  # noqa: E402
import social_links  # noqa: E402
from weekly_content import site_export as se  # noqa: E402

DRAWS = [{"draw_round": 1246, "numbers": [28, 16, 22, 23, 24, 27], "bonus": 6},
         {"draw_round": 1245, "numbers": [1, 2, 3, 4, 5, 6], "bonus": 7}]
STATS = [{"draw_round": 1246, "rank_1": 0, "rank_2": 0, "rank_3": 1, "rank_4": 9, "rank_5": 99, "finalized_at": "t"},
         {"draw_round": 1247, "rank_1": 0, "rank_2": 0, "rank_3": 0, "rank_4": 0, "rank_5": 0, "finalized_at": None}]


class SiteExportTest(unittest.TestCase):
    def setUp(self):
        self.d = se.build_data(DRAWS, STATS)

    def test_E1_draws(self):
        self.assertEqual(self.d["latest_round"], 1246)
        self.assertEqual(self.d["draws"][0], [1246, "2026-10-17", 16, 22, 23, 24, 27, 28, 6])
        self.assertEqual(self.d["draws"][1][0], 1245)

    def test_E2_our_stats(self):
        self.assertEqual(self.d["our_stats"], [{"round": 1246, "rank": [0, 0, 1, 9]}])

    def test_E3_public_keys_only(self):
        self.assertEqual(set(self.d), {"schema", "generated_at", "latest_round", "draws", "our_stats", "tarot",
                                       "balls", "links"})
        self.assertEqual(self.d["tarot"]["round"], 1247)
        from weekly_content import cards
        self.assertEqual(self.d["tarot"]["key"], cards.tarot_for_round(1246)["key"])   # SNS 주간 카드 4번과 같은 카드
        self.assertTrue(self.d["tarot"]["image"].startswith("tarot/images/"))

    def test_E4_sources(self):
        self.assertIn("utm_source%3Dhomepage", self.d["links"]["play"])
        self.assertTrue(self.d["links"]["play"].startswith(social_links.PLAY_URL))
        self.assertEqual(self.d["links"]["manual"], social_links.MANUAL_URL)
        self.assertEqual(len(self.d["links"]["manual_posts"]), 8)
        self.assertEqual(self.d["links"]["manual_posts"][0]["url"], social_links.MANUAL_URL)
        self.assertEqual(self.d["balls"]["7"]["fill"], ball_style.ball_fill(7))
        self.assertNotIn("유튜브", [c["name"] for c in self.d["links"]["channels"]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
