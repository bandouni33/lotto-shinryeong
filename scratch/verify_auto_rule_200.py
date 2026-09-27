# -*- coding: utf-8 -*-
"""'후보패턴 이웃수(200회)' 추가 검증 — 단위(규칙·창·대상집합) + 조립(앱 파이프라인).

검증 항목
  U1 DB에서 로드되는 AUTO 규칙이 4개이고 그 안에 CAND_NEIGHBOR_200_RULE이 있다
  U2 앱이 쓰는 창 계산이 창 인자에 대해 정확하다 — 200회 창 격차순위가 내 독립 계산과 일치
     (그리고 100회 창일 때는 기존 앱 함수와 동일 — 후방호환)
  U3 그 창으로 만든 대상집합이 기대값과 정확히 같다(창이 실제로 결과를 바꾼다)
  U4 (조립) 앱 파이프라인 combo_filter_v2._compute_pool_for_anchor(anchor=1241)의
     stage2_count가 파일 규칙(4 AUTO)로 계산한 2,296,748과 일치한다
     → 규칙 추가 전에는 2,427,439(DB 기록)였다. 이게 '앱 == 파일'의 실증이다.
     ※ U4는 무거워서(고정 378규칙 재계산) 기본은 건너뛰고 --assemble 로 켠다.

실행: venv312\\Scripts\\python.exe scratch\\verify_auto_rule_200.py [--assemble]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import combo_filter_v2 as cf  # noqa: E402

from env_loader import load_dotenv_file  # noqa: E402

load_dotenv_file()

SRC = ROOT / "★조합생성_후보숫자_추적표" / "조합생성_후보숫자_추적표_샘플.xlsx"
OUT = ROOT / "scratch" / "verify_auto_rule_200_out.txt"
ANCHOR_WINDOW = 1242    # 앞선 진단(probe)과 같은 기준 회차 — 창/대상집합 기대값의 기준
ANCHOR_POOL = 1241      # 1242회차를 예측하는 기준 회차 — 앱 파이프라인 stage2 기대값의 기준
EXPECT_ORDER200_HEAD = [18, 34, 14, 17, 39, 43, 45, 1, 12, 27]
EXPECT_TARGETS_200 = [4, 5, 7, 9, 10, 11, 15, 16, 23, 24, 29, 37, 38, 44]
EXPECT_TARGETS_100 = [6, 11, 13, 15, 25, 26, 27, 28, 36, 37, 38, 42, 44]
EXPECT_STAGE2 = 2_296_748           # 파일 규칙(4 AUTO)로 계산한 1242회차 2차 통과수
R: list[str] = []
FAILS: list[str] = []


def w(s: str = "") -> None:
    R.append(str(s))
    print(s, flush=True)


def ok(cond: bool, msg: str) -> bool:
    if cond:
        w(f"  ok   {msg}")
    else:
        FAILS.append(msg)
        w(f"  FAIL {msg}")
    return bool(cond)


def gap_order_window(hist, anchor_round, window):
    rounds = [h["draw_round"] for h in hist]
    idx = rounds.index(anchor_round)
    allc: dict[int, int] = {}
    for h in hist[: idx + 1]:
        for x in h["nums"]:
            allc[x] = allc.get(x, 0) + 1
    rec: dict[int, int] = {}
    for h in hist[max(0, idx + 1 - window): idx + 1]:
        for x in h["nums"]:
            rec[x] = rec.get(x, 0) + 1
    ar = {n: i + 1 for i, n in enumerate(sorted(range(1, 46), key=lambda x: (-allc.get(x, 0), x)))}
    rr = {n: i + 1 for i, n in enumerate(sorted(range(1, 46), key=lambda x: (-rec.get(x, 0), x)))}
    return sorted(range(1, 46), key=lambda x: (-(rr[x] - ar[x]), x))


# ── U1 규칙
static_rules, auto_rules, gap_rules = cf._load_rules()
names = [a["name"] for a in auto_rules]
w(f"== U1 AUTO 규칙 (DB에서 로드) ==\n  {names}")
ok(cf.CAND_NEIGHBOR_200_RULE in names,
   f"'{cf.CAND_NEIGHBOR_200_RULE}' 규칙이 실제로 로드된다")
ok(names.count(cf.CAND_NEIGHBOR_200_RULE) == 1, "그 규칙은 정확히 1개다(중복 없음)")
rule = next(a for a in auto_rules if a["name"] == cf.CAND_NEIGHBOR_200_RULE)
ok((rule["min"], rule["max"]) == (0, 4),
   f"그 규칙의 범위가 파일과 같다 (min={rule['min']}, max={rule['max']})")
ok(cf.CAND_NEIGHBOR_WINDOW == 200, f"그 규칙의 창 상수 = {cf.CAND_NEIGHBOR_WINDOW}")

# ── 이력
wb = openpyxl.load_workbook(SRC, data_only=True)
try:
    ws = wb["전체당첨내역"]
    draws = {}
    for r in range(2, ws.max_row + 1):
        rr = ws.cell(r, 1).value
        if isinstance(rr, int):
            draws[rr] = [ws.cell(r, c).value for c in range(2, 9)]
finally:
    wb.close()
hist_w = [{"draw_round": x, "nums": list(draws[x][:6]), "bonus": draws[x][6]}
          for x in sorted(draws) if x <= ANCHOR_WINDOW]
anchors7 = draws[ANCHOR_WINDOW][:6] + [draws[ANCHOR_WINDOW][6]]
hist_p = [h for h in hist_w if h["draw_round"] <= ANCHOR_POOL]

# ── U2 창 계산(앱 함수 vs 독립 계산), 후방호환
w(f"\n== U2 창 계산 (기준 회차 {ANCHOR_WINDOW}) ==")
app100 = cf._gap_order_for_anchor(hist_w, ANCHOR_WINDOW)
app200 = cf._gap_order_for_anchor(hist_w, ANCHOR_WINDOW, cf.CAND_NEIGHBOR_WINDOW)
mine100 = gap_order_window(hist_w, ANCHOR_WINDOW, 100)
mine200 = gap_order_window(hist_w, ANCHOR_WINDOW, 200)
ok(app100 == mine100, "기본(창 미지정) 호출 결과가 변하지 않았다(후방호환)")
ok(app200 == mine200, "200회 창 호출 결과가 독립 계산과 일치")
ok(app200[:10] == EXPECT_ORDER200_HEAD, f"200회 창 상위10 = {app200[:10]}")

# ── U3 대상집합
w("\n== U3 '후보패턴 이웃수' 대상집합 ==")
t100 = sorted(cf._cand_neighbor_of(app100, anchors7))
t200 = sorted(cf._cand_neighbor_of(app200, anchors7))
w(f"  100회 창 = {t100}\n  200회 창 = {t200}")
ok(t100 == EXPECT_TARGETS_100, "100회 창 대상집합이 진단 당시와 같다(기존 규칙 불변)")
ok(t200 == EXPECT_TARGETS_200, "200회 창 대상집합이 진단 당시와 같다(추가한 규칙)")
ok(t100 != t200, "두 창이 실제로 다른 집합을 만든다(규칙 추가가 의미를 가진다)")

# ── U4 조립 검증(무거움)
if "--assemble" in sys.argv:
    w("\n== U4 앱 파이프라인 (combo_filter_v2._compute_pool_for_anchor) ==")
    import time

    t0 = time.time()
    (_combos, _oh, stage4_mask, static_gap, stage2_count, gap_order) = \
        cf._compute_pool_for_anchor(hist_p, ANCHOR_POOL)
    w(f"  [{time.time() - t0:.0f}s] 기준 {ANCHOR_POOL}회차(→{ANCHOR_POOL + 1} 예측) "
      f"static_gap={static_gap:,} stage2={stage2_count:,} stage4={int(stage4_mask.sum()):,}")
    ok(stage2_count == EXPECT_STAGE2,
       f"앱 stage2_count {stage2_count:,} == 파일 규칙 계산값 {EXPECT_STAGE2:,}")
    ok(gap_order == gap_order_window(hist_p, ANCHOR_POOL, 100),
       "파이프라인이 쓴 격차순위가 100회 창과 일치")
else:
    w("\n== U4 건너뜀 (--assemble 로 실행) ==")

w(f"\n단언 실패 {len(FAILS)}건" + ("" if not FAILS else ": " + " | ".join(FAILS[:5])))
OUT.write_text("\n".join(R), encoding="utf-8")
print(f"written {OUT}")
os._exit(1 if FAILS else 0)
