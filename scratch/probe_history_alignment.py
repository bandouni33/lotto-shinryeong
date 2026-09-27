# -*- coding: utf-8 -*-
"""12개 시트 과거행 정합성 전수 진단(읽기 전용).

각 3차필터 시트의 과거행(8행~마지막)에 대해:
  "그 행의 회차 직전 이력만으로 재계산한 예측순위" == "그 행에 박혀 있는 L:BD"
를 전부 대조한다. 재계산은 **기존 검증된 정합화 로직**을 그대로 쓴다
(candidate_tracker_auto_update._prediction_for — realign_sliding_blocks가 쓰는 함수).

이 검사가 잡아내는 것: 회차·당첨번호와 예측순위가 서로 다른 회차로 어긋난 블록
(2026-09-27에 표본vs최근50회 파일의 3차필터(500회_후보) 시트에서 실제로 났던 사고).
외부 검증기(verify_workbook_ranking.py)는 '행 안에서의 자기정합'만 보므로,
행↔회차 배정이 통째로 밀린 경우는 이 검사가 아니면 드러나지 않는다.

실행: venv312\\Scripts\\python.exe scratch\\probe_history_alignment.py
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import candidate_tracker_auto_update as tracker  # noqa: E402
import weekly_lotto_file_update as weekly  # noqa: E402

TRACKER = ROOT / "★조합생성_후보숫자_추적표"
OUT = ROOT / "scratch" / "probe_history_alignment_out.txt"
TARGETS = {
    "파일1(기준빈도=전체)": TRACKER / "조합생성_후보숫자_추적표_전체표본_윈도우비교.xlsx",
    "파일2(기준빈도=최근500회)": TRACKER / "조합생성_후보숫자_추적표_최근500표본_윈도우비교.xlsx",
}
NUMS = list(range(1, 46))
LINES: list[str] = []


def w(s: str = "") -> None:
    LINES.append(s)


t0 = time.time()
total_rows = 0
total_bad = 0

for label, path in TARGETS.items():
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        ws_all = wb["전체당첨내역"]
        draws = []
        for row in ws_all.iter_rows(min_row=2, max_col=8, values_only=True):
            if row[0] is None:
                continue
            draws.append((int(row[0]), [int(x) for x in row[1:7]]))
        draws.sort(key=lambda t: t[0])
        latest = draws[-1][0]
        w("=" * 78)
        w(f"{label} -> {path.name}  (이력 {len(draws)}회차, 최신 {latest})")

        for sn in [s for s in wb.sheetnames if s.startswith("3차필터")]:
            ws = wb[sn]
            n_window = int(re.search(r"(\d+)", sn).group(1))
            w2 = weekly._window_from_label(ws.cell(2, 11).value)
            w3 = weekly._window_from_label(ws.cell(3, 11).value)
            maxr = ws.max_row
            rows = list(ws.iter_rows(min_row=7, max_row=maxr, max_col=56, values_only=True))
            bad = []
            checked = 0
            for i, row in enumerate(rows):
                r = 7 + i
                rnd_cell = row[0]
                drawn = list(row[1:7])
                ranking = list(row[11:56])
                if (not isinstance(rnd_cell, int) or any(v is None for v in drawn)
                        or any(not isinstance(v, int) for v in ranking) or len(set(ranking)) != 45):
                    continue
                checked += 1
                exp = tracker._prediction_for(draws, rnd_cell, w2, w3)
                if exp is None or ranking != exp:
                    first = next((j for j, (a, b) in enumerate(zip(ranking, exp or [])) if a != b), 0)
                    bad.append(f"{r}행({rnd_cell}회차) {first + 1}위: 시트 {ranking[first]} vs 재계산 "
                               f"{exp[first] if exp else None}")
            total_rows += checked
            total_bad += len(bad)
            w(f"  ── {sn}: 창(2행)={w2 or '전체'} 창(3행)={w3}  검사 {checked}행, "
              f"불일치 {len(bad)}행  (블록 {7}~{maxr}행)")
            for b in bad[:6]:
                w(f"       ! {b}")
            if len(bad) > 6:
                w(f"       ... 외 {len(bad) - 6}행")
    finally:
        wb.close()

w("=" * 78)
w(f"총 검사 {total_rows}행 / 불일치 {total_bad}행 / 경과 {time.time() - t0:.1f}s")
OUT.write_text("\n".join(LINES), encoding="utf-8")
print(f"written {OUT} ({len(LINES)} lines)  bad={total_bad} rows={total_rows} {time.time() - t0:.1f}s")
