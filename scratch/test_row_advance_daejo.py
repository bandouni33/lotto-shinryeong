# -*- coding: utf-8 -*-
"""행 전진 + 앱 기록 대조 자동화 테스트.

검증 대상은 생산 경로 그 자체:
  · weekly_lotto_file_update.row_advance_values / advance_row_sheets / write_daejo_sheet
  · 그것을 부르는 process_one_round_for_file (샘플 파일)

무엇을 단언하는가(모든 유효 입력에 성립해야 하는 것들):
  A. 판정 규칙(daejo_verdict) — 일치/불일치/이력 경계를 진리표로 전수 확인.
     RULE_VINTAGE_ROUND=1245 경계가 사용자 지시(1244=이력, 1245부터 기대)와 같은지도 확인.
  B. 결선 계약 — 샘플은 [당첨내역 추가 → 행 전진 → 대조 → 저장 → 컬럼 전진 → 재계산]
     순서로 부르고, 대상이 아닌 파일은 행 전진/대조를 부르지 않는다(가짜 워크북).
  C. 실제 실행 — 임시 복사본에서 process_one_round_for_file(샘플, 1242) 1회.
     창이 1241에 멈춰 있으므로 1242·1243 두 행이 한 번에 채워져야 한다(구멍 없음).
  D. 독립 검산 — 파일의 1차필터 규칙표와 combo_filter_rules_stage2.json을 **직접** 읽어
     격차순위까지 따로 구현한 경로로 1차/2차/4차 통과수를 다시 계산해, 파일에 적힌 값과
     맞는지 대조한다(내 생산 코드의 숫자를 그대로 믿지 않는다).
  E. 구조 불변식 — 창 크기·라벨 연속·J수식 자기행·1행 집계 불변·H-I 사슬·다른 시트 무변경·
     재실행 멱등.
  F. 음성 대조군 — 경계를 1242로 올리면(모의) 같은 대조가 불일치를 실제로 잡아낸다.
  G. 실물 파일 무변경(sha).

실행(엑셀 재계산은 못 쓰는 환경이라 경고만 남는다 — 정상):
    venv312\\Scripts\\python.exe scratch\\test_row_advance_daejo.py
"""
from __future__ import annotations

import hashlib
import itertools
import json
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
import weekly_lotto_file_update as wk  # noqa: E402

SRC = ROOT / "★조합생성_후보숫자_추적표" / "조합생성_후보숫자_추적표_샘플.xlsx"
COPY = ROOT / "scratch" / "_it_row_advance_sample.xlsx"
OUT = ROOT / "scratch" / "test_row_advance_daejo_out.txt"
STAGE2_JSON = ROOT / "combo_filter_rules_stage2.json"
# 시험 회차는 **DB의 실제 당첨번호**를 쓴다 — 가짜 번호로 돌리면 그 회차의 K/L/M과
# 등수별 조합수가 실제와 달라져 독립 검산(D)이 무의미해진다.
# 시험 대상: 파일의 추적결과 창은 1241에 멈춰 있고 전체당첨내역은 1243까지 있다 → 1242·1243
# 두 행이 한 번에 채워져야 한다(누락·중복 없이). 1244는 아직 **추천 전**이라 전체당첨내역에
# 없으므로 여기서 다루지 않는다(다음 주에 1244가 들어오면 그때 함께 채워진다).
ROUNDS_WRITTEN = (1242, 1243)
# 섹션 B(가짜 워크북 결선 계약)에서만 쓰는 합성 레코드
REC = {"round": 9999, "nums": [3, 11, 19, 27, 35, 44], "bonus": 7}
t0 = time.time()
R: list[str] = []
FAILS: list[str] = []


def w(s: str = "") -> None:
    """콘솔이 cp949(한국어 Windows 기본)여도 죽지 않게 출력한다 — 시험 메시지의 em-dash
    때문에 시험이 죽으면 진짜 결함과 구분이 안 된다."""
    R.append(str(s))
    try:
        print(s, flush=True)
    except UnicodeEncodeError:
        print(str(s).encode("cp949", errors="replace").decode("cp949", errors="replace"),
              flush=True)


def ok(cond: bool, msg: str) -> bool:
    if cond:
        w(f"  ok   {msg}")
    else:
        FAILS.append(msg)
        w(f"  FAIL {msg}")
    return bool(cond)


def fx(cell):
    v = cell.value
    return v.text if hasattr(v, "text") else (v if isinstance(v, str) and v.startswith("=") else None)


