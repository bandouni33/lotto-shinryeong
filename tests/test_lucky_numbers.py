"""lucky_numbers 월일 검증 테스트."""

import unittest

import lucky_numbers as ln


class LuckyNumbersTests(unittest.TestCase):
    def test_validate_mmdd_rejects_1234(self):
        ok, err = ln.validate_mmdd("1234")
        self.assertFalse(ok)
        self.assertIn("01~31", err or "")

    def test_validate_mmdd_accepts_0315(self):
        ok, err = ln.validate_mmdd("0315")
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_calculate_all_skips_invalid(self):
        result = ln.calculate_all_lucky_numbers(["1234", "0315"])
        expected = ln.calculate_lucky_numbers("0315")
        self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
