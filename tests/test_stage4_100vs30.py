"""4차 필터 순위 100vs30 전환(2026-10-11 사용자 지시, 1247회차부터).

  V1 앵커 1245 이하 = 옛 순위(역대 vs 최근100) — 확정 회차 풀·참고등수 불변
  V2 앵커 1246 이상 = 최근100(기준) vs 최근30(비교) — 추적표 '4차필터(100vs30회_후보)'와 같은 정의
  V3 compute_stage_masks: 상중하·top5 는 새 순위, 1차 AUTO 는 옛 순위(auto_gap_order), gap_order = 새 순위
  V4 주간 대조 기준 회차 1247

실행: python tests/test_stage4_100vs30.py
"""
from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import combo_filter_v2 as cf  # noqa: E402
import weekly_lotto_file_update as w  # noqa: E402


def _hist(last=1246, seed=3):
    rnd = random.Random(seed)
    return [{"draw_round": r, "nums": sorted(rnd.sample(range(1, 46), 6)), "bonus": rnd.randint(1, 45)}
            for r in range(1, last + 1)]


class Stage4Test(unittest.TestCase):
    def test_V1_old_rule_until_1245(self):
        h = _hist()
        self.assertEqual(cf.stage4_order_for_anchor(h, 1245), cf._gap_order_for_anchor(h, 1245))
        self.assertEqual(cf._gap_order_for_anchor(h, 1245), w.gap_forecast(h, 1245, 100))

    def test_V2_new_rule_from_1246(self):
        h = _hist()
        new = cf.stage4_order_for_anchor(h, 1246)
        self.assertEqual(new, w.gap_forecast(h, 1246, 30, 100))
        self.assertNotEqual(new, cf._gap_order_for_anchor(h, 1246))
        self.assertEqual(cf.STAGE4_100VS30_FROM_ANCHOR, 1246)

    def test_V3_stage_masks(self):
        h = _hist()
        rnd = random.Random(9)
        combos = np.array([sorted(rnd.sample(range(1, 46), 6)) for _ in range(3000)])
        oh = cf._onehot(combos)
        ones = np.ones(len(combos), dtype=bool)
        base = {"combos": combos, "combo_oh": oh, "static_mask": ones, "gap_mask": ones,
                "static_rules": [], "auto_rules": [{"name": "후보패턴 이웃수", "min": 0, "max": 6}]}
        m = cf.compute_stage_masks(h, 1246, base)
        order = cf.stage4_order_for_anchor(h, 1246)
        self.assertEqual(m["gap_order"], order)
        self.assertEqual(m["auto_gap_order"], cf._gap_order_for_anchor(h, 1246))
        for row, ok in zip(combos, m["stage4_mask"]):
            s = set(int(x) for x in row)
            g = [len(s & set(order[i:i + 15])) for i in (0, 15, 30)]
            want = all(1 <= x <= 4 for x in g) and bool(s & set(order[:5]))
            self.assertEqual(bool(ok), want)
        old = cf.compute_stage_masks(h, 1245, base)
        self.assertEqual(old["gap_order"], cf._gap_order_for_anchor(h, 1245))

    def test_V4_vintage(self):
        self.assertEqual(w.RULE_VINTAGE_ROUND, 1247)


if __name__ == "__main__":
    unittest.main(verbosity=2)