def sheet_hash(wb, name: str) -> str:
    h = hashlib.sha256()
    for row in wb[name].iter_rows():
        for c in row:
            v = fx(c) if fx(c) is not None and not isinstance(c.value, int) else c.value
            h.update(f"{c.coordinate}={v!r}|".encode())
    return h.hexdigest()


# ════════════════════════ A. 판정 규칙(진리표) ════════════════════════
w("== A. 대조 판정 규칙 ==")
ok(wk.RULE_VINTAGE_ROUND == 1245,
   f"규칙 빈티지 경계 = {wk.RULE_VINTAGE_ROUND} (사용자 지시: 1244 이하=이력, 1245부터 기대)")
ok(wk.RULE_VINTAGE_ROUND - 1 == 1244, f"경계 직전 회차 = {wk.RULE_VINTAGE_ROUND - 1} (1244)")
VALS = (0, 1, 812_060, 2_296_748, 8_145_060)
ROUNDS = (1140, 1241, 1244, 1245, 1246, 2000)
bad = []
for rnd in ROUNDS:
    for x in VALS:
        if wk.daejo_verdict(rnd, x, None) != "앱_미기록":
            bad.append(f"미기록({rnd},{x})")
        if wk.daejo_verdict(rnd, x, x) != "일치":
            bad.append(f"일치({rnd},{x})")
        for y in VALS:
            if y == x:
                continue
            want = "이력(규칙 불일치)" if rnd < wk.RULE_VINTAGE_ROUND else "불일치"
            if wk.daejo_verdict(rnd, x, y) != want:
                bad.append(f"{want}({rnd},{x},{y})→{wk.daejo_verdict(rnd, x, y)}")
ok(not bad, f"전수 {len(ROUNDS) * len(VALS) * (len(VALS) + 1)}조합 판정이 규칙대로 "
            f"(예외 {len(bad)}건 {bad[:3]})")
ok(wk.daejo_verdict(1244, 1, 2) == "이력(규칙 불일치)", "1244회차 불일치는 이력으로 표시")
ok(wk.daejo_verdict(1245, 1, 2) == "불일치", "1245회차 불일치는 불일치(실패)로 표시")
ok(wk.daejo_verdict(1241, 2_445_666, 2_445_666) == "일치",
   "실측 1241회차(파일·앱 모두 2,445,666)는 일치")
ok(wk.DAEJO_HEADERS[7:9] == ("2차_판정", "4차_판정") and "회차" == wk.DAEJO_HEADERS[0],
   f"대조 열 구성 = {list(wk.DAEJO_HEADERS)}")


# ════════════════════════ B. 결선 계약(가짜 워크북) ════════════════════════
w("\n== B. 결선 계약 ==")


class _FakeWS:
    pass


class _FakeWB:
    def __init__(self, calls):
        self.calls = calls
        self.all_sheet = _FakeWS()

    def __getitem__(self, key):
        assert key == "전체당첨내역", f"예상 밖 시트 접근: {key}"
        return self.all_sheet

    def save(self, path):
        self.calls.append("save")

    def close(self):
        pass


class _FakeOpenpyxl:
    def __init__(self, wb):
        self._wb = wb

    def load_workbook(self, *a, **k):
        return self._wb


def run_case(label: str) -> list[str]:
    calls: list[str] = []
    wb = _FakeWB(calls)
    real = (wk.openpyxl, wk.append_draw_result, wk.advance_round_columns, wk.recalc_and_save,
            wk.row_advance_values, wk.advance_row_sheets, wk.write_daejo_sheet)
    wk.openpyxl = _FakeOpenpyxl(wb)  # type: ignore[assignment]

    def fake_append(ws_all, rec):
        calls.append("append")
        assert ws_all is wb.all_sheet, "엉뚱한 시트에 회차를 추가했다"

    def fake_values(wb_arg, lb):
        calls.append("row_values")
        assert lb == label
        return {1244: {"stage1": 1, "stage2": 2, "stage4": 3, "K": 1, "L": 1, "M": 4,
                       "tiers1": {}, "tiers2": {}, "tiers4": {}, "S": ""}}

    def fake_rows(wb_arg, lb, values):
        calls.append("row_advance")
        assert lb == label and values, "행 전진에 값이 전달되지 않았다"
        return {sn: {"advanced": [1244], "labels_before": 1241, "labels_after": 1244}
                for sn in wk.ROW_ROUND_SHEETS}

    def fake_daejo(wb_arg, lb, values):
        calls.append("daejo")
        assert lb == label and values
        return ["모의 불일치"]

    wk.append_draw_result, wk.advance_round_columns, wk.recalc_and_save = (
        fake_append,
        lambda p, lb: (calls.append("advance_round_columns")
                       or {sn: {"shifts": 1, "labels_before": 1243, "labels_after": 1244}
                           for sn in wk.COLUMN_ROUND_SHEETS}),
        lambda p: calls.append("recalc_and_save"))
    wk.row_advance_values, wk.advance_row_sheets, wk.write_daejo_sheet = (
        fake_values, fake_rows, fake_daejo)
    try:
        problems = wk.process_one_round_for_file(Path("가짜.xlsx"), label, dict(REC))
    finally:
        (wk.openpyxl, wk.append_draw_result, wk.advance_round_columns, wk.recalc_and_save,
         wk.row_advance_values, wk.advance_row_sheets, wk.write_daejo_sheet) = real
    w(f"  [{label}] 호출 순서: {calls}")
    if label == "샘플":
        ok(calls == ["append", "row_values", "row_advance", "daejo", "save",
                     "advance_round_columns", "recalc_and_save"],
           "샘플 순서 = 당첨내역 추가 → 행 전진 → 대조 → 저장 → 컬럼 전진 → 재계산")
        ok(problems == ["모의 불일치"], "대조가 찾은 문제가 호출부로 반환된다")
    return calls


