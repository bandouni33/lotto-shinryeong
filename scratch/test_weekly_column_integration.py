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
    # 2026-09-27: 행 전진이 편입되면서 "회차 라벨"이 실제로 연속이어야 한다 — 예전처럼
    # 9999(실제와 띄엄띄엄한 값)를 넣으면 행 전진의 구멍 검사에 걸린다(그게 정상 동작이다).
    # 파일 전체당첨내역 최신이 1243이므로 다음 회차 1244를 쓴다.
    "round": 1244,                       # 실제 회차와 연속인 시험용 라벨
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
                    if sn not in wk.COLUMN_ROUND_SHEETS
                    and sn not in wk.ROW_ROUND_SHEETS}
    row_labels_before = {sn: [wb_before[sn].cell(r, 1).value
                              for r in range(wk.ROW_FIRST, wk.ROW_LAST + 1)
                              if isinstance(wb_before[sn].cell(r, 1).value, int)]
                         for sn in wk.ROW_ROUND_SHEETS}
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
w("(위 로그의 '회차 컬럼/행 전진' 및 엑셀 재계산 경고는 정상 동작)")

wb_after = openpyxl.load_workbook(COPY, data_only=False)
try:
    ok(any("회차 컬럼" in line and "전진" in line for line in R),
       "로그에 회차 컬럼 전진이 남았다")
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

    # 2026-09-27: 행 전진(1차추적결과·2차추적결과·4차필터)도 같은 호출에서 일어난다
    for sn in wk.ROW_ROUND_SHEETS:
        ws = wb_after[sn]
        ints = [ws.cell(r, 1).value for r in range(wk.ROW_FIRST, wk.ROW_LAST + 1)
                if isinstance(ws.cell(r, 1).value, int)]
        ok(len(ints) == len(row_labels_before[sn]) == wk.ROW_WINDOW,
           f"{sn}: 행 창 크기 유지 ({len(row_labels_before[sn])}→{len(ints)})")
        ok(ints == list(range(ints[0], ints[0] - len(ints), -1))
           and ints[0] == NEW_ROUND["round"],
           f"{sn}: 행 라벨이 새 회차까지 연속·내림차순 ({ints[0]}..{ints[-1]})")
    ok(wk.DAEJO_SHEET in wb_after.sheetnames, f"대조 시트 '{wk.DAEJO_SHEET}' 생성됨")

    changed = [sn for sn in all_before if sn not in wk.COLUMN_ROUND_SHEETS
               and sn not in wk.ROW_ROUND_SHEETS
               and sn != wk.DAEJO_SHEET
               and sheet_hash(wb_after, sn) != other_before[sn]]
    # 전체당첨내역은 1행 늘어난 게 정상이므로 제외하고 본다
    changed = [sn for sn in changed if sn != "전체당첨내역"]
    ok(not changed, f"다른 시트 내용 무변경 (변경 {changed})")
    # 시험 복사본은 실물을 복사한 것이라 이미 대조 시트가 있을 수도 있다(실물에 한 번
    # 돌려놓은 뒤에는 있다) — 새로 생기는 시트는 '없음 또는 대조 시트' 중 하나여야 한다.
    new_sheets = [sn for sn in wb_after.sheetnames if sn not in all_before]
    ok(new_sheets in ([], [wk.DAEJO_SHEET]),
       f"새 시트 = {new_sheets} (기대: 없음 또는 '{wk.DAEJO_SHEET}')")
    ok(all(sn in wb_after.sheetnames for sn in all_before), "기존 시트가 모두 남아 있다")
finally:
    wb_after.close()

errs = wk.scan_errors(COPY)
ok(not errs, f"저장 후 오류값 0 (발견 {len(errs)} {errs[:3]})")

w(f"\n단언 실패 {len(FAILS)}건" + ("" if not FAILS else ": " + " | ".join(FAILS[:5])))
w(f"실물 무변경 확인: sha(앞12) = {hashlib.sha256(SRC.read_bytes()).hexdigest()[:12]}")
OUT.write_text("\n".join(R), encoding="utf-8")
print(f"written {OUT}")
# 2026-09-27: 대조 시트가 DB(draw_generation_stats)를 읽으면서 db_turso의 non-daemon
# 스레드가 인터프리터 종료를 불잡아 스크립트가 안 끝난다(실측) — 종료코드를 받을 수 있게
# 생산 스크립트·test_filter_rules_source.py와 같은 방식(os._exit)으로 즉시 종료한다.
import os as _os

_os._exit(1 if FAILS else 0)
