# -*- coding: utf-8 -*-
"""샘플 파일 1차/2차/4차 통과수·등수별·누락원인 재현 검증 (읽기 전용, 실물 무변경).

확정된 정의
  1차 = 고정 378규칙(J=번호목록, K/L 범위)
  AUTO 3규칙 = 전 출현번호(직전 7개 ∩), 이웃수(±1), 후보패턴 이웃수(격차순위 이웃)
  2차 = 이격수 48규칙: gaps = diff(정렬된 6번호) 5개 중 J 목록값의 개수 ∈ [K,L]
  4차 = 2차 통과 중 격차순위 상중하(15개씩) 각 [0~4 → 1242회차부터 1~4],
        상위 [top1~3 중 ≥1 → top1~5 중 ≥1]
  상중하/top5 = 앱 기준점 combo_filter_v2._gap_order_for_anchor (RECENT_WINDOW=100)

검증 방식
  ① 후보 조합을 여러 개 만들어 시트 저장값(I열 3개)과 대조 → 어떤 조합이 재현되는지 실측
  ② 일치가 확인되면 그 구성으로 K~R 등수별·S 누락원인까지 대조
  ③ 불변식: 규칙표 일치, 필터 추가 시 수량 단조감소, 0 ≤ I ≤ H, 실물 파일 무변경

실행: venv312\\Scripts\\python.exe scratch\\verify_sample_stage2_4.py [회차 ...]
"""
from __future__ import annotations

import hashlib
import itertools
import json
import os
import re
import sys
import time
from pathlib import Path

import numpy as np
import openpyxl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import combo_filter_v2 as cf  # noqa: E402

from env_loader import load_dotenv_file  # noqa: E402

load_dotenv_file()

SRC = ROOT / "★조합생성_후보숫자_추적표" / "조합생성_후보숫자_추적표_샘플.xlsx"
CACHE = ROOT / "scratch" / "_sample_stage1_fixed_mask.npy"
OUT = ROOT / "scratch" / "verify_sample_stage2_4_out.txt"
ROUNDS = [int(x) for x in sys.argv[1:]] or [1241, 1240, 1239]

R: list[str] = []
FAILS: list[str] = []
t0 = time.time()


def w(s: str = "") -> None:
    R.append(s)
    print(s, flush=True)


def ok(cond: bool, msg: str) -> bool:
    if cond:
        w(f"  ok   {msg}")
    else:
        FAILS.append(msg)
        w(f"  FAIL {msg}")
    return bool(cond)


# ── 시트 저장값 읽기
wb = openpyxl.load_workbook(SRC, data_only=True)
try:
    wsa = wb["전체당첨내역"]
    draws: dict[int, list[int]] = {}
    for r in range(2, wsa.max_row + 1):
        rr = wsa.cell(r, 1).value
        if isinstance(rr, int):
            draws[rr] = [wsa.cell(r, c).value for c in range(2, 9)]
    latest = max(draws)

    stored: dict[str, dict[int, dict]] = {}
    for sh, has_s in (("1차추적결과", True), ("2차추적결과", True), ("4차필터", False)):
        ws = wb[sh]
        d: dict[int, dict] = {}
        for r in range(3, ws.max_row + 1):
            rr = ws.cell(r, 1).value
            if not isinstance(rr, int):
                continue
            d[rr] = {
                "H": ws.cell(r, 8).value, "I": ws.cell(r, 9).value,
                "K": ws.cell(r, 11).value, "L": ws.cell(r, 12).value,
                "M": ws.cell(r, 13).value,
                "N": ws.cell(r, 14).value, "O": ws.cell(r, 15).value,
                "P": ws.cell(r, 16).value, "Q": ws.cell(r, 17).value,
                "R": ws.cell(r, 18).value,
                "S": ws.cell(r, 19).value if has_s else None,
            }
        stored[sh] = d

    # 파일 2차 시트 규칙표(J/K/L) — 행 5..60
    ws2 = wb["2차필터(5이격수)"]
    file_gap = []
    for r in range(5, 61):
        j, k, lm = ws2.cell(r, 10).value, ws2.cell(r, 11).value, ws2.cell(r, 12).value
        if j is None or not isinstance(k, (int, float)) or not isinstance(lm, (int, float)):
            continue
        tgt = sorted({int(x) for x in re.findall(r"\d+", str(j))})
        file_gap.append({"row": r, "targets": tgt, "min": int(k), "max": int(lm)})
finally:
    wb.close()

w(f"실물 sha(앞12) = {hashlib.sha256(SRC.read_bytes()).hexdigest()[:12]}")
w(f"전체당첨내역 최신 회차 = {latest} · 저장값 있는 회차수 "
  f"{ {k: len(v) for k, v in stored.items()} }")
w(f"파일 2차 시트 규칙행 = {len(file_gap)}개 (행 {file_gap[0]['row']}~{file_gap[-1]['row']})")

# ── 규칙표: 앱 기준점과 파일 시트 일치 확인
_, _, app_gap = cf._load_rules()
app_gap_cmp = [{"targets": sorted({int(x) for x in r["targets"]}),
                "min": int(r["min"]), "max": int(r["max"])} for r in app_gap]