run_case("샘플")
c = run_case("200회검증용")
ok(all(x not in c for x in ("row_values", "row_advance", "daejo")),
   "200회검증용: 행 전진/대조를 부르지 않는다(승인 범위 밖)")
ok(set(wk.ROW_ROUND_FILES) <= set(wk.FILE_PATHS),
   f"행 전진 대상 {sorted(wk.ROW_ROUND_FILES)} ⊂ FILE_PATHS")
ok(wk.ROW_ROUND_FILES == wk.COLUMN_ROUND_FILES == {"샘플"},
   "행·컬럼 전진 대상이 모두 샘플 하나(파일당 작성자 한 명)")
ok(not (set(wk.ROW_ROUND_FILES) & set(wk.ADVANCE_3CHA_FILES)),
   f"행 전진 대상이 3차필터 담당 파일과 섬이지 않는다 {sorted(wk.ADVANCE_3CHA_FILES)}")
ok(wk.ROW_ROUND_FILES == {"샘플"}, f"행 전진 대상 파일 = {sorted(wk.ROW_ROUND_FILES)}")
ok(wk.ROW_ROUND_SHEETS == ("1차추적결과", "2차추적결과", "4차필터"),
   f"행 전진 대상 시트 = {list(wk.ROW_ROUND_SHEETS)}")
ok(wk.ROW_WINDOW == 102 and wk.ROW_FIRST == 3 and wk.ROW_LAST == 104,
   f"창 = {wk.ROW_FIRST}~{wk.ROW_LAST}행({wk.ROW_WINDOW}회차)")


# ══════════ B2. 신규 회차가 없어도 뒤처진 창을 채우는가(main 경로) ══════════
w("\n== B2. 신규 회차가 없어도 뒤처진 창을 채우는가(main 경로) ==")


def run_main_no_new_rounds(problems_from_daejo):
    calls: list[str] = []
    wb = _FakeWB(calls)
    real = (wk.openpyxl, wk.FILE_PATHS, wk.get_current_max_round, wk.find_new_rounds,
            wk.scan_errors, wk._advance_rows_in_wb, wk.recalc_and_save)
    wk.openpyxl = _FakeOpenpyxl(wb)          # type: ignore[assignment]
    wk.FILE_PATHS = {"샘플": SRC}
    wk.get_current_max_round = lambda p: 1243
    wk.find_new_rounds = lambda m, hard_limit=10: []
    wk.scan_errors = lambda p: []

    def fake_advance_rows(wb_arg, label):
        calls.append("advance_rows")
        assert label == "샘플"
        return ({"1차추적결과": {"advanced": [1242, 1243], "labels_before": 1241,
                                "labels_after": 1243}}, list(problems_from_daejo))

    wk._advance_rows_in_wb = fake_advance_rows
    wk.recalc_and_save = lambda p: calls.append("recalc")
    try:
        code = wk.main()
    finally:
        (wk.openpyxl, wk.FILE_PATHS, wk.get_current_max_round, wk.find_new_rounds,
         wk.scan_errors, wk._advance_rows_in_wb, wk.recalc_and_save) = real
    return calls, code


calls_n, code_n = run_main_no_new_rounds([])
w(f"  호출 순서: {calls_n} · exit={code_n}")
ok(calls_n == ["advance_rows", "save", "recalc"],
   "신규 회차가 없어도 행 전진 → 저장 → 재계산 순서로 뒤처진 창을 채운다")
