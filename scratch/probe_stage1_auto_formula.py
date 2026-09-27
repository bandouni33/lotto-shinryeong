# -*- coding: utf-8 -*-
"""샘플 파일 1차필터 회차 열의 **수식 원문 전체**를 읽어 AUTO 정의와 판정 방식을 확정한다.

앞선 시도에서 내가 세운 AUTO 정의 추정으로는 저장값 3,452,560이 재현되지 않았다.
정의의 정답은 이 시트의 수식 자체에 들어 있으므로, 잘리지 않은 원문을 본다.

실행: venv312\\Scripts\\python.exe scratch\\probe_stage1_auto_formula.py
"""
from __future__ import annotations

import os
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
SRC = ROOT / "★조합생성_후보숫자_추적표" / "조합생성_후보숫자_추적표_샘플.xlsx"
OUT = ROOT / "scratch" / "probe_stage1_auto_formula_out.txt"
L: list[str] = []


def w(s: str = "") -> None:
    L.append(s)


def txt(ws, r, c, limit=1500):
    v = ws.cell(r, c).value
    t = v.text if hasattr(v, "text") else v
    if t is None:
        return None
    s = str(t)
    return s if len(s) <= limit else s[:limit] + f"…(총 {len(s)}자)"


wb = openpyxl.load_workbook(SRC, data_only=False)
try:
    ws = wb["1차필터(7기본필터)"]
    cols = {}
    for c in range(1, ws.max_column + 1):
        v = ws.cell(4, c).value
        if isinstance(v, int):
            cols[v] = c
    w(f"회차 라벨 열: {cols}")
    cN = cols.get(1240)
    cO = cols.get(1239)
    w(f"\n=== 열 N({cN}) = 회차 1240 : 규칙행 5,6,7,8 수식 원문")
    for r in (5, 6, 7, 8):
        w(f"  N{r} = {txt(ws, r, cN)}")
    w(f"\n=== 같은 열 N 헬퍼행 1500~1516 수식 원문")
    for r in range(1500, 1517):
        w(f"  N{r} = {txt(ws, r, cN, 400)}")
    w(f"\n=== 열 O({cO}) = 회차 1239 : 5~8행(비교용)")
    for r in (5, 6, 7, 8):
        w(f"  O{r} = {txt(ws, r, cO)}")

    w("\n=== 행별 수식 유무(1~20행 × 14~16열)")
    for r in range(1, 21):
        row = []
        for c in (14, 15, 16):
            v = ws.cell(r, c).value
            row.append("-" if v is None else ("F" if (hasattr(v, "text") or (isinstance(v, str) and v.startswith("="))) else "v"))
        w(f"  r{r}: {row}")

    # 1차추적결과: H/I 가 수식인지 값인지 + 1행 합계 원문
    ws2 = wb["1차추적결과"]
    w("\n=== 1차추적결과 1~3행 × A~S 원문/값")
    for r in (1, 2, 3, 4):
        parts = []
        for c in range(1, 20):
            v = ws2.cell(r, c).value
            t = v.text if hasattr(v, "text") else v
            if t is None:
                continue
            s = str(t)
            parts.append(f"{openpyxl.utils.get_column_letter(c)}{r}={s[:60]}")
        w(f"  r{r}: " + " | ".join(parts))
finally:
    wb.close()

OUT.write_text("\n".join(L), encoding="utf-8")
print(f"written {OUT} ({len(L)} lines)")
