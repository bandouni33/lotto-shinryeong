"""combo_round_stats 스냅샷 불변식 테스트 (2026-10-04 신규).

무엇을 고정하는 테스트인가 — "회차별 당첨번호 배출표"가 조합 풀 삭제와 무관하게
과거 회차 행·숫자를 영구히 유지한다는 성질이다(실제 사고: 정리 로직이 1243회차 풀을
지우자 표에서 그 행이 통째로 사라졌다).

각 테스트는 하나의 예시가 아니라 **모든 유효 입력에 대해 성립해야 하는 성질**을 건다:
  · 멱등·불변 : 같은 회차를 다시 기록해도 기존 값이 절대 바뀌지 않는다
  · 근거 조건 : 확정 근거(참고등수/win_rank 동기화)가 없으면 확정하지 않는다
                (추첨 전 회차를 0건으로 못 박는 사고 방지)
  · 출처 독립 : 행 목록이 lotto_combinations 가 아니라 스냅샷에서 온다 → 풀 삭제와 무관
  · 경계      : 정렬·limit·하한 회차·NULL 표기
  · 표시 계약 : 표에 "조합수" 열이 없고, 스냅샷 dict만으로 DataFrame이 만들어진다

실행: venv312\\Scripts\\python.exe -X utf8 tests\\test_combo_round_stats_snapshot.py
격리: tests/_db_isolation.isolated_db() — 운영 Turso에는 어떤 경로로도 접속하지 않는다.
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

# 시드 회차(1234~1236)와 겹치지 않는 표시 대상 구간을 쓴다.
R_OLD, R_MID, R_NEW = 2001, 2002, 2003


class ComboRoundStatsSnapshotTests(unittest.TestCase):
    def setUp(self):
        self._iso = _db_isolation.isolated_db()
        self._iso.__enter__()
        self.addCleanup(self._iso.__exit__, None, None, None)
        mdb.init_marketing_tables()

    # ── 헬퍼 ────────────────────────────────────────────────────────────
    def _pool(self, draw_round, rows=2):
        combos = [
            (1 + i, 7, 12, 14, 33, 45) if i == 0 else (2 + i, 8, 13, 15, 34, 44)
            for i in range(rows)
        ]
        return mdb.bulk_insert_lotto_combinations(draw_round, combos)

    def _set_first_win_rank(self, draw_round, rank):
        conn = mdb._connect()
        conn.execute(
            "UPDATE lotto_combinations SET win_rank = ? "
            "WHERE draw_round = ? AND id = (SELECT MIN(id) FROM lotto_combinations WHERE draw_round = ?)",
            (rank, draw_round, draw_round),
        )
        conn.commit()
        conn.close()

    def _sync(self, draw_round):
        mdb.mark_win_rank_synced(draw_round, "lotto_combinations")

    def _row(self, draw_round):
        conn = mdb._connect()
        conn.row_factory = None
        row = conn.execute(
            "SELECT draw_round, pattern_count, rank_1, rank_2, rank_3, rank_4, rank_5, "
            "created_at, finalized_at FROM combo_round_stats WHERE draw_round = ?",
            (draw_round,),
        ).fetchone()
        conn.close()
        return row

    def _count(self):
        conn = mdb._connect()
        row = conn.execute("SELECT COUNT(*) FROM combo_round_stats").fetchone()
        conn.close()
        return int(row[0])

    def _by_round(self, limit=20):
        return {r["draw_round"]: r for r in mdb.get_round_stats_snapshot(limit=limit)}

    # ── 1. 못 박기: 추출 시점 값은 다시 써도 안 바뀐다 ──────────────────
    def test_snapshot_is_create_once_and_never_overwrites(self):
        self.assertTrue(mdb.snapshot_round_stats(R_MID, 6465))
        # 같은 회차를 다른 값으로 다시 기록 시도 → 무시되고 기존 값이 남는다.
        self.assertFalse(mdb.snapshot_round_stats(R_MID, 9999))
        self.assertFalse(mdb.snapshot_round_stats(R_MID, None))
        self.assertEqual(self._count(), 1)
        row = self._row(R_MID)
        self.assertEqual(row[1], 6465)
        self.assertIsNotNone(row[7])  # created_at
        self.assertIsNone(row[8])  # finalized_at — 등수는 아직

    def test_snapshot_accepts_missing_pattern_count(self):
        """적용패턴수 기록이 없는 회차(구 회차)도 행은 만들어야 한다 — 표에서 사라지면 안 된다."""
        self.assertTrue(mdb.snapshot_round_stats(R_OLD, None))
        self.assertIsNone(self._row(R_OLD)[1])

    # ── 2. 확정은 1회만 ────────────────────────────────────────────────
    def test_finalize_writes_ranks_once_and_never_overwrites(self):
        self._pool(R_MID)
        self._set_first_win_rank(R_MID, 1)
        self._sync(R_MID)
        mdb.snapshot_round_stats(R_MID, 6465)

        self.assertTrue(mdb.finalize_round_stats(R_MID))
        first = self._row(R_MID)
        self.assertEqual((first[2], first[3], first[4], first[5], first[6]), (1, 0, 0, 0, 0))
        finalized_at = first[8]
        self.assertIsNotNone(finalized_at)

        # 이후 원본이 어떻게 바뀌든(2등 추가 + 참고등수 기록) 확정값은 불변.
        self._set_first_win_rank(R_MID, 2)
        mdb.set_reference_ranks(R_MID, (9, 8, 7, 6, 5))
        self.assertFalse(mdb.finalize_round_stats(R_MID))
        again = self._row(R_MID)
        self.assertEqual((again[2], again[3], again[4], again[5], again[6]), (1, 0, 0, 0, 0))
        self.assertEqual(again[8], finalized_at)

    def test_finalize_requires_settled_evidence(self):
        """추첨 전 회차 보호 — 근거가 없으면 0으로 못 박지 않고 미확정으로 남긴다."""
        self._pool(R_NEW)
        mdb.snapshot_round_stats(R_NEW, 6465)
        self.assertFalse(mdb.finalize_round_stats(R_NEW))
        row = self._row(R_NEW)
        self.assertIsNone(row[8], "근거 없이 finalized_at 이 채워지면 안 된다")
        self.assertIsNone(row[2])
        # 표시용 조회는 미확정을 0으로 보여준다(추첨 전과 0건을 같은 표기로).
        self.assertEqual(self._by_round()[R_NEW]["rank_1"], 0)

    def test_finalize_prefers_reference_ranks_over_live_counts(self):
        """1241회차 이상 규칙 — 참고등수가 있으면 라이브 집계 대신 그 값을 쓴다(표시와 동일)."""
        self._pool(R_MID)
        self._set_first_win_rank(R_MID, 3)
        self._sync(R_MID)
        mdb.set_reference_ranks(R_MID, (0, 1, 18, 169, 1157))
        mdb.snapshot_round_stats(R_MID, 6465)
        self.assertTrue(mdb.finalize_round_stats(R_MID))
        row = self._row(R_MID)
        self.assertEqual((row[2], row[3], row[4], row[5], row[6]), (0, 1, 18, 169, 1157))

    def test_finalize_pending_only_returns_eligible_rounds(self):
        self._pool(R_OLD)
        self._sync(R_OLD)
        self._pool(R_NEW)  # 동기화·참고등수 없음 → 대상 아님
        mdb.snapshot_round_stats(R_OLD, 6465)
        mdb.snapshot_round_stats(R_NEW, 6465)
        self.assertEqual(mdb.finalize_pending_round_stats(), [R_OLD])
        self.assertEqual(mdb.finalize_pending_round_stats(), [])
        self.assertIsNone(self._row(R_NEW)[8])

    # ── 3. 출처 독립: 풀이 지워져도 행·값이 남는다 ──────────────────────
    def test_row_survives_pool_deletion(self):
        """스냅샷에만 있고 lotto_combinations 에는 없는 회차(실제 1243회차 상황)도 표에 남는다."""
        mdb.set_reference_ranks(1243, (0, 0, 2, 53, 590))
        mdb.snapshot_round_stats(1243, 6465)
        self.assertTrue(mdb.finalize_round_stats(1243))
        self.assertEqual(mdb.get_combination_count_by_draw(1243), 0)

        row = self._by_round()[1243]
        self.assertEqual(row["pattern_count"], 6465)
        self.assertEqual((row["rank_1"], row["rank_5"]), (0, 590))
        self.assertIsNotNone(row["finalized_at"])

    def test_rows_survive_cleanup_old_pools(self):
        """정리 로직이 돌아도 스냅샷 행 수와 값이 그대로다 (이번 사안의 본질)."""
        for draw_round in (R_OLD, R_MID, R_NEW):
            self._pool(draw_round)
            self._sync(draw_round)
            mdb.snapshot_round_stats(draw_round, 6465)
            self.assertTrue(mdb.finalize_round_stats(draw_round))
        before = self._by_round()
        self.assertEqual(sorted(before), [R_OLD, R_MID, R_NEW])

        deleted = mdb.cleanup_old_lotto_combinations(keep_rounds=2)
        self.assertGreater(deleted, 0, "정리가 실제로 풀을 지웠어야 검증이 성립한다")
        self.assertEqual(mdb.get_combination_count_by_draw(R_OLD), 0)

        after = self._by_round()
        self.assertEqual(sorted(after), [R_OLD, R_MID, R_NEW])
        for draw_round, row in before.items():
            self.assertEqual(after[draw_round]["pattern_count"], row["pattern_count"])
            self.assertEqual(after[draw_round]["rank_1"], row["rank_1"])
            self.assertEqual(after[draw_round]["rank_5"], row["rank_5"])

    # ── 4. 경계: 정렬·limit·하한 회차·NULL 표기 ────────────────────────
    def test_ordering_limit_and_display_floor(self):
        mdb.snapshot_round_stats(1233, 6465)  # 표시 하한 미만 → 제외
        mdb.snapshot_round_stats(1234, None)
        mdb.snapshot_round_stats(R_OLD, 6465)
        mdb.snapshot_round_stats(R_NEW, 6465)

        rows = mdb.get_round_stats_snapshot(limit=20)
        self.assertEqual([r["draw_round"] for r in rows], [R_NEW, R_OLD, 1234])
        self.assertEqual([r["draw_round"] for r in rows], sorted((r["draw_round"] for r in rows), reverse=True))
        self.assertEqual([r["draw_round"] for r in mdb.get_round_stats_snapshot(limit=2)], [R_NEW, R_OLD])
        self.assertEqual(mdb.get_round_stats_snapshot(limit=0), [])
        self.assertIsNone(self._by_round()[1234]["pattern_count"])
        for key in ("rank_1", "rank_2", "rank_3", "rank_4", "rank_5"):
            self.assertEqual(self._by_round()[1234][key], 0)

    def test_empty_table_returns_empty_list(self):
        self.assertEqual(mdb.get_round_stats_snapshot(limit=20), [])

    # ── 5. 수동 리셋은 그 회차만 지운다 ────────────────────────────────
    def test_reset_touches_only_that_round(self):
        mdb.snapshot_round_stats(R_OLD, 6465)
        mdb.snapshot_round_stats(R_MID, 6465)
        self.assertEqual(mdb.reset_round_stats_snapshot(R_OLD), 1)
        self.assertEqual(mdb.reset_round_stats_snapshot(R_OLD), 0)
        self.assertEqual([r["draw_round"] for r in mdb.get_round_stats_snapshot()], [R_MID])

    # ── 6. 설계 지시(2026-10-04): 조합수는 저장하지도 표시하지도 않는다 ──
    def test_schema_has_no_total_count_column(self):
        conn = mdb._connect()
        cols = [row[1] for row in conn.execute("PRAGMA table_info(combo_round_stats)").fetchall()]
        conn.close()
        self.assertEqual(
            cols,
            ["draw_round", "pattern_count", "rank_1", "rank_2", "rank_3", "rank_4",
             "rank_5", "created_at", "finalized_at"],
        )
        self.assertNotIn("total_count", cols)

    def test_display_dataframe_has_no_combination_count_column(self):
        """표(DataFrame)에 "조합수" 열이 없어야 한다 — 사용자 화면 기준."""
        import page_auto

        mdb.snapshot_round_stats(R_MID, 6465)
        rows = mdb.get_round_stats_snapshot(limit=20)

        df = page_auto._stats_to_dataframe(rows, False)
        self.assertEqual(list(df.columns), ["회차", "적용패턴수", "1등", "2등", "3등", "4등", "5등"])
        self.assertFalse([c for c in df.columns if "조합수" in str(c) or "total_count" in str(c)])
        self.assertEqual(df.iloc[0]["회차"], R_MID)
        self.assertEqual(df.iloc[0]["적용패턴수"], "6,465")

    def test_load_stats_table_reads_snapshot_source(self):
        """화면 로딩 함수가 라이브 풀이 아니라 스냅샷을 출처로 쓴다.

        풀이 아예 없는 회차(스냅샷에만 있는 회차)가 표에 나온다면, 정리 로직이 원본을
        지운 뒤에도 표가 유지된다는 뜻이다 — 이번 사안의 회귀 방지선.
        """
        import page_auto

        sentinel = [
            {
                "draw_round": 4242,
                "pattern_count": 6465,
                "rank_1": 0,
                "rank_2": 1,
                "rank_3": 18,
                "rank_4": 169,
                "rank_5": 1157,
                "finalized_at": "2026-10-04T00:00:00",
            }
        ]
        original = mdb.get_round_stats_snapshot
        mdb.get_round_stats_snapshot = lambda limit=20: [dict(r) for r in sentinel]
        self.addCleanup(setattr, mdb, "get_round_stats_snapshot", original)
        self.assertEqual(mdb.get_combination_count_by_draw(4242), 0, "풀에 없는 회차여야 검증이 성립한다")

        df, is_mock = page_auto._load_stats_table()

        self.assertFalse(is_mock)
        self.assertIn(4242, list(df["회차"]))
        row = df[df["회차"] == 4242].iloc[0]
        self.assertEqual(row["5등"], 1157)
        self.assertEqual(row["적용패턴수"], "6,465")

    def test_display_maps_missing_pattern_count_to_dash(self):
        import page_auto

        mdb.snapshot_round_stats(R_MID, None)
        df = page_auto._stats_to_dataframe(mdb.get_round_stats_snapshot(limit=20), False)
        self.assertEqual(df.iloc[0]["적용패턴수"], "—")


if __name__ == "__main__":
    unittest.main(verbosity=2)
