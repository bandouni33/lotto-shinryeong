# -*- coding: utf-8 -*-
"""GitHub Actions가 실행하는 진입점(.github/workflows/weekly_combo_gen.yml →
combo_gen_worker.py)의 계약 검증.

워크플로가 기대하는 것:
  · 이미 그 회차 풀이 있으면 **계산을 시작하지 않고** 상태 'skipped' + exit 0
    (앱 트리거와 겹쳐도 같은 회차를 두 번 만들지 않는 1차 방어)
  · 정상 생성이면 5% 추출 후 적재하고 상태 'done' + exit 0
  · DB/네트워크 실패면 상태 'error' + **exit 1** (그래야 Actions가 실패로 표시하고
    사용자가 알 수 있다 — 조용한 성공이 되면 안 된다)

DB를 쓰지 않는다: 워커가 쓰는 DB 함수들을 전부 스텁으로 바꿔치고 오케스트레이션만
그대로 돌린다(실제 삽입/로컬 파일 생성은 하지 않는다).

실행: venv312\\Scripts\\python.exe scratch\\test_actions_entrypoint.py
"""

from __future__ import annotations

import json
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import app_settings  # noqa: E402
import combo_filter_v2  # noqa: E402
import combo_gen_worker as worker  # noqa: E402
import draw_results_db  # noqa: E402
import marketing_db  # noqa: E402
import wallet_db  # noqa: E402

TOP5 = (34, 14, 45, 33, 40)


class _Patcher:
    def __init__(self, pairs):
        self.pairs = pairs

    def __enter__(self):
        self.orig = [(m, a, getattr(m, a)) for m, a, _ in self.pairs]
        for m, a, v in self.pairs:
            setattr(m, a, v)
        return self

    def __exit__(self, *exc):
        for m, a, v in self.orig:
            setattr(m, a, v)
        return False


def _tiered_combos(per_tier: int = 40) -> list[tuple[int, ...]]:
    """tier i 전용 조합 — top5[i]만 포함(나머지는 top5 밖 숫자) → _rank_tier가 i를 돌려준다."""
    rnd = random.Random(7)
    others = [n for n in range(1, 46) if n not in TOP5]
    out = []
    for i, top in enumerate(TOP5):
        seen = set()
        while len(seen) < per_tier:
            seen.add(tuple(sorted((top,) + tuple(rnd.sample(others, 5)))))
        out.extend(sorted(seen))
    return out


STATS = {
    "anchor_round": 1243,
    "target_round": 1244,
    "static_gap_count": 2594759,
    "stage2_count": 2410385,
    "final_count": 200,
    "top3_numbers": TOP5[:3],
    "top5_numbers": TOP5,
}


class WorkerEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.status = Path(tempfile.gettempdir()) / "lotto_worker_status_test.json"
        self.status.unlink(missing_ok=True)
        self._orig_status = worker.STATUS_FILE
        worker.STATUS_FILE = str(self.status)

    def tearDown(self):
        worker.STATUS_FILE = self._orig_status
        self.status.unlink(missing_ok=True)

    def _read_status(self) -> dict:
        self.assertTrue(self.status.exists(), "상태 파일이 기록되지 않았다(Actions 로그로 원인 파악 불가)")
        return json.loads(self.status.read_text(encoding="utf-8"))

    def _base_patches(self, count):
        return [
            (draw_results_db, "init_draw_results_table", lambda: None),
            (app_settings, "init_settings_table", lambda: None),
            (app_settings, "set_setting", lambda *a, **k: None),
            (draw_results_db, "get_all_draw_results",
             lambda: [{"draw_round": 1243, "numbers": [9, 18, 24, 38, 43, 44], "bonus": 35}]),
            (combo_filter_v2, "peek_target_round", lambda history: 1244),
            (marketing_db, "get_combination_count_by_draw", lambda r: count),
        ]

    def test_existing_pool_skips_without_computing(self):
        def boom(*a, **k):
            raise AssertionError("이미 있는 회차인데 무거운 계산을 시작했다(중복 삽입 위험)")

        with _Patcher(self._base_patches(count=52187) + [
            (combo_filter_v2, "generate_next_round_combos", boom),
        ]):
            self.assertEqual(worker.main(), 0, "이미 있으면 exit 0이어야 한다")
        st = self._read_status()
        self.assertEqual(st["state"], "skipped")
        self.assertEqual(st["target_round"], 1244)

    def test_full_path_inserts_balanced_sample_and_reports_done(self):
        combos = _tiered_combos(40)          # 200개, 5그룹 각 40개
        inserted = {}

        def fake_insert(round_no, sample, **kw):
            inserted.update(round_no=round_no, count=len(sample), top5=kw.get("top5_numbers"))
            return len(sample)

        with _Patcher(self._base_patches(count=0) + [
            (combo_filter_v2, "generate_next_round_combos", lambda h: (1244, combos, STATS)),
            (marketing_db, "bulk_insert_lotto_combinations", fake_insert),
            (marketing_db, "record_draw_pattern_count", lambda *a: None),
            (marketing_db, "record_draw_generation_stats", lambda *a: None),
            (marketing_db, "cleanup_old_lotto_combinations", lambda keep_rounds=2: 0),
            (marketing_db, "cleanup_old_guest_generated_combos", lambda keep_rounds=2: 0),
            (marketing_db, "cleanup_old_guest_auto_orders", lambda keep_rounds=2: 0),
            (wallet_db, "cleanup_old_auto_orders", lambda keep_rounds=2: 0),
            (combo_filter_v2, "compute_reference_stats", lambda h, r: None),
            (worker, "save_local_verification_copy", lambda r, s: "(테스트: 생략)"),
            (worker, "save_full_stage4_pool", lambda r, c: "(테스트: 생략)"),
            (worker, "cleanup_old_full_stage4_pools", lambda r: []),
        ]):
            self.assertEqual(worker.main(), 0)

        st = self._read_status()
        self.assertEqual(st["state"], "done")
        self.assertEqual(st["target_round"], 1244)
        # 5% 추출 = floor(200*0.05) = 10개, 1~5위그룹 각 2개(1:1:1:1:1)
        self.assertEqual(inserted["count"], 10)
        self.assertEqual(inserted["round_no"], 1244)
        self.assertEqual(tuple(inserted["top5"]), TOP5)
        self.assertEqual(st["inserted"], 10)
        self.assertEqual(st["sample_size"], 10)

    def test_db_failure_reports_error_and_nonzero_exit(self):
        def explode():
            raise TimeoutError("Turso 무응답")

        with _Patcher(self._base_patches(count=0) + [
            (draw_results_db, "get_all_draw_results", explode),
        ]):
            self.assertEqual(worker.main(), 1, "실패는 exit 1이어야 Actions가 실패로 표시한다")
        self.assertEqual(self._read_status()["state"], "error")

    def test_worker_never_touches_payments(self):
        """워커는 결제/지급 경로를 건드리지 않는다(구글플레이 승인은 서버 전담 원칙).

        이 진입점이 호출하는 모듈 목록을 실제로 감시해 확인한다 — 무거운 계산은
        스텁으로 대체하고, 결제 모듈이 호출되면 즉시 실패시킨다.
        """
        import google_play_pg
        import toss_pg

        called = []

        def spy(name):
            def _inner(*a, **k):
                called.append(name)
                raise AssertionError(f"{name}이 호출됐다 — 조합 생성 경로가 결제에 손대면 안 된다")
            return _inner

        with _Patcher(self._base_patches(count=52187) + [
            (combo_filter_v2, "generate_next_round_combos", spy("generate_next_round_combos")),
            (google_play_pg, "handle_google_play_purchase_return",
             spy("google_play_pg.handle_google_play_purchase_return")),
            (google_play_pg, "_verify_and_credit_one_time", spy("google_play_pg._verify_and_credit_one_time")),
            (toss_pg, "handle_toss_payment_return", spy("toss_pg.handle_toss_payment_return")),
            (toss_pg, "_confirm_with_toss", spy("toss_pg._confirm_with_toss")),
        ]):
            self.assertEqual(worker.main(), 0)
        self.assertEqual(called, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
