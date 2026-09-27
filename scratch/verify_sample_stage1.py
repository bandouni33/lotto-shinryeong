# -*- coding: utf-8 -*-
"""샘플 파일 '값 사슬' 재현 검증 — 1차필터(7기본필터) 단계(읽기 전용).

사용자 정의(2026-09-27):
  1. 1차필터(7기본필터) 규칙 적용 → 1차추적결과   (H=입력 조합수, I=최종 통과수)
  2. 1차추적결과의 조합수량 → 2차필터(5이격수) 규칙 적용 → 2차추적결과
  3. 2차추적결과의 조합수량 → 4차필터(100출현빈도순 후보) 줄세우기
  4. 후보 1~5위를 절대수로, 45순위까지 전체 필터링

이 스크립트는 1단계만 본다: 1차필터 시트의 규칙표(H=패턴명, J=번호입력, K=최소, L=최대)를
그대로 읽어, 특정 회차의 조합 통과수를 계산하고 시트에 저장된 값과 맞대어 본다.
AUTO 3개 규칙(전 출현번호·이웃수·후보패턴 이웃수)은 배포 엔진과 같은 정의로 계산한다
(combo_filter_v2._compute_pool_for_anchor 참고 — 직전 회차 번호 / 그 이웃 / 격차순위 이웃).

실행: venv312\\Scripts\\python.exe scratch\\verify_sample_stage1.py [회차]
"""
from __future__ import annotations

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

SRC = ROOT / "★조합생성_후보숫자_추적표" / "조합생성_후보숫자_추적표_샘플.xlsx"
OUT = ROOT / "scratch" / "verify_sample_stage1_out.txt"
R = int(sys.argv[1]) if len(sys.argv) > 1 else 1241
L: list[str] = []


def w(s: str = "") -> None:
    L.append(s)
    print(s, flush=True)


def parse_targets(txt) -> list[int]:
    if txt is None:
        return []
    return [int(x) for x in re.findall(r"\d+", str(txt))]


def gap_order_window(hist, anchor_round, window):
    """역대 rank − 최근 `window`회 rank (동점은 작은 번호) — _gap_order_for_anchor의 창 일반화.
    4번째 AUTO 규칙('후보패턴 이웃수(200회)')의 정의 후보로 쓴다."""
    rounds = [h["draw_round"] for h in hist]
    idx = rounds.index(anchor_round)
    allc = {}
    for h in hist[: idx + 1]:
        for x in h["nums"]:
            allc[x] = allc.get(x, 0) + 1
    rec = {}
    lo = max(0, idx + 1 - window)
    for h in hist[lo : idx + 1]:
        for x in h["nums"]:
            rec[x] = rec.get(x, 0) + 1
    ar = {n: i + 1 for i, n in enumerate(sorted(range(1, 46), key=lambda x: (-allc.get(x, 0), x)))}
    rr = {n: i + 1 for i, n in enumerate(sorted(range(1, 46), key=lambda x: (-rec.get(x, 0), x)))}
    return sorted(range(1, 46), key=lambda x: (-(rr[x] - ar[x]), x))


