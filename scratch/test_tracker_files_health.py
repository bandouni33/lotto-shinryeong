# -*- coding: utf-8 -*-
"""추적표 워크북 5개의 '서식·수식 건강' 계약 + 샘플/200회검증용 자동 점검 편입 검증.

대상(★조합생성_후보숫자_추적표 폴더):
  · 컬럼식 구조 2개 — 조합생성_후보숫자_추적표_샘플.xlsx, ..._샘플_200회검증용.xlsx
  · 3차필터 구조 3개 — 전체표본/최근500표본_윈도우비교.xlsx, ★후보숫자_추적표_표본vs최근50회.xlsx

계약(모든 유효 입력에 대해 성립해야 함):
  A) 오류값 0 — 5개 파일 전부에서 엑셀 오류값(#REF!·#DIV/0!·#VALUE!·#N/A …)이 하나도 없다.
     생산 스크립트의 weekly_lotto_file_update.scan_errors()를 그대로 재사용한다.
  B) 컬럼식 2개 파일의 서식 불변식(scratch/fix_filter_sheet_formulas.py가 세운 규칙):
      · '적중' 머리글을 가진 시트의 모든 회차행에서, J열이 SUM 수식이면 **자기 행**을 가리킨다
        (=SUM(K{r}:M{r})). 다른 회차의 상/중/하 합계를 적중으로 보여주면 실패.
      · 1행에 있는 합계 수식 범위 = 그 시트의 실제 회차행 범위(머리글 아래 A열이 정수 ≥1000인 행).
      · 회차행 번호는 연속(구멍 없음)이다.
     검사한 J열 SUM 셀이 0개면(검사가 헛돌면) 실패로 본다.
  C) 자동화 편입: weekly_lotto_file_update.FILE_PATHS가 4개 파일(샘플·200회검증용 포함)을
     정확한 경로로 가리키고, **신규 회차가 없는 실행에서도** 오류값 스캔이 4개 파일 전부에 대해
     실제로 돌며 exit code 0으로 끝난다(예전엔 그 경로에서 continue해 점검이 아예 안 돌았다).
  D) 컬럼식 2개 파일은 ADVANCE_3CHA_FILES에 넣지 않는다(3차필터 예측행 전진 대상이 아님 — 문서화된 결정).
  E) 이 테스트는 워크북을 바꾸지 않는다(해시 불변).

실행: venv312\\Scripts\\python.exe scratch\\test_tracker_files_health.py
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import weekly_lotto_file_update as weekly  # noqa: E402

TRACKER = ROOT / "★조합생성_후보숫자_추적표"
FILES = {
    "샘플": TRACKER / "조합생성_후보숫자_추적표_샘플.xlsx",
    "200회검증용": TRACKER / "조합생성_후보숫자_추적표_샘플_200회검증용.xlsx",
    "전체표본": TRACKER / "조합생성_후보숫자_추적표_전체표본_윈도우비교.xlsx",
    "최근500표본": TRACKER / "조합생성_후보숫자_추적표_최근500표본_윈도우비교.xlsx",
    "표본vs최근50회": TRACKER / "★후보숫자_추적표_표본vs최근50회.xlsx",
}
COLUMN_FILES = ("샘플", "200회검증용")
TMP = Path(tempfile.mkdtemp(prefix="lotto_health_test_"))
_HASH = {label: hashlib.sha256(p.read_bytes()).hexdigest() for label, p in FILES.items()
         if p.exists()}


def setUpModule() -> None:
    weekly.LOG_FILE = TMP / "weekly_health_test.log"


def _hash_all() -> dict[str, str]:
    return {label: hashlib.sha256(p.read_bytes()).hexdigest()
            for label, p in FILES.items() if p.exists()}


class ErrorValueTests(unittest.TestCase):
    """A) 오류값 0 — 생산 스크립트의 스캐너를 그대로 쓴다."""

    def test_no_excel_error_values_in_any_tracker_file(self):
        for label, path in FILES.items():
            with self.subTest(file=label):
                self.assertTrue(path.exists(), f"{label}: 파일이 없다 → {path}")
                self.assertEqual(weekly.scan_errors(path), [])


class ColumnSheetFormatTests(unittest.TestCase):
    """B) 컬럼식 파일의 적중열·합계범위·회차행 불변식."""

    def _sheets(self, path: Path):
        """(시트이름, 머리글행, 회차행목록, SUM_J셀수, 1행 합계 수식들) — 읽기 전용."""
        out = []
        wb = openpyxl.load_workbook(path, data_only=False, read_only=True)
        try:
            for sn in wb.sheetnames:
                ws = wb[sn]
                hdr = None
                rows: list[int] = []
                j_sum: list[str] = []
                row1_sums: list[tuple[int, str]] = []
                for row in ws.iter_rows():
                    for c in row:
                        v = c.value
                        # read_only 모드의 빈 자리는 EmptyCell(column 속성 없음)이라 먼저 걸러낸다.
                        if v is None:
                            continue
                        t = v.text if hasattr(v, "text") else v
                        # A열 숫자(회차번호)를 먼저 잡는다 — 아래 문자열 필터보다 앞에 두어야 한다.
                        if c.column == 1 and isinstance(t, int) and t >= 1000:
                            rows.append(c.row)
                        if not isinstance(t, str):
                            continue
                        up = t.upper().replace(" ", "")
                        if c.column == 10 and t == "적중" and 1 <= c.row <= 10 and hdr is None:
                            hdr = c.row
                        if c.column == 10 and up.startswith("=SUM(") and c.row > 1:
                            j_sum.append(f"J{c.row}={t}")
                        if c.row == 1 and up.startswith("=SUM(") and 11 <= c.column <= 16:
                            row1_sums.append((c.column, t))
                if hdr is not None:
                    out.append((sn, hdr, sorted(rows), j_sum, row1_sums))
        finally:
            wb.close()
        return out

    def test_every_hit_column_sum_points_to_its_own_row(self):
        for label in COLUMN_FILES:
            path = FILES[label]
            sheets = self._sheets(path)
            self.assertTrue(sheets, f"{label}: '적중' 머리글을 가진 시트를 못 찾음")
            checked = 0
            for sn, hdr, rows, j_sum, _ in sheets:
                for entry in j_sum:
                    coord, text = entry.split("=", 1)
                    n = int(coord[1:])
                    with self.subTest(file=label, sheet=sn, cell=coord):
                        self.assertEqual(text.upper().replace(" ", ""), f"=SUM(K{n}:M{n})".upper(),
                                         f"{sn}!{coord}가 자기 행이 아닌 범위를 가리킴")
                    checked += 1
            with self.subTest(file=label):
                self.assertGreaterEqual(checked, 100,
                                        f"{label}: 검사한 J열 SUM 셀이 {checked}개뿐이다(검사가 헛돎)")

    def test_row1_total_range_matches_data_rows(self):
        for label in COLUMN_FILES:
            path = FILES[label]
            for sn, hdr, rows, _, row1_sums in self._sheets(path):
                if not rows:
                    continue
                lo, hi = min(rows), max(rows)
                for col, text in row1_sums:
                    letter = openpyxl.utils.get_column_letter(col)
                    with self.subTest(file=label, sheet=sn, cell=f"{letter}1"):
                        self.assertEqual(text.upper().replace(" ", ""),
                                         f"=SUM({letter}{lo}:{letter}{hi})".upper(),
                                         f"{sn}!{letter}1 합계 범위가 회차행 {lo}~{hi}와 다름")

    def test_round_rows_are_contiguous_integers(self):
        for label in COLUMN_FILES:
            path = FILES[label]
            for sn, hdr, rows, _, _ in self._sheets(path):
                with self.subTest(file=label, sheet=sn):
                    self.assertTrue(rows, f"{sn}: 회차행(A열 정수 ≥1000)이 없다")
                    self.assertEqual(max(rows) - min(rows) + 1, len(rows),
                                     f"{sn}: 회차행 사이에 구멍이 있다 → {rows[:5]}…{rows[-5:]}")


class AutomationCoverageTests(unittest.TestCase):
    """C·D) 이 파일들이 자동 점검·자동 업데이트에 실제로 걸려 있는가."""

    def test_file_paths_point_at_the_four_files(self):
        for label in ("샘플", "200회검증용", "전체표본", "최근500표본"):
            with self.subTest(file=label):
                self.assertIn(label, weekly.FILE_PATHS)
                self.assertEqual(weekly.FILE_PATHS[label], FILES[label])

    def test_up_to_date_run_still_scans_every_file(self):
        """신규 회차가 없어도(=샘플이 항상 가는 경로) 4개 파일 전부 오류값 스캔이 돈다."""
        before = _hash_all()
        scanned: list[Path] = []
        orig_scan, orig_find = weekly.scan_errors, weekly.find_new_rounds
        weekly.scan_errors = lambda p: (scanned.append(Path(p)), orig_scan(p))[1]
        weekly.find_new_rounds = lambda local_max, hard_limit=10: []
        try:
            rc = weekly.main()
        finally:
            weekly.scan_errors, weekly.find_new_rounds = orig_scan, orig_find

        self.assertEqual(rc, 0, f"신규 회차 없는 실행이 실패로 끝났다(exit {rc})")
        for label, path in weekly.FILE_PATHS.items():
            with self.subTest(file=label):
                self.assertIn(path, scanned, f"{label}: 오류값 스캔이 돌지 않았다")
        self.assertEqual(before, _hash_all(), "이 실행이 워크북을 바꿨다(읽기 전용이어야 함)")

    def test_column_files_are_not_advance_targets(self):
        for label in COLUMN_FILES:
            with self.subTest(file=label):
                self.assertNotIn(label, weekly.ADVANCE_3CHA_FILES,
                                 "'3차필터 예측행 전진' 대상이 아니다 — 넣으면 진행 로직이 없는 파일을 건드린다")

    def test_scan_errors_reports_real_error_cells(self):
        """스캐너 자체가 살아 있는지 — 일부러 오류값을 넣은 임시 파일에서 잡아야 한다."""
        p = TMP / "err_probe.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws["A1"] = 1
        ws["A2"] = "#REF!"
        ws["A3"] = "#DIV/0!"
        ws["A4"] = "정상"
        wb.save(p)
        wb.close()
        found = weekly.scan_errors(p)
        self.assertEqual(len(found), 2, f"오류값 2개를 못 잡음 → {found}")
        self.assertIn("#REF!", " ".join(c for _, _, c in found))


class SourceUntouchedTests(unittest.TestCase):
    """E) 이 테스트는 워크북을 바꾸지 않는다."""

    def test_hashes_unchanged(self):
        self.assertEqual(_HASH, _hash_all())


if __name__ == "__main__":
    unittest.main(verbosity=2)
