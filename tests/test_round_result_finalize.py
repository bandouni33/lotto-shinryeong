"""토요일 밤 등수 즉시 확정(round_result_finalize) + 다음 회차 미리보기 행 숨김 — 2026-10-10 사용자 지시.

  F1 최신 회차 스냅샷이 있고 참고등수가 없으면 계산해 저장하고 스냅샷을 확정한다.
  F2 다시 돌리면 계산하지 않는다(멱등) — 이미 확정된 값은 안 바뀐다.
  F3 1241회 미만·스냅샷 없음이면 계산 없이 건너뛴다.
  F4 참고등수는 있는데 스냅샷 확정만 빠진 경우 확정만 한다.
  V1 다음 회차 조합이 아직 없으면 자동조합 표에 미리보기 행이 없다(최신 회차가 맨 위).
  V2 다음 회차 조합이 생성됐는데 스냅샷 행이 없으면 예전처럼 미리보기 행이 있다.
  W1 워크플로에 토요일 21:10(KST) 확인과 등수 확정 단계가 있다.

실행: python tests/test_round_result_finalize.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _p in (str(ROOT), str(TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import _db_isolation  # noqa: E402


class _FakeRules:
    def __init__(self):
        import combo_filter_v2

        self.mod = combo_filter_v2
        self.calls = 0

    def __enter__(self):
        self._rules = self.mod._load_rules
        self._ref = self.mod.compute_reference_stats
        outer = self
        self.mod._load_rules = lambda: ([1], [1], [1])

        def _fake_ref(history, drawn_round):
            outer.calls += 1
            return 812345, {"raw_tiers": {}, "ref_ranks": (1, 2, 30, 400, 5000)}

        self.mod.compute_reference_stats = _fake_ref
        return self

    def __exit__(self, *exc):
        self.mod._load_rules = self._rules
        self.mod.compute_reference_stats = self._ref


def _seed(rounds):
    import draw_results_db
    import marketing_db

    draw_results_db.init_draw_results_table()
    marketing_db.init_marketing_tables()
    for r in rounds:
        draw_results_db.upsert_draw_result(r, [1, 2, 3, 4, 5, 6], 7)


class RoundResultFinalizeTest(unittest.TestCase):
    def setUp(self):
        self._iso = _db_isolation.isolated_db()
        self._iso.__enter__()
        self.addCleanup(self._iso.__exit__, None, None, None)

    def test_F1_F2_compute_once_then_idempotent(self):
        import marketing_db
        import round_result_finalize as rrf

        _seed([1244, 1245])
        marketing_db.snapshot_round_stats(1245, 300)
        with _FakeRules() as fake:
            msg = rrf.finalize_latest_round()
            self.assertTrue(msg.startswith("ok: 1245"), msg)
            self.assertEqual(fake.calls, 1)
            row = [s for s in marketing_db.get_round_stats_snapshot(5) if s["draw_round"] == 1245][0]
            self.assertEqual((row["rank_1"], row["rank_3"], row["rank_5"]), (1, 30, 5000))
            self.assertIsNotNone(row["finalized_at"])
            msg2 = rrf.finalize_latest_round()
            self.assertTrue(msg2.startswith("skip: 1245회 참고등수 이미"), msg2)
            self.assertEqual(fake.calls, 1, "F2: 두 번째 실행에서 다시 계산했다")

    def test_F3_skips(self):
        import marketing_db
        import round_result_finalize as rrf

        _seed([1239, 1240])
        with _FakeRules() as fake:
            self.assertIn("대상(1241회~)이 아님", rrf.finalize_latest_round())
            _seed([1246])
            self.assertIn("스냅샷 행 없음", rrf.finalize_latest_round())
            self.assertEqual(fake.calls, 0)
        self.assertIsNone(marketing_db.get_reference_ranks(1246))

    def test_F4_finalize_only(self):
        import marketing_db
        import round_result_finalize as rrf

        _seed([1244, 1245])
        marketing_db.snapshot_round_stats(1245, 300)
        marketing_db.set_reference_ranks(1245, (0, 1, 2, 3, 4))
        with _FakeRules() as fake:
            msg = rrf.finalize_latest_round()
            self.assertEqual(fake.calls, 0)
        self.assertIn("이번에 함", msg)
        row = [s for s in marketing_db.get_round_stats_snapshot(5) if s["draw_round"] == 1245][0]
        self.assertEqual(row["rank_5"], 4)

    def _table_rounds(self, next_round):
        import auto_purchase_service
        import page_auto

        orig = auto_purchase_service._next_draw_round
        auto_purchase_service._next_draw_round = lambda: next_round
        try:
            df, _mock = page_auto._load_stats_table()
        finally:
            auto_purchase_service._next_draw_round = orig
        return [int(x) for x in df.iloc[:, 0].tolist()]

    def test_V1_V2_preview_row(self):
        import marketing_db

        _seed([1244, 1245])
        marketing_db.snapshot_round_stats(1244, 300)
        marketing_db.snapshot_round_stats(1245, 300)
        rounds = self._table_rounds(1246)
        self.assertEqual(rounds[0], 1245, f"V1: 조합 생성 전인데 1246 미리보기 행이 보인다: {rounds}")
        self.assertNotIn(1246, rounds)
        marketing_db.bulk_insert_lotto_combinations(1246, [[1, 2, 3, 4, 5, 6], [7, 8, 9, 10, 11, 12]])
        import ttl_cache

        ttl_cache.invalidate("")
        rounds2 = self._table_rounds(1246)
        self.assertEqual(rounds2[0], 1246, f"V2: 조합 생성 뒤 미리보기 행이 없다: {rounds2}")

    def test_W1_workflow(self):
        wf = (ROOT / ".github" / "workflows" / "hourly_draw_sync.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "10 12 * * 6"', wf)
        self.assertIn("python round_result_finalize.py", wf)
        self.assertIn("timeout-minutes: 40", wf)


if __name__ == "__main__":
    unittest.main(verbosity=2)
