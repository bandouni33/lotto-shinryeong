# -*- coding: utf-8 -*-
"""대조표 시뮬레이터 — 임시 복사본에서만 실행(실물 파일 무변경).

하는 일(회차 하나에 대해):
  1) 규칙 스냅샷 — 그 시점의 1차 규칙표(활성 380행 = 수식 있는 378 고정 + AUTO 2행)와
     2차 규칙표를 새 시트 `규칙스냅샷`에 그대로 적는다(나중에 그 회차를 재현할 수 있게).
  2) 수치 계산 — 그 스냅샷으로 대상 회차의 1차 통과수를 계산한다.
     (AUTO 2행: 5행 '전 출현번호' = 직전 회차 7개와 같은 개수 0~2,
                6행 '이웃수'      = 직전 회차 7개의 ±1과 겹치는 개수 0~4)
  3) 대조 시트 — 새 시트 `앱자동화_대조`에 회차별로 파일 계산값과
     앱 자동화 기록(DB draw_generation_stats: stage2_count·stage4_count·rank1~5)을 나란히 적는다.
  4) 불변식 검사 — 스냅샷 행수/재현성/오류값 0/기존 시트 무변경/회차 라벨.

실행: venv312\\Scripts\\python.exe scratch\\sim_sample_daejo.py
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import sys
import tempfile
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
OUT = ROOT / "scratch" / "sim_sample_daejo_out.txt"
REPORT: list[str] = []
FAILS: list[str] = []


def w(s: str = "") -> None:
    REPORT.append(s)
    print(s, flush=True)


def fail(s: str) -> None:
    FAILS.append(s)
    w(f"  FAIL {s}")


def ok(cond: bool, msg: str) -> None:
    if cond:
        w(f"  ok   {msg}")
    else:
        fail(msg)


def sheet_hash(path: Path, names: set[str]) -> dict[str, str]:
    """지정 시트들의 셀 내용 해시(값+수식) — 변경 감지용."""
    wb = openpyxl.load_workbook(path, data_only=False)
    out = {}
    try:
        for sn in names:
            ws = wb[sn]
            h = hashlib.sha256()
            for row in ws.iter_rows():
                for c in row:
                    v = c.value
                    t = v.text if hasattr(v, "text") else v
                    h.update(f"{c.coordinate}={t!r}|".encode())
            out[sn] = h.hexdigest()
    finally:
        wb.close()
    return out


t0 = time.time()
TMP = Path(tempfile.mkdtemp(prefix="lotto_daejo_"))
COPY = TMP / SRC.name
SRC_SHA = hashlib.sha256(SRC.read_bytes()).hexdigest()
shutil.copy2(SRC, COPY)
w(f"복사본 {COPY}")
w(f"실물 sha(앞12) = {SRC_SHA[:12]}")

# ── 1) 규칙 추출 (수식이 있는 행 = 평가되는 행)
wb = openpyxl.load_workbook(SRC, data_only=True)
wbf = openpyxl.load_workbook(SRC, data_only=False)
try:
    wsa = wb["전체당첨내역"]
    draws = {}
    for r in range(2, wsa.max_row + 1):
        rr = wsa.cell(r, 1).value
        if isinstance(rr, int):
            draws[rr] = [wsa.cell(r, c).value for c in range(2, 9)]
    latest = max(draws)
    TARGET = latest + 1

    ws1, ws1f = wb["1차필터(7기본필터)"], wbf["1차필터(7기본필터)"]
    first_round_col = None
    for c in range(1, ws1.max_column + 1):
        if isinstance(ws1.cell(4, c).value, int):
            first_round_col = c
            break

    def is_formula(ws, r, c) -> bool:
        v = ws.cell(r, c).value
        return hasattr(v, "text") or (isinstance(v, str) and v.startswith("="))

    rules1 = []
    skipped_empty = []
    for r in range(5, 1504):
        k, lm = ws1.cell(r, 11).value, ws1.cell(r, 12).value
        if not isinstance(k, (int, float)) or not isinstance(lm, (int, float)):
            continue
        if not is_formula(ws1f, r, first_round_col):
            continue                              # 회차 열에 수식이 없으면 평가 대상 아님
        j = ws1.cell(r, 10).value
        tgt = sorted({int(x) for x in re.findall(r"\d+", str(j))}) if j is not None else []
        if j is None or (not tgt and str(j).strip().upper() != "AUTO"):
            skipped_empty.append(r)               # 빈 목록은 무시(2026-09-27 사용자 지시)
            continue
        rules1.append({"row": r, "name": ws1.cell(r, 8).value, "j": j,
                       "targets": tgt, "min": int(k), "max": int(lm)})

    ws2 = wb["2차필터(5이격수)"]
    rules2 = []
    for r in range(5, 1504):
        k, lm = ws2.cell(r, 11).value, ws2.cell(r, 12).value
        if not isinstance(k, (int, float)) or not isinstance(lm, (int, float)):
            continue
        j = ws2.cell(r, 10).value
        tgt = sorted({int(x) for x in re.findall(r"\d+", str(j))}) if j is not None else []
        if not tgt:
            continue
        rules2.append({"row": r, "name": ws2.cell(r, 8).value, "j": j,
                       "targets": tgt, "min": int(k), "max": int(lm)})
    w(f"\n규칙 추출: 1차 활성 {len(rules1)}행(빈 목록 무시 {len(skipped_empty)}행), 2차 {len(rules2)}행")
    w(f"  최신 회차 {latest} → 대상 회차 {TARGET}")
finally:
    wb.close()
    wbf.close()

# ── 2) 1차 통과수 계산
combos = cf._all_combos()
nums_prev = [x for x in draws[latest][:6]]
bonus_prev = draws[latest][6]
prev7 = nums_prev + [bonus_prev]
v_prev = np.zeros(46, dtype=np.int8)
for x in prev7:
    v_prev[x] = 1
nb = set()
for x in prev7:
    for d in (-1, 0, 1):
        if 1 <= x + d <= 45:
            nb.add(x + d)
v_nb = np.zeros(46, dtype=np.int8)
for x in nb:
    v_nb[x] = 1

mask = np.ones(combos.shape[0], dtype=bool)
for rule in rules1:
    if str(rule["j"]).strip().upper() == "AUTO":
        continue                                   # AUTO는 아래에서 정의대로 적용
    vec = np.zeros(46, dtype=np.int8)
    for x in rule["targets"]:
        if 1 <= x <= 45:
            vec[x] = 1
    cnt = vec[combos].sum(axis=1)
    mask &= (cnt >= rule["min"]) & (cnt <= rule["max"])
t_fixed = time.time()
w(f"[{t_fixed - t0:.1f}s] 고정 규칙 적용 → {int(mask.sum()):,}")

stage1_fixed = int(mask.sum())
cnt_prev = v_prev[combos].sum(axis=1)
mask &= (cnt_prev >= 0) & (cnt_prev <= 2)
stage1 = int(mask.sum())
cnt_nb = v_nb[combos].sum(axis=1)
mask &= (cnt_nb >= 0) & (cnt_nb <= 4)
stage1_auto = int(mask.sum())
w(f"[{time.time() - t0:.1f}s] 1차 통과: 고정만 {stage1_fixed:,} → 전출현번호 후 {stage1:,}"
  f" → 이웃수까지(1차 최종) {stage1_auto:,}")

# ── 3) 앱 자동화 기록(DB 읽기 전용)
app = {}
try:
    import marketing_db
    for rnd in (TARGET, latest):
        app[rnd] = marketing_db.get_draw_generation_stats(rnd)
except Exception as e:  # noqa: BLE001
    w(f"  [경고] DB 조회 실패: {type(e).__name__}: {e}")

# ── 4) 복사본에 스냅샷 시트 + 대조 시트 쓰기
before = sheet_hash(COPY, {"1차추적결과", "2차추적결과", "4차필터", "전체당첨내역"})
wbw = openpyxl.load_workbook(COPY, data_only=False)
try:
    if "규칙스냅샷" in wbw.sheetnames:
        del wbw["규칙스냅샷"]
    snap = wbw.create_sheet("규칙스냅샷")
    snap.cell(1, 1, f"{TARGET}회차 기준 규칙 스냅샷 (기준 회차 {latest})")
    snap.cell(2, 1, "차수")
    snap.cell(2, 2, "행")
    snap.cell(2, 3, "패턴명")
    snap.cell(2, 4, "번호입력(J)")
    snap.cell(2, 5, "최소")
    snap.cell(2, 6, "최대")
    r = 3
    for rule in rules1:
        snap.cell(r, 1, "1차")
        snap.cell(r, 2, rule["row"])
        snap.cell(r, 3, rule["name"])
        snap.cell(r, 4, rule["j"])
        snap.cell(r, 5, rule["min"])
        snap.cell(r, 6, rule["max"])
        r += 1
    for rule in rules2:
        snap.cell(r, 1, "2차")
        snap.cell(r, 2, rule["row"])
        snap.cell(r, 3, rule["name"])
        snap.cell(r, 4, rule["j"])
        snap.cell(r, 5, rule["min"])
        snap.cell(r, 6, rule["max"])
        r += 1
    snap.cell(r + 1, 1, "AUTO 해석(대상 회차 기준)")
    snap.cell(r + 2, 1, "전 출현번호(직전 회차 7개)")
    for i, x in enumerate(prev7):
        snap.cell(r + 2, 2 + i, x)
    snap.cell(r + 3, 1, "이웃수(±1)")
    for i, x in enumerate(sorted(nb)):
        snap.cell(r + 3, 2 + i, x)

    if "앱자동화_대조" in wbw.sheetnames:
        del wbw["앱자동화_대조"]
    cmp_ = wbw.create_sheet("앱자동화_대조")
    heads = ["회차", "파일_1차통과", "파일_규칙수",
             "앱_stage2_count", "앱_stage4_count", "앱_rank1~5",
             "1차_규칙수_일치", "비고"]
    for i, h in enumerate(heads, start=1):
        cmp_.cell(1, i, h)
    row = 2
    for rnd, label in ((TARGET, "이번 회차(다음 배포 대상)"), (latest, "직전 회차(참고)")):
        a = app.get(rnd)
        cmp_.cell(row, 1, rnd)
        cmp_.cell(row, 2, stage1_auto if rnd == TARGET else "")
        cmp_.cell(row, 3, len(rules1))
        cmp_.cell(row, 4, a["stage2_count"] if a else "미기록")
        cmp_.cell(row, 5, a["stage4_count"] if a else "미기록")
        cmp_.cell(row, 6, str(a.get("top5_numbers")) if a else "미기록")
        cmp_.cell(row, 7, "")
        cmp_.cell(row, 8, label)
        row += 1
    wbw.save(COPY)
finally:
    wbw.close()
w(f"[{time.time() - t0:.1f}s] 복사본 저장 완료")

# ── 5) 불변식 검사
w("\n== 불변식 ==")
wbs = openpyxl.load_workbook(COPY, data_only=True)
try:
    ok("규칙스냅샷" in wbs.sheetnames, "스냅샷 시트 존재")
    ok("앱자동화_대조" in wbs.sheetnames, "대조 시트 존재")
    snap = wbs["규칙스냅샷"]
    snap_1 = sum(1 for r in range(3, snap.max_row + 1) if snap.cell(r, 1).value == "1차")
    snap_2 = sum(1 for r in range(3, snap.max_row + 1) if snap.cell(r, 1).value == "2차")
    ok(snap_1 == len(rules1), f"스냅샷 1차 행수 {snap_1} == 규칙수 {len(rules1)}")
    ok(snap_2 == len(rules2), f"스냅샷 2차 행수 {snap_2} == 규칙수 {len(rules2)}")
    cmp_ = wbs["앱자동화_대조"]
    ok(cmp_.cell(2, 1).value == TARGET, f"대조 시트 첫 행 회차 = {TARGET}")
    ok(isinstance(cmp_.cell(2, 2).value, int) and cmp_.cell(2, 2).value > 0,
       "대조 시트에 파일 계산값이 들어 있다")
    errs = []
    for sn in wbs.sheetnames:
        ws = wbs[sn]
        for rr in ws.iter_rows():
            for c in rr:
                if isinstance(c.value, str) and c.value.strip() in (
                        "#REF!", "#VALUE!", "#DIV/0!", "#NAME?", "#NULL!", "#NUM!", "#N/A"):
                    errs.append(f"{sn}!{c.coordinate}")
    ok(not errs, f"오류값 0 (발견 {len(errs)}개 {errs[:5]})")
finally:
    wbs.close()

after = sheet_hash(COPY, {"1차추적결과", "2차추적결과", "4차필터", "전체당첨내역"})
ok(before == after, "기존 시트 4개 내용 무변경")
ok(hashlib.sha256(SRC.read_bytes()).hexdigest() == SRC_SHA, "실물 파일 무변경(진단은 복사본에서만)")
ok(not FAILS, f"실패 {len(FAILS)}건")

w("\n== 앱 자동화 기록(DB) ==")
for rnd in (TARGET, latest):
    a = app.get(rnd)
    w(f"  {rnd}회차: " + (f"stage2={a['stage2_count']:,} stage4={a['stage4_count']:,} "
                        f"top5={a.get('top5_numbers')} recorded={a.get('recorded_at')}"
                        if a else "기록 없음"))
w(f"\n파일 계산(대상 {TARGET}회차): 1차 통과 {stage1_auto:,} (규칙 {len(rules1)}행)")
w(f"총 경과 {time.time() - t0:.1f}s")
Path(OUT).write_text("\n".join(REPORT), encoding="utf-8")
print(f"written {OUT}")