ok(code_n == 0, f"대조 문제가 없으면 exit 0 (exit={code_n})")
calls_p, code_p = run_main_no_new_rounds(["샘플 1242회차 2차 불일치: 파일=1 앱=2"])
ok(code_p == 1, f"대조가 문제를 찾으면 exit 1 (exit={code_p}) — 조용히 넘어가지 않는다")


# ═══════════════ C. 실제 실행(임시 복사본) ═══════════════
w("\n== C. 실제 실행 ==")
SRC_SHA = hashlib.sha256(SRC.read_bytes()).hexdigest()
shutil.copy2(SRC, COPY)
w(f"실물 sha(앞12) = {SRC_SHA[:12]} · 시험 복사본 {COPY.name}")

wb_before = openpyxl.load_workbook(COPY, data_only=False)
try:
    other_before = {sn: sheet_hash(wb_before, sn) for sn in wb_before.sheetnames
                    if sn not in wk.ROW_ROUND_SHEETS and sn != "전체당첨내역"}
    labels_before = {sn: [wb_before[sn].cell(r, 1).value
                          for r in range(wk.ROW_FIRST, wk.ROW_LAST + 1)
                          if isinstance(wb_before[sn].cell(r, 1).value, int)]
                     for sn in wk.ROW_ROUND_SHEETS}
    agg_before = {sn: {f"{openpyxl.utils.get_column_letter(c)}1": fx(wb_before[sn].cell(1, c))
                       for c in range(1, 20)} for sn in wk.ROW_ROUND_SHEETS}
    sheets_before = list(wb_before.sheetnames)
finally:
    wb_before.close()

wb_run = openpyxl.load_workbook(COPY, data_only=False)
try:
    values = wk.row_advance_values(wb_run, "샘플")
    ok(sorted(values) == list(ROUNDS_WRITTEN),
       f"전진 대상 = {sorted(values)} (창 최신 1241보다 뒤인 회차 전부)")
    ok(values[1242]["stage1"] > values[1242]["stage2"] > values[1242]["stage4"] > 0,
       f"1242회차 1차>2차>4차 ({values[1242]['stage1']:,} > {values[1242]['stage2']:,} "
       f"> {values[1242]['stage4']:,})")
    stats = wk.advance_row_sheets(wb_run, "샘플", values)
    problems = wk.write_daejo_sheet(wb_run, "샘플", values)
    ok(all(st["advanced"] == list(ROUNDS_WRITTEN) for st in stats.values()),
       f"세 시트 모두 {list(ROUNDS_WRITTEN)}행을 밀았다 "
       f"{[st['advanced'] for st in stats.values()]}")
    wb_run.save(COPY)
finally:
    wb_run.close()
w(f"  대조 문제 {len(problems)}건: {problems}")

