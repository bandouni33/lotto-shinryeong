"""당첨번호 ↔ 추출 조합 등수 연동 테스트.

2026-09-19 수정(중요): 예전엔 setUp에서 mdb.DB_PATH를 임시경로로 바꿔 격리한다고
했지만, marketing_db._connect()는 DB_PATH를 안 봐서 그 패치가 no-op이었다 —
이 테스트는 운영 DB의 lotto_combinations(시험 회차 1234/9999 + 그 회차 win_rank
일괄 UPDATE)에 실제로 썼다. 이제 db_turso.connect 자체를 임시 sqlite로 바꿔치기한다.
"""

import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _path in (str(ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import _db_isolation  # noqa: E402
import marketing_db as mdb  # noqa: E402
from lotto_stats import calc_lotto_win_rank, sync_marketing_win_ranks_for_round  # noqa: E402


class LottoWinRankTests(unittest.TestCase):
    def setUp(self):
        self._iso = _db_isolation.isolated_db()
        self._iso.__enter__()
        self.addCleanup(self._iso.__exit__, None, None, None)
        mdb.init_marketing_tables()

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
        # R1(2026-09-19): 반환값은 "실제로 쓴 행 수" — 낙첨 조합([1,2,3,4,5,6])은
        # NULL을 NULL로 다시 쓰지 않으므로 6행 중 5행만 쓴다.
        self.assertEqual(updated, 5)
        summary = mdb.get_win_rank_counts_by_draw(1234)
        self.assertEqual(summary.get(1), 1)
        self.assertEqual(summary.get(2), 1)
        self.assertEqual(summary.get(3), 1)
        self.assertEqual(summary.get(4), 1)
        self.assertEqual(summary.get(5), 1)

        # 낙첨 행은 NULL 그대로 남는다(등수 집계에서 빠지는 것과 같은 의미)
        conn = mdb._connect()
        loser = conn.execute(
            "SELECT win_rank FROM lotto_combinations WHERE draw_round = 1234 "
            "AND num1 = 1 AND num2 = 2 AND num3 = 3"
        ).fetchone()
        conn.close()
        self.assertIsNone(loser["win_rank"], "낙첨 조합의 win_rank가 NULL이 아니다")

        # 같은 입력으로 다시 동기화하면 아무 행도 다시 쓰지 않는다(멱등 — R1의 요점)
        self.assertEqual(
            mdb.update_win_ranks_for_draw(1234, winning, bonus),
            0,
            "재동기화가 같은 값을 다시 썼다(쓰기 낭비)",
        )

    def test_sync_skips_when_draw_missing_in_excel(self):
        mdb.bulk_insert_lotto_combinations(9999, [(1, 2, 3, 4, 5, 6)])
        outcome = sync_marketing_win_ranks_for_round(9999, filepath="__missing__.xlsb")
        self.assertFalse(outcome["synced"])
        self.assertEqual(outcome["reason"], "draw_not_found")


if __name__ == "__main__":
    unittest.main()
