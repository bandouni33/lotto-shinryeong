# -*- coding: utf-8 -*-
"""샘플 파일 '행 단위 시트 전진' 시뮬레이터 — 임시 복사본에서만 실행(실물 무변경).

대상: 1차추적결과 / 2차추적결과 / 4차필터 (3행~104행 = 102회차 창).
전진 1회 = 3행에 새 회차 행을 넣고 맨 아래 행을 버린다(창 크기 고정).

값 사슬(2026-09-27 실측으로 확정)
  · 1차추적결과: H=전체 조합수(8,145,060), I=1차 통과수(규칙+AUTO)
  · 2차추적결과: H=1차 I, I=2차 통과수(= 1차 & 이격수)  ← 앱 DB stage2_count와 일치(1241 실측)
  · 4차필터    : H=2차 I, I=4차 통과수(상중하·top5 조건) ← 앱 DB stage4_count와 일치(1241 실측)
  · K/L/M = 그 회차 당첨 6개가 격차순위 상위/중위/하위(각 15개)에 든 개수
  · N~R   = 그 단계 통과 풀에서 실제 당첨번호와 1~5등으로 맞은 조합 수
  · S     = 당첨 조합이 위반한 1차 규칙 목록(시트 표기 그대로)

정의는 파일 자체 근거를 쓴다: 1차 규칙표는 파일의 1차필터 시트(고정 378 + AUTO 4),
이격수 48개는 앱 기준점 combo_filter_rules_stage2.json(파일 2차 시트와 내용 완전 일치 확인됨).

불변식: 창 크기·라벨 연속성·J수식 유지·1행 집계 불변·다른 시트 무변경·오류값 0·
        실물 무변경 + (검증) 앱 DB 기록(stage2/stage4)과의 대조.

실행: venv312\\Scripts\\python.exe scratch\\sim_sample_row_advance.py
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
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
CACHE = ROOT / "scratch" / "_sample_stage1_fixed_mask.npy"
COPY = ROOT / "scratch" / "_sim_row_advance_sample.xlsx"
OUT = ROOT / "scratch" / "sim_sample_row_advance_out.txt"
SHEETS = ("1차추적결과", "2차추적결과", "4차필터")
DATA_FIRST, DATA_LAST = 3, 104
R: list[str] = []
FAILS: list[str] = []
t0 = time.time()


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


def gap_order_for_window(hist, anchor_round, window):
    """격차순위 = (최근 window회 rank − 역대 rank) 내림차순. cf._gap_order_for_anchor와
    같은 정의이며 window=cf.RECENT_WINDOW(100)일 때 완전히 같아야 한다(아래에서 단언)."""
    rounds = [h["draw_round"] for h in hist]
    idx = rounds.index(anchor_round)
    freq_all: dict[int, int] = {}
    for h in hist[: idx + 1]:
        for x in h["nums"]:
            freq_all[x] = freq_all.get(x, 0) + 1
    freq_rec: dict[int, int] = {}
    for h in hist[max(0, idx + 1 - window): idx + 1]:
        for x in h["nums"]:
            freq_rec[x] = freq_rec.get(x, 0) + 1
    all_rank = {n: i + 1 for i, n in enumerate(
        sorted(range(1, 46), key=lambda x: (-freq_all.get(x, 0), x)))}
    rec_rank = {n: i + 1 for i, n in enumerate(
        sorted(range(1, 46), key=lambda x: (-freq_rec.get(x, 0), x)))}
    return sorted(range(1, 46), key=lambda x: (-(rec_rank[x] - all_rank[x]), x))


# ── 파일에서 이력·규칙 읽기
wb = openpyxl.load_workbook(SRC, data_only=True)
try:
    wsa = wb["전체당첨내역"]
    draws: dict[int, list[int]] = {}
    for r in range(2, wsa.max_row + 1):
        rr = wsa.cell(r, 1).value
        if isinstance(rr, int):
            draws[rr] = [wsa.cell(r, c).value for c in range(2, 9)]
    latest = max(draws)
    ws1 = wb["1차필터(7기본필터)"]
    static, auto = [], []
    for r in range(5, 1504):
        k, lm, j = ws1.cell(r, 11).value, ws1.cell(r, 12).value, ws1.cell(r, 10).value
        if not isinstance(k, (int, float)) or not isinstance(lm, (int, float)) or j is None:
            continue
        if str(j).strip().upper() == "AUTO":
            auto.append({"row": r, "name": ws1.cell(r, 8).value, "min": int(k), "max": int(lm)})
        else:
            tgt = sorted({int(x) for x in re.findall(r"\d+", str(j))})
            if tgt:
                static.append({"row": r, "name": ws1.cell(r, 8).value, "targets": tgt,
                               "min": int(k), "max": int(lm)})
    stored = {}
    for sn in SHEETS:
        ws = wb[sn]
        rows = {}
        for r in range(DATA_FIRST, DATA_LAST + 1):
            rr = ws.cell(r, 1).value
            if isinstance(rr, int):
                rows[rr] = {"H": ws.cell(r, 8).value, "I": ws.cell(r, 9).value,
                            "K": ws.cell(r, 11).value, "L": ws.cell(r, 12).value,
                            "M": ws.cell(r, 13).value,
                            "N": ws.cell(r, 14).value, "O": ws.cell(r, 15).value,
                            "P": ws.cell(r, 16).value, "Q": ws.cell(r, 17).value,
                            "R": ws.cell(r, 18).value}
        stored[sn] = rows
finally:
    wb.close()

w(f"실물 sha(앞12) = {hashlib.sha256(SRC.read_bytes()).hexdigest()[:12]} · 최신 회차 {latest}")
w(f"1차 규칙: 고정 {len(static)} + AUTO {len(auto)} {[a['name'] for a in auto]}")

# 전진 대상 = 창(추적결과) 최신보다 뒤에 추첨된 회차
NEW = sorted(r for r in draws if r > max(stored["1차추적결과"]))
w(f"추적결과 창 최신 = {max(stored['1차추적결과'])} · 전진 대상(그 뒤 회차) = {NEW}")
ok(len(NEW) == latest - max(stored["1차추적결과"]),
   f"전진 대상 {len(NEW)}회차 == 최신 {latest} − 창 최신 {max(stored['1차추적결과'])}")
if not NEW:
    w("전진할 회차가 없습니다 — 창이 이미 최신입니다.")
    OUT.write_text("\n".join(R), encoding="utf-8")
    sys.exit(0)

# ── 마스크 준비
combos = cf._all_combos()
fixed = np.load(CACHE)
ok(fixed.shape[0] == combos.shape[0], f"고정 규칙 마스크 길이 {fixed.shape[0]} == 조합수")
w(f"[{time.time() - t0:.0f}s] 고정 378규칙 통과 = {int(fixed.sum()):,}")

_, _, gap_rules = cf._load_rules()
gaps = np.diff(combos, axis=1)
gap_mask = np.ones(combos.shape[0], dtype=bool)
for rule in gap_rules:
    lut = np.zeros(cf.MAXGAP + 1, dtype=np.int8)
    for x in rule["targets"]:
        if 0 <= x <= cf.MAXGAP:
            lut[x] = 1
    c = lut[gaps].sum(axis=1)
    gap_mask &= (c >= rule["min"]) & (c <= rule["max"])
w(f"[{time.time() - t0:.0f}s] 이격수 48규칙 적용 → 1차+이격 = {int((fixed & gap_mask).sum()):,}")


def vec(nums) -> np.ndarray:
    v = np.zeros(46, dtype=np.int8)
    for x in nums:
        if isinstance(x, int) and 1 <= x <= 45:
            v[x] = 1
    return v


def count_of(v) -> np.ndarray:
    return v[combos].sum(axis=1)


def tier_counts(mask, nums, bonus) -> dict:
    c = count_of(vec(nums))[mask]
    bh = (combos[mask] == bonus).any(axis=1)
    return {"N": int((c == 6).sum()), "O": int(((c == 5) & bh).sum()),
            "P": int(((c == 5) & ~bh).sum()), "Q": int((c == 4).sum()),
            "R": int((c == 3).sum())}


def missing_reason(nums) -> str:
    """1차 규칙(정적+AUTO) 중 당첨 조합이 범위를 벗어난 것 — 시트 S열과 같은 형식."""
    parts = []
    for rule in static:
        c = int(vec(rule["targets"])[list(nums)].sum())
        if c < rule["min"] or c > rule["max"]:
            nm = f"{rule['name']}" if rule["name"] else ""
            parts.append(f"{nm}(row{rule['row']}){c}개/허용{rule['min']}~{rule['max']}")
    return "; ".join(parts)


computed: dict[int, dict] = {}
for rnd in NEW:
    anchor = rnd - 1
    hist = [{"draw_round": x, "nums": list(draws[x][:6]), "bonus": draws[x][6]}
            for x in sorted(draws) if x <= anchor]
    g100 = gap_order_for_window(hist, anchor, 100)
    if not computed:
        ok(g100 == cf._gap_order_for_anchor(hist, anchor),
           "내 격차순위 함수(window=100) == 앱 기준점 cf._gap_order_for_anchor")
    g200 = gap_order_for_window(hist, anchor, 200)
    prev7 = draws[anchor][:6] + [draws[anchor][6]]
    nb = sorted({x + d for x in prev7 for d in (-1, 0, 1) if 1 <= x + d <= 45})
    cn100 = sorted({g100[g100.index(w) + d] for w in prev7
                    for d in (-1, 1) if 0 <= g100.index(w) + d <= 44})
    cn200 = sorted({g200[g200.index(w) + d] for w in prev7
                    for d in (-1, 1) if 0 <= g200.index(w) + d <= 44})

    m1 = fixed.copy()
    for rule, targets in zip(auto, [prev7, nb, cn100, cn200]):
        c = count_of(vec(targets))
        m1 &= (c >= rule["min"]) & (c <= rule["max"])
    m2 = m1 & gap_mask
    sang, jung, ha = vec(g100[:15]), vec(g100[15:30]), vec(g100[30:45])
    top5 = vec(g100[:5])
    m4 = (m2 & (count_of(sang) >= 1) & (count_of(sang) <= 4)
          & (count_of(jung) >= 1) & (count_of(jung) <= 4)
          & (count_of(ha) >= 1) & (count_of(ha) <= 4) & (count_of(top5) >= 1))
    nums = draws[rnd][:6]
    bonus = draws[rnd][6]
    got = {n for n in nums}
    computed[rnd] = {
        "stage1": int(m1.sum()), "stage2": int(m2.sum()), "stage4": int(m4.sum()),
        "K": len(got & set(g100[:15])), "L": len(got & set(g100[15:30])),
        "M": len(got & set(g100[30:45])),
        "tiers1": tier_counts(m1, nums, bonus), "tiers2": tier_counts(m2, nums, bonus),
        "tiers4": tier_counts(m4, nums, bonus),
        "S": missing_reason(nums), "top5": g100[:5],
    }
    w(f"[{time.time() - t0:.0f}s] {rnd}회차 계산: 1차={computed[rnd]['stage1']:,} "
      f"2차={computed[rnd]['stage2']:,} 4차={computed[rnd]['stage4']:,} "
      f"상중하={computed[rnd]['K']}/{computed[rnd]['L']}/{computed[rnd]['M']}")

# ── 앱 DB 기록과 대조(검증용)
app = {}
try:
    from env_loader import load_dotenv_file

    load_dotenv_file()
    import marketing_db

    for rnd in sorted(set(NEW) | {max(stored["1차추적결과"])}):
        app[rnd] = marketing_db.get_draw_generation_stats(rnd)
except Exception as e:  # noqa: BLE001
    w(f"  [경고] DB 조회 실패: {type(e).__name__}: {e}")

w("\n== 계산값 vs 파일 저장값 vs 앱 DB 기록 ==")
w(f"{'회차':>6} {'내2차':>11} {'파일2차(저장)':>13} {'DB stage2':>11} "
  f"{'내4차':>10} {'파일4차(저장)':>13} {'DB stage4':>10}")
def _fmt(v) -> str:
    return format(v, ",") if isinstance(v, int) else "-"


for rnd in sorted(set(NEW) | {max(stored["1차추적결과"])}, reverse=True):
    s2, s4 = stored["2차추적결과"].get(rnd), stored["4차필터"].get(rnd)
    a = app.get(rnd) or {}
    c = computed.get(rnd)          # 1241은 창 안에 이미 있어 계산 대상이 아니다(저장값만 표시)
    w(f"{rnd:>6} {_fmt(c['stage2'] if c else None):>11} {_fmt((s2 or {}).get('I')):>13} "
      f"{_fmt(a.get('stage2_count')):>11} {_fmt(c['stage4'] if c else None):>10} "
      f"{_fmt((s4 or {}).get('I')):>13} {_fmt(a.get('stage4_count')):>10}")

# ── 복사본에 행 전진 적용
SRC_SHA = hashlib.sha256(SRC.read_bytes()).hexdigest()
shutil.copy2(SRC, COPY)
wbw = openpyxl.load_workbook(COPY, data_only=False)
try:
    before_other = {}
    for sn in wbw.sheetnames:
        if sn in SHEETS:
            continue
        h = hashlib.sha256()
        for row in wbw[sn].iter_rows():
            for c in row:
                h.update(f"{c.coordinate}={c.value!r}|".encode())
        before_other[sn] = h.hexdigest()
    aggregates = {sn: {f"{openpyxl.utils.get_column_letter(c)}1": wbw[sn].cell(1, c).value
                       for c in range(1, 20) if wbw[sn].cell(1, c).value is not None}
                  for sn in SHEETS}

    for sn in SHEETS:
        ws = wbw[sn]
        for rnd in NEW:                      # 오래된 회차부터 3행에 쌓는다(최신이 맨 위)
            ws.insert_rows(DATA_FIRST, amount=1)
            row = DATA_FIRST
            ws.cell(row, 1).value = rnd
            for i, n in enumerate(draws[rnd][:6]):
                ws.cell(row, 2 + i).value = n
            if sn == "1차추적결과":
                ws.cell(row, 8).value = len(combos)
                ws.cell(row, 9).value = computed[rnd]["stage1"]
                tiers = computed[rnd]["tiers1"]
            elif sn == "2차추적결과":
                ws.cell(row, 8).value = computed[rnd]["stage1"]
                ws.cell(row, 9).value = computed[rnd]["stage2"]
                tiers = computed[rnd]["tiers2"]
            else:
                ws.cell(row, 8).value = computed[rnd]["stage2"]
                ws.cell(row, 9).value = computed[rnd]["stage4"]
                tiers = computed[rnd]["tiers4"]
            ws.cell(row, 10).value = f"=SUM(K{row}:M{row})"
            ws.cell(row, 11).value = computed[rnd]["K"]
            ws.cell(row, 12).value = computed[rnd]["L"]
            ws.cell(row, 13).value = computed[rnd]["M"]
            for i, key in enumerate("NOPQR"):
                ws.cell(row, 14 + i).value = tiers[key]
            if sn != "4차필터":
                ws.cell(row, 19).value = computed[rnd]["S"]
        # J수식은 자기 행 번호를 쓰므로 밀린 행 전부 다시 쓴다
        for r in range(DATA_FIRST, DATA_LAST + 1):
            if ws.cell(r, 1).value is None:
                continue
            ws.cell(r, 10).value = f"=SUM(K{r}:M{r})"
        ws.delete_rows(DATA_LAST + 1, amount=len(NEW))   # 창 크기 유지(하단부터 버림)
    wbw.save(COPY)
finally:
    wbw.close()
w(f"[{time.time() - t0:.0f}s] 복사본 저장 완료")

# ── 불변식
w("\n== 불변식 ==")
wbs = openpyxl.load_workbook(COPY, data_only=True)
wbf = openpyxl.load_workbook(COPY, data_only=False)
try:
    for sn in SHEETS:
        wsv, wsf = wbs[sn], wbf[sn]
        labels = [wsv.cell(r, 1).value for r in range(DATA_FIRST, DATA_LAST + 1)]
        ok(all(isinstance(x, int) for x in labels) and labels == sorted(labels, reverse=True)
           and labels[0] == latest and labels[-1] == latest - (DATA_LAST - DATA_FIRST),
           f"{sn}: 창 {DATA_FIRST}~{DATA_LAST}행 = {labels[0]}..{labels[-1]} 연속·내림차순·최신 포함")
        ok(wsv.max_row == 104, f"{sn}: 행 수 {wsv.max_row} == 104 (창 크기 고정)")
        js = [wsf.cell(r, 10).value for r in range(DATA_FIRST, DATA_LAST + 1)]
        ok(all(isinstance(t, str) and t == f"=SUM(K{r}:M{r})"
               for r, t in zip(range(DATA_FIRST, DATA_LAST + 1), js)),
           f"{sn}: J열 수식이 전 행에서 자기 행을 가리킨다")
        agg = {f"{openpyxl.utils.get_column_letter(c)}1": wsf.cell(1, c).value
               for c in range(1, 20) if wsf.cell(1, c).value is not None}
        ok(agg == aggregates[sn], f"{sn}: 1행 집계 수식 불변 {agg}")
        for rnd in NEW:
            r = labels.index(rnd) + DATA_FIRST
            c = computed[rnd]
            want = {"1차추적결과": (len(combos), c["stage1"], c["K"], c["L"], c["M"], c["tiers1"]),
                    "2차추적결과": (c["stage1"], c["stage2"], c["K"], c["L"], c["M"], c["tiers2"]),
                    "4차필터": (c["stage2"], c["stage4"], c["K"], c["L"], c["M"], c["tiers4"])}[sn]
            got = (wsv.cell(r, 8).value, wsv.cell(r, 9).value, wsv.cell(r, 11).value,
                   wsv.cell(r, 12).value, wsv.cell(r, 13).value,
                   {k: wsv.cell(r, 14 + i).value for i, k in enumerate("NOPQR")})
            ok(got == want, f"{sn} {rnd}행: 계산값이 그대로 들어갔다")

    changed = [sn for sn in wbs.sheetnames if sn not in SHEETS
               and hashlib.sha256("".join(
                   # 비교는 같은 뷰(수식 포함, data_only=False)로 해야 한다 —
                   # data_only=True 해시와 섞으면 수식 있는 시트가 전부 '변경'으로 보인다.
                   f"{c.coordinate}={c.value!r}|" for row in wbf[sn].iter_rows() for c in row
               ).encode()).hexdigest() != before_other[sn]]
    ok(not changed, f"다른 시트 무변경 (변경 {changed})")
    errs = [f"{sn}!{c.coordinate}" for sn in wbs.sheetnames for row in wbs[sn].iter_rows()
            for c in row if isinstance(c.value, str) and c.value.strip() in (
                "#REF!", "#VALUE!", "#DIV/0!", "#NAME?", "#NULL!", "#NUM!", "#N/A")]
    ok(not errs, f"오류값 0 (발견 {len(errs)} {errs[:5]})")
finally:
    wbs.close()
    wbf.close()

ok(hashlib.sha256(SRC.read_bytes()).hexdigest() == SRC_SHA, "실물 파일 무변경(복사본에서만)")
w(f"\n단언 실패 {len(FAILS)}건" + ("" if not FAILS else ": " + " | ".join(FAILS[:5])))
w(f"총 경과 {time.time() - t0:.0f}s · 복사본 {COPY.name}")
OUT.write_text("\n".join(R), encoding="utf-8")
print(f"written {OUT}")
sys.exit(1 if FAILS else 0)