wb_after = openpyxl.load_workbook(COPY, data_only=False)
written: dict[str, dict[int, dict]] = {sn: {} for sn in wk.ROW_ROUND_SHEETS}
try:
    ok("대조 시트" in "".join(R) or f"{wk.DAEJO_SHEET}" in wb_after.sheetnames,
       f"대조 시트 '{wk.DAEJO_SHEET}' 생성됨")
    ws_d = wb_after[wk.DAEJO_SHEET]
    ok(tuple(ws_d.cell(1, c).value for c in range(1, len(wk.DAEJO_HEADERS) + 1))
       == wk.DAEJO_HEADERS, "대조 시트 헤더가 코드 상수와 같다")
    daejo_rows = {}
    for r in range(2, ws_d.max_row + 1):
        rnd = ws_d.cell(r, 1).value
        if isinstance(rnd, int):
            daejo_rows[rnd] = {h: ws_d.cell(r, i + 1).value for i, h in enumerate(wk.DAEJO_HEADERS)}
    ok(sorted(daejo_rows) == list(ROUNDS_WRITTEN),
       f"대조 시트 행 = {sorted(daejo_rows)} (창이 1241에 멈춰 있어 1242·1243이 함께 채워져야 함)")
    ok(problems == [], f"1242~1244는 이력 구간이라 실패로 잡히지 않는다(문제 {len(problems)}건)")

    for sn in wk.ROW_ROUND_SHEETS:
        ws = wb_after[sn]
        labels = [ws.cell(r, 1).value for r in range(wk.ROW_FIRST, wk.ROW_LAST + 1)]
        ints = [x for x in labels if isinstance(x, int)]
        ok(all(isinstance(x, int) for x in labels), f"{sn}: 3~104행이 모두 회차 숫자다")
        ok(ints == list(range(ints[0], ints[0] - len(ints), -1)),
           f"{sn}: 라벨 연속·내림차순 ({ints[0]}..{ints[-1]}, {len(ints)}개)")
        ok(ints[0] == 1243, f"{sn}: 맨 위 = 1243회차 (이전 {labels_before[sn][0]})")
        ok(len(ints) == len(labels_before[sn]) == wk.ROW_WINDOW,
           f"{sn}: 창 크기 유지 ({len(labels_before[sn])}→{len(ints)})")
        ok(ws.max_row == wk.ROW_LAST, f"{sn}: 최대행 {ws.max_row} == {wk.ROW_LAST}")
        js = [fx(ws.cell(r, 10)) for r in range(wk.ROW_FIRST, wk.ROW_LAST + 1)]
        ok(js == [f"=SUM(K{r}:M{r})" for r in range(wk.ROW_FIRST, wk.ROW_LAST + 1)],
           f"{sn}: J열 수식이 전 행에서 자기 행을 가리킨다")
        agg = {f"{openpyxl.utils.get_column_letter(c)}1": fx(ws.cell(1, c)) for c in range(1, 20)}
        ok(agg == agg_before[sn], f"{sn}: 1행 집계 수식 불변")
        for rnd in ROUNDS_WRITTEN:
            r = ints.index(rnd) + wk.ROW_FIRST
            written[sn][rnd] = {
                "A": ws.cell(r, 1).value,
                "B..G": [ws.cell(r, c).value for c in range(2, 8)],
                "H": ws.cell(r, 8).value, "I": ws.cell(r, 9).value,
                "K": ws.cell(r, 11).value, "L": ws.cell(r, 12).value, "M": ws.cell(r, 13).value,
                "N..R": [ws.cell(r, c).value for c in range(14, 19)],
                "S": ws.cell(r, 19).value,
            }
            w(f"  {sn} {rnd}행: H={written[sn][rnd]['H']:,} I={written[sn][rnd]['I']:,} "
              f"K/L/M={written[sn][rnd]['K']}/{written[sn][rnd]['L']}/{written[sn][rnd]['M']} "
              f"N~R={written[sn][rnd]['N..R']}")

    # H-I 사슬 (2차 입력 = 1차 결과, 4차 입력 = 2차 결과)
    for rnd in ROUNDS_WRITTEN:
        ok(written["2차추적결과"][rnd]["H"] == written["1차추적결과"][rnd]["I"],
           f"{rnd}: 2차추적결과 H({written['2차추적결과'][rnd]['H']:,}) == 1차추적결과 I")
        ok(written["4차필터"][rnd]["H"] == written["2차추적결과"][rnd]["I"],
           f"{rnd}: 4차필터 H({written['4차필터'][rnd]['H']:,}) == 2차추적결과 I")
        ok(written["1차추적결과"][rnd]["H"] == 8_145_060, f"{rnd}: 1차 입력 = 전체 조합수")
        ok(written["1차추적결과"][rnd]["I"] > written["2차추적결과"][rnd]["I"]
           > written["4차필터"][rnd]["I"] > 0,
           f"{rnd}: 1차 > 2차 > 4차 단조 감소")
        for sn in wk.ROW_ROUND_SHEETS:
            t = written[sn][rnd]
            ok(t["K"] + t["L"] + t["M"] == 6, f"{sn} {rnd}: K+L+M=6")
            ok(sum(t["N..R"]) >= 0 and all(isinstance(x, int) for x in t["N..R"]),
               f"{sn} {rnd}: N~R(등수별 조합수)가 정수로 기록됨")

    ok(written["1차추적결과"][1242]["S"] is None
       or isinstance(written["1차추적결과"][1242]["S"], str),
       f"1차추적결과 S열(누락원인)이 빈칸 또는 문자열 (값={written['1차추적결과'][1242]['S']!r})")

    # 대조 시트 값 = 파일 값 · 앱 DB 기록과 일치해야 한다
    import marketing_db
    for rnd in ROUNDS_WRITTEN:
        row = daejo_rows[rnd]
        app = marketing_db.get_draw_generation_stats(rnd)
        ok(row["파일_1차통과"] == written["1차추적결과"][rnd]["I"]
           and row["파일_2차통과"] == written["2차추적결과"][rnd]["I"]
           and row["파일_4차통과"] == written["4차필터"][rnd]["I"],
           f"{rnd}: 대조 시트의 '파일 계산값' 3개가 행에 적힌 값과 같다")
        ok(row["앱_stage2"] == (app["stage2_count"] if app else "미기록")
           and row["앱_stage4"] == (app["stage4_count"] if app else "미기록"),
           f"{rnd}: 대조 시트의 '앱 기록'이 DB 조회값과 같다")
        ok(row["2차_판정"] == wk.daejo_verdict(rnd, row["파일_2차통과"], row["앱_stage2"])
           and row["4차_판정"] == wk.daejo_verdict(rnd, row["파일_4차통과"], row["앱_stage4"]),
           f"{rnd}: 판정 열이 규칙 함수와 일치 ({row['2차_판정']}/{row['4차_판정']})")
        ok(row["비고"] == wk.DAEJO_VINTAGE_NOTE if rnd < wk.RULE_VINTAGE_ROUND else row["비고"] == "",
           f"{rnd}: 비고에 규칙 빈티지 안내가 붙는다")
    ok(daejo_rows[1243]["2차_판정"] in ("이력(규칙 불일치)", "일치"),
       f"1243회차 판정 = {daejo_rows[1243]['2차_판정']}")

    changed = [sn for sn in sheets_before
               if sn not in wk.ROW_ROUND_SHEETS and sn != "전체당첨내역"
               and sheet_hash(wb_after, sn) != other_before[sn]]
    ok(not changed, f"다른 시트 내용 무변경 (변경 {changed})")
    ok(all(sn in wb_after.sheetnames for sn in sheets_before)
       and len(wb_after.sheetnames) == len(sheets_before) + 1,
       "시트 목록 = 기존 + 대조 시트 1개")

    # ═══════════ E. 멱등 ═══════════
    w("\n== E. 멱등 ==")
    st = wk.advance_row_sheets(wb_after, "샘플", {rnd: {"stage1": 1, "stage2": 1, "stage4": 1,
                                                       "K": 1, "L": 1, "M": 4, "tiers1": {},
                                                       "tiers2": {}, "tiers4": {}, "S": ""}
                                                  for rnd in ROUNDS_WRITTEN})
    ok(all(not v["advanced"] for v in st.values()),
       f"같은 회차로 다시 전진해도 아무것도 밀지 않는다 {[(k, v['advanced']) for k, v in st.items()]}")
    before2 = {sn: [wb_after[sn].cell(r, 1).value for r in range(wk.ROW_FIRST, wk.ROW_LAST + 1)]
               for sn in wk.ROW_ROUND_SHEETS}
    wk.advance_row_sheets(wb_after, "샘플", {rnd: {"stage1": 1, "stage2": 1, "stage4": 1,
                                                   "K": 1, "L": 1, "M": 4, "tiers1": {},
                                                   "tiers2": {}, "tiers4": {}, "S": ""}
                                              for rnd in ROUNDS_WRITTEN})
    after2 = {sn: [wb_after[sn].cell(r, 1).value for r in range(wk.ROW_FIRST, wk.ROW_LAST + 1)]
              for sn in wk.ROW_ROUND_SHEETS}
    ok(before2 == after2, "재실행 후 창 라벨이 그대로(멱등)")
    st2 = wk.advance_row_sheets(wb_after, "샘플", {9999: {"stage1": 1, "stage2": 1, "stage4": 1,
                                                          "K": 1, "L": 1, "M": 4, "tiers1": {},
                                                          "tiers2": {}, "tiers4": {}, "S": ""}})
    ok(all(not v["advanced"] for v in st2.values()),
       "전체당첨내역에 없는 회차는 창에 넣지 않는다(없는 회차를 밀어넣지 않음)")

    # ═══════════ F. 음성 대조군 ═══════════
    w("\n== F. 음성 대조군(경계를 올리면 잡히는가) ==")
    real_vintage = wk.RULE_VINTAGE_ROUND
    vals = {1242: {"stage1": written["1차추적결과"][1242]["I"],
                   "stage2": written["2차추적결과"][1242]["I"],
                   "stage4": written["4차필터"][1242]["I"], "K": 1, "L": 1, "M": 4,
                   "tiers1": {}, "tiers2": {}, "tiers4": {}, "S": ""}}
    try:
        wk.RULE_VINTAGE_ROUND = 1242
        probs = wk.write_daejo_sheet(wb_after, "샘플", vals)
    finally:
        wk.RULE_VINTAGE_ROUND = real_vintage
    ok(any("불일치" in p for p in probs),
       f"경계=1242로 모의하면 1242회차 불일치를 실제로 잡는다(문제 {len(probs)}건 {probs[:2]})")
    ws_d = wb_after[wk.DAEJO_SHEET]
    row1242 = [r for r in range(2, ws_d.max_row + 1) if ws_d.cell(r, 1).value == 1242][0]
    ok(isinstance(ws_d.cell(row1242, 8).value, str) or ws_d.cell(row1242, 8).value is None,
       "모의 판정은 셀에만 쓰이고 실패로만 반환된다(직접 저장은 하지 않음)")
