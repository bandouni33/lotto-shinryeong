# -*- coding: utf-8 -*-
"""scratch/sim_filter_generation.py가 주장하는 불변식 검증.

이 턴에서 이 파일(시뮬레이터)에 넣은 변경은 딱 한 줄이다 — 표본 중복 검사식:

    (수정 전) dup = len(combos) - len(set(sample))     → 1,028,408 - 51,420 으로 "중복 976,988개"라는 무의미한 값
    (수정 후) dup = len(sample) - len(set(sample))     → 실제 중복 개수

그래서 여기서 검증하는 것은 두 가지다:
  A) 그 중복 계측식 자체의 성질 — 유효한 모든 리스트에 대해 "중복이 없으면 0,
     있으면 개수만큼"을 만족해야 한다(빈 리스트·단일 원소·중복 포함 경계 포함).
  B) 시뮬레이터가 출력 근거로 삼는 추출기
     combo_gen_worker.extract_sample_by_rank_tier_ratio()의 불변식 — 한 예시가
     아니라 입력 크기·비율·그룹 불균형을 바꿔가며 항상 성립해야 하는 성질만 본다.

pytest 없음 — 이 프로젝트 관례대로 __main__ 러너로 실행한다:
    venv312\\Scripts\\python.exe scratch\\test_sim_invariants.py
"""

from __future__ import annotations

import math
import os
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import combo_gen_worker as cgw  # noqa: E402

TOP5 = (34, 14, 45, 33, 40)
NON_TOP5 = [n for n in range(1, 46) if n not in TOP5]


def dup_count(items: list) -> int:
    """scratch/sim_filter_generation.py가 쓰는 것과 같은 계측식(사본이 아니라
    동일 정의) — 이 식이 가진 성질을 검사한다."""
    return len(items) - len(set(items))


def make_combos(per_tier: list[int], seed: int = 0) -> list[tuple[int, ...]]:
    """tier i 전용 조합을 per_tier[i]개 만든다 — top5[i]만 포함하고 나머지는
    top5가 아닌 숫자에서 뽑으므로 _rank_tier()가 정확히 i를 돌려준다."""
    rnd = random.Random(seed)
    out: list[tuple[int, ...]] = []
    for i, cnt in enumerate(per_tier):
        seen: set[tuple[int, ...]] = set()
        guard = 0
        while len(seen) < cnt:
            guard += 1
            if guard > cnt * 200 + 1000:
                raise AssertionError("테스트 조합 생성 실패(조합 공간 부족)")
            rest = rnd.sample(NON_TOP5, 5)
            seen.add(tuple(sorted((TOP5[i],) + tuple(rest))))
        out.extend(sorted(seen))
    return out


class DuplicateMetricTests(unittest.TestCase):
    """A) 이번에 고친 한 줄이 만족해야 하는 성질 — 모든 리스트에 대해."""

    def test_zero_iff_unique(self):
        cases = [
            [],
            [1],
            [(1, 2, 3, 4, 5, 6)],
            list(range(100)),
            [(1, 2, 3, 4, 5, 6)] * 7,
            [(1, 2, 3, 4, 5, 6), (1, 2, 3, 4, 5, 7)] * 3,
            ["가", "나", "가", "가"],
        ]
        for items in cases:
            with self.subTest(items=items[:3]):
                dup = dup_count(items)
                self.assertGreaterEqual(dup, 0)
                self.assertEqual(dup == 0, len(set(items)) == len(items))

    def test_counts_every_extra_copy(self):
        # 고유 3개 + 사본 5개 → 중복 5 (원소 종류 수가 아니라 "초과분"을 센다)
        items = [1, 2, 3, 3, 3, 2, 1, 1]
        self.assertEqual(dup_count(items), 5)
        self.assertEqual(len(items) - dup_count(items), 3)

    def test_matches_reference_implementation(self):
        rnd = random.Random(7)
        for _ in range(200):
            n = rnd.randrange(0, 40)
            items = [rnd.randrange(0, 6) for _ in range(n)]
            ref = sum(c - 1 for c in __import__("collections").Counter(items).values() if c > 1)
            self.assertEqual(dup_count(items), ref)

    def test_old_formula_was_wrong(self):
        """수정 전 식(len(전체)-len(set(표본)))은 중복이 하나도 없어도 큰 값을
        낸다 — 그게 바로 잘못 보고된 '중복 976,988개'의 정체였다."""
        combos = [(1, 2, 3, 4, 5, 6), (1, 2, 3, 4, 5, 7), (1, 2, 3, 4, 5, 8)]
        sample = combos[:1]
        self.assertEqual(len(combos) - len(set(sample)), 2)  # 수정 전: 중복 2개라고 거짓 보고
        self.assertEqual(dup_count(sample), 0)               # 수정 후: 0