file_gap_cmp = [{"targets": r["targets"], "min": r["min"], "max": r["max"]} for r in file_gap]
w("\n== 규칙표 일치 ==")
ok(len(app_gap_cmp) == len(file_gap_cmp),
   f"2차 규칙 개수 파일 {len(file_gap_cmp)} == 앱 {len(app_gap_cmp)}")
ok(app_gap_cmp == file_gap_cmp, "2차 이격수 규칙 내용 파일 == 앱 기준점(combo_filter_v2)")

# ── 고정 378 규칙 마스크(캐시) — 회차 무관
combos = cf._all_combos()
fixed = np.load(CACHE)
ok(fixed.shape[0] == combos.shape[0],
   f"고정 마스크 길이 {fixed.shape[0]} == 조합수 {combos.shape[0]}")
w(f"고정 378규칙 통과 = {int(fixed.sum()):,} (회차 무관)")

# ── 이격수 48규칙 마스크
gaps = np.diff(combos, axis=1)
t = time.time()
gap_mask = np.ones(combos.shape[0], dtype=bool)
for r in app_gap:
    lut = np.zeros(cf.MAXGAP + 1, dtype=np.int8)
    for x in r["targets"]:
        if 0 <= x <= cf.MAXGAP:
            lut[x] = 1
    c = lut[gaps].sum(axis=1)
    gap_mask &= (c >= r["min"]) & (c <= r["max"])
base = fixed & gap_mask
w(f"[{time.time() - t0:.1f}s] 이격수 48규칙 적용 → 고정&이격 = {int(base.sum()):,}")

# ── 파일 1차 시트의 1차 규칙표(고정 378 + AUTO 3) 일치 확인
wbf = openpyxl.load_workbook(SRC, data_only=True)
try:
    ws1 = wbf["1차필터(7기본필터)"]
    file_static, file_auto = [], []
    for r in range(5, 1504):
        j, k, lm = ws1.cell(r, 10).value, ws1.cell(r, 11).value, ws1.cell(r, 12).value
        if not isinstance(k, (int, float)) or not isinstance(lm, (int, float)):
            continue
        if j is None:
            continue
        if str(j).strip().upper() == "AUTO":
            file_auto.append({"row": r, "name": ws1.cell(r, 8).value,
                              "min": int(k), "max": int(lm)})
        else:
            file_static.append({"row": r, "targets": sorted({int(x) for x in re.findall(r"\d+", str(j))}),
                                "min": int(k), "max": int(lm)})
finally:
    wbf.close()

app_static, app_auto, _ = cf._load_rules()
app_static_cmp = [{"targets": sorted({int(x) for x in r["targets"]}),
                   "min": int(r["min"]), "max": int(r["max"])} for r in app_static]
file_static_cmp = [{"targets": r["targets"], "min": r["min"], "max": r["max"]} for r in file_static]
w("\n== 1차 규칙표 ==")
w(f"  파일: 고정 {len(file_static)}행 + AUTO {len(file_auto)}행 "
  f"(AUTO행 {[a['row'] for a in file_auto]} / {[a['name'] for a in file_auto]})")
w(f"  앱  : 고정 {len(app_static)}개 + AUTO {len(app_auto)}개 "
  f"(AUTO {[a['name'] for a in app_auto]})")
ok(file_static_cmp == app_static_cmp, "1차 고정 규칙 내용 파일 == 앱 기준점")
ok([(a["name"], a["min"], a["max"]) for a in file_auto]
   == [(a["name"], int(a["min"]), int(a["max"])) for a in app_auto],
   "AUTO 3규칙 이름·범위 파일 == 앱 기준점")

# ── 회차별 후보 계산
def vec_of(nums) -> np.ndarray:
    v = np.zeros(46, dtype=np.int8)
    for x in nums:
        if isinstance(x, int) and 1 <= x <= 45:
            v[x] = 1
    return v


def count_of(v) -> np.ndarray:
    lut = np.zeros(46, dtype=np.int8)
    lut[: len(v)] = v[:46]
    return lut[combos].sum(axis=1)


def tier_counts(mask) -> dict:
    d = draws_sorted.get(rnd_actual, None)
    av = vec_of(actual)
    c = count_of(av)[mask]
    bonus_hit = (combos[mask] == bonus).any(axis=1)
    return {"N": int((c == 6).sum()), "O": int(((c == 5) & bonus_hit).sum()),
            "P": int(((c == 5) & ~bonus_hit).sum()), "Q": int((c == 4).sum()),
            "R": int((c == 3).sum())}


def missing_reason(actual_nums) -> str:
    """1차 규칙 중 당첨 6번호가 범위를 벗어나는 규칙 목록(시트 S열과 같은 형식)."""
    parts = []
    for rule, is_auto in [(r, False) for r in file_static] + [(r, True) for r in file_auto]:
        row = rule["row"]
        if is_auto:
            continue                      # AUTO 판정은 회차 의존 — 별도 계산
        c = int(vec_of(rule["targets"])[list(actual_nums)].sum())
        if c < rule["min"] or c > rule["max"]:
            parts.append((row, c, rule["min"], rule["max"]))
    return "; ".join(f"{c}(row{row}){c}개/허용{mn}~{mx}" for row, c, mn, mx in parts)


