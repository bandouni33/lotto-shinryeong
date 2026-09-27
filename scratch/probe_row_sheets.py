# -*- coding: utf-8 -*-
"""행 단위 시트 구조 정밀 덤프 — 전진(행 삽입) 자동화 설계용 (읽기 전용).

대상: 샘플 파일의
  · 1차추적결과 / 2차추적결과 / 4차필터 : 3행부터 회차별 1행, 어디까지 값이고 어디부터 수식인가
  · 3차필터(100출현빈도순 후보)        : 7행(대기) / 8행(확정) 구조와 S~BK 후보 수식
  · 회차별 추적표                      : 3행부터 회차별 1행, S열 이후 등급 보드
목적: 컬럼 전진과 같은 방식(임시 복사본 불변식 → 실물)으로 행 전진을 만들기 위한 근거 확보.

실행: venv312\\Scripts\\python.exe scratch\\probe_row_sheets.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter as cl

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
SRC = ROOT / "★조합생성_후보숫자_추적표" / "조합생성_후보숫자_추적표_샘플.xlsx"
OUT = ROOT / "scratch" / "probe_row_sheets_out.txt"
SHEETS = ("1차추적결과", "2차추적결과", "4차필터", "3차필터(100출현빈도순 후보)", "회차별 추적표")
L: list[str] = []


def w(s: str = "") -> None:
    L.append(str(s))
    print(s, flush=True)


def txt(v, n: int = 120) -> str:
    if v is None:
        return "None"
    if hasattr(v, "text"):
        t = v.text
        return t if len(t) <= n else t[:n] + "…"
    s = str(v)
    return s if len(s) <= n else s[:n] + "…"


def isf(v) -> bool:
    return hasattr(v, "text") or (isinstance(v, str) and v.startswith("="))


wv = openpyxl.load_workbook(SRC, data_only=True)
wf = openpyxl.load_workbook(SRC, data_only=False)
try:
    for sn in SHEETS:
        wv_s, wf_s = wv[sn], wf[sn]
        w(f"\n=== {sn}: rows={wv_s.max_row} cols={wv_s.max_column} ===")
        # 1~4행 상세(수식/값)
        for r in range(1, min(5, wv_s.max_row) + 1):
            parts = []
            for c in range(1, min(wv_s.max_column, 22) + 1):
                v, f = wv_s.cell(r, c).value, wf_s.cell(r, c).value
                if v is None and f is None:
                    continue
                parts.append(f"{cl(c)}{r}={txt(v, 40)}" + (f" [식 {txt(f, 90)}]" if isf(f) else ""))
            if parts:
                w(f"  ★row{r}: " + " | ".join(parts))
        # 컬럼별 '값/수식' 분포: 데이터 행 구간에서 각 열이 수식인지 값인지
        data_rows = list(range(3, min(wv_s.max_row, 12) + 1))
        w(f"  -- 3~{data_rows[-1]}행 열별 성격 --")
        for c in range(1, min(wv_s.max_column, 22) + 1):
            vals = [wf_s.cell(r, c).value for r in data_rows]
            nf = sum(1 for v in vals if isf(v))
            nv = sum(1 for v in vals if v is not None and not isf(v))
            if nf or nv:
                sample = txt(vals[0], 70)
                w(f"    {cl(c)}{data_rows[0]}: 수식{nf} 값{nv} 예시={sample}")
        # 꼬리 행(마지막 4행) — 창 크기 확인
        w(f"  -- 꼬리 행 --")
        for r in range(max(3, wv_s.max_row - 3), wv_s.max_row + 1):
            parts = [f"{cl(c)}{r}={txt(wv_s.cell(r, c).value, 30)}"
                     for c in range(1, min(wv_s.max_column, 12) + 1)
                     if wv_s.cell(r, c).value is not None]
            w(f"    row{r}: " + " | ".join(parts))
        # 후보열(S~) 구간 표본: 3차필터/회차별 추적표만
        if sn.startswith("3차필터") or sn == "회차별 추적표":
            w(f"  -- S~BK 구간 수식 표본(row2, row3, row7) --")
            for r in (2, 3, 7):
                if r > wv_s.max_row:
                    continue
                for c in range(19, min(wv_s.max_column, 63) + 1):
                    f = wf_s.cell(r, c).value
                    if isf(f):
                        w(f"    {cl(c)}{r} = {txt(f, 200)}")
                        break
                else:
                    w(f"    row{r}: S~BK에 수식 없음")
            w(f"  -- S~BK 값 표본(row7, row8) --")
            for r in (7, 8):
                if r > wv_s.max_row:
                    continue
                vals = [wv_s.cell(r, c).value for c in range(19, min(wv_s.max_column, 63) + 1)]
                w(f"    row{r}: {vals[:12]} … (총 {len(vals)}칸, 빈칸 {sum(1 for v in vals if v is None)})")
finally:
    wv.close()
    wf.close()

OUT.write_text("\n".join(L), encoding="utf-8")
print(f"written {OUT} ({len(L)}줄)")
sys.exit(0)
