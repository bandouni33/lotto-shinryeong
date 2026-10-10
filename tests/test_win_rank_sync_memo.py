"""당첨 등수 '동기화 끝남' 확인 줄이기(2026-10-10 사용자 승인) 잠금 테스트.

  W1 끝난 회차는 한 번 확인되면 다시 DB 에 묻지 않는다.
  W2 아직 안 끝난 회차는 기억하지 않는다(매번 실제 확인) — 나중에 끝나면 바로 True.
  W3 묶음 확인(prefetch)은 출처별 1회 조회로 끝난 회차 전부를 채운다.
  W4 기억은 DB 연결(격리 DB)마다 따로라 다른 DB 와 섞이지 않는다.
  W5 sync_marketing_win_ranks_for_db_draws 가 회차마다 묻지 않는다(조회 수 감소).

실행: python tests/test_win_rank_sync_memo.py
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
import db_turso  # noqa: E402
import marketing_db as mdb  # noqa: E402

SRC = "lotto_combinations"


class _Counter:
    """db_turso.connect 를 감싸 'draw_win_rank_sync_status' 조회 수를 센다."""

    def __init__(self):
        self.n = 0
        self._orig = db_turso.connect

    def __enter__(self):
        outer = self
        orig = self._orig

        class _Conn:
            def __init__(self, c):
                self._c = c

            def execute(self, sql, *a, **k):
                if "draw_win_rank_sync_status" in str(sql) and str(sql).lstrip().upper().startswith("SELECT"):
                    outer.n += 1
                return self._c.execute(sql, *a, **k)

            def __getattr__(self, name):
                return getattr(self._c, name)

        def _connect(*a, **k):
            return _Conn(orig(*a, **k))

        db_turso.connect = _connect
        return self

    def __exit__(self, *exc):
        db_turso.connect = self._orig


class WinRankSyncMemoTests(unittest.TestCase):
    def setUp(self):
        self._iso = _db_isolation.isolated_db()
        self._iso.__enter__()
        self.addCleanup(self._iso.__exit__, None, None, None)
        mdb.init_marketing_tables()

    def test_W1_synced_round_asked_once(self):
        mdb.mark_win_rank_synced(1201, SRC)
        with _Counter() as c:
            # 카운터가 connect 를 바꿔치기하므로 새 기억 칸 — 첫 확인만 DB 를 탄다.
            self.assertTrue(mdb.is_win_rank_synced(1201, SRC))
            self.assertTrue(mdb.is_win_rank_synced(1201, SRC))
            self.assertTrue(mdb.is_win_rank_synced(1201, SRC))
        self.assertEqual(c.n, 1)

    def test_W2_unsynced_not_memoized(self):
        self.assertFalse(mdb.is_win_rank_synced(1202, SRC))
        self.assertFalse(mdb.is_win_rank_synced(1202, SRC))
        mdb.mark_win_rank_synced(1202, SRC)
        self.assertTrue(mdb.is_win_rank_synced(1202, SRC))
        self.assertFalse(mdb.is_win_rank_synced(1202, "guest_generated_combos"))

    def test_W3_prefetch_one_query(self):
        for r in (1210, 1211, 1212, 1213):
            mdb.mark_win_rank_synced(r, SRC)
        with _Counter() as c:
            mdb.prefetch_synced_win_rank_rounds(SRC)
            mdb.prefetch_synced_win_rank_rounds(SRC)  # 두 번째는 조회 없음
            for r in (1210, 1211, 1212, 1213):
                self.assertTrue(mdb.is_win_rank_synced(r, SRC))
        self.assertEqual(c.n, 1)

    def test_W4_memo_separate_per_db(self):
        mdb.mark_win_rank_synced(1220, SRC)
        self.assertTrue(mdb.is_win_rank_synced(1220, SRC))
        with _db_isolation.isolated_db():
            mdb.init_marketing_tables()
            self.assertFalse(mdb.is_win_rank_synced(1220, SRC))

    def test_W5_batch_sync_does_not_ask_per_round(self):
        import lotto_stats

        rounds = [1230, 1231, 1232, 1233, 1234]
        for r in rounds:
            mdb.mark_win_rank_synced(r, SRC)
        orig = mdb.get_draw_extraction_stats
        mdb.get_draw_extraction_stats = lambda limit=100: [{"draw_round": r} for r in rounds]
        try:
            with _Counter() as c:
                lotto_stats.sync_marketing_win_ranks_for_db_draws()
                lotto_stats.sync_marketing_win_ranks_for_db_draws()
        finally:
            mdb.get_draw_extraction_stats = orig
        self.assertEqual(c.n, 1, "회차 5개를 두 번 돌려도 동기화 확인 조회는 1회여야 한다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
