# -*- coding: utf-8 -*-
"""1차필터 회차 열의 '판정 캐시값' 불변식 검사(읽기 전용).

주장: 회차 열(20개)의 규칙행(수식이 있는 행)에는 숫자 캐시값이 **하나도 없다**
      = 엑셀 재계산이 반영되지 않은 상태(미계산/stale)라 판정칸을 검증 기준으로 쓸 수 없다.
검사: 20개 회차 열 × 5~1503행 전체를 훑어
      (a) 숫자 캐시값이 있는 셀을 전부 모으고,
      (b) 그 셀들 중 '수식이 있는 행'이 하나라도 있으면 실패로 보고한다.
      즉 "숫자는 수식 없는 행에만 있다"가 모든 열·행에 대해 성립해야 한다.

실행: venv312\\Scripts\\python.exe scratch\\check_stage1_cells_invariant.py
"""
from __future__ import annotations

import os
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
SRC = ROOT / "★조합생성_후보숫자_추적표" / "조합생성_후보숫자_추적표_샘플.xlsx"

wb = openpyxl.load_workbook(SRC, data_only=True)
wb2 = openpyxl.load_workbook(SRC, data_only=False)
try:
    ws = wb["1차필터(7기본필터)"]
    wf = wb2["1차필터(7기본필터)"]
    cols = [c for c in range(1, ws.max_column + 1)
            if isinstance(ws.cell(4, c).value, int)]

    def has_formula(r, c) -> bool:
        v = wf.cell(r, c).value
        return hasattr(v, "text") or (isinstance(v, str) and v.startswith("="))

    numeric_on_formula = []      # 수식 있는 행인데 숫자 캐시값이 있는 셀 (있으면 실패)
    numeric_total = 0
    for c in cols:
        for r in range(5, 1504):
            v = ws.cell(r, c).value
            if not isinstance(v, (int, float)):
                continue
            numeric_total += 1
            if has_formula(r, c):
                numeric_on_formula.append((ws.cell(r, c).coordinate, v))

    print(f"회차 열 {len(cols)}개(5~1503행) · 숫자 캐시값 있는 셀 {numeric_total}개")
    print(f"그중 '수식 있는 행'에 있는 셀: {len(numeric_on_formula)}개 "
          f"{numeric_on_formula[:10]}")
    print("판정:", "PASS (숫자는 수식 없는 행에만 있음 → 판정칸은 미계산 상태)"
          if not numeric_on_formula else "FAIL (수식 있는 행에 숫자 캐시값이 있다)")
finally:
    wb.close()
    wb2.close()
