"""안티·액땜 — 기준값패턴 전부 만족 우선, 없으면 최다 만족(2026-10-12 사용자 규칙).

  H1 풀 조합이 겹침 조건을 통과해도 패턴 미달이면 바로 쓰지 않고, 패턴 전부 만족 조합이 먼저 채워진다
  H2 패턴 전부 만족 조합이 모자라면 최다 만족 순으로 채운다(겹침 상한은 그대로)
  H3 전체리셋 누적 겹침 3개 상한 유지
실행: python tests/test_hedge_pattern_first.py
"""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import page_hedge as ph  # noqa: E402
import lotto_stats  # noqa: E402

ODD = set(range(1, 46, 2))
RULES = [{"targets": ODD, "min": 3, "max": 3}]            # 홀수 정확히 3개
LINES = [(1, 2, 3, 4, 5, 6)]


def _score(combo, rules):
    m = sum(1 for r in rules if r["min"] <= len(set(combo) & r["targets"]) <= r["max"])
    return m == len(rules), m, len(rules)


class HedgeTest(unittest.TestCase):
    def setUp(self):
        self.p = [
            mock.patch.object(lotto_stats, "get_number_weights", lambda: {n: 1 for n in range(1, 46)}),
            mock.patch.object(lotto_stats, "get_resolved_pattern_rules", lambda: RULES),
            mock.patch.object(lotto_stats, "score_combo_against_pattern_rules", _score),
        ]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()

    def test_H1_pool_needs_pattern(self):
        bad = (7, 9, 11, 13, 15, 17)      # 겹침 0, 홀수 6 → 패턴 미달
        good = (7, 9, 11, 20, 22, 24)     # 겹침 0, 홀수 3 → 패턴 만족
        with mock.patch.object(ph, "_pool_priority_matches", lambda cond, n: [c for c in (bad, good) if cond(c)]):
            res = ph.generate_anti_combinations(LINES, 5)
        self.assertEqual(len(res), 5)
        self.assertNotIn(bad, res)
        self.assertIn(good, res)
        for c in res:
            self.assertTrue(_score(c, RULES)[0])
            self.assertLessEqual(len(set(c) & set(LINES[0])), 2)

    def test_H2_best_fallback(self):
        rules = [{"targets": {1}, "min": 1, "max": 1}]        # 1 포함 — 겹침 상한 때문에 거의 못 만족하지 않음(1은 허용)
        with mock.patch.object(lotto_stats, "get_resolved_pattern_rules", lambda: rules), \
             mock.patch.object(ph, "_pool_priority_matches", lambda cond, n: []), \
             mock.patch.object(ph, "_MAX_ATTEMPTS", 50):
            res = ph.generate_anti_combinations(LINES, 5)
        self.assertEqual(len(res), 5)

    def test_H3_aekddaem_cap(self):
        pool = [(1, 7, 9, 11, 20, 22), (2, 3, 13, 15, 17, 30), (7, 9, 11, 20, 22, 24)]
        with mock.patch.object(ph, "_pool_priority_matches", lambda cond, n: pool):
            res = ph.generate_aekddaem_combinations(LINES, 5)
        total = sum(len(set(c) & set(LINES[0])) for c in res)
        self.assertLessEqual(total, 3)
        self.assertNotIn((2, 3, 13, 15, 17, 30), res)   # 홀수 4 → 패턴 미달(전부 만족 조합이 있으면 안 씀)


if __name__ == "__main__":
    unittest.main(verbosity=2)
