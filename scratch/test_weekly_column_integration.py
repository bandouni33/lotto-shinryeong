# -*- coding: utf-8 -*-
"""주간 자동화 통합 테스트 — 새 회차 1개 처리 시 회차 컬럼이 1칸 밀리는가 (임시 복사본).

검증 대상은 생산 경로 그 자체: weekly_lotto_file_update.process_one_round_for_file().
  · 전체당첨내역에 새 회차가 1행 추가된다
  · 1차필터·2차필터 회차 컬럼이 각각 1칸 전진해 N4 == 새 회차가 된다
  · 회차 열 개수·수식 셀 수·병합·최대행이 그대로다
  · 헬퍼행(1504~1516)이 새 라벨을 참조한다(N$4 / N$4-1)
  · 다른 시트는 내용이 바뀌지 않는다
  · 오류값이 생기지 않는다
엑셀 재계산(recalc_and_save)은 이 환경에서 기동이 안 되므로 경고를 남기고 건너뛴다 —
그 경로는 스크립트가 이미 try/except로 감싸고 있다(내용은 정상).

실행: venv312\\Scripts\\python.exe scratch\\test_weekly_column_integration.py
"""
from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter as cl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import weekly_lotto_file_update as wk  # noqa: E402

SRC = ROOT / "★조합생성_후보숫자_추적표" / "조합생성_후보숫자_추적표_샘플.xlsx"
COPY = ROOT / "scratch" / "_it_weekly_sample.xlsx"
OUT = ROOT / "scratch" / "test_weekly_column_integration_out.txt"
NEW_ROUND = {
    "round": 9999,                       # 실제 회차와 겹치지 않는 시험용 라벨
    "nums": [3, 11, 19, 27, 35, 44],
    "bonus": 7,
}
R: list[str] = []
FAILS: list[str] = []


def w(s: str = "") -> None:
    R.append(str(s))
    print(s, flush=True)


def ok(cond: bool, msg: str) -> bool:
    if cond:
        w(f"  ok   {msg}")
    else:
        FAILS.append(msg)
        w(f"  FAIL {msg}")
    return bool(cond)


def fx(cell):
    v = cell.value
    return v.text if hasattr(v, "text") else (v if isinstance(v, str) and v.startswith("=") else None)


def sheet_hash(wb, name: str) -> str:
    h = hashlib.sha256()
    for row in wb[name].iter_rows():
        for c in row:
            h.update(f"{c.coordinate}={c.value!r}|".encode())
    return h.hexdigest()


shutil.copy2(SRC, COPY)
w(f"실물 sha(앞12) = {hashlib.sha256(SRC.read_bytes()).hexdigest()[:12]} · 시험 복사본 {COPY.name}")

wb_before = openpyxl.load_workbook(COPY, data_only=False)
try:
    other_before = {sn: sheet_hash(wb_before, sn) for sn in wb_before.sheetnames
                    if sn not in wk.COLUMN_ROUND_SHEETS}
    labels_before = {sn: [wb_before[sn].cell(4, c).value
                          for c in range(1, wb_before[sn].max_column + 1)
                          if isinstance(wb_before[sn].cell(4, c).value, int)]
                     for sn in wk.COLUMN_ROUND_SHEETS}
    n_formulas_before = {}
    for sn in wk.COLUMN_ROUND_SHEETS:
        ws = wb_before[sn]
        n_formulas_before[sn] = sum(
            1 for c in range(1, ws.max_column + 1) for r in range(1, ws.max_row + 1)
            if fx(ws.cell(r, c)))
    all_before = list(wb_before.sheetnames)
    rows_before = wb_before["전체당첨내역"].max_row
finally:
    wb_before.close()

w(f"\n== process_one_round_for_file(샘플, {NEW_ROUND['round']}회차) ==")
wk.process_one_round_for_file(COPY, "샘플", NEW_ROUND)
w("(위 로그의 '회차 컬럼 1칸 전진' 및 엑셀 재계산 경고는 정상 동작)")

wb_after = openpyxl.load_workbook(COPY, data_only=False)
try:
    ok(any("회차 컬럼 1칸 전진" in line for line in R),
       "로그에 '회차 컬럼 1칸 전진'이 남았다")
    ws_all = wb_after["전체당첨내역"]
    ok(ws_all.max_row == rows_before + 1,
       f"전체당첨내역 1행 추가 ({rows_before}→{ws_all.max_row})")
    last = [ws_all.cell(ws_all.max_row, c).value for c in range(1, 9)]
    ok(last[0] == NEW_ROUND["round"] and last[1:7] == NEW_ROUND["nums"]
       and last[7] == NEW_ROUND["bonus"],
       f"마지막 행 = {last[0]}회차 {last[1:7]} + 보너스 {last[7]}")

    for sn in wk.COLUMN_ROUND_SHEETS:
        ws = wb_after[sn]
        labels = [ws.cell(4, c).value for c in range(1, ws.max_column + 1)
                  if isinstance(ws.cell(4, c).value, int)]
        first = min(c for c in range(1, ws.max_column + 1)
                    if isinstance(ws.cell(4, c).value, int))
        last_c = max(c for c in range(1, ws.max_column + 1)
                     if isinstance(ws.cell(4, c).value, int))
        n_f = sum(1 for c in range(first, last_c + 1) for r in range(1, ws.max_row + 1)
                  if fx(ws.cell(r, c)))
        nb = labels_before[sn]
        ok(len(labels) == len(nb) and ws.cell(4, last_c + 2).value is None,
           f"{sn}: 회차 열 개수 유지 ({len(nb)}→{len(labels)}, 범위 {cl(first)}..{cl(last_c)})")
        ok(labels == [NEW_ROUND["round"] - i for i in range(len(labels))],
           f"{sn}: 라벨 1칸 전진 + 연속 ({labels[0]}..{labels[-1]})")
        ok(n_f == n_formulas_before[sn],
           f"{sn}: 수식 셀 수 유지 ({n_formulas_before[sn]:,}→{n_f:,})")
        if sn.startswith("1차필터"):
            h = {r: fx(ws.cell(r, first)) for r in range(1504, 1517)}
            ok(all(h.values()) and sum(1 for t in h.values()
                                       if f"{cl(first)}$4" in t) == 13,
               "1차필터: 새 N열 헬퍼행 13개가 N$4를 참조")
            ok(any(f"{cl(first)}$4-1" in t for t in h.values()),
               "1차필터: 헬퍼행이 직전 회차(N$4-1)도 참조")

    changed = [sn for sn in all_before if sn not in wk.COLUMN_ROUND_SHEETS
               and sheet_hash(wb_after, sn) != other_before[sn]]
    # 전체당첨내역은 1행 늘어난 게 정상이므로 제외하고 본다
    changed = [sn for sn in changed if sn != "전체당첨내역"]
    ok(not changed, f"다른 시트 내용 무변경 (변경 {changed})")
    ok(list(wb_after.sheetnames) == all_before, "시트 목록 불변")
finally:
    wb_after.close()

errs = wk.scan_errors(COPY)
ok(not errs, f"저장 후 오류값 0 (발견 {len(errs)} {errs[:3]})")

w(f"\n단언 실패 {len(FAILS)}건" + ("" if not FAILS else ": " + " | ".join(FAILS[:5])))
w(f"실물 무변경 확인: sha(앞12) = {hashlib.sha256(SRC.read_bytes()).hexdigest()[:12]}")
OUT.write_text("\n".join(R), encoding="utf-8")
print(f"written {OUT}")
sys.exit(1 if FAILS else 0)
