"""당첨번호 ↔ 추출 조합 등수 연동 테스트."""

import os
import tempfile
import unittest

import marketing_db as mdb
from lotto_stats import calc_lotto_win_rank, sync_marketing_win_ranks_for_round


class LottoWinRankTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_path = mdb.DB_PATH
        mdb.DB_PATH = os.path.join(self._tmpdir.name, "test_lotto.db")
        mdb.init_marketing_tables()

    def tearDown(self):
        mdb.DB_PATH = self._orig_path
        self._tmpdir.cleanup()

    def test_calc_lotto_win_rank_rules(self):
        winning = [1, 2, 3, 4, 5, 6]
        bonus = 7
        self.assertEqual(calc_lotto_win_rank(winning, winning, bonus), 1)
        self.assertEqual(calc_lotto_win_rank([1, 2, 3, 4, 5, 7], winning, bonus), 2)
        self.assertEqual(calc_lotto_win_rank([1, 2, 3, 4, 5, 8], winning, bonus), 3)
        self.assertEqual(calc_lotto_win_rank([1, 2, 3, 4, 9, 10], winning, bonus), 4)
        self.assertEqual(calc_lotto_win_rank([1, 2, 3, 11, 12, 13], winning, bonus), 5)
        self.assertEqual(calc_lotto_win_rank([1, 2, 11, 12, 13, 14], winning, bonus), None)

    def test_update_win_ranks_for_draw(self):
        winning = [10, 20, 30, 40, 41, 42]
        bonus = 45
        mdb.bulk_insert_lotto_combinations(
            1234,
            [
                winning,
                [10, 20, 30, 40, 41, bonus],
                [10, 20, 30, 40, 41, 43],
                [10, 20, 30, 40, 44, 45],
                [10, 20, 30, 44, 45, 43],
                [1, 2, 3, 4, 5, 6],
            ],
        )
        updated = mdb.update_win_ranks_for_draw(1234, winning, bonus)
        self.assertEqual(updated, 6)
        summary = mdb.get_win_rank_counts_by_draw(1234)
        self.assertEqual(summary.get(1), 1)
        self.assertEqual(summary.get(2), 1)
        self.assertEqual(summary.get(3), 1)
        self.assertEqual(summary.get(4), 1)
        self.assertEqual(summary.get(5), 1)

    def test_sync_skips_when_draw_missing_in_excel(self):
        mdb.bulk_insert_lotto_combinations(9999, [(1, 2, 3, 4, 5, 6)])
        outcome = sync_marketing_win_ranks_for_round(9999, filepath="__missing__.xlsb")
        self.assertFalse(outcome["synced"])
        self.assertEqual(outcome["reason"], "draw_not_found")


if __name__ == "__main__":
    unittest.main()