t0 = time.time()
# 주의: 이 파일은 셀 단위 임의 접근이 많아 read_only 모드로는 O(n²)이 된다(실측: 멈춤).
wb = openpyxl.load_workbook(SRC, data_only=True)
try:
    ws_all = wb["전체당첨내역"]
    draws = []
    for row in ws_all.iter_rows(min_row=2, max_col=8, values_only=True):
        if row[0] is None:
            continue
        draws.append((int(row[0]), [int(x) for x in row[1:7]], int(row[7] or 0)))
    draws.sort(key=lambda t: t[0])
    hist = [{"draw_round": r, "nums": ns, "bonus": b} for r, ns, b in draws]
    by_round = {r: (ns, b) for r, ns, b in draws}

    ws1 = wb["1차필터(7기본필터)"]
    rules = []
    for r in range(5, 1504):
        name = ws1.cell(r, 8).value
        j = ws1.cell(r, 10).value
        k = ws1.cell(r, 11).value
        lm = ws1.cell(r, 12).value
        if name is None and j is None:
            continue
        if not isinstance(k, (int, float)) or not isinstance(lm, (int, float)):
            continue
        rules.append({"row": r, "name": name, "is_auto": str(j).strip().upper() == "AUTO",
                      "targets": parse_targets(j), "min": int(k), "max": int(lm)})
    # 2026-09-27 실측: 번호목록(J)이 비어 있는 행들이 있다(24,25,33,34,153,412,458,461,463~483).
    # 이들을 "대상 0개 규칙"으로 취급하면 최소≥1인 행에서 전 조합이 탈락해 통과수가 0이 된다
    # (첫 시도에서 실측). 그래서 여기서는 **번호목록이 있는 행만 규칙으로 센다**.
    inactive = [x["row"] for x in rules if not x["targets"] and not x["is_auto"]]
    rules = [x for x in rules if x["targets"] or x["is_auto"]]
    w(f"[{time.time() - t0:.1f}s] 이력 {len(draws)}회차 · 1차 규칙 {len(rules)}개")
    auto = [x for x in rules if x["is_auto"]]
    w(f"  AUTO 규칙 {len(auto)}개: {[x['name'] for x in auto]}")
    w(f"  고정 규칙 {len(rules) - len(auto)}개 (번호목록 없는 비활성행 {len(inactive)}개: {inactive}")

    stored = {}
    ws_track = wb["1차추적결과"]
    for r in range(3, ws_track.max_row + 1):
        rr = ws_track.cell(r, 1).value
        if isinstance(rr, int):
            stored[rr] = (ws_track.cell(r, 8).value, ws_track.cell(r, 9).value)
finally:
    wb.close()

w(f"\n대상 회차 {R}: 시트 저장값 H={stored.get(R, (None, None))[0]:,} / I={stored.get(R, (None, None))[1]:,}")

# ── 계산
t1 = time.time()
combos = cf._all_combos()
oh = cf._onehot(combos)
w(f"[{time.time() - t1:.1f}s] 조합 {combos.shape[0]:,}개 준비")

prev_round = R - 1
nums, bonus = by_round[prev_round]
gap_order = cf._gap_order_for_anchor(hist, prev_round)
anchors7 = list(nums) + [bonus]
neighbor = set()
for n in anchors7:
    neighbor.add(n)
    if n > 1:
        neighbor.add(n - 1)
    if n < 45:
        neighbor.add(n + 1)
cand_neighbor = set()
for v in anchors7:
    gi = gap_order.index(v)
    if gi > 0:
        cand_neighbor.add(gap_order[gi - 1])
    if gi < 44:
        cand_neighbor.add(gap_order[gi + 1])

t2 = time.time()
pass_mask = np.ones(combos.shape[0], dtype=bool)
detail = []
batch = 30
fixed = [x for x in rules if not x["is_auto"]]
for start in range(0, len(fixed), batch):
    chunk = fixed[start:start + batch]
    mat = np.stack([cf._targets_to_vec(x["targets"]) for x in chunk], axis=1)
    cnt = oh @ mat
    mins = np.array([x["min"] for x in chunk])
    maxs = np.array([x["max"] for x in chunk])
    ok = (cnt >= mins) & (cnt <= maxs)
    pass_mask &= ok.all(axis=1)
    if start == 0:
        for i, x in enumerate(chunk[:0]):
            pass
w(f"[{time.time() - t2:.1f}s] 고정 규칙 적용 완료 → 통과 {int(pass_mask.sum()):,}")
# 2026-09-27: 이 120초짜리 고정 규칙 패스를 반복하지 않도록 마스크를 캐시한다.
import pathlib as _pl
_CACHE = _pl.Path("scratch/_sample_stage1_fixed_mask.npy")
np.save(_CACHE, pass_mask)

t3 = time.time()
for x in rules:
    if not x["is_auto"]:
        continue
    name = str(x["name"])
    if name == "전 출현번호":
        tv = cf._targets_to_vec(anchors7)
    elif name == "이웃수":
        tv = cf._targets_to_vec(neighbor)
    elif name == "후보패턴 이웃수":
        tv = cf._targets_to_vec(cand_neighbor)
    elif name == "후보패턴 이웃수(200회)":
        order200 = gap_order_window(hist, prev_round, 200)
        cn200 = set()
        for v in anchors7:
            gi = order200.index(v)
            if gi > 0:
                cn200.add(order200[gi - 1])
            if gi < 44:
                cn200.add(order200[gi + 1])
        tv = cf._targets_to_vec(cn200)
    else:
        w(f"  [경고] 알 수 없는 AUTO 규칙: {name} → 건너뜀")
        continue
    cnt = oh @ tv
    ok = (cnt >= x["min"]) & (cnt <= x["max"])
    before = int(pass_mask.sum())
    pass_mask &= ok
    w(f"  AUTO '{name}' (최소{x['min']}~최대{x['max']}): {before:,} → {int(pass_mask.sum()):,}")