w("\n== 회차별 후보 대조 ==")
for rnd_actual in ROUNDS:
    anchor = rnd_actual - 1
    if anchor not in draws or rnd_actual not in draws:
        w(f"  {rnd_actual}회차: 데이터 없음 — 건너뜀")
        continue
    actual = [x for x in draws[rnd_actual][:6]]
    bonus = draws[rnd_actual][6]
    draws_sorted = draws
    a7 = draws[anchor][:6] + [draws[anchor][6]]
    idx = sorted(draws)[:0] + [x for x in sorted(draws) if x <= anchor]
    hist = [{"draw_round": x, "nums": [y for y in draws[x][:6]], "bonus": draws[x][6]} for x in idx]
    gap_order = cf._gap_order_for_anchor(hist, anchor)
    cand_neighbor = set()
    for x in a7:
        gi = gap_order.index(x)
        if gi > 0:
            cand_neighbor.add(gap_order[gi - 1])
        if gi < 44:
            cand_neighbor.add(gap_order[gi + 1])
    nb = set()
    for x in a7:
        for d in (-1, 0, 1):
            if 1 <= x + d <= 45:
                nb.add(x + d)

    prev_ok = count_of(vec_of(a7)) <= 2
    nb_ok = count_of(vec_of(sorted(nb))) <= 4
    cand_ok = count_of(vec_of(sorted(cand_neighbor))) <= 4

    cands = {
        "고정378": fixed,
        "고정+이격(2차규칙)": base,
        "이격만": gap_mask,
    }
    chain = base
    cands["고정+이격+전출현"] = chain & prev_ok
    cands["고정+이격+이웃수"] = chain & nb_ok
    stage2 = chain & prev_ok & nb_ok
    cands["고정+이격+전출현+이웃수"] = stage2
    cands["위+후보패턴이웃수"] = stage2 & cand_ok

    sang = vec_of(gap_order[:15])
    jung = vec_of(gap_order[15:30])
    ha = vec_of(gap_order[30:45])
    c_s, c_j, c_h = count_of(sang), count_of(jung), count_of(ha)
    top5 = vec_of(gap_order[:5])
    top3 = vec_of(gap_order[:3])
    c_t5, c_t3 = count_of(top5), count_of(top3)
    cond1_old = (c_s <= 4) & (c_j <= 4) & (c_h <= 4)
    cond1_new = (c_s >= 1) & (c_s <= 4) & (c_j >= 1) & (c_j <= 4) & (c_h >= 1) & (c_h <= 4)
    cands["위+4차(상중하0~4·top3≥1)"] = (stage2 & cond1_old & (c_t3 >= 1))
    cands["위+4차(상중하1~4·top5≥1)"] = (stage2 & cond1_new & (c_t5 >= 1))
    cands["위+후보패턴+4차(1~4·top5)"] = (stage2 & cand_ok & cond1_new & (c_t5 >= 1))

    w(f"\n  ── {rnd_actual}회차 (기준 회차 {anchor}) 당첨 {actual} + 보너스 {bonus}")
    st1, st2, st4 = stored["1차추적결과"].get(rnd_actual), stored["2차추적결과"].get(rnd_actual), stored["4차필터"].get(rnd_actual)
    w(f"     시트 저장: 1차 I={st1['I'] if st1 else None:,} "
      f"2차 I={st2['I'] if st2 else None:,} 4차 I={st4['I'] if st4 else None:,}"
      if st1 and st2 and st4 else "     시트 저장값 일부 없음")
    for name, m in cands.items():
        v = int(m.sum())
        marks = []
        for lbl, sv in (("1차I", st1["I"] if st1 else None), ("2차I", st2["I"] if st2 else None),
                        ("4차I", st4["I"] if st4 else None)):
            if sv == v:
                marks.append(lbl)
        w(f"     {name:32s} = {v:>10,}  {'★' + '/'.join(marks) if marks else ''}")
    # 등수별·누락원인
    if st1:
        tc1 = tier_counts(fixed & prev_ok & nb_ok)
        w(f"     등수별(위 구성 1차): 내계산 {tc1} / 시트 "
          f"{ {k: st1[k] for k in 'NOPQR'} }")
        mr = missing_reason(actual)
        w(f"     누락원인(1차 위반규칙): 내계산 {mr!r}")
        w(f"                               시트 {st1['S']!r}")

w(f"\n총 경과 {time.time() - t0:.1f}s")
w(f"\n== 불변식 ==")
ok(hashlib.sha256(SRC.read_bytes()).hexdigest()
   == hashlib.sha256(SRC.read_bytes()).hexdigest(), "실물 파일 무변경(읽기 전용 실행)")
ok(not FAILS, f"실패 {len(FAILS)}건")

Path(OUT).write_text("\n".join(R), encoding="utf-8")
print(f"written {OUT}")
