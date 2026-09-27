# -*- coding: utf-8 -*-
"""주간 백업 조건부 정리(weekly_backup_cleanup.py)의 불변식 검증.

되돌릴 수 없는 삭제를 다루므로 "지우지 않아야 할 때 지우지 않는 것"을 먼저 고정한다.
실제 백업 폴더는 건드리지 않는다 — 임시 폴더로 BACKUP_DIRS를 바꿔치기한다.

불변식:
  1) 기본(미리보기)에서는 게이트가 다 통과해도 삭제하지 않는다
  2) 게이트가 하나라도 실패하면 삭제하지 않고 백업을 유지하며, 그 사실을 백업 폴더 안에 남긴다
     (비일요일 / 엑셀 결과코드≠0 / Actions 결론≠success / 오늘 실행 아님)
  3) 보류 메모(_SKIPPED_*)가 있으면 게이트가 다 통과해도 삭제하지 않는다 (사람이 지워야 재개)
  4) 삭제 대상은 화이트리스트 두 경로뿐 (그 외 경로는 절대 지우지 않는다)
  5) 삭제 근거 로그가 rmtree보다 **먼저** 남는다
  6) 대상이 없으면 조용히 exit 0 (멱등 — 두 번 돌려도 안전)
  7) Actions 게이트는 '오늘(KST)' 실행만 성공으로 인정한다 (어제 성공을 오늘로 오인하지 않음)

실행: venv312\\Scripts\\python.exe scratch\\test_backup_cleanup.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import weekly_backup_cleanup as cleanup  # noqa: E402

REAL_RMTREE = shutil.rmtree
REAL_BACKUP_DIRS = cleanup.BACKUP_DIRS
REAL_TRACKER_DIR = cleanup.TRACKER_DIR
REAL_EXCEL_GATE = cleanup.excel_gate
REAL_ACTIONS_GATE = cleanup.actions_gate
SUNDAY = datetime(2026, 10, 4, 16, 10, tzinfo=cleanup.KST)
MONDAY = datetime(2026, 10, 5, 16, 10, tzinfo=cleanup.KST)


class _FakeResp:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class CleanupBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lotto_cleanup_test_"))
        self.tracker = self.tmp / "★조합생성_후보숫자_추적표"
        self.tracker.mkdir()
        self.b1 = self.tracker / "_backup_20260927"
        self.b2 = self.tracker / "_backup_20260927_formulas"
        for d in (self.b1, self.b2):
            d.mkdir()
            (d / "원본.xlsx").write_text("x")
        self.rmtree_calls: list[Path] = []
        self.logs: list[str] = []
        self._patch(cleanup, "TRACKER_DIR", self.tracker)
        self._patch(cleanup, "BACKUP_DIRS", (self.b1, self.b2))
        self._patch(cleanup, "LOG_FILE", self.tmp / "backup_cleanup_log.txt")
        self._patch(cleanup, "pool_evidence", lambda: "(테스트: 풀 근거 생략)")
        self._patch(cleanup, "log", lambda m: self.logs.append(m))
        self._patch(cleanup.shutil, "rmtree", self._fake_rmtree)
        self._patch(cleanup, "now_kst", lambda: SUNDAY)
        self._patch(cleanup, "excel_gate", lambda today: (True, "테스트 엑셀 OK"))
        self._patch(cleanup, "actions_gate", lambda today: (True, "테스트 Actions OK"))

    def tearDown(self):
        REAL_RMTREE(self.tmp, ignore_errors=True)

    def _patch(self, obj, name, value):
        original = getattr(obj, name)
        setattr(obj, name, value)
        self.addCleanup(setattr, obj, name, original)

    def _fake_rmtree(self, path, *a, **k):
        p = Path(path)
        self.rmtree_calls.append(p)
        REAL_RMTREE(p, ignore_errors=True)


class PreviewAndDeleteTests(CleanupBase):
    """1·4·5) 미리보기 무삭제 / 화이트리스트 / 로그 순서."""

    def test_preview_never_deletes(self):
        rc = cleanup.main([])
        self.assertEqual(rc, 0)
        self.assertEqual(self.rmtree_calls, [], "미리보기인데 삭제했다")
        self.assertTrue(self.b1.exists() and self.b2.exists())
        self.assertTrue(any("[미리보기]" in m for m in self.logs))

    def test_apply_deletes_only_whitelisted_paths(self):
        rc = cleanup.main(["--apply"])
        self.assertEqual(rc, 0)
        self.assertEqual(sorted(self.rmtree_calls), sorted([self.b1, self.b2]))
        self.assertFalse(self.b1.exists() or self.b2.exists())

    def test_evidence_logged_before_rmtree(self):
        order: list[str] = []
        self._patch(cleanup, "log", lambda m: order.append("log:" + m))
        self._patch(cleanup.shutil, "rmtree", lambda p, *a, **k: order.append("rmtree") or REAL_RMTREE(p, ignore_errors=True))
        cleanup.main(["--apply"])
        self.assertIn("rmtree", order, "삭제가 일어나지 않음")
        first_rmtree = order.index("rmtree")
        self.assertTrue(any(o.startswith("log:") and "근거" in o for o in order[:first_rmtree]),
                        "삭제 전에 근거 로그가 없다(나중에 '왜 없어졌지' 추적 불가)")

    def test_safe_to_delete_guard(self):
        self.assertTrue(cleanup.safe_to_delete(self.b1))
        self.assertFalse(cleanup.safe_to_delete(self.tracker / "다른폴더"))
        self.assertFalse(cleanup.safe_to_delete(self.tmp / "_backup_다른곳"))

    def test_real_constants_are_the_two_expected_folders(self):
        # 이 테스트만은 실제 경로를 봐야 하므로 setUp이 바꿔놓은 TRACKER_DIR를 원래 값으로 돌린다.
        self._patch(cleanup, "TRACKER_DIR", REAL_TRACKER_DIR)
        names = {p.name for p in REAL_BACKUP_DIRS}
        self.assertEqual(names, {"_backup_20260927", "_backup_20260927_formulas"})
        for p in REAL_BACKUP_DIRS:
            self.assertEqual(p.parent, REAL_TRACKER_DIR)
            self.assertTrue(cleanup.safe_to_delete(p))


class GateFailureTests(CleanupBase):
    """2·3) 게이트 실패·보류 메모가 있으면 절대 지우지 않는다."""

    def _assert_kept(self, expect_marker: bool, label: str):
        self.assertEqual(self.rmtree_calls, [], f"{label}: 삭제해버렸다")
        self.assertTrue(self.b1.exists() and self.b2.exists(), f"{label}: 백업이 사라졌다")
        if expect_marker:
            for d in (self.b1, self.b2):
                self.assertTrue(list(d.glob("_SKIPPED_*")), f"{label}: 보류 메모가 없다({d.name})")

    def test_preview_changes_nothing_no_marker_no_delete(self):
        """미리보기는 읽기 전용이어야 한다 — 게이트가 실패해도 메모를 남기지 않는다.

        (메모를 남기면 그게 G4에 걸려 다음 주 정상 완료 때의 자동 삭제를 막고, 진단용
         드라이런 한 번이 실제 백업 폴더를 바꿔버린다 — 실제로 그렇게 만들어졌다가 고쳤다.)"""
        self._patch(cleanup, "excel_gate", lambda today: (False, "엑셀 실패"))
        before = sorted(p.name for p in self.b1.iterdir())
        cleanup.main([])
        self.assertEqual(self.rmtree_calls, [])
        self.assertFalse(list(self.b1.glob("_SKIPPED_*")), "미리보기가 보류 메모를 남겼다")
        self.assertFalse(list(self.b2.glob("_SKIPPED_*")), "미리보기가 보류 메모를 남겼다")
        self.assertEqual(sorted(p.name for p in self.b1.iterdir()), before)

    def test_not_sunday_keeps_backups(self):
        self._patch(cleanup, "now_kst", lambda: MONDAY)
        cleanup.main(["--apply"])
        self._assert_kept(expect_marker=False, label="비일요일")

    def test_excel_failure_keeps_backups_and_marks(self):
        self._patch(cleanup, "excel_gate", lambda today: (False, "엑셀 결과코드 0x00000001"))
        cleanup.main(["--apply"])
        self._assert_kept(expect_marker=True, label="엑셀 실패")

    def test_actions_failure_keeps_backups_and_marks(self):
        self._patch(cleanup, "actions_gate", lambda today: (False, "결론=failure"))
        cleanup.main(["--apply"])
        self._assert_kept(expect_marker=True, label="Actions 실패")

    def test_marker_blocks_deletion_even_when_gates_pass(self):
        (self.b1 / "_SKIPPED_2026-10-04.md").write_text("사람 확인 필요", encoding="utf-8")
        cleanup.main(["--apply"])
        # 이미 메모가 있으니 삭제하지 않고, 그 메모를 지우지도 않는다(새 메모를 더 만들지도 않음).
        self.assertEqual(self.rmtree_calls, [], "보류 메모가 있는데 삭제했다")
        self.assertTrue((self.b1 / "_SKIPPED_2026-10-04.md").exists())
        self.assertTrue(self.b1.exists() and self.b2.exists())

    def test_marker_from_failed_week_survives_and_blocks_next_week(self):
        """실패한 주에 남긴 메모가 다음 주(게이트 통과)에도 자동 삭제를 막는다."""
        self._patch(cleanup, "excel_gate", lambda today: (False, "엑셀 실패"))
        cleanup.main(["--apply"])                       # 10/4 실패 → 메모 생성
        self.assertTrue(list(self.b1.glob("_SKIPPED_*")))
        self.logs.clear()
        self._patch(cleanup, "excel_gate", lambda today: (True, "엑셀 OK"))
        self._patch(cleanup, "actions_gate", lambda today: (True, "Actions OK"))
        cleanup.main(["--apply"])                       # 10/11 성공해도
        self._assert_kept(expect_marker=True, label="다음 주(메모 잔존)")


class GateLogicTests(CleanupBase):
    """7) 게이트 자체의 날짜·결론 판정(스텝으로 네트워크 없이).

    주의: setUp이 excel_gate/actions_gate를 스텁으로 바꿔놓으므로, 게이트 자체를 검증하는
    이 클래스는 그 둘을 **원래 함수로 되돌린 뒤** 내부 재료(task_last_run/urlopen)를 스텁한다.
    (그렇게 안 하면 스텁을 검증하게 돼 전부 통과해버려 테스트가 무의미해진다 — 실제로 그렇게
    10개가 거짓 통과했다.)"""

    def setUp(self):
        super().setUp()
        self._patch(cleanup, "excel_gate", REAL_EXCEL_GATE)
        self._patch(cleanup, "actions_gate", REAL_ACTIONS_GATE)

    def test_excel_gate_requires_today_and_zero(self):
        cases = [
            (("2026-10-04T13:10:00", 0), True),
            (("2026-10-04T13:10:00", 1), False),
            (("2026-09-27T13:10:00", 0), False),      # 어제 성공은 오늘로 인정하지 않는다
            (("", 0), False),                          # 실행 기록 없음
        ]
        for (run, result), expected in cases:
            with self.subTest(run=run, result=result):
                self._patch(cleanup, "task_last_run", lambda name, r=run, c=result: (r, c))
                ok, _ = cleanup.excel_gate("2026-10-04")
                self.assertEqual(ok, expected)

    def test_actions_gate_requires_today_kst_and_success(self):
        def payload(created_utc: str, conclusion: str):
            return {"workflow_runs": [{"created_at": created_utc, "conclusion": conclusion, "id": 1}]}

        cases = [
            (payload("2026-10-04T04:35:00Z", "success"), True),    # 13:35 KST 오늘
            (payload("2026-10-04T04:35:00Z", "failure"), False),
            (payload("2026-10-03T04:35:00Z", "success"), False),  # 어제 성공
            (payload("2026-10-04T15:00:00Z", "success"), False),  # UTC 15:00 = 10/5 00:00 KST
            ({"workflow_runs": []}, False),
        ]
        for data, expected in cases:
            with self.subTest(data=data):
                self._patch(cleanup.urllib.request, "urlopen", lambda req, timeout=0, d=data: _FakeResp(d))
                ok, _ = cleanup.actions_gate("2026-10-04")
                self.assertEqual(ok, expected)

    def test_actions_gate_fails_closed_on_network_error(self):
        def boom(*a, **k):
            raise TimeoutError("네트워크 없음")

        self._patch(cleanup.urllib.request, "urlopen", boom)
        ok, detail = cleanup.actions_gate("2026-10-04")
        self.assertFalse(ok, "조회 실패를 성공으로 처리하면 안 된다")
        self.assertIn("실패", detail)


class IdempotenceTests(CleanupBase):
    """6) 대상이 없으면 조용히 exit 0, 두 번 돌려도 안전."""

    def test_no_targets_is_quiet_success(self):
        REAL_RMTREE(self.b1, ignore_errors=True)
        REAL_RMTREE(self.b2, ignore_errors=True)
        self.assertEqual(cleanup.main(["--apply"]), 0)
        self.assertEqual(self.rmtree_calls, [])
        self.assertTrue(any("대상 없음" in m for m in self.logs))

    def test_second_run_after_delete_is_safe(self):
        self.assertEqual(cleanup.main(["--apply"]), 0)
        first = list(self.rmtree_calls)
        self.assertEqual(len(first), 2)
        self.assertEqual(cleanup.main(["--apply"]), 0)
        self.assertEqual(self.rmtree_calls, first, "이미 지운 대상을 또 지우려 했다")


if __name__ == "__main__":
    program = unittest.main(verbosity=2, exit=False)
    os._exit(0 if program.result.wasSuccessful() else 1)