w(f"[{time.time() - t3:.1f}s] 최종 통과 {int(pass_mask.sum()):,}")

sh, si = stored.get(R, (None, None))
w(f"\n== 대조 (회차 {R}) ==")
w(f"  재계산 최종 통과수 = {int(pass_mask.sum()):,}")
w(f"  시트 1차추적결과 I(최종) = {si:,}" if isinstance(si, int) else f"  시트 I = {si}")
w(f"  일치 = {isinstance(si, int) and int(pass_mask.sum()) == si}")
w(f"  시트 H(필터1, 입력) = {sh:,}" if isinstance(sh, int) else f"  시트 H = {sh}")
w(f"\n총 경과 {time.time() - t0:.1f}s")

# ── AUTO 규칙 조합 탐색: 저장값 3,452,560과 정확히 맞는 조합을 찾는다.
#    (고정 규칙만 = 3,489,350 > 저장값이므로 AUTO는 "일부만" 적용됐을 가능성이 크다.)
t4 = time.time()
w("\n== AUTO 규칙 조합 탐색 ==")


def ok_of(tv, mn, mx):
    cnt = oh @ tv
    return (cnt >= mn) & (cnt <= mx)


nums_only = list(nums)
cands = [
    ("전출현번호(7개:번호+보너스) 0~2", ok_of(cf._targets_to_vec(anchors7), 0, 2)),
    ("전출현번호(6개:번호만) 0~2", ok_of(cf._targets_to_vec(nums_only), 0, 2)),
    ("이웃수(번호+보너스 기준) 0~4", ok_of(cf._targets_to_vec(neighbor), 0, 4)),
]
nb_nums = set()
for n in nums_only:
    nb_nums.add(n)
    if n > 1:
        nb_nums.add(n - 1)
    if n < 45:
        nb_nums.add(n + 1)
cands.append(("이웃수(번호만 기준) 0~4", ok_of(cf._targets_to_vec(nb_nums), 0, 4)))
ordered = list(gap_order)
cn100 = set()
for v in anchors7:
    gi = ordered.index(v)
    if gi > 0:
        cn100.add(ordered[gi - 1])
    if gi < 44:
        cn100.add(ordered[gi + 1])
cands.append(("후보패턴이웃수(100회) 0~4", ok_of(cf._targets_to_vec(cn100), 0, 4)))
order200 = gap_order_window(hist, prev_round, 200)
cn200 = set()
for v in anchors7:
    gi = order200.index(v)
    if gi > 0:
        cn200.add(order200[gi - 1])
    if gi < 44:
        cn200.add(order200[gi + 1])
cands.append(("후보패턴이웃수(200회) 0~4", ok_of(cf._targets_to_vec(cn200), 0, 4)))

for i, (lab, _) in enumerate(cands):
    w(f"  [{i}] {lab}")

TARGET = stored.get(R, (None, None))[1]
best: list[tuple[int, str]] = []
for bits in range(64):
    m = pass_mask.copy()
    names = []
    for i in range(len(cands)):
        if bits & (1 << i):
            m &= cands[i][1]
            names.append(str(i))
    c = int(m.sum())
    if TARGET is not None and c == TARGET:
        best.append((c, "+".join(names) or "(AUTO 없음)"))
    if TARGET is not None and abs(c - TARGET) <= 500:
        w(f"  근접: AUTO{{{'+'.join(names) or '없음'}}} → {c:,} (차 {c - TARGET:+,})")
if best:
    for c, combo in best:
        w(f"  ★ 정확히 일치: AUTO{{{combo}}} → {c:,}")
else:
    w(f"  정확히 일치하는 조합 없음 (저장값 {TARGET:,})")
w(f"[{time.time() - t4:.1f}s] 탐색 완료")

OUT.write_text("\n".join(L), encoding="utf-8")
print(f"written {OUT}")
