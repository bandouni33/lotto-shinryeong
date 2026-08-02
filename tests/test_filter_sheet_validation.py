"""filter_sheet_validation 단위 테스트."""

import pickle
import unittest

from filter_sheet_validation import validate_four_filter_sheets


class FilterSheetValidationTests(unittest.TestCase):
    def test_saved_filters_pkl_validates_or_reports(self):
        with open("saved_filters.pkl", "rb") as f:
            saved = pickle.load(f)
        errors, summary = validate_four_filter_sheets(saved)
        self.assertIsInstance(errors, list)
        self.assertIn("basic_rows", summary)
        if errors:
            print("\n[검증] saved_filters.pkl 오류 샘플:", errors[:3])


if __name__ == "__main__":
    unittest.main()
