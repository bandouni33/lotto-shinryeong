# -*- coding: utf-8 -*-
"""1차필터 시트의 회차 열 판정을 시트 자신의 캐시값과 대조해 규칙 파싱을 검증(읽기 전용).

시트 회차 열의 규칙행 수식 구조(원문 실측):
  =IF(ISNA(MATCH(N$4,전체당첨내역!$A$2:$A$1500,0)),"",
     IF(OR( (위반개수) < $K{규칙행}, (위반개수) > $L{규칙행} ), (위반개수), ""))
  → 캐시값이 **숫자면 그 규칙은 위반**(값 = 위반 개수), **빈칸이면 통과**.

헬퍼행(=시트 자체 정의):
  N1504..N1509 = 그 회차 당첨번호 6개
  N1510..N1516 = 직전 회차 7개(번호 6 + 보너스)
  5행 '전 출현번호' = 그 회차 6개 중 직전 7개와 같은 개수
  6행 '이웃수'      = 그 회차 6개 중 직전 7개의 ±1(±1 포함)과 겹치는 개수
  7행 '후보패턴 이웃수' = 사용자 정의(2026-09-27): 직전 7개 각각의 이웃(예 9→8,9,10)
  8행~            = 그 회차 6개 중 J열 목록에 들어 있는 개수

검증: 각 규칙행의 (통과/위반, 위반개수)를 제가 계산한 값과 시트 캐시값으로 맞대어 본다.

실행: venv312\\Scripts\\python.exe scratch\\verify_stage1_rule_cells.py
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
SRC = ROOT / "★조합생성_후보숫자_추적표" / "조합생성_후보숫자_추적표_샘플.xlsx"
OUT = ROOT / "scratch" / "verify_stage1_rule_cells_out.txt"
L: list[str] = []


def w(s: str = "") -> None:
    L.append(s)


def targets_of(txt) -> set[int]:
    return {int(x) for x in re.findall(r"\d+", str(txt))} if txt is not None else set()


wbv = openpyxl.load_workbook(SRC, data_only=True)
try:
    wsa = wbv["전체당첨내역"]
    draws = {}
    for r in range(2, wsa.max_row + 1):
        rr = wsa.cell(r, 1).value
        if isinstance(rr, int):
            draws[rr] = [wsa.cell(r, c).value for c in range(2, 9)]   # 번호6 + 보너스

    wsv = wbv["1차필터(7기본필터)"]
    cols = {wsv.cell(4, c).value: c for c in range(1, wsv.max_column + 1)
            if isinstance(wsv.cell(4, c).value, int)}
    w(f"회차 열: {sorted(cols)}")

    # 규칙행: H 또는 J 가 있는 5~1503행 (K/L 도 숫자)
    rule_rows = []
    for r in range(5, 1504):
        h, j, k, lm = (wsv.cell(r, 8).value, wsv.cell(r, 10).value,
                       wsv.cell(r, 11).value, wsv.cell(r, 12).value)
        if h is None and j is None:
            continue
        if not isinstance(k, (int, float)) or not isinstance(lm, (int, float)):
            continue
        rule_rows.append({"row": r, "name": h, "j": j, "min": int(k), "max": int(lm)})
    w(f"규칙 후보행 {len(rule_rows)}개 (5~1503행 기준)")

    total_cells = matched = mismatched = blank_in_sheet = 0
    examples = []
    for rnd, col in sorted(cols.items(), reverse=True):
        nums6 = [draws[rnd][i] for i in range(6)]
        prev7 = draws.get(rnd - 1, [None] * 7)
        for r in rule_rows:
            cell = wsv.cell(r["row"], col)
            cached = cell.value
            has_formula = cell.data_type == "f" if hasattr(cell, "data_type") else None
            # 계산
            name = str(r["name"] or "")
            j = r["j"]
            if r["row"] == 5:
                tgt = {x for x in prev7 if isinstance(x, int)}
            elif r["row"] == 6:
                tgt = set()
                for x in prev7:
                    if isinstance(x, int):
                        for d in (-1, 0, 1):
                            if 1 <= x + d <= 45:
                                tgt.add(x + d)
            elif r["row"] == 7:
                tgt = set()
                for x in prev7:
                    if isinstance(x, int):
                        for d in (-1, 0, 1):
                            if 1 <= x + d <= 45:
                                tgt.add(x + d)
            elif str(j).strip().upper() == "AUTO":
                tgt = set()          # 정의 미확인 AUTO (7행 외)
            else:
                tgt = targets_of(j)
            cnt = len(set(nums6) & tgt)
            violated_mine = not (r["min"] <= cnt <= r["max"])
            if cached is None or cached == "":
                violated_sheet = False
                sheet_count = None
            else:
                violated_sheet = True
                sheet_count = cached
                blank_in_sheet += 1
            total_cells += 1
            ok = (violated_mine == violated_sheet) and (
                not violated_sheet or (isinstance(sheet_count, int) and int(sheet_count) == cnt))
            if ok:
                matched += 1
            else:
                mismatched += 1
                if len(examples) < 12:
                    examples.append(
                        f"{rnd}회차 row{r['row']}({name or '-'}) 시트={sheet_count!r} / 내계산 "
                        f"위반={violated_mine} 개수={cnt} (min{r['min']}~max{r['max']}, targets {len(tgt)}개)")
    w(f"\n검사 셀 {total_cells:,}개 · 일치 {matched:,} · 불일치 {mismatched:,} "
      f"(시트에 위반 숫자가 적힌 셀 {blank_in_sheet:,}개)")
    w("불일치 예시:")
    for e in examples:
        w("  " + e)
finally:
    wbv.close()

OUT.write_text("\n".join(L), encoding="utf-8")
print(f"written {OUT}")