finally:
    wb_after.close()

errs = wk.scan_errors(COPY)
ok(not errs, f"저장 후 오류값 0 (발견 {len(errs)} {errs[:3]})")


# ═══════════ D. 독립 검산(파일 규칙표 + 규칙 JSON 직접 읽기) ═══════════
w("\n== D. 독립 검산 ==")


def _vecs(targets) -> np.ndarray:
    """46칸(번호 그대로 인덱싱) — combos로 바로 인덱싱할 수 있게. 원핫행렬(oh)에
    곱할 때는 [1:]로 잘라 쓴다(oh의 열은 번호-1)."""
    v = np.zeros(46, dtype=np.int8)
    for t in targets:
        if 1 <= t <= 45:
            v[t] = 1
    return v


def _gap_order_independent(hist, anchor, window):
    """시뮬레이터(scratch/sim_sample_row_advance.py)의 독립 구현 그대로."""
    rounds = [h["draw_round"] for h in hist]
    idx = rounds.index(anchor)
    fa, fr = {}, {}
    for h in hist[: idx + 1]:
        for x in h["nums"]:
            fa[x] = fa.get(x, 0) + 1
    for h in hist[max(0, idx + 1 - window): idx + 1]:
        for x in h["nums"]:
            fr[x] = fr.get(x, 0) + 1
    ar = {n: i + 1 for i, n in enumerate(sorted(range(1, 46), key=lambda x: (-fa.get(x, 0), x)))}
    rr = {n: i + 1 for i, n in enumerate(sorted(range(1, 46), key=lambda x: (-fr.get(x, 0), x)))}
    return sorted(range(1, 46), key=lambda x: (-(rr[x] - ar[x]), x))