class RankTierTests(unittest.TestCase):
    """_rank_tier: 4차 통과 조합은 1~5위그룹 중 '정확히 하나'에만 속한다."""

    def test_partition_is_disjoint_and_exhaustive(self):
        combos = make_combos([40, 41, 42, 43, 44], seed=1)
        tiers = [cgw._rank_tier(c, TOP5) for c in combos]
        self.assertEqual(sorted(set(tiers)), [0, 1, 2, 3, 4])
        counts = [tiers.count(i) for i in range(5)]
        self.assertEqual(counts, [40, 41, 42, 43, 44])
        self.assertEqual(sum(counts), len(combos))  # 겹침 없음 + 빠짐 없음

    def test_priority_is_by_lowest_index(self):
        # 1위와 5위를 동시에 포함하면 1위그룹(0)이어야 한다
        self.assertEqual(cgw._rank_tier((34, 40, 1, 2, 3, 4), TOP5), 0)
        # 2위와 4위 → 2위그룹(1)
        self.assertEqual(cgw._rank_tier((14, 33, 1, 2, 3, 4), TOP5), 1)
        self.assertEqual(cgw._rank_tier((40, 1, 2, 3, 4, 5), TOP5), 4)

    def test_raises_when_no_top5_number(self):
        # 4차 조건상 나올 수 없는 입력은 조용히 분류하지 않고 예외로 알린다
        with self.assertRaises(ValueError):
            cgw._rank_tier((1, 2, 3, 4, 5, 6), TOP5)


class ExtractSampleInvariantTests(unittest.TestCase):
    """B) 시뮬레이터가 출력 근거로 쓰는 추출기의 불변식 (입력/비율을 바꿔가며)."""

    def _run(self, per_tier, rate):
        combos = make_combos(per_tier, seed=sum(per_tier))
        orig_rate = cgw.EXTRACT_RATE
        cgw.EXTRACT_RATE = rate
        try:
            sample = cgw.extract_sample_by_rank_tier_ratio(combos, TOP5)
        finally:
            cgw.EXTRACT_RATE = orig_rate
        return combos, sample

    def test_no_duplicates_and_subset_for_many_inputs(self):
        cases = [
            ([10, 10, 10, 10, 10], 0.05),
            ([10, 10, 10, 10, 10], 1.0),
            ([1, 2, 3, 4, 5], 0.5),
            ([200, 7, 3, 150, 1], 0.05),
            ([5, 5, 5, 5, 5], 0.0),
            ([37, 0, 0, 0, 0], 0.05),   # 그룹 0개(빈 그룹) 경계
            ([3, 3, 3, 3, 3], 0.9),
        ]
        for per_tier, rate in cases:
            with self.subTest(per_tier=per_tier, rate=rate):
                combos, sample = self._run(per_tier, rate)
                # 불변식 1: 표본에 중복이 없다 (이번에 고친 계측식이 0을 내야 하는 성질)
                self.assertEqual(dup_count(sample), 0)
                # 불변식 2: 표본은 입력의 부분집합이다
                self.assertTrue(set(sample).issubset(set(combos)))
                # 불변식 3: 크기 = 각 그룹 min(배정목표, 그룹크기)의 합
                total_target = math.floor(len(combos) * rate)
                unit, leftover = divmod(total_target, sum(cgw.RANK_TIER_RATIO))
                targets = [unit * r for r in cgw.RANK_TIER_RATIO]
                order = sorted(range(len(cgw.RANK_TIER_RATIO)), key=lambda i: -cgw.RANK_TIER_RATIO[i])
                for i in range(leftover):
                    targets[order[i % len(order)]] += 1
                groups = [0] * 5
                for c in combos:
                    groups[cgw._rank_tier(c, TOP5)] += 1
                expected = sum(min(t, g) for t, g in zip(targets, groups))
                self.assertEqual(len(sample), expected)
                # 불변식 4: 그룹별 산출량은 그 그룹 크기를 넘지 않는다
                picked = [0] * 5
                for c in sample:
                    picked[cgw._rank_tier(c, TOP5)] += 1
                for i in range(5):
                    self.assertLessEqual(picked[i], groups[i])
                    self.assertLessEqual(picked[i], targets[i])

    def test_groups_balanced_when_input_balanced(self):
        # 실제 배포 규칙의 핵심: 5개묶음마다 각 그룹 1개씩이므로 그룹별 산출량이
        # 같아야 한다 — 입력 그룹 크기가 충분히 크면 정확히 같은 수.
        combos, sample = self._run([500, 500, 500, 500, 500], 0.05)
        picked = [0] * 5
        for c in sample:
            picked[cgw._rank_tier(c, TOP5)] += 1
        self.assertEqual(len(set(picked)), 1)
        self.assertEqual(sum(picked), len(sample))
        self.assertEqual(len(sample), math.floor(len(combos) * 0.05))

    def test_empty_input_yields_empty_sample(self):
        combos, sample = self._run([0, 0, 0, 0, 0], 0.05)
        self.assertEqual(combos, [])
        self.assertEqual(sample, [])
        self.assertEqual(dup_count(sample), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
