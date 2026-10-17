"""4차 상위 1~7위 절대수 + 7그룹 랜덤 균등 배분(2026-10-17 사용자 지시, 1247회차부터).

  T1 마스크: 7위까지 비트(1..64), 5개면 예전과 같은 값
  T2 추출: 7그룹 균등(각 1/7), 그룹은 1위>…>7위 우선순위로 정확히 하나
  T3 배분 할당량: 5그룹·5/10개는 예전과 완전히 같음 / 7그룹·5개 = 서로 다른 5그룹 랜덤, 10개 = 각1 + 3그룹 랜덤
  T4 실제 배포(격리 DB): 7그룹 풀에서 5개 묶음 반복 → 묶음 안 그룹 중복 없음·조합 중복 없음·
     그룹별 소진이 고르게(편차 작음) · 회전(재고 소진)까지 문제없음 / 옛 5그룹 풀은 묶음마다 1~5위 각 1개
실행: python tests/test_stage4_top7.py
"""
from __future__ import annotations

import random
import sys
import unittest
from collections import Counter
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _p in (str(ROOT), str(TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import _db_isolation  # noqa: E402
import combo_gen_worker as cgw  # noqa: E402
import marketing_db as mdb  # noqa: E402

TOP7 = (34, 14, 45, 33, 40, 7, 21)


def _combo_for_tier(rnd: random.Random, tier: int, top: tuple) -> tuple:
    """tier 위 숫자를 포함하고 그보다 높은 순위 숫자는 뺀 조합."""
    banned = set(top[:tier])
    rest = [n for n in range(1, 46) if n not in banned and n != top[tier]]
    return tuple(sorted([top[tier]] + rnd.sample(rest, 5)))


class Top7Test(unittest.TestCase):
    def test_T1_mask(self):
        self.assertEqual(mdb._compute_top3_mask((34, 1, 2, 3, 4, 5), TOP7), 1)
        self.assertEqual(mdb._compute_top3_mask((21, 7, 2, 3, 4, 5), TOP7), 32 | 64)
        self.assertEqual(mdb._rank_tier_from_mask(32 | 64), 5)
        self.assertEqual(mdb._rank_tier_from_mask(64), 6)
        self.assertEqual(mdb._compute_top3_mask((40, 14, 2, 3, 4, 5), TOP7[:5]), 2 | 16)

    def test_T2_extract_equal_7(self):
        rnd = random.Random(1)
        combos = list({_combo_for_tier(rnd, t, TOP7) for t in range(7) for _ in range(3000)})
        sample = cgw.extract_sample_by_rank_tier_ratio(combos, TOP7)
        c = Counter(cgw._rank_tier(x, TOP7) for x in sample)
        self.assertEqual(set(c), set(range(7)))
        self.assertLessEqual(max(c.values()) - min(c.values()), 1)
        with self.assertRaises(ValueError):
            cgw._rank_tier((1, 2, 3, 4, 5, 6), TOP7)

    def test_T3_quota(self):
        self.assertEqual(mdb._rank_tier_quota(5)[:5], [1, 1, 1, 1, 1])
        self.assertEqual(mdb._rank_tier_quota(10)[:5], [2, 2, 2, 2, 2])
        seen = Counter()
        for _ in range(700):
            q = mdb._rank_tier_quota(5, list(range(7)))
            self.assertEqual(sum(q), 5)
            self.assertTrue(all(x in (0, 1) for x in q))
            seen.update(i for i, x in enumerate(q) if x)
            q10 = mdb._rank_tier_quota(10, list(range(7)))
            self.assertEqual(sum(q10), 10)
            self.assertTrue(all(x in (1, 2) for x in q10))
        self.assertEqual(set(seen), set(range(7)))
        self.assertLess(max(seen.values()) - min(seen.values()), 120)   # 기대 500씩

    def _alloc_rounds(self, draw_round, top, per_tier, bundles):
        rnd = random.Random(draw_round)
        combos = list({_combo_for_tier(rnd, t, top) for t in range(len(top)) for _ in range(per_tier)})
        mdb.bulk_insert_lotto_combinations(draw_round, combos, top5_numbers=top)
        ids = []
        for k in range(bundles):
            rows = mdb.allocate_lotto_combinations_random_sequential(draw_round, 5, auto_order_id=10_000 + k)
            self.assertEqual(len(rows), 5)
            t = [mdb._rank_tier_from_mask(mdb._compute_top3_mask(r["combo"], top)) for r in rows]
            if any(r["rotated"] for r in rows):
                ids = []                                              # 회전 = 회차 배포 초기화
            self.assertFalse(set(ids) & {r["id"] for r in rows})      # 회전 사이엔 중복 배정 없음
            ids += [r["id"] for r in rows]
            yield t

    def test_T4_allocate(self):
        with _db_isolation.isolated_db():
            mdb.init_marketing_tables()
            used = Counter()
            for t in self._alloc_rounds(7001, TOP7, 40, 50):
                self.assertEqual(len(set(t)), 5, t)          # 묶음 안 그룹 중복 없음
                used.update(t)
            self.assertEqual(set(used), set(range(7)))
            self.assertLess(max(used.values()) - min(used.values()), 25)   # 250개 ÷ 7 ≈ 36씩
            # 재고(약 280) 넘게 계속 사도 회전 후 정상
            for t in self._alloc_rounds(7002, TOP7, 6, 20):
                self.assertEqual(len(t), 5)
            # 옛 5그룹 풀 = 묶음마다 1~5위 각 1개(예전과 동일)
            for t in self._alloc_rounds(7003, TOP7[:5], 40, 20):
                self.assertEqual(sorted(t), [0, 1, 2, 3, 4])


if __name__ == "__main__":
    unittest.main(verbosity=2)
