# -*- coding: utf-8 -*-
"""3차필터(순번세우기·적중수) 시트 검증 — 워크북이 실제로 맞는지 독립 재계산으로 대조.

2026-09-27 개정 이력(중요 — 이 검증기 자체의 버그 3개를 고친 뒤의 버전):
  ① 시트 이름에 파일 라벨을 붙여 넘겨서 "표본vs최근50회/..."의 '50회'가 창으로 잘못 파싱됐다
     → 이제 시트 이름만 넘긴다.
  ② 창 후보 목록에서 '최근50'을 빼먹어(창이 50일 때) 정상 시트를 불일치로 몰았다
     → 전체/500/시트N/50 네 후보를 항상 비교한다.
  ③ 1행(L1:BD1 = 1~45 고정)이 당연히 순열이라 '순번 행'으로 잘못 잡혀 모든 시트가 거짓 FAIL
     → 1행을 제외하고, 회차번호가 들어 있는 과거블록 직전의 순열 행을 순번 행으로 고른다.

가정하지 않는 것: 2행·3행이 어떤 창(전체/500/N/50)인지는 **시트에서 역으로 찾아** 출력한다.
4행(오차)과 순번은 **시트 자신의 2행·3행을 재료로** 재계산해 대조한다(함수오류 검출).
배포 엔진(combo_filter_v2._gap_order_for_anchor) 대조는 정의가 일치할 때만 한다.

실행(읽기 전용):  venv312\\Scripts\\python.exe scratch\\verify_workbook_ranking.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

TRACKER = ROOT / "★조합생성_후보숫자_추적표"
FILES = {
    "전체표본": TRACKER / "조합생성_후보숫자_추적표_전체표본_윈도우비교.xlsx",
    "최근500표본": TRACKER / "조합생성_후보숫자_추적표_최근500표본_윈도우비교.xlsx",
    "최근300표본": TRACKER / "조합생성_후보숫자_추적표_최근300표본_윈도우비교.xlsx",
    "표본vs최근50회": TRACKER / "★후보숫자_추적표_표본vs최근50회.xlsx",
}
NUMS = list(range(1, 46))
FAILS: list[str] = []


def fail(msg: str) -> None:
    FAILS.append(msg)
    print(f"    FAIL  {msg}")


def note(msg: str) -> None:
    print(f"    {msg}")


def window_of(sheet_name: str) -> int | None:
    m = re.search(r"(\d+)\s*회", sheet_name)
    return int(m.group(1)) if m else None


def load_draws(ws_all):
    draws = []
    for r in ws_all.iter_rows(min_row=2, values_only=True):
        if r[0] is None:
            continue
        draws.append((int(r[0]), [int(x) for x in r[1:7]], int(r[7] or 0)))
    draws.sort(key=lambda t: t[0])
    return draws


def window_counts(draws, w) -> dict[int, int]:
    lo = draws[0][0] if (w is None or w >= len(draws)) else draws[-1][0] - (w - 1)
    return {n: sum(1 for r, ns, _ in draws if r >= lo and n in ns) for n in NUMS}


def comp_ranks(vals: dict[int, int]) -> dict[int, int]:
    """엑셀 RANK(x,범위,0)+COUNTIFS(동점&작은번호)와 동일한 고유 순위."""
    return {n: (1 + sum(1 for m in NUMS if vals[m] > vals[n])
                + sum(1 for m in NUMS if vals[m] == vals[n] and m < n)) for n in NUMS}


def sheet_row(ws, r) -> list:
    return [ws.cell(r, c).value for c in range(12, 57)]


def is_perm(vals) -> bool:
    return sorted(v for v in vals if v is not None) == NUMS


def check_sheet(name: str, ws, draws, app_gap_order=None) -> dict:
    n_win = window_of(name)
    cands: list[tuple[str, dict[int, int]]] = [("전체", window_counts(draws, None))]
    for w in (500, n_win, 50):
        if w and all(w != existing for existing, _ in cands):
            cands.append((f"최근{w}", window_counts(draws, w)))

    st = {"hist": 0, "bad": 0}
    print(f"\n  ── {name}")
    if not is_perm(sheet_row(ws, 1)):
        fail(f"{name}: L1:BD1이 1~45 순열이 아님")

    row2, row3 = sheet_row(ws, 2), sheet_row(ws, 3)
    m2 = next((lbl for lbl, c in cands if all(row2[n - 1] == c[n] for n in NUMS)), None)
    m3 = next((lbl for lbl, c in cands if all(row3[n - 1] == c[n] for n in NUMS)), None)
    note(f"2행 기준빈도 = {m2 or '불일치'}, 3행 빈도 = {m3 or '불일치'}")
    if m2 is None:
        fail(f"{name}: 2행이 어느 창과도 불일치 → 앞5개 {row2[:5]}")
    if m3 is None:
        fail(f"{name}: 3행이 어느 창과도 불일치 → 앞5개 {row3[:5]}")

    v2, v3 = {n: row2[n - 1] for n in NUMS}, {n: row3[n - 1] for n in NUMS}
    r2, r3 = comp_ranks(v2), comp_ranks(v3)
    gap = {n: r3[n] - r2[n] for n in NUMS}
    row4 = sheet_row(ws, 4)
    bad4 = [n for n in NUMS if row4[n - 1] != gap[n]]
    if bad4:
        fail(f"{name}: 4행 오차가 자기 기준행(2·3행) 재계산과 불일치 {len(bad4)}개 "
             f"(예: 번호 {bad4[:5]} → 시트 {[row4[n - 1] for n in bad4[:5]]} vs 재계산 {[gap[n] for n in bad4[:5]]})")
    else:
        note("4행 오차 = 자기 2·3행 기준 재계산과 완전 일치")

    # 회차번호(>=1000)가 들어 있는 행부터가 '과거회차 블록'이다. 이 블록의 첫 행이
    # 바로 다음회차 예측(순번세우기 결과)이고(=전체표본·최근500표본 계열), 그 파일이
    # 아닌 경우(표본vs최근50회의 기준N회 계열)는 블록 직전의 순열 행이 순번 행이다.
    block_start = next((r for r in range(2, ws.max_row + 1)
                        if isinstance(ws.cell(r, 1).value, int) and ws.cell(r, 1).value >= 1000), None)
    perms = [r for r in range(2, (block_start or 13) + 1) if is_perm(sheet_row(ws, r))]
    if block_start and is_perm(sheet_row(ws, block_start)):
        pend_row = block_start
    else:
        before = [r for r in perms if block_start is None or r < block_start]
        pend_row = max(before) if before else (max(perms) if perms else None)

    order = sorted(NUMS, key=lambda n: (-gap[n], n))
    if pend_row is None:
        fail(f"{name}: 1~45 순열인 '순번 행'을 찾지 못함")
    else:
        pend = sheet_row(ws, pend_row)
        if list(pend) != order:
            first = next(i for i, (a, b) in enumerate(zip(pend, order)) if a != b)
            fail(f"{name}: 순번 행({pend_row}행)이 자기 오차 기준 정렬과 다름 — {first + 1}위: "
                 f"시트 {pend[first]} vs 재계산 {order[first]}")
        else:
            note(f"순번 행({pend_row}행) = (-오차,번호) 정렬과 완전 일치 · 앞5개 {pend[:5]} · "
                 f"A{pend_row}={ws.cell(pend_row, 1).value}")

    if block_start:
        for r in range(block_start, ws.max_row + 1):
            rnd = ws.cell(r, 1).value
            if not isinstance(rnd, int):
                continue
            frozen, drawn = sheet_row(ws, r), [ws.cell(r, c).value for c in range(2, 8)]
            if any(v is None for v in frozen) or any(v is None for v in drawn):
                continue
            st["hist"] += 1
            exp = [sum(1 for d in drawn if d in set(frozen[i * 15:(i + 1) * 15])) for i in range(3)]
            got = [ws.cell(r, c).value for c in (9, 10, 11)]
            if exp != got or sum(exp) != 6:
                st["bad"] += 1
                if st["bad"] <= 2:
                    fail(f"{name}: {rnd}회차 적중수 시트 {got} vs 재계산 {exp} (합={sum(exp)})")
        note(f"과거 블록 {st['hist']}행 검사(시작 {block_start}행) · 적중수 불일치 {st['bad']}행")
        if st["bad"] > 2:
            fail(f"{name}: 과거 블록 적중수 불일치 총 {st['bad']}행")

    if app_gap_order is not None and pend_row is not None:
        pend = sheet_row(ws, pend_row)
        if list(pend) == list(app_gap_order):
            note("★ 배포 엔진 gap_order와 완전 일치")
        else:
            first = next((i for i, (a, b) in enumerate(zip(pend, app_gap_order)) if a != b), None)
            fail(f"{name}: 배포 엔진 gap_order와 다름 — {first}번째: 시트 {pend[first]} vs 엔진 {app_gap_order[first]}")
    return st


def main() -> int:
    import combo_filter_v2 as cf

    checked = 0
    for label, path in FILES.items():
        wb = openpyxl.load_workbook(path, data_only=True)
        draws = load_draws(wb["전체당첨내역"])
        hist_asc = [{"draw_round": r, "nums": ns, "bonus": b} for r, ns, b in draws]
        all_c, n100_c = window_counts(draws, None), window_counts(draws, cf.RECENT_WINDOW)
        print(f"\n=== {label} ({len(draws)}회차, 최신 {draws[-1][0]}) ===")
        for sn in [s for s in wb.sheetnames
                   if s.startswith("3차필터") or re.match(r"기준\d+회_후보$", s)]:
            ws = wb[sn]
            app = None
            if window_of(sn) == cf.RECENT_WINDOW:
                r2 = {i: ws.cell(2, 11 + i).value for i in NUMS}
                r3 = {i: ws.cell(3, 11 + i).value for i in NUMS}
                if all(r2[i] == all_c[i] for i in NUMS) and all(r3[i] == n100_c[i] for i in NUMS):
                    anchor = (ws.cell(7, 1).value or 0) - 1
                    if anchor in {r for r, _, _ in draws}:
                        app = cf._gap_order_for_anchor(hist_asc, anchor)
            check_sheet(sn, ws, draws, app)
            checked += 1
        wb.close()

    print("\n" + "=" * 70)
    print(f"시트 {checked}개 검사 완료 / 문제 {len(FAILS)}건")
    for f in FAILS:
        print("  - " + f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
