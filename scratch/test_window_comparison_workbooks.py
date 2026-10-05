# -*- coding: utf-8 -*-
"""12종 비교검토표(2파일 × 6시트) 구조·수식·자동화 계약 검증.

대상(★조합생성_후보숫자_추적표 폴더 — 폴더 안에서 아래 특징으로 찾은 두 파일):
  · 조합생성_후보숫자_추적표_전체표본_윈도우비교.xlsx   — 3차필터 시트 2행 K2='기준빈도(전체)'
  · 조합생성_후보숫자_추적표_최근500표본_윈도우비교.xlsx — 3차필터 시트 2행 K2='기준빈도(최근500회)'
각 파일의 3차필터(50/100/150/200/250/300회_후보) 6시트 = 12종(기준모집단 2 × 창 6).
앱의 고정 파라미터(역대기준 + 최근100회, combo_filter_v2.RECENT_WINDOW=100)를 대체할
조합을 고르기 위한 비교검토표이며, 이 테스트는 **구조·수식 정합성과 자동화만** 본다
(어느 창이 더 나은지는 판단하지 않는다 — 그건 사용자 몫).

계약(모든 유효 입력에 대해 성립해야 하는 것):
  A) 창 6종이 시트마다 정확히 따로 읽힌다 — 시트 이름·K3 라벨·3행 수식의 창 상수
     (MAX(...)-K, K=창-1)가 서로 일치하고, 6시트의 창 값은 서로 다르며, 기준모집단
     수식(2행)은 한 파일 안 6시트가 모두 같다.
  B) 값: 2행=기준모집단 빈도, 3행=최근N회 빈도, 4행=RANK+COUNTIFS 오차, 7행=(-오차,번호) 정렬.
     다른 창의 빈도와 같아질 수 없다(각 행 합계가 6N으로 서로 다르므로).
  C) 과거행 정합: 각 행의 L:BD는 '그 회차 직전 이력만으로 만든 예측'과 같다 —
     기존 정합화 로직(candidate_tracker_auto_update._prediction_for)을 그대로 재사용한다.
     (행↔회차가 통째로 밀린 블록은 이 검사로만 드러난다. 외부 검증기는 행 안의
      자기정합만 보므로 그것만으로는 부족하다.)
  D) 수식 패턴: 7행 L:BD 45칸이 모두
     =INDEX(L$1:BD$1,MATCH(LARGE((L$4:BD$4*1000-L$1:BD$1),k),(L$4:BD$4*1000-L$1:BD$1),0))
     이고, k가 1~45를 한 번씩 돈다.
  E) 자동화 편입: weekly_lotto_file_update.FILE_PATHS가 이 두 파일을 가리키고, 둘 다
     ADVANCE_3CHA_FILES에 있어 다음 회차 예측행까지 전진한다(6시트 전부).
  F) 실제 전진(임시 복사본): process_one_round_for_file로 다음 회차를 넣으면 12시트가
     '7행=새 대기행(배열수식 45칸)·8행=방금 회차 동결'로 바뀌고 행수·라벨 사슬·적중수·
     순열 불변식이 유지되며, 실물 파일은 한 바이트도 바뀌지 않는다.
  G) 외부 검증기(scratch/verify_workbook_ranking.py) 별도 프로세스 exit code 0.

엑셀 COM은 쓰지 않는다 — 테스트가 이 PC의 엑셀 상태에 매달리지 않게 하려고 전진 시뮬에서만
재계산 경로를 파이썬 폴백으로 바꾼다(그 폴백이 엑셀이 계산한 값과 일치함은
scratch/test_python_forecast_fallback.py가 12시트 전부에 대해 이미 검증했다).
수식의 캐시값(2·3행)은 엑셀이 재계산하므로 시뮬에서는 구조만 단언한다.

실행: venv312\\Scripts\\python.exe scratch\\test_window_comparison_workbooks.py
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.formula import ArrayFormula

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scratch"))
os.chdir(ROOT)

import candidate_tracker_auto_update as tracker  # noqa: E402
import verify_workbook_ranking as vwr  # noqa: E402  (기존 외부 검증기 로직 재사용)
import weekly_lotto_file_update as weekly  # noqa: E402

TRACKER = ROOT / "★조합생성_후보숫자_추적표"
WINDOWS = (50, 100, 150, 200, 250, 300)
COLS = [get_column_letter(c) for c in range(12, 57)]          # L..BD (45칸)
NUMS = list(range(1, 46))
TMP = Path(tempfile.mkdtemp(prefix="lotto_window_test_"))

# 파일 라벨 → (경로, 2행 기준모집단 창(None=전체), 기대 K2 라벨)
FILES = {
    "전체표본": (TRACKER / "조합생성_후보숫자_추적표_전체표본_윈도우비교.xlsx", None, "기준빈도(전체)"),
    "최근500표본": (TRACKER / "조합생성_후보숫자_추적표_최근500표본_윈도우비교.xlsx", 500, "기준빈도(최근500회)"),
    "최근300표본": (TRACKER / "조합생성_후보숫자_추적표_최근300표본_윈도우비교.xlsx", 300, "기준빈도(최근300회)"),
}
_SRC_HASH = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p, _, _ in FILES.values()}

# D) 7행 순번세우기 배열수식 원문 패턴 (k = 1..45)
_ARRAY_PAT = re.compile(
    r"^=INDEX\(L\$1:BD\$1,MATCH\(LARGE\(\(L\$4:BD\$4\*1000-L\$1:BD\$1\),(\d+)\),"
    r"\(L\$4:BD\$4\*1000-L\$1:BD\$1\),0\)\)$")


def expected_window_formula(col: str, window: int) -> str:
    """3행(최근N회 빈도) / 최근500회 기준모집단(2행)이 쓰는 원문 그대로의 수식."""
    inner = "+".join(f"(전체당첨내역!${c}$2:${c}$1500={col}$1)" for c in "BCDEFG")
    return (f"=SUMPRODUCT((전체당첨내역!$A$2:$A$1500>="
            f"(MAX(전체당첨내역!$A$2:$A$1500)-{window - 1}))*({inner}))")


def expected_gap_formula(col: str) -> str:
    """4행 오차 = RANK+COUNTIFS 정의(동점은 작은 번호 우선) 원문 그대로의 수식."""
    r1, r2, r3 = "L$1:BD$1", "L$2:BD$2", "L$3:BD$3"
    return (f"=(RANK({col}$3,{r3},0)+COUNTIFS({r3},{col}$3,{r1},\"<\"&{col}$1))"
            f"-(RANK({col}$2,{r2},0)+COUNTIFS({r2},{col}$2,{r1},\"<\"&{col}$1))")


def expected_row2_formula(col: str, basis: int | None) -> str:
    """2행 = 기준모집단 빈도. 전체면 통째 COUNTIF, 최근500회면 3행과 같은 SUMPRODUCT."""
    if basis is None:
        return f"=COUNTIF(전체당첨내역!$B$2:$G$1500,{col}$1)"
    return expected_window_formula(col, basis)


def sheet_of(window: int) -> str:
    return f"3차필터({window}회_후보)"


class Book:
    """파일 하나의 '값 뷰'와 '수식 뷰' + 이력."""

    def __init__(self, label: str, path: Path, basis: int | None, k2_label: str):
        self.label, self.path, self.basis, self.k2_label = label, path, basis, k2_label
        self.values = openpyxl.load_workbook(path, data_only=True)
        self.formulas = openpyxl.load_workbook(path, data_only=False, read_only=True)
        # 두 가지 형태를 나눠 갖는다: 외부 검증기(vwr)는 (회차, 번호, 보너스),
        # 정합화 로직(tracker._prediction_for)은 (회차, 번호)를 받는다.
        self.draws3 = vwr.load_draws(self.values["전체당첨내역"])
        self.draws = [(r, ns) for r, ns, _ in self.draws3]
        self.latest = self.draws3[-1][0]

    def sheets(self) -> list[str]:
        return [sheet_of(n) for n in WINDOWS]

    def row(self, sheet: str, r: int) -> list:
        """1~56열(값 뷰). A..H/I..K/L..BD 를 한 번에 본다."""
        return [self.values[sheet].cell(r, c).value for c in range(1, 57)]

    def frow(self, sheet: str, r: int) -> list:
        """1~56열(수식 뷰). 배열수식은 ArrayFormula 객체로 온다."""
        for row in self.formulas[sheet].iter_rows(min_row=r, max_row=r, max_col=56, values_only=True):
            return list(row)
        raise AssertionError(f"{sheet}: {r}행을 읽지 못함")

    def lrow(self, sheet: str, row: list) -> list:
        """행 튜플에서 L:BD(45칸)만."""
        return list(row[11:56])

    def close(self) -> None:
        self.values.close()
        self.formulas.close()


_BOOKS: dict[str, Book] = {}


def setUpModule() -> None:
    # 테스트가 실제 로그 파일을 오염시키지 않게 임시 경로로 돌린다.
    weekly.LOG_FILE = TMP / "weekly_test.log"
    tracker.LOG_FILE = TMP / "tracker_test.log"
    for label, (path, basis, k2) in FILES.items():
        if not path.exists():
            raise unittest.SkipTest(f"{label}: 파일이 없다 → {path}")
        _BOOKS[label] = Book(label, path, basis, k2)


def tearDownModule() -> None:
    for b in _BOOKS.values():
        b.close()
    shutil.rmtree(TMP, ignore_errors=True)


class WindowParsingTests(unittest.TestCase):
    """A) 창 6종이 시트마다 정확히 따로 읽히는가 — 12시트 개별 단언."""

    def test_each_sheet_reads_its_own_window(self):
        for label, book in _BOOKS.items():
            for n in WINDOWS:
                sn = sheet_of(n)
                with self.subTest(file=label, window=n):
                    self.assertIn(sn, book.values.sheetnames)
                    # 시트 이름 → 창 (외부 검증기와 같은 규칙)
                    self.assertEqual(vwr.window_of(sn), n)
                    # K3 라벨 → 창 (자동화가 쓰는 규칙)
                    self.assertEqual(weekly._window_from_label(book.values[sn].cell(3, 11).value), n)
                    self.assertIn(f"최근{n}회", str(book.values[sn].cell(3, 11).value))
                    # K2 라벨 → 기준모집단 창
                    self.assertEqual(weekly._window_from_label(book.values[sn].cell(2, 11).value),
                                     book.basis)
                    self.assertEqual(book.values[sn].cell(2, 11).value, book.k2_label)

    def test_sheet_set_is_exactly_one_basis_and_six_windows(self):
        for label, book in _BOOKS.items():
            with self.subTest(file=label):
                self.assertEqual(book.values.sheetnames,
                                 ["전체당첨내역"] + [sheet_of(n) for n in WINDOWS])

    def test_six_windows_differ_and_basis_formula_is_shared(self):
        """'window 크기만 다르게 읽는지' — 창은 6시트가 서로 다르고, 기준모집단은 6시트가 같아야."""
        for label, book in _BOOKS.items():
            constants, basis_forms, k3_labels = set(), set(), set()
            for n in WINDOWS:
                sn = sheet_of(n)
                m = re.search(r"MAX\([^)]*\)-(\d+)\)", str(book.frow(sn, 3)[11]))
                with self.subTest(file=label, window=n):
                    self.assertIsNotNone(m, f"{sn}: 3행 수식에서 창 상수를 못 찾음")
                constants.add(int(m.group(1)))
                basis_forms.add(str(book.frow(sn, 2)[11]))
                k3_labels.add(str(book.values[sn].cell(3, 11).value))
            with self.subTest(file=label):
                self.assertEqual(constants, {n - 1 for n in WINDOWS},
                                 "6시트의 창 상수가 각 시트의 창(N-1)과 다르다")
                self.assertEqual(len(basis_forms), 1, "기준모집단(2행) 수식이 시트마다 다르다")
                self.assertEqual(len(k3_labels), len(WINDOWS), "3행 라벨이 시트마다 같다")


class FormulaPatternTests(unittest.TestCase):
    """D) 수식 원문이 12시트 전부 기존 패턴 그대로인가(값이 아니라 수식인가)."""

    def test_row2_formula_is_basis_definition(self):
        for label, book in _BOOKS.items():
            for n in WINDOWS:
                sn = sheet_of(n)
                expected = [expected_row2_formula(c, book.basis) for c in COLS]
                with self.subTest(file=label, window=n):
                    self.assertEqual(list(book.frow(sn, 2)[11:56]), expected)

    def test_row3_formula_uses_its_own_window(self):
        for label, book in _BOOKS.items():
            for n in WINDOWS:
                sn = sheet_of(n)
                expected = [expected_window_formula(c, n) for c in COLS]
                with self.subTest(file=label, window=n):
                    self.assertEqual(list(book.frow(sn, 3)[11:56]), expected)

    def test_row4_formula_is_gap_definition(self):
        for label, book in _BOOKS.items():
            for n in WINDOWS:
                sn = sheet_of(n)
                expected = [expected_gap_formula(c) for c in COLS]
                with self.subTest(file=label, window=n):
                    self.assertEqual(list(book.frow(sn, 4)[11:56]), expected)

    def test_row7_array_formula_pattern_and_order(self):
        for label, book in _BOOKS.items():
            for n in WINDOWS:
                sn = sheet_of(n)
                cells = book.lrow(sn, book.frow(sn, 7))
                with self.subTest(file=label, window=n):
                    self.assertTrue(all(isinstance(v, ArrayFormula) for v in cells),
                                    f"{sn} 7행 L:BD에 배열수식이 아닌 칸이 있다")
                    ks = []
                    for i, v in enumerate(cells, start=1):
                        m = _ARRAY_PAT.match(str(v.text))
                        self.assertIsNotNone(m, f"{sn} {COLS[i - 1]}7 수식이 패턴과 다름 → {v.text}")
                        ks.append(int(m.group(1)))
                    self.assertEqual(ks, list(range(1, 46)),
                                     f"{sn} 7행 배열수식의 k가 1~45를 순서대로 돌지 않는다")

    def test_past_rows_are_frozen_values_not_formulas(self):
        """과거행(8행~)의 L:BD는 값이다 — 이 파일들의 회차 라벨도 값이라 밀리지 않는다.
        (그래서 candidate_tracker_auto_update의 정합화 대상이 아니다.)"""
        for label, book in _BOOKS.items():
            for n in WINDOWS:
                sn = sheet_of(n)
                last = 6 + n
                with self.subTest(file=label, window=n):
                    for r in (8, 9, last):
                        cells = book.lrow(sn, book.frow(sn, r))
                        self.assertTrue(all(isinstance(v, int) and 1 <= v <= 45 for v in cells),
                                        f"{sn} {r}행 L:BD에 값(1~45 정수)이 아닌 칸이 있다")


class ValueInvariantTests(unittest.TestCase):
    """B) 값 불변식 — 시트 자신의 2·3행을 재료로 재계산해 대조한다."""

    def _gap_and_order(self, book: Book, sn: str):
        row2, row3 = book.lrow(sn, book.row(sn, 2)), book.lrow(sn, book.row(sn, 3))
        v2 = {n: row2[n - 1] for n in NUMS}
        v3 = {n: row3[n - 1] for n in NUMS}
        r2, r3 = vwr.comp_ranks(v2), vwr.comp_ranks(v3)
        gap = {n: r3[n] - r2[n] for n in NUMS}
        return gap, sorted(NUMS, key=lambda n: (-gap[n], n))

    def test_row1_is_the_1_to_45_header(self):
        for label, book in _BOOKS.items():
            for n in WINDOWS:
                sn = sheet_of(n)
                with self.subTest(file=label, window=n):
                    self.assertEqual(book.lrow(sn, book.row(sn, 1)), NUMS)

    def test_row2_is_basis_counts(self):
        for label, book in _BOOKS.items():
            expected = vwr.window_counts(book.draws3, book.basis)
            with self.subTest(file=label):
                for n in WINDOWS:
                    self.assertEqual(book.lrow(sheet_of(n), book.row(sheet_of(n), 2)),
                                     [expected[i] for i in NUMS])

    def test_row3_is_exactly_this_window_and_no_other(self):
        """6창 전부에 대해: 자기 창과 일치하고, 다른 창과는 (합이 6N이라) 절대 같지 않다."""
        for label, book in _BOOKS.items():
            counts = {n: vwr.window_counts(book.draws3, n) for n in WINDOWS}
            basis_counts = vwr.window_counts(book.draws3, book.basis)
            for n in WINDOWS:
                sn = sheet_of(n)
                got = book.lrow(sn, book.row(sn, 3))
                with self.subTest(file=label, window=n):
                    self.assertEqual(got, [counts[n][i] for i in NUMS])
                    self.assertEqual(sum(got), 6 * n, f"{sn}: 3행 합계가 6×{n}이 아니다")
                    for other in WINDOWS:
                        if other == n:
                            continue
                        self.assertNotEqual(got, [counts[other][i] for i in NUMS],
                                            f"{sn}의 3행이 최근{other}회 빈도와 같다")
                    if book.basis is not None and book.basis != n:
                        self.assertNotEqual(got, [basis_counts[i] for i in NUMS])
                    # 2026-10-05: 최근300표본의 300회 시트는 기준(2행)=비교창(3행)=300이라
                    # 3행이 2행과 같은 것이 정상이다(오차 전부 0 — 사용자 결정으로 시트 유지).

    def test_row2_sum_matches_basis_length(self):
        for label, book in _BOOKS.items():
            expected_len = (len(book.draws3) if book.basis is None
                            else min(book.basis, len(book.draws3)))
            with self.subTest(file=label):
                for n in WINDOWS:
                    sn = sheet_of(n)
                    self.assertEqual(sum(book.lrow(sn, book.row(sn, 2))), 6 * expected_len)

    def test_row4_is_recomputed_gap(self):
        for label, book in _BOOKS.items():
            for n in WINDOWS:
                sn = sheet_of(n)
                gap, _ = self._gap_and_order(book, sn)
                with self.subTest(file=label, window=n):
                    self.assertEqual(book.lrow(sn, book.row(sn, 4)), [gap[i] for i in NUMS])

    def test_row7_is_gap_order(self):
        for label, book in _BOOKS.items():
            for n in WINDOWS:
                sn = sheet_of(n)
                _, order = self._gap_and_order(book, sn)
                got = book.lrow(sn, book.row(sn, 7))
                with self.subTest(file=label, window=n):
                    self.assertEqual(sorted(got), NUMS, f"{sn} 7행이 1~45 순열이 아니다")
                    self.assertEqual(got, order, f"{sn} 7행이 (-오차,번호) 정렬과 다르다")

    def test_block_shape_and_label_chain(self):
        """7행=다음 회차 대기, 8행=최신 회차, 아래로 1씩 감소, 행수는 정확히 창 크기."""
        for label, book in _BOOKS.items():
            latest = book.latest
            for n in WINDOWS:
                sn = sheet_of(n)
                ws = book.values[sn]
                with self.subTest(file=label, window=n):
                    self.assertEqual(ws.max_row, 6 + n, f"{sn}: 블록 행수가 창 크기와 다르다")
                    for r in range(7, 7 + n):
                        self.assertEqual(ws.cell(r, 1).value, latest + 1 - (r - 7),
                                         f"{sn} {r}행 회차라벨이 사슬과 어긋남")
                    pending = book.row(sn, 7)
                    self.assertTrue(all(v is None for v in pending[1:11]),
                                    f"{sn} 7행(대기행)에 당첨번호/적중수가 들어 있다")
                    last = book.row(sn, 6 + n)
                    self.assertTrue(all(isinstance(v, int) for v in last[1:7]),
                                    f"{sn} 마지막 행 당첨번호가 비어 있다")

    def test_past_rows_pair_own_prediction_with_own_numbers(self):
        """각 과거행의 적중수는 그 행의 순위(L:BD)와 그 행의 당첨번호로 재계산한 값과 같아야 한다."""
        for label, book in _BOOKS.items():
            by_round = {r: ns for r, ns, _ in book.draws3}
            for n in WINDOWS:
                sn = sheet_of(n)
                ws = book.values[sn]
                checked = 0
                with self.subTest(file=label, window=n):
                    for r in range(7, 7 + n):
                        rnd = ws.cell(r, 1).value
                        drawn = [ws.cell(r, c).value for c in range(2, 8)]
                        if not isinstance(rnd, int) or any(v is None for v in drawn):
                            continue
                        ranking = book.lrow(sn, book.row(sn, r))
                        got = [ws.cell(r, c).value for c in (9, 10, 11)]
                        exp = list(tracker._hits(ranking, drawn))
                        self.assertEqual(sorted(ranking), NUMS, f"{sn} {r}행 순열 아님")
                        self.assertEqual(drawn, by_round[rnd], f"{sn} {r}행 당첨번호가 이력과 다름")
                        self.assertEqual(got, exp, f"{sn} {r}행 적중수가 재계산과 다름")
                        self.assertEqual(sum(got), 6)
                        checked += 1
                    self.assertGreater(checked, 0, f"{sn}: 검사한 과거행이 없다")

    def test_external_verifier_logic_passes_per_sheet(self):
        """외부 검증기(verify_workbook_ranking)의 check_sheet를 시트별로 그대로 재사용."""
        for label, book in _BOOKS.items():
            for n in WINDOWS:
                sn = sheet_of(n)
                vwr.FAILS.clear()
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    vwr.check_sheet(sn, book.values[sn], book.draws3)
                fails = list(vwr.FAILS)
                vwr.FAILS.clear()
                with self.subTest(file=label, window=n):
                    self.assertEqual(fails, [], f"{sn}: 외부 검증기 지적 → {fails}")


class HistoryAlignmentTests(unittest.TestCase):
    """C) 행↔회차 정합 — 12시트의 모든 과거행을 회차별로 재계산해 대조(약 25초)."""

    def test_every_past_row_matches_recomputation_for_its_own_round(self):
        total, bad = 0, []
        for label, book in _BOOKS.items():
            for n in WINDOWS:
                sn = sheet_of(n)
                ws = book.values[sn]
                for r in range(7, 7 + n):
                    rnd = ws.cell(r, 1).value
                    drawn = [ws.cell(r, c).value for c in range(2, 8)]
                    if not isinstance(rnd, int) or any(v is None for v in drawn):
                        continue
                    got = book.lrow(sn, book.row(sn, r))
                    exp = tracker._prediction_for(book.draws, rnd, book.basis, n)
                    total += 1
                    if exp is None or got != exp:
                        first = next((i for i, (a, b) in enumerate(zip(got, exp or [])) if a != b), 0)
                        bad.append(f"{label}/{sn} {r}행({rnd}회차) {first + 1}위: "
                                   f"시트 {got[first]} vs 재계산 {exp[first] if exp else None}")
        self.assertGreaterEqual(total, 12, "검사한 행이 12개(시트당 1개) 미만이다")
        self.assertEqual(bad, [], f"회차와 예측이 어긋난 행 {len(bad)}개: {bad[:5]}")


class AutomationWiringTests(unittest.TestCase):
    """E) 이 두 파일이 주간 자동 업데이트 대상인가(단일 작성자 = weekly)."""

    def test_weekly_targets_these_two_files_and_advances_them(self):
        for label, book in _BOOKS.items():
            with self.subTest(file=label):
                self.assertIn(label, weekly.FILE_PATHS)
                self.assertEqual(weekly.FILE_PATHS[label], book.path)
                self.assertIn(label, weekly.ADVANCE_3CHA_FILES)

    def test_weekly_collects_all_six_sheets_per_file(self):
        for label, book in _BOOKS.items():
            sheets = [sn for sn in book.values.sheetnames if sn.startswith("3차필터")]
            with self.subTest(file=label):
                self.assertEqual(sheets, book.sheets())

    def test_external_verifier_covers_these_two_files(self):
        for label, book in _BOOKS.items():
            with self.subTest(file=label):
                self.assertEqual(vwr.FILES[label], book.path)

    def test_realign_script_intentionally_skips_these_blocks(self):
        """candidate_tracker_auto_update는 이 두 파일을 **건드리지 않는 것이 맞다**:
        회차 라벨(A열)이 값이라 밀릴 수 없고, 그래서 _block_start가 블록으로 잡지 않는다.
        (이 성질이 깨지면 두 스크립트가 같은 파일을 서로 다르게 고칠 수 있으므로 여기서 잡는다.)
        또 이 파일들에는 _calc_누적빈도·_calc_라운드기준 시트가 없어 그쪽 검증 절차를 태울 수 없다."""
        for label, book in _BOOKS.items():
            for n in WINDOWS:
                sn = sheet_of(n)
                with self.subTest(file=label, window=n):
                    self.assertIsNone(tracker._block_start(book.values[sn]))
                    self.assertFalse(isinstance(book.values[sn].cell(7, 1).value, str))
                    self.assertEqual(tracker._block_mismatch_rows(book.path), 0)

    def test_tracker_only_target_file_has_the_sheets_it_needs(self):
        """정합화 스크립트의 대상 파일은 지금도 자기 전제(_calc_* 시트)를 갖고 있다."""
        wb = openpyxl.load_workbook(tracker.TARGET_FILE, data_only=True, read_only=True)
        try:
            for sn in (tracker.CUM_SHEET, tracker.ANCHOR_SHEET, tracker.SAMPLE_CHECK_SHEET):
                self.assertIn(sn, wb.sheetnames, f"{tracker.TARGET_FILE.name}에 {sn} 시트가 없다")
            for _, book in _BOOKS.items():
                for sn in (tracker.CUM_SHEET, tracker.ANCHOR_SHEET, tracker.SAMPLE_CHECK_SHEET):
                    self.assertNotIn(sn, book.values.sheetnames)
        finally:
            wb.close()


class AdvanceSimulationTests(unittest.TestCase):
    """F) 실제 주간 전진을 임시 복사본에서 돌려 12시트가 계약대로 바뀌는지."""

    @classmethod
    def setUpClass(cls):
        latest = max(b.latest for b in _BOOKS.values())
        cls.rec = {"round": latest + 1, "nums": [2, 9, 17, 28, 36, 44], "bonus": 13}
        cls.latest = latest
        # 엑셀 COM 대신 파이썬 폴백 (모듈 docstring 참고)
        cls._orig = (weekly.recalc_and_save, weekly.recalc_and_read_pending_row)
        weekly.recalc_and_save = lambda path: None
        weekly.recalc_and_read_pending_row = (
            lambda path, sheets: weekly._python_pending_forecast(path, sheets))
        try:
            # 전진 전 이력으로 '이번 회차의 예측'을 미리 계산해 둔다(= 7행에 있던 값)
            cls.expected = {
                label: {n: tracker._prediction_for(book.draws, cls.rec["round"], book.basis, n)
                        for n in WINDOWS}
                for label, book in _BOOKS.items()}
            cls.copies = {}
            for label, book in _BOOKS.items():
                dst = TMP / f"sim_{label}.xlsx"
                shutil.copy2(book.path, dst)
                cls.copies[label] = dst
                weekly.process_one_round_for_file(dst, label, cls.rec)
            cls.after = {label: openpyxl.load_workbook(p, data_only=True)
                         for label, p in cls.copies.items()}
        finally:
            weekly.recalc_and_save, weekly.recalc_and_read_pending_row = cls._orig

    @classmethod
    def tearDownClass(cls):
        for wb in cls.after.values():
            wb.close()

    def test_new_round_appended_to_history(self):
        for label, wb in self.after.items():
            ws = wb["전체당첨내역"]
            last = [ws.cell(ws.max_row, c).value for c in range(1, 9)]
            with self.subTest(file=label):
                self.assertEqual(last[0], self.rec["round"])
                self.assertEqual(last[1:7], self.rec["nums"])
                self.assertEqual(last[7], self.rec["bonus"])

    def test_all_twelve_sheets_advanced(self):
        for label, wb in self.after.items():
            for n in WINDOWS:
                sn = sheet_of(n)
                ws = wb[sn]
                with self.subTest(file=label, window=n):
                    self.assertEqual(ws.max_row, 6 + n, "행수가 창 크기에서 벗어났다")
                    for r in range(7, 7 + n):
                        self.assertEqual(ws.cell(r, 1).value,
                                         self.rec["round"] + 1 - (r - 7),
                                         f"전진 후 {r}행 회차라벨이 사슬과 어긋남")
                    self.assertTrue(all(ws.cell(7, c).value is None for c in range(2, 12)),
                                    "새 대기행(7행)에 값이 남아 있다")

    def test_frozen_row_keeps_the_prediction_that_was_pending(self):
        """8행에 동결된 순위는 '전진 전 7행에 있던 예측'(= 이번 회차 직전 이력 기준)이어야 한다."""
        for label, wb in self.after.items():
            for n in WINDOWS:
                sn = sheet_of(n)
                ws = wb[sn]
                ranking = [ws.cell(8, c).value for c in range(12, 57)]
                got = [ws.cell(8, c).value for c in (9, 10, 11)]
                with self.subTest(file=label, window=n):
                    self.assertEqual(ranking, self.expected[label][n],
                                     f"{sn} 8행 동결 순위가 전진 전 예측과 다르다")
                    self.assertEqual(sorted(ranking), NUMS)
                    self.assertEqual(got, list(tracker._hits(ranking, self.rec["nums"])))
                    self.assertEqual(sum(got), 6)

    def test_new_pending_row_has_the_array_formula_again(self):
        for label, wb in self.after.items():
            fwb = openpyxl.load_workbook(self.copies[label], data_only=False, read_only=True)
            try:
                for n in WINDOWS:
                    sn = sheet_of(n)
                    for row in fwb[sn].iter_rows(min_row=7, max_row=7, max_col=56, values_only=True):
                        cells = list(row[11:56])
                    with self.subTest(file=label, window=n):
                        self.assertTrue(all(isinstance(v, ArrayFormula) for v in cells),
                                        f"{sn} 새 7행 L:BD가 배열수식이 아니다")
                        ks = []
                        for v in cells:
                            m = _ARRAY_PAT.match(str(v.text))
                            self.assertIsNotNone(m, f"{sn} 새 7행 수식이 패턴과 다름 → {v}")
                            ks.append(int(m.group(1)))
                        self.assertEqual(ks, list(range(1, 46)))
            finally:
                fwb.close()

    def test_source_files_untouched_by_simulation(self):
        for label, book in _BOOKS.items():
            with self.subTest(file=label):
                self.assertEqual(hashlib.sha256(book.path.read_bytes()).hexdigest(),
                                 _SRC_HASH[book.path.name],
                                 "시뮬레이션이 실물 파일을 바꿨다")


class ExternalVerifierExitCodeTests(unittest.TestCase):
    """G) 외부 검증기를 별도 프로세스로 실행 — 실제 CLI exit code 확인(약 6초)."""

    def test_exit_code_zero_and_no_problems(self):
        p = subprocess.run(
            [sys.executable, "-X", "utf8", str(ROOT / "scratch" / "verify_workbook_ranking.py")],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(p.returncode, 0,
                         f"검증기 exit={p.returncode}\n{(p.stdout or '')[-2000:]}\n{(p.stderr or '')[-500:]}")
        self.assertIn("시트 24개 검사 완료", p.stdout or "")
        self.assertIn("문제 0건", p.stdout or "")


class SourceFilesUntouchedTests(unittest.TestCase):
    """대상 파일 2개가 이 테스트 실행으로 한 바이트도 바뀌지 않았는지(읽기 전용 계약)."""

    def test_source_hashes_unchanged(self):
        for label, book in _BOOKS.items():
            with self.subTest(file=label):
                self.assertEqual(hashlib.sha256(book.path.read_bytes()).hexdigest(),
                                 _SRC_HASH[book.path.name])


if __name__ == "__main__":
    unittest.main(verbosity=2)
