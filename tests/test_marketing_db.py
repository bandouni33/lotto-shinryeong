"""marketing_db 단위 테스트."""

import os
import tempfile
import unittest

import marketing_db as mdb


class MarketingDbTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_path = mdb.DB_PATH
        mdb.DB_PATH = os.path.join(self._tmpdir.name, "test_lotto.db")
        mdb.init_marketing_tables()

    def tearDown(self):
        mdb.DB_PATH = self._orig_path
        self._tmpdir.cleanup()

    def test_tables_are_independent(self):
        sms_id = mdb.enqueue_sms("01012345678", "정기구독")
        combo_count = mdb.bulk_insert_lotto_combinations(
            1200,
            [(1, 2, 3, 4, 5, 6), (7, 8, 9, 10, 11, 12)],
        )
        self.assertGreater(sms_id, 0)
        self.assertEqual(combo_count, 2)
        self.assertEqual(mdb.get_combination_count_by_draw(1200), 2)

    def test_sms_queue_no_lotto_numbers(self):
        mdb.enqueue_sms("01099998888", "일반구매")
        conn = mdb._connect()
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(sms_queue)").fetchall()
        }
        conn.close()
        self.assertNotIn("num1", cols)
        self.assertNotIn("draw_round", cols)

    def test_bulk_insert_and_win_rank_group_by(self):
        mdb.bulk_insert_lotto_combinations(1201, [(1, 2, 3, 4, 5, 6)])
        conn = mdb._connect()
        conn.execute(
            "UPDATE lotto_combinations SET win_rank = 1 WHERE draw_round = 1201"
        )
        conn.commit()
        conn.close()
        summary = mdb.get_win_rank_counts_by_draw(1201)
        self.assertEqual(summary.get(1), 1)

    def test_parse_text_rows(self):
        text = "1,2,3,4,5,6\n7 8 9 10 11 12\nbad row\n"
        rows = mdb.parse_combination_rows_from_text(text)
        self.assertEqual(len(rows), 2)

    def test_number_frequency_and_priority(self):
        draw = 7777
        hot = (7, 8, 9, 10, 11, 12)
        cold = (1, 2, 3, 4, 5, 6)
        mdb.bulk_insert_lotto_combinations(draw, [hot] * 30)
        mdb.bulk_insert_lotto_combinations(draw, [cold] * 10)

        freq = mdb.build_number_frequency_map(draw)
        self.assertEqual(freq[7], 30)
        self.assertEqual(freq[1], 10)
        self.assertGreater(
            mdb.combo_priority_score(hot, freq),
            mdb.combo_priority_score(cold, freq),
        )

    def test_allocate_priority_order(self):
        draw = 7778
        hot = (7, 8, 9, 10, 11, 12)
        cold = (1, 2, 3, 4, 5, 6)
        mdb.bulk_insert_lotto_combinations(draw, [hot] * 5)
        mdb.bulk_insert_lotto_combinations(draw, [cold] * 5)

        first = mdb.allocate_lotto_combinations(draw, 1, auto_order_id=101)[0]
        self.assertEqual(first["combo"], hot)

        second = mdb.allocate_lotto_combinations(draw, 1, auto_order_id=102)[0]
        self.assertEqual(second["combo"], hot)

    def test_allocate_insufficient_raises(self):
        draw = 7779
        mdb.bulk_insert_lotto_combinations(draw, [(1, 2, 3, 4, 5, 6)])
        with self.assertRaises(mdb.InsufficientCombinationsError) as ctx:
            mdb.allocate_lotto_combinations(draw, 3, auto_order_id=1)
        self.assertEqual(ctx.exception.available, 1)

    def test_rotate_when_fully_exhausted(self):
        draw = 7781
        hot = (7, 8, 9, 10, 11, 12)
        cold = (1, 2, 3, 4, 5, 6)
        mdb.bulk_insert_lotto_combinations(draw, [hot, cold])

        first = mdb.allocate_lotto_combinations(draw, 2, auto_order_id=301)
        self.assertEqual(len(first), 2)
        self.assertFalse(first[0]["rotated"])
        self.assertEqual(mdb.count_available_combinations(draw), 0)

        second = mdb.allocate_lotto_combinations(draw, 1, auto_order_id=302)
        self.assertEqual(len(second), 1)
        self.assertTrue(second[0]["rotated"])
        self.assertEqual(second[0]["combo"], hot)

    def test_rotate_when_pending_less_than_quantity(self):
        draw = 7782
        combos = [
            (7, 8, 9, 10, 11, 12),
            (7, 8, 9, 13, 14, 15),
            (7, 8, 16, 17, 18, 19),
            (1, 2, 3, 4, 5, 6),
            (1, 2, 3, 4, 5, 7),
        ]
        mdb.bulk_insert_lotto_combinations(draw, combos)
        mdb.allocate_lotto_combinations(draw, 4, auto_order_id=401)
        self.assertEqual(mdb.count_available_combinations(draw), 1)

        rotated = mdb.allocate_lotto_combinations(draw, 3, auto_order_id=402)
        self.assertEqual(len(rotated), 3)
        self.assertTrue(rotated[0]["rotated"])
        self.assertEqual(mdb.count_available_combinations(draw), 2)

    def test_release_allocation(self):
        draw = 7780
        mdb.bulk_insert_lotto_combinations(draw, [(1, 2, 3, 4, 5, 6), (7, 8, 9, 10, 11, 12)])
        allocated = mdb.allocate_lotto_combinations(draw, 1, auto_order_id=200)
        self.assertEqual(mdb.count_available_combinations(draw), 1)
        mdb.release_lotto_combination_allocation([allocated[0]["id"]])
        self.assertEqual(mdb.count_available_combinations(draw), 2)


if __name__ == "__main__":
    unittest.main()
