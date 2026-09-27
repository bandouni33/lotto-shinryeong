# -*- coding: utf-8 -*-
"""회차별 1차 통과수를 '오늘 규칙표'로 계산해 시트 저장값과 나란히 비교(읽기 전용).

고정 규칙 378개의 마스크는 앞선 실행에서 캐시해 둔 것을 쓴다
(scratch/_sample_stage1_fixed_mask.npy) → 회차별 차이는 AUTO 2규칙(전 출현번호 0~2,
이웃수 0~4)만 만들므로 회차 수만큼 빠르게 계산된다.

가설 확인: 만약 규칙표가 그 사이에 바뀌었다면(사용자가 J/최소/최대를 수정),
저장값과 오늘 규칙표 계산값의 차이가 회차마다 일정하지 않게 나온다.
차이가 매 회차 **같은 상수**면 규칙표가 그대로였고 AUTO 정의가 틀린 것이고,
회차마다 달라지면 그 사이 규칙/문턱이 바뀐 것이다.

실행: venv312\\Scripts\\python.exe scratch\\compare_stage1_by_round.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import openpyxl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import combo_filter_v2 as cf  # noqa: E402

SRC = ROOT / "★조합생성_후보숫자_추적표" / "조합생성_후보숫자_추적표_샘플.xlsx"
CACHE = ROOT / "scratch" / "_sample_stage1_fixed_mask.npy"
OUT = ROOT / "scratch" / "compare_stage1_by_round_out.txt"
L: list[str] = []


def w(s: str = "") -> None:
    L.append(s)


if not CACHE.exists():
    print("고정 규칙 마스크 캐시가 없습니다 — verify_sample_stage1.py를 먼저 실행하세요")
    raise SystemExit(1)

wb = openpyxl.load_workbook(SRC, data_only=True)
try:
    wsa = wb["전체당첨내역"]
    draws = {}
    for r in range(2, wsa.max_row + 1):
        rr = wsa.cell(r, 1).value
        if isinstance(rr, int):
            draws[rr] = [wsa.cell(r, c).value for c in range(2, 9)]
    wst = wb["1차추적결과"]
    stored = {}
    for r in range(3, wst.max_row + 1):
        rr = wst.cell(r, 1).value
        if isinstance(rr, int):
            stored[rr] = (wst.cell(r, 8).value, wst.cell(r, 9).value)
finally:
    wb.close()

mask = np.load(CACHE)
combos = cf._all_combos()
w(f"고정 규칙 통과(회차 무관) = {int(mask.sum()):,}")
w(f"조합 {len(combos):,}개 · 저장값 있는 회차 {len(stored)}개")
w("")
w(f"{'회차':>6} {'내계산(고정+AUTO2)':>20} {'시트 I':>12} {'차이':>10} {'시트 H':>12}")
deltas = []
for rnd in sorted(stored, reverse=True)[:15]:
    prev7 = [x for x in draws.get(rnd - 1, []) if isinstance(x, int)]
    v_prev = np.zeros(46, dtype=np.int8)
    for x in prev7:
        v_prev[x] = 1
    nb = set()
    for x in prev7:
        for d in (-1, 0, 1):
            if 1 <= x + d <= 45:
                nb.add(x + d)
    v_nb = np.zeros(46, dtype=np.int8)
    for x in nb:
        v_nb[x] = 1
    cnt_prev = v_prev[combos].sum(axis=1)
    cnt_nb = v_nb[combos].sum(axis=1)
    m = mask & (cnt_prev >= 0) & (cnt_prev <= 2) & (cnt_nb >= 0) & (cnt_nb <= 4)
    mine = int(m.sum())
    sh, si = stored[rnd]
    d = (si - mine) if isinstance(si, int) else None
    deltas.append(d)
    w(f"{rnd:>6} {mine:>20,} {si if si is None else format(si, ','):>12} "
      f"{d if d is None else format(d, '+,'):>10} {sh if sh is None else format(sh, ','):>12}")
w("")
w(f"차이 목록: {deltas}")
if deltas and all(x == deltas[0] for x in deltas if x is not None):
    w("→ 차이가 회차마다 동일(상수): 규칙표는 그대로이고 AUTO 정의 쪽이 다르다")
else:
    w("→ 차이가 회차마다 다름: 그 사이 규칙표(고정 규칙/문턱)가 바뀐 것으로 보인다")
OUT.write_text("\n".join(L), encoding="utf-8")
print(f"written {OUT}")
