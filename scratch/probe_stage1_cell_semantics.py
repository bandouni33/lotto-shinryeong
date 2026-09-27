# -*- coding: utf-8 -*-
"""1차필터 판정 셀의 의미 확정(읽기 전용).

확인:
  · 규칙행 수식 **원문 전체**(잘림 없이) — 참/거짓 가지가 각각 무엇을 내는지
  · 20개 회차 열 × 380 활성 규칙 중 시트가 숫자를 적어둔 셀 전부(그 값의 의미)
  · 내 계산이 '위반'이라는데 시트가 빈칸인 셀 1개(같은 조건으로 나란히)

실행: venv312\\Scripts\\python.exe scratch\\probe_stage1_cell_semantics.py
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
SRC = ROOT / "★조합생성_후보숫자_추적표" / "조합생성_후보숫자_추적표_샘플.xlsx"
OUT = ROOT / "scratch" / "probe_stage1_cell_semantics_out.txt"
L: list[str] = []


def w(s: str = "") -> None:
    L.append(s)


def ft(ws, r, c):
    v = ws.cell(r, c).value
    return v.text if hasattr(v, "text") else v


wbv = openpyxl.load_workbook(SRC, data_only=True)
wbf = openpyxl.load_workbook(SRC, data_only=False)
try:
    wsa = wbv["전체당첨내역"]
    draws = {}
    for r in range(2, wsa.max_row + 1):
        rr = wsa.cell(r, 1).value
        if isinstance(rr, int):
            draws[rr] = [wsa.cell(r, c).value for c in range(2, 9)]
    wsv, wsf = wbv["1차필터(7기본필터)"], wbf["1차필터(7기본필터)"]
    cols = {wsv.cell(4, c).value: c for c in range(1, wsv.max_column + 1)
            if isinstance(wsv.cell(4, c).value, int)}

    w("=== 규칙행 8 (홀짝) 열 N(회차 1240) 수식 전문")
    w(str(ft(wsf, 8, 14)))
    w("\n=== 규칙행 5 (전 출현번호) 열 N 수식 전문")
    w(str(ft(wsf, 5, 14)))

    w("\n=== 활성 규칙(380행) × 20회차 열에서 시트가 숫자를 적어둔 셀 전부")
    active = []
    for r in range(5, 1504):
        k, lm = wsv.cell(r, 11).value, wsv.cell(r, 12).value
        if not isinstance(k, (int, float)) or not isinstance(lm, (int, float)):
            continue
        t = ft(wsf, r, 14)
        if isinstance(t, str) and t.startswith("="):
            active.append(r)
    w(f"활성 규칙 {len(active)}개")
    hits = 0
    for rnd, col in sorted(cols.items(), reverse=True):
        for r in active:
            v = wsv.cell(r, col).value
            if v is None or v == "":
                continue
            hits += 1
            j = wsv.cell(r, 10).value
            nums6 = [draws[rnd][i] for i in range(6)]
            tgt = {int(x) for x in re.findall(r"\d+", str(j))} if j else set()
            prev7 = [x for x in draws.get(rnd - 1, []) if isinstance(x, int)]
            if r == 5:
                tgt = set(prev7)
            elif r in (6, 7):
                tgt = {v2 + d for v2 in prev7 for d in (-1, 0, 1) if 1 <= v2 + d <= 45}
            cnt = len(set(nums6) & tgt)
            w(f"  {rnd}회차 row{r} '{wsv.cell(r, 8).value}' 시트값={v!r} min{int(wsv.cell(r,11).value)}"
              f"~max{int(wsv.cell(r,12).value)} targets={len(tgt)} · 내계산 개수={cnt} "
              f"(당첨 {nums6})")
    w(f"→ 시트가 숫자를 적어둔 셀 {hits}개")

    w("\n=== 내가 '위반'이라 한 대표 셀 (시트는 빈칸)")
    for rnd, row in ((1234, 8), (1239, 5), (1228, 9)):
        col = cols[rnd]
        nums6 = [draws[rnd][i] for i in range(6)]
        j = wsv.cell(row, 10).value
        tgt = {int(x) for x in re.findall(r"\d+", str(j))} if j else set()
        prev7 = [x for x in draws.get(rnd - 1, []) if isinstance(x, int)]
        if row == 5:
            tgt = set(prev7)
        cnt = len(set(nums6) & tgt)
        w(f"  {rnd}회차 row{row} '{wsv.cell(row,8).value}' 시트값={wsv.cell(row,col).value!r} "
          f"min{int(wsv.cell(row,11).value)}~max{int(wsv.cell(row,12).value)} "
          f"targets={len(tgt)} 내계산={cnt} 당첨={nums6} 직전7={prev7}")

    w("\n=== 1240회차 열(N) 활성 규칙 캐시값 분포")
    vals = [wsv.cell(r, 14).value for r in active]
    numeric = [v for v in vals if isinstance(v, (int, float))]
    w(f"  캐시값 있는 셀 {len(numeric)}개 / {len(vals)}개, 값 예시 {numeric[:10]}")
finally:
    wbv.close()
    wbf.close()

OUT.write_text("\n".join(L), encoding="utf-8")
print(f"written {OUT} ({len(L)} lines)")
