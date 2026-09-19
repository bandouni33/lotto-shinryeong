"""marketing_db 단위 테스트.

2026-09-19 수정(중요): 예전엔 setUp에서 mdb.DB_PATH를 임시경로로 바꿔 격리한다고
했지만, marketing_db._connect()는 DB_PATH를 안 보고 db_turso.connect()(=진짜 운영
Turso)를 그대로 부른다 — 그 패치는 no-op이었고, 이 테스트들은 매 실행마다 운영 DB의
lotto_combinations(시험 회차 1200/1201/1236/7777~7782 — 1236은 실제 배포 풀 CSV를
통째로 적재하는 경로)와 sms_queue에 시험 데이터를 실제로 썼다.
이제 db_turso.connect 자체를 임시 sqlite 파일로 바꿔치기한다(tests/_db_isolation.py).
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


class MarketingDbTests(unittest.TestCase):
    def setUp(self):
        self._iso = _db_isolation.isolated_db()
        self._iso.__enter__()
        self.addCleanup(self._iso.__exit__, None, None, None)
        mdb.init_marketing_tables()

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

    def test_marketing_pool_seed_imports_repo_draw_1236(self):
        imported = mdb.ensure_marketing_pool_seeds((1236,))
        seed_path = mdb._marketing_pool_seed_path(1236)
        if not seed_path.is_file():
            self.skipTest("data/marketing_pools/draw_1236.csv.gz 없음")
        self.assertGreater(imported.get(1236, 0), 0)
        self.assertEqual(mdb.get_combination_count_by_draw(1236), imported[1236])

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

    def test_cleanup_preserves_seed_rounds_and_is_idempotent(self):
        """R2 — 정리는 시드 회차를 지우지 않고, 반복 실행해도 아무것도 지우지 않는다.

        시드를 지우면 ensure_marketing_pool_seeds()가 repo CSV를 다시 적재해
        (삭제↔재적재) 회차당 수천 행 쓰기가 매주 반복된다 — 그 왕복을 없앤 게 R2다.
        """
        for draw in (1234, 1235, 1236, 9001, 9002):
            mdb.bulk_insert_lotto_combinations(draw, [(1, 2, 3, 4, 5, 6)])

        deleted = mdb.cleanup_old_lotto_combinations(keep_rounds=1)  # 9002만 보관
        self.assertEqual(deleted, 1, f"보관 규칙이 틀렸거나 시드를 지웠다: {deleted}")
        for seed in mdb.MARKETING_POOL_SEED_DRAWS:
            self.assertEqual(
                mdb.get_combination_count_by_draw(seed), 1, f"시드 회차 {seed}가 삭제됐다"
            )
        self.assertEqual(mdb.get_combination_count_by_draw(9001), 0)
        self.assertEqual(mdb.get_combination_count_by_draw(9002), 1)

        # 멱등 — 두 번째 정리는 아무것도 지우지 않는다(낭비 제거의 핵심 성질)
        self.assertEqual(mdb.cleanup_old_lotto_combinations(keep_rounds=1), 0)
        for seed in mdb.MARKETING_POOL_SEED_DRAWS:
            self.assertEqual(mdb.get_combination_count_by_draw(seed), 1)

    def test_bulk_insert_rejects_rows_over_capacity_without_writing(self):
        """안전장치 — 한도 초과 요청은 ValueError로 거부되고 한 행도 쓰지 않는다.

        한도 상수를 일시적으로 3으로 낮춰 경계(3=통과, 4=거부)를 실제로 확인한다
        (200,001행을 진짜로 넣어보는 테스트는 몇 분이 걸려 쓸 수 없다).
        """
        original = mdb.MAX_BULK_INSERT_ROWS
        mdb.MAX_BULK_INSERT_ROWS = 3
        try:
            self.assertEqual(
                mdb.bulk_insert_lotto_combinations(9100, [(1, 2, 3, 4, 5, 6)] * 3), 3
            )
            with self.assertRaises(ValueError):
                mdb.bulk_insert_lotto_combinations(9101, [(1, 2, 3, 4, 5, 6)] * 4)
            self.assertEqual(
                mdb.get_combination_count_by_draw(9101), 0, "거부됐는데 일부가 저장됐다"
            )
            self.assertEqual(mdb.get_combination_count_by_draw(9100), 3)
        finally:
            mdb.MAX_BULK_INSERT_ROWS = original

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