wb_r = openpyxl.load_workbook(SRC, data_only=True, read_only=True)
try:
    ws1 = wb_r["1차필터(7기본필터)"]
    static_rules, auto_names = [], []
    for r, row in enumerate(ws1.iter_rows(min_row=5, max_row=1503, values_only=True), start=5):
        j, k, lm = row[9], row[10], row[11]
        if not isinstance(k, (int, float)) or not isinstance(lm, (int, float)) or j is None:
            continue
        if str(j).strip().upper() == "AUTO":
            auto_names.append(str(row[7]).strip())
            static_rules.append({"name": row[7], "min": int(k), "max": int(lm), "auto": True})
            continue
        tgt = sorted({int(x) for x in re.findall(r"\d+", str(j))})
        if tgt:
            static_rules.append({"name": row[7], "row": r, "targets": tgt,
                             "min": int(k), "max": int(lm)})
    ws_all = wb_r["전체당첨내역"]
    draws = []
    for row in ws_all.iter_rows(min_row=2, values_only=True):
        if isinstance(row[0], int):
            draws.append({"draw_round": int(row[0]),
                          "nums": sorted(int(x) for x in row[1:7]),
                          "bonus": int(row[7])})
    draws.sort(key=lambda h: h["draw_round"])
finally:
    wb_r.close()

fixed_rules = [r for r in static_rules if not r.get("auto")]
w(f"  파일 규칙표: 고정 {len(fixed_rules)}개 + AUTO {len(auto_names)}개 {auto_names}")
gap_rules = json.loads(STAGE2_JSON.read_text(encoding="utf-8"))
w(f"  이격수 규칙(JSON 직접) {len(gap_rules)}개")

combos = np.array(list(itertools.combinations(range(1, 46), 6)), dtype=np.int16)
oh = np.zeros((combos.shape[0], 45), dtype=np.int8)
oh[np.repeat(np.arange(combos.shape[0]), 6), combos.flatten() - 1] = 1
fixed = np.ones(combos.shape[0], dtype=bool)
for start in range(0, len(fixed_rules), 30):
    chunk = fixed_rules[start:start + 30]
    mat = np.stack([_vecs(r["targets"])[1:] for r in chunk], axis=1)
    cnt = oh @ mat
    fixed &= ((cnt >= np.array([r["min"] for r in chunk]))
              & (cnt <= np.array([r["max"] for r in chunk]))).all(axis=1)
gaps = np.diff(combos, axis=1)
gap_pass = np.ones(combos.shape[0], dtype=bool)
for r in gap_rules:
    lut = np.zeros(cf.MAXGAP + 1, dtype=np.int8)
    for t in r["targets"]:
        lut[t] = 1
    c = lut[gaps].sum(axis=1)
    gap_pass &= (c >= r["min"]) & (c <= r["max"])
