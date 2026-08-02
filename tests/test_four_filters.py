"""3종 필터 엔진 검증 테스트."""

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
        gap_rules = {1: [{"targets": {1}, "min": 5, "max": 5}]}
        ball_rules = [{"targets": {2, 3, 4, 5, 6}, "min": 6, "max": 6}]
        self.assertTrue(passes_interval_filters(combo, gap_rules))
        self.assertFalse(passes_set_filters(set(combo), ball_rules))

    def test_interval_skips_rules_for_absent_ball(self):
        combo = (1, 2, 3, 4, 5, 6)
        grouped = {10: [{"targets": {10}, "min": 1, "max": 1}]}
        self.assertTrue(passes_interval_filters(combo, grouped))

    def test_interval_triggers_on_ball_not_on_gap_only(self):
        combo_with_ball = (1, 2, 3, 4, 5, 10)
        combo_gap_only = (1, 11, 21, 31, 41, 42)
        grouped = {10: [{"targets": {10}, "min": 0, "max": 5}]}
        self.assertTrue(passes_interval_filters(combo_with_ball, grouped))
        self.assertTrue(passes_interval_filters(combo_gap_only, grouped))
        strict = {10: [{"targets": {10}, "min": 1, "max": 5}]}
        self.assertFalse(passes_interval_filters(combo_with_ball, strict))

    def test_interval_same_gap_value_counts_up_to_five(self):
        combo = (1, 2, 3, 4, 5, 6)
        self.assertEqual(combo_gaps(combo), [1, 1, 1, 1, 1])
        grouped = {1: [{"targets": {1}, "min": 5, "max": 5}]}
        self.assertTrue(passes_interval_filters(combo, grouped))
        grouped_fail = {1: [{"targets": {1}, "min": 4, "max": 4}]}
        self.assertFalse(passes_interval_filters(combo, grouped_fail))

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

    def test_staged_matches_single_pass_four_sheet(self):
        from lotto_engine import run_admin_three_filter_staged, run_filtering_engine
        from filter_sheet_validation import normalize_three_filter_data

        data = normalize_three_filter_data(self.saved)
        staged, stats = run_admin_three_filter_staged(data)
        single = run_filtering_engine(
            data,
            apply_premium_patterns=False,
            apply_builtin_gates=False,
        )
        self.assertEqual(len(staged), len(single))
        self.assertEqual(stats["stage3_interval"], len(staged))

    def test_each_sheet_has_rules(self):
        from filter_sheet_validation import normalize_three_filter_data

        data = normalize_three_filter_data(self.saved)
        for key in ("absolute", "interval"):
            df = data[key]
            active = df[df["입력데이터"].astype(str).str.strip() != ""] if len(df) else df
            self.assertGreater(len(active), 0, f"{key} sheet should have active rules")
        basic = data["basic"]
        basic_active = basic[basic["입력데이터"].astype(str).str.strip() != ""] if len(basic) else basic
        self.assertGreaterEqual(len(basic_active), 0, "basic may be empty")

    def test_all_three_sheets_produce_results(self):
        from lotto_engine import run_admin_three_filter_staged
        from filter_sheet_validation import normalize_three_filter_data

        data = normalize_three_filter_data(self.saved)
        staged, stats = run_admin_three_filter_staged(data)
        total = len(staged)
        self.assertGreater(total, 0, "3종 필터 통합 결과는 0개가 아니어야 함")
        print(
            f"\n[검증] 3종 3단계 최종: {total:,}개 "
            f"(①{stats['stage1_basic']:,} → ②{stats['stage2_absolute']:,})"
        )

    def test_admin_mode_skips_premium_checkbox_filters(self):
        from filter_sheet_validation import normalize_three_filter_data

        data = normalize_three_filter_data(self.saved)
        total = len(
            run_filtering_engine(
                data,
                apply_premium_patterns=False,
                apply_builtin_gates=False,
            )
        )
        with_premium_empty = len(run_filtering_engine(data, apply_premium_patterns=True))
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
        self.assertGreater(
            scoped_pass,
            global_pass,
            "절대필터는 I열 볼별 조건이라 전역 교집합(기본필터 방식)보다 통과 조합이 많아야 함",
        )


if __name__ == "__main__":
    unittest.main()
