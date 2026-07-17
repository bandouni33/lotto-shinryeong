"""4종 필터 엔진 검증 테스트."""

import itertools
import pickle
import unittest

from lotto_engine import (
    combo_gaps,
    passes_absolute_filters,
    passes_interval_filters,
    passes_set_filters,
    prep_absolute_filters,
    prep_interval_filters,
    prep_set_filters,
    run_filtering_engine,
)


class FourFilterLogicTests(unittest.TestCase):
    def test_combo_gaps(self):
        self.assertEqual(combo_gaps((1, 2, 3, 4, 5, 6)), [1, 1, 1, 1, 1])
        self.assertEqual(combo_gaps((1, 3, 10, 20, 30, 45)), [2, 7, 10, 10, 15])

    def test_set_filter_matches_step2(self):
        combo = (1, 11, 21, 31, 41, 45)
        rules = [{"targets": {1, 11, 21, 31, 41}, "min": 1, "max": 5}]
        self.assertTrue(passes_set_filters(set(combo), rules))

    def test_interval_uses_gaps_not_ball_numbers(self):
        combo = (1, 2, 3, 4, 5, 6)
        gap_rules = [{"targets": {1}, "min": 5, "max": 5}]
        ball_rules = [{"targets": {2, 3, 4, 5, 6}, "min": 6, "max": 6}]
        self.assertTrue(passes_interval_filters(combo, gap_rules))
        self.assertFalse(passes_set_filters(set(combo), ball_rules))

    def test_absolute_only_applies_when_number_in_combo(self):
        combo_set = {1, 2, 3, 4, 5, 6}
        grouped = {
            1: [{"targets": {1, 11, 21}, "min": 1, "max": 1}],
            8: [{"targets": {8, 18, 28}, "min": 1, "max": 1}],
        }
        self.assertTrue(passes_absolute_filters(combo_set, grouped))

    def test_absolute_skips_rules_for_absent_numbers(self):
        combo_set = {1, 2, 3, 4, 5, 6}
        grouped = {40: [{"targets": {40}, "min": 1, "max": 1}]}
        self.assertTrue(passes_absolute_filters(combo_set, grouped))


class SavedFiltersIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open("saved_filters.pkl", "rb") as f:
            cls.saved = pickle.load(f)

    def test_each_sheet_has_rules(self):
        for key in ("basic", "special", "interval", "absolute"):
            df = self.saved[key]
            self.assertGreater(len(df), 0, f"{key} sheet should not be empty")

    def test_all_four_sheets_produce_results(self):
        total = len(run_filtering_engine(self.saved, apply_premium_patterns=False))
        self.assertGreater(total, 0, "4종 필터 통합 결과는 0개가 아니어야 함")
        print(f"\n[검증] 4종 필터 통합 통과 조합: {total:,}개")

    def test_admin_mode_skips_premium_checkbox_filters(self):
        total = len(run_filtering_engine(self.saved, apply_premium_patterns=False))
        with_premium_empty = len(run_filtering_engine(self.saved, apply_premium_patterns=True))
        self.assertGreater(total, 0)
        self.assertEqual(with_premium_empty, 0)

    def test_interval_logic_changes_outcome(self):
        interval_df = self.saved["interval"]
        gap_rules = prep_interval_filters(interval_df)
        set_rules = prep_set_filters(interval_df)

        gap_pass = 0
        set_pass = 0
        for combo in itertools.combinations(range(1, 46), 6):
            combo_set = set(combo)
            if passes_interval_filters(combo, gap_rules):
                gap_pass += 1
            if passes_set_filters(combo_set, set_rules):
                set_pass += 1

        self.assertNotEqual(gap_pass, set_pass)

    def test_absolute_scoped_beats_global_and(self):
        absolute_df = self.saved["absolute"]
        scoped_rules = prep_absolute_filters(absolute_df)
        global_rules = prep_set_filters(absolute_df)

        scoped_pass = 0
        global_pass = 0
        for combo in itertools.combinations(range(1, 46), 6):
            combo_set = set(combo)
            if passes_absolute_filters(combo_set, scoped_rules):
                scoped_pass += 1
            if passes_set_filters(combo_set, global_rules):
                global_pass += 1

        self.assertGreater(scoped_pass, 0)
        self.assertEqual(global_pass, 0)


if __name__ == "__main__":
    unittest.main()
