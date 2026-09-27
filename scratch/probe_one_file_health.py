# -*- coding: utf-8 -*-
"""추적표 파일 1개 진단(읽기 전용) — 샘플/200회검증용처럼 컬럼식 구조 파일용.

사용: python scratch/probe_one_file_health.py sample
      (sample | verify | 전체표본 | 최근500표본 | 표본vs최근50회)
결과: scratch/probe_one_file_health_out_<키>.txt (UTF-8)
"""
from __future__ import annotations

import datetime
import os
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
TRACKER = ROOT / "★조합생성_후보숫자_추적표"
FILES = {
    "sample": TRACKER / "조합생성_후보숫자_추적표_샘플.xlsx",
    "verify": TRACKER / "조합생성_후보숫자_추적표_샘플_200회검증용.xlsx",
}
ERRS = {"#REF!", "#VALUE!", "#DIV/0!", "#NAME?", "#NULL!", "#NUM!", "#N/A"}
key = sys.argv[1] if len(sys.argv) > 1 else "sample"
path = FILES[key]
OUT = ROOT / "scratch" / f"probe_one_file_health_out_{key}.txt"
LINES: list[str] = []


def w(s: str = "") -> None:
    LINES.append(s)


def is_err(v) -> bool:
    return isinstance(v, str) and v.strip().upper() in ERRS


w(f"{path.name}  mtime={datetime.datetime.fromtimestamp(path.stat().st_mtime):%Y-%m-%d %H:%M} "
  f"size={path.stat().st_size:,}")

# ── 1) 캐시값: 오류값 + 시트별 모양 + 회차 등장 셀
wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
try:
    w(f"SHEETS({len(wb.sheetnames)}): {wb.sheetnames}")
    for sn in wb.sheetnames:
        ws = wb[sn]
        errs, rounds, nonempty = [], [], 0
        for row in ws.iter_rows():
            for c in row:
                v = c.value
                if v is None:
                    continue
                nonempty += 1
                if is_err(v):
                    errs.append(f"{c.coordinate}={v}")
                if isinstance(v, int) and 1200 <= v <= 1260:
                    rounds.append(f"{c.coordinate}={v}")
                elif isinstance(v, str) and any(str(y) in v for y in range(1238, 1250)) and len(v) < 40:
                    rounds.append(f"{c.coordinate}={v!r}")
        w(f"  [{sn}] rows={ws.max_row} cols={ws.max_column} 값셀={nonempty} "
          f"오류셀={len(errs)}{errs[:5]} 회차셀={len(rounds)}{rounds[:8]}")
finally:
    wb.close()

# ── 2) 수식 보기: 수식셀 수 + SUM 수식이 자기 행을 가리키는지(J열) + 1행 합계 범위
wf = openpyxl.load_workbook(path, data_only=False, read_only=True)
try:
    for sn in wf.sheetnames:
        ws = wf[sn]
        fcount, jbads, sums = 0, [], []
        for row in ws.iter_rows():
            for c in row:
                v = c.value
                t = v.text if hasattr(v, "text") else v
                if isinstance(t, str) and t.startswith("="):
                    fcount += 1
                    if c.column == 10 and t.upper().startswith("=SUM("):
                        want = f"=SUM(K{c.row}:M{c.row})"
                        if t.upper().replace(" ", "") != want.upper():
                            jbads.append(f"J{c.row}={t}")
                    if c.row == 1 and t.upper().startswith("=SUM(") and 11 <= c.column <= 16:
                        sums.append(f"{c.coordinate}={t}")
        w(f"  [{sn}] 수식셀={fcount} J열 불일치={len(jbads)}{jbads[:6]} 1행 합계={sums}")
finally:
    wf.close()

OUT.write_text("\n".join(LINES), encoding="utf-8")
print(f"written {OUT} ({len(LINES)} lines)")
