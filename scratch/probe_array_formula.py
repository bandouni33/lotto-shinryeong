# -*- coding: utf-8 -*-
"""두 윈도우비교 파일의 3차필터 시트 수식 원문 패턴 확인(읽기 전용).

확인 항목:
  · 2행(기준빈도) / 3행(최근N회) / 4행(오차) 수식이 어느 범위를 읽는지
  · 7행(대기 예측행) L:BD = 배열수식 45칸의 text 가
    =INDEX(L$1:BD$1,MATCH(LARGE((L$4:BD$4*1000-L$1:BD$1),1),...)) 패턴인지
  · 3행 수식의 창 상수(MAX(...)-K)가 시트 이름의 N과 일치하는지 (K == N-1)
"""
from __future__ import annotations

import re
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
TRACKER = ROOT / "★조합생성_후보숫자_추적표"
OUT = ROOT / "scratch" / "probe_array_formula_out.txt"
TARGETS = {
    "파일1 K2=기준빈도(전체)": TRACKER / "조합생성_후보숫자_추적표_전체표본_윈도우비교.xlsx",
    "파일2 K2=기준빈도(최근500회)": TRACKER / "조합생성_후보숫자_추적표_최근500표본_윈도우비교.xlsx",
}
LINES: list[str] = []


def w(s: str = "") -> None:
    LINES.append(s)


def text_of(v):
    return v.text if hasattr(v, "text") else v


for label, path in TARGETS.items():
    w("=" * 78)
    w(f"{label} -> {path.name}")
    wb = openpyxl.load_workbook(path, read_only=True, data_only=False)
    try:
        for sn in [s for s in wb.sheetnames if s.startswith("3차필터")]:
            ws = wb[sn]
            rows = {}
            for r in (2, 3, 4, 7):
                for row in ws.iter_rows(min_row=r, max_row=r, values_only=True):
                    rows[r] = list(row)
            w(f"\n── {sn}")
            w(f"   이름창(N) = {re.search(r'(\d+)', sn).group(1)}")
            w(f"   K2={ws.cell(2, 11).value!r}  K3={ws.cell(3, 11).value!r}")
            w(f"   2행 L = {text_of(rows[2][11])}")
            w(f"   3행 L = {str(text_of(rows[3][11]))[:260]}")
            w(f"   4행 L = {text_of(rows[4][11])}")
            w(f"   3행 BD = {str(text_of(rows[3][44]))[:120]}")
            # 창 상수
            m = re.search(r"MAX\([^)]*\)-(\d+)", str(text_of(rows[3][11])))
            w(f"   3행 창 상수 MAX(...)-{m.group(1) if m else '없음'}  → 창 = "
              f"{int(m.group(1)) + 1 if m else '?'}회")
            # 7행 배열수식 text
            l7 = rows[7][11:56]
            kinds = {}
            for v in l7:
                kinds[type(v).__name__] = kinds.get(type(v).__name__, 0) + 1
            w(f"   7행 L:BD 종류 = {kinds}")
            w(f"   7행 L text = {text_of(l7[0])}")
            w(f"   7행 M text = {text_of(l7[1])}")
            w(f"   7행 BD text = {text_of(l7[44])}")
            pat = re.compile(
                r"^=INDEX\(L\$1:BD\$1,MATCH\(LARGE\(\(L\$4:BD\$4\*1000-L\$1:BD\$1\),(\d+)\),"
                r"LARGE\(\(L\$4:BD\$4\*1000-L\$1:BD\$1\),(\d+)\),0\)\)$")
            ok = []
            for i, v in enumerate(l7, start=1):
                t = str(text_of(v))
                mm = pat.match(t.replace(" ", ""))
                ok.append(bool(mm) and int(mm.group(1)) == i and int(mm.group(2)) == i)
            w(f"   INDEX/MATCH/LARGE 패턴 일치 = {sum(ok)}/45")
            if not all(ok):
                idx = [i for i, o in enumerate(ok, 1) if not o]
                w(f"   불일치 위치(45칸 기준) = {idx[:10]}")
                w(f"   예시(불일치): {text_of(l7[idx[0] - 1])}")
    finally:
        wb.close()

OUT.write_text("\n".join(LINES), encoding="utf-8")
print(f"written {OUT} ({len(LINES)} lines)")