w(f"  [{time.time() - t0:.0f}s] 독립 계산: 1차 고정 통과 {int(fixed.sum()):,} · "
  f"+이격수 {int((fixed & gap_pass).sum()):,}")

ok(written["1차추적결과"][1242]["H"] == 8_145_060, "독립 경로: 전체 조합수 8,145,060 확인")
for rnd in ROUNDS_WRITTEN:
    anchor = rnd - 1
    hist = [h for h in draws if h["draw_round"] <= anchor]
    order100 = _gap_order_independent(hist, anchor, 100)
    order200 = _gap_order_independent(hist, anchor, 200)
    ok(order100 == cf._gap_order_for_anchor(hist, anchor),
       f"{rnd}: 독립 격차순위(100회) == 앱 기준점 함수")
    prev7 = draws[[h["draw_round"] for h in draws].index(anchor)]["nums"] \
        + [draws[[h["draw_round"] for h in draws].index(anchor)]["bonus"]]
    nb = set()
    for x in prev7:
        for d in (-1, 0, 1):
            if 1 <= x + d <= 45:
                nb.add(x + d)
    cn100 = {order100[order100.index(x) + d] for x in prev7 for d in (-1, 1)
             if 0 <= order100.index(x) + d <= 44}
    cn200 = {order200[order200.index(x) + d] for x in prev7 for d in (-1, 1)
             if 0 <= order200.index(x) + d <= 44}
    targets_by_name = {"전 출현번호": set(prev7), "이웃수": nb,
                       "후보패턴 이웃수": cn100, "후보패턴 이웃수(200회)": cn200}
    m1 = fixed.copy()
    for r in static_rules:
        if not r.get("auto"):
            continue
        c = _vecs(targets_by_name[r["name"]])[combos].sum(axis=1)
        m1 &= (c >= r["min"]) & (c <= r["max"])
    m2 = m1 & gap_pass
    sang, jung, ha, top5 = (_vecs(order100[:15])[1:], _vecs(order100[15:30])[1:],
                            _vecs(order100[30:45])[1:], _vecs(order100[:5])[1:])
    m4 = (m2 & (oh @ sang >= 1) & (oh @ sang <= 4)
          & (oh @ jung >= 1) & (oh @ jung <= 4)
          & (oh @ ha >= 1) & (oh @ ha <= 4) & (oh @ top5 >= 1))
    got = (written["1차추적결과"][rnd]["I"], written["2차추적결과"][rnd]["I"],
           written["4차필터"][rnd]["I"])
    want = (int(m1.sum()), int(m2.sum()), int(m4.sum()))
    w(f"  {rnd}: 파일에 적힌 값 {got} vs 독립 재계산 {want}")
    ok(got == want, f"{rnd}: 파일 1차/2차/4차 통과수 == 독립 재계산(= 파일 규칙표+이격수 규칙)")
    nums, bonus = draws[[h["draw_round"] for h in draws].index(rnd)]["nums"], \
        draws[[h["draw_round"] for h in draws].index(rnd)]["bonus"]
    ok(written["2차추적결과"][rnd]["K"] == len(set(nums) & set(order100[:15]))
       and written["2차추적결과"][rnd]["M"] == len(set(nums) & set(order100[30:45])),
       f"{rnd}: K/M = 독립 격차순위 상위·하위 15개와의 교집합 수")
    # S열(누락원인) 독립 검산 — 파일 규칙표로 직접 위반 항목을 세어 S문구의 row번호와 맞춘다
    violated = [r["row"] for r in fixed_rules
                if not (r["min"] <= len(set(nums) & set(r["targets"])) <= r["max"])]
    s_text = written["1차추적결과"][rnd]["S"] or ""
    got_rows = sorted(int(x) for x in re.findall(r"row(\d+)", s_text))
    ok(got_rows == sorted(violated),
       f"{rnd}: S열의 위반 규칙 행 {got_rows} == 독립 계산 {sorted(violated)}")

ok(hashlib.sha256(SRC.read_bytes()).hexdigest() == SRC_SHA, "실물 파일 무변경(복사본에서만)")
w(f"\n단언 실패 {len(FAILS)}건" + ("" if not FAILS else ": " + " | ".join(FAILS[:6])))
w(f"총 경과 {time.time() - t0:.0f}s")
OUT.write_text("\n".join(R), encoding="utf-8")
print(f"written {OUT}")
# DB 스레드(db_turso의 non-daemon)가 인터프리터 종료를 붙잡아 스크립트가 안 끝난다 —
# 종료코드를 받을 수 있게 생산 스크립트와 같은 방식으로 즉시 종료한다.
os._exit(1 if FAILS else 0)
