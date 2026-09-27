# -*- coding: utf-8 -*-
"""엑셀 자동 업데이트 스크립트의 "실패를 성공으로 넘기지 않는다" 불변식 검증.

2026-09-27 이번 턴에서 두 스크립트(weekly_lotto_file_update.py,
candidate_tracker_auto_update.py)를 이렇게 바꿨다:
  · 회차 조회를 죽은 동행복권 엔드포인트에서 DB(draw_results)로 교체
  · 조회 실패·회차 구멍을 **예외로 올려 exit 1** (예전엔 빈 리스트 → "이미 최신" → exit 0)

이 파일은 그 변경이 실제로 지켜지는지, 네트워크·DB 없이 스텁으로 확인한다:
  A) DB가 비었을 때 / 조회가 예외일 때  → 빈 리스트가 아니라 **예외**
  B) 회차 구멍(1244가 없는데 1245가 있음) → **예외** (조용히 뒤처진 채 넘어가지 않음)
  C) DB가 정상일 때 → 로컬 최신 다음 회차부터 정확히, 오름차순으로
  D) main()이 조회 실패 시 **0이 아닌 값**을 반환 (스케줄러가 실패로 인식)
  E) 정말 최신일 때만 0을 반환

실행: venv312\\Scripts\\python.exe scratch\\test_excel_update_robustness.py
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import candidate_tracker_auto_update as tracker  # noqa: E402
import draw_results_db  # noqa: E402
import weekly_lotto_file_update as weekly  # noqa: E402


def rows(rounds_with_nums: dict[int, list[int]]):
    """draw_results_db.get_all_draw_results()가 돌려주는 모양(최신 먼저)."""
    return [
        {"draw_round": r, "numbers": ns, "bonus": 7}
        for r, ns in sorted(rounds_with_nums.items(), reverse=True)
    ]


class FakeDb:
    """get_all_draw_results()만 바꿔치기하는 컨텍스트 매니저."""

    def __init__(self, payload=None, raises: Exception | None = None):
        self.payload, self.raises = payload, raises

    def __enter__(self):
        self.orig = draw_results_db.get_all_draw_results

        def fake():
            if self.raises:
                raise self.raises
            return self.payload

        draw_results_db.get_all_draw_results = fake
        return self

    def __exit__(self, *exc):
        draw_results_db.get_all_draw_results = self.orig
        return False


FULL = {1241: [7, 13, 16, 23, 24, 43], 1242: [2, 4, 10, 16, 31, 41], 1243: [9, 18, 24, 38, 43, 44]}


def setUpModule():
    """테스트가 실제 로그(weekly_update_log.txt 등)를 오염시키지 않게 임시 파일로 돌린다."""
    import tempfile

    tmp = Path(tempfile.gettempdir()) / "lotto_excel_update_robustness_test.log"
    for mod in (weekly, tracker):
        if hasattr(mod, "LOG_FILE"):
            mod.LOG_FILE = tmp


class FetchFailureIsNotSuccessTests(unittest.TestCase):
    """A) 조회가 안 되면 '최신'이 아니라 실패다 — 두 스크립트 모두."""

    def test_empty_db_raises(self):
        for mod in (weekly, tracker):
            with self.subTest(mod=mod.__name__), FakeDb(payload=[]):
                with self.assertRaises(RuntimeError):
                    mod.find_new_rounds(1241)

    def test_db_error_propagates(self):
        for mod in (weekly, tracker):
            with self.subTest(mod=mod.__name__), FakeDb(raises=TimeoutError("Turso 무응답")):
                with self.assertRaises(TimeoutError):
                    mod.find_new_rounds(1241)

    def test_round_gap_raises(self):
        """B) 1244가 DB에 없는데 1245가 있으면 여기서 멈춘다(구멍을 넘어가지 않는다)."""
        gap = {1243: FULL[1243], 1245: [1, 2, 3, 4, 5, 6]}
        for mod in (weekly, tracker):
            with self.subTest(mod=mod.__name__), FakeDb(payload=rows(gap)):
                with self.assertRaises(RuntimeError):
                    mod.find_new_rounds(1243)


class FetchShapeTests(unittest.TestCase):
    """C) 정상일 때의 계약: 로컬 다음 회차부터, 오름차순, DB값 그대로."""

    def test_returns_ascending_from_local_max(self):
        for mod in (weekly, tracker):
            with self.subTest(mod=mod.__name__), FakeDb(payload=rows(FULL)):
                got = mod.find_new_rounds(1241)
                self.assertEqual([r["round"] for r in got], [1242, 1243])
                self.assertEqual(got[0]["nums"], sorted(FULL[1242]))
                self.assertEqual(got[1]["nums"], sorted(FULL[1243]))
                self.assertEqual(got[0]["bonus"], 7)

    def test_already_latest_returns_empty(self):
        for mod in (weekly, tracker):
            with self.subTest(mod=mod.__name__), FakeDb(payload=rows(FULL)):
                self.assertEqual(mod.find_new_rounds(1243), [])

    def test_hard_limit_caps_work_per_run(self):
        many = {r: [1, 2, 3, 4, 5, 6] for r in range(1, 21)}
        for mod in (weekly, tracker):
            with self.subTest(mod=mod.__name__), FakeDb(payload=rows(many)):
                self.assertEqual(len(mod.find_new_rounds(0)), 10)

    def test_numbers_are_sorted_ints(self):
        weird = {1242: [41, 2, 31, 4, 10, 16]}
        for mod in (weekly, tracker):
            with self.subTest(mod=mod.__name__), FakeDb(payload=rows(weird)):
                self.assertEqual(mod.find_new_rounds(1241)[0]["nums"], [2, 4, 10, 16, 31, 41])


class ExitCodeTests(unittest.TestCase):
    """D·E) 스케줄러가 보는 종료코드 — 실패는 0이 아니어야 한다."""

    def test_weekly_main_returns_nonzero_on_fetch_failure(self):
        with FakeDb(raises=TimeoutError("Turso 무응답")):
            self.assertNotEqual(weekly.main(), 0)

    def test_tracker_main_returns_nonzero_on_fetch_failure(self):
        with FakeDb(raises=TimeoutError("Turso 무응답")):
            self.assertNotEqual(tracker.main(), 0)

    def test_mains_return_zero_when_truly_latest(self):
        """워크북이 이미 최신(DB 최신 == 파일 최신)일 때만 0 — 조회 성공 + 빈 결과."""
        with FakeDb(payload=rows({1241: [7, 13, 16, 23, 24, 43]})):
            self.assertEqual(weekly.main(), 0)
        with FakeDb(payload=rows({1241: [7, 13, 16, 23, 24, 43]})):
            self.assertEqual(tracker.main(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
