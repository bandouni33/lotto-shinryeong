# -*- coding: utf-8 -*-
"""★조합생성_후보숫자_추적표 폴더 5개 파일 전수 진단(읽기 전용).

중점: 컬럼식 구조 파일 2개(샘플 / 200회검증용)의 서식·수식 오류와 회차 참조,
      그리고 3차필터 구조 파일 3개와의 차이.
      엑셀 오류값(#REF! 등)은 두 읽기 모드(수식/캐시) 모두에서 스캔한다.

실행: venv312\\Scripts\\python.exe scratch\\probe_sample_file_health.py
"""
from __future__ import annotations

import datetime
import os
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
TRACKER = ROOT / "★조합생성_후보숫자_추적표"
OUT = ROOT / "scratch" / "probe_sample_file_health_out.txt"
ERRS = {"#REF!", "#VALUE!", "#DIV/0!", "#NAME?", "#NULL!", "#NUM!", "#N/A", "#GETTING_DATA"}

TARGETS = {
    "샘플": TRACKER / "조합생성_후보숫자_추적표_샘플.xlsx",
    "200회검증용": TRACKER / "조합생성_후보숫자_추적표_샘플_200회검증용.xlsx",
    "전체표본_윈도우비교": TRACKER / "조합생성_후보숫자_추적표_전체표본_윈도우비교.xlsx",
    "최근500표본_윈도우비교": TRACKER / "조합생성_후보숫자_추적표_최근500표본_윈도우비교.xlsx",
    "표본vs최근50회": TRACKER / "★후보숫자_추적표_표본vs최근50회.xlsx",
}
LINES: list[str] = []


def w(s: str = "") -> None:
    LINES.append(s)


def is_err(v) -> bool:
    return isinstance(v, str) and v.strip().upper().startswith("#") and v.strip().upper() in ERRS


for label, path in TARGETS.items():
    w("=" * 78)
    w(f"{label}: {path.name}")
    w(f"  mtime={datetime.datetime.fromtimestamp(path.stat().st_mtime):%Y-%m-%d %H:%M} size={path.stat().st_size:,}")

    # 1) 캐시값 읽기(오류값 스캔 + 구조)
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        w(f"  SHEETS({len(wb.sheetnames)}): {wb.sheetnames}")
        errors: list[str] = []
        for sn in wb.sheetnames:
            ws = wb[sn]
            for row in ws.iter_rows():
                for c in row:
                    if is_err(c.value):
                        errors.append(f"{sn}!{c.coordinate}={c.value}")
        w(f"  캐시값 오류 셀: {len(errors)}개 {errors[:8]}")
        if "전체당첨내역" in wb.sheetnames:
            ws = wb["전체당첨내역"]
            rounds = [ws.cell(r, 1).value for r in range(2, ws.max_row + 1)
                      if isinstance(ws.cell(r, 1).value, int)]
            w(f"  전체당첨내역: max_row={ws.max_row} 최신값행={max(rounds) if rounds else None} "
              f"(총 {len(rounds)}행, 위에서 3행: {[ws.cell(r, 1).value for r in (2,3,4)]})")
    finally:
        wb.close()

    # 2) 수식 읽기(오류값 문자열 + 수식 셀 수 + 회차 참조)
    wbf = openpyxl.load_workbook(path, data_only=False, read_only=True)
    try:
        for sn in wbf.sheetnames:
            ws = wbf[sn]
            fcount = 0
            errs_f: list[str] = []
            for row in ws.iter_rows():
                for c in row:
                    v = c.value
                    if isinstance(v, str) and v.startswith("="):
                        fcount += 1
                        if is_err(v):
                            errs_f.append(f"{c.coordinate}={v}")
                    if hasattr(v, "text"):
                        fcount += 1
            w(f"  [{sn}] rows={ws.max_row} cols={ws.max_column} 수식셀={fcount} 수식오류={errs_f[:5]}")
    finally:
        wbf.close()

    # 3) 회차 참조 현황 — '회차' 라벨/숫자 1240~1250 등장 위치
    wb = openpyxl.load_workbook(path, data_only=True)
    try:
        hits: list[str] = []
        for sn in wb.sheetnames:
            ws = wb[sn]
            for row in ws.iter_rows():
                for c in row:
                    v = c.value
                    if isinstance(v, int) and 1230 <= v <= 1250:
                        hits.append(f"{sn}!{c.coordinate}={v}")
                    elif isinstance(v, str) and any(str(y) in v for y in range(1230, 1251)):
                        if len(v) < 40:
                            hits.append(f"{sn}!{c.coordinate}={v!r}")
        w(f"  회차 숫자/문자 등장 셀: {len(hits)}개 → {hits[:14]}")
    finally:
        wb.close()

OUT.write_text("\n".join(LINES), encoding="utf-8")
print(f"written {OUT} ({len(LINES)} lines)")
