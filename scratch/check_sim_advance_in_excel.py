# -*- coding: utf-8 -*-
"""전진 시뮬레이터 결과물(_sim_advance_sample.xlsx)을 실제 엑셀로 열어 재계산 검증.

왜 필요한가: openpyxl은 수식 문자열만 옮겨 적을 뿐 **계산을 하지 않는다**. 밀기가
제대로 됐다는 최종 증거는 실제 엑셀이 그 수식들을 다시 계산해서
  · 헬퍼행(1504~1516)이 각 컬럼 라벨에 맞는 회차 번호를 가져오고
  · 규칙 판정 셀에 오류값(#REF!/#VALUE! 등)이 하나도 없으며
  · 값이 정상 숫자/""
를 보여주는 것이다. 파일은 읽기 전용으로 열고 저장하지 않는다.

실행: venv312\\Scripts\\python.exe scratch\\check_sim_advance_in_excel.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
COPY = ROOT / "scratch" / "_sim_advance_sample.xlsx"
SRC = ROOT / "★조합생성_후보숫자_추적표" / "조합생성_후보숫자_추적표_샘플.xlsx"
SH1 = "1차필터(7기본필터)"
ERRS = {"#REF!", "#VALUE!", "#DIV/0!", "#NAME?", "#NULL!", "#NUM!", "#N/A", "#GETTING_DATA"}

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


# ── 기대값(파일 자체의 전체당첨내역에서)
wb0 = openpyxl.load_workbook(SRC, data_only=True)
try:
    ws0 = wb0["전체당첨내역"]
    draws = {}
    for r in range(2, ws0.max_row + 1):
        rr = ws0.cell(r, 1).value
        if isinstance(rr, int):
            draws[rr] = [ws0.cell(r, c).value for c in range(2, 9)]
finally:
    wb0.close()

wb1 = openpyxl.load_workbook(COPY, data_only=True)
try:
    ws1 = wb1[SH1]
    labels = [(c, ws1.cell(4, c).value) for c in range(1, ws1.max_column + 1)
              if isinstance(ws1.cell(4, c).value, int)]
    first_col, last_col = labels[0][0], labels[-1][0]
    all_labels = [v for _, v in labels]
finally:
    wb1.close()

w(f"복사본 {COPY.name} ({COPY.stat().st_size:,} bytes)")
w(f"{SH1}: 회차열 {all_labels[0]}..{all_labels[-1]} ({len(all_labels)}개)")
w(f"전체당첨내역 회차 {min(draws)}~{max(draws)}")

# ── 실제 엑셀로 열어 재계산
try:
    import win32com.client
except Exception as e:  # noqa: BLE001
    w(f"[SKIP] win32com 사용 불가({type(e).__name__}: {e}) — 엑셀 재계산 검증을 건너뜁니다")
    Path(ROOT / "scratch" / "check_sim_advance_in_excel_out.txt").write_text("\n".join(R), encoding="utf-8")
    sys.exit(2)

excel = win32com.client.DispatchEx("Excel.Application")
excel.Visible = False
excel.DisplayAlerts = False
try:
    wb = None
    last = None
    # 2026-09-27 실측(weekly_lotto_file_update._open_workbook와 같은 현상): 이 PC는
    # 엑셀 기동 초반에 'Workbooks.Open' 오류(-2147352567)를 몇 번 더지다 그 다음부터 정상
    # 동작한다. 자동화를 멈추지 않도록 시도 횟수를 넉넉히 두고 간격도 늘렸다.
    for attempt in range(1, 7):
        try:
            wb = excel.Workbooks.Open(str(COPY.resolve()), ReadOnly=True)
            break
        except Exception as e:  # noqa: BLE001
            last = e
            w(f"  [주의] 엑셀이 파일을 열지 못함(시도 {attempt}/6): {e}")
            time.sleep(6)
    if wb is None:
        raise RuntimeError(f"엑셀에서 파일을 열 수 없습니다: {last}")

    excel.CalculateFullRebuild()
    w(f"[{time.time() - t0:.0f}s] 엑셀 재계산 완료")

    # ① 헬퍼행 1504~1516 값이 각 컬럼 라벨의 회차와 맞는가
    rng = wb.Sheets(SH1).Range(f"N1504:{openpyxl.utils.get_column_letter(last_col)}1516").Value2
    mism = []
    checked = 0
    for i, label in enumerate(all_labels):
        col_vals = [rng[row][i] for row in range(13)]        # 1504..1516 (13행)
        # 헬퍼 1504~1509 = 이 컬럼 회차의 6개 번호, 1510~1516 = 직전 회차의 6개+보너스
        want = ([int(x) for x in draws[label][:6]]
                + [int(x) for x in draws[label - 1][:6]] + [int(draws[label - 1][6])])
        if label - 1 not in draws:
            continue
        checked += 1
        if [int(v) if v is not None else None for v in col_vals] != want:
            mism.append((label, col_vals, want))
    ok(not mism, f"헬퍼행 13개가 컬럼 라벨(그 회차 7개 + 직전 회차 7개)과 일치 "
                 f"(확인 {checked}열, 불일치 {len(mism)} {mism[:1]})")

    # ② 규칙 판정 셀이 숫자 또는 "" 인가(오류값·엉뚱한 값 없음)
    vals = wb.Sheets(SH1).Range(f"N5:{openpyxl.utils.get_column_letter(last_col)}1500").Value2
    bad_vals, blank, num = [], 0, 0
    for row in vals:
        for v in row:
            if v is None or v == "":
                blank += 1
            elif isinstance(v, str):
                bad_vals.append(v)
            else:
                num += 1
    ok(not bad_vals, f"규칙 판정 셀에 문자열(오류값 등) 없음 — 숫자 {num:,} / 빈칸 {blank:,} "
                     f"(이상값 {len(bad_vals)} {bad_vals[:3]})")
    ok(num > 0, f"새로 만든 N열에도 판정 숫자가 채워졌다 (전체 숫자 {num:,})")

    # ③ 전 시트 오류값 스캔(엑셀이 계산한 값 기준)
    errs = []
    for sn in [s.Name for s in wb.Sheets]:
        try:
            used = wb.Sheets(sn).UsedRange.Value2
        except Exception:  # noqa: BLE001
            continue
        if used is None:
            continue
        rows = used if isinstance(used, tuple) else ((used,),)
        for row in rows:
            cells = row if isinstance(row, tuple) else (row,)
            for v in cells:
                if isinstance(v, str) and v.strip() in ERRS:
                    errs.append(f"{sn}={v}")
    ok(not errs, f"엑셀 재계산 후 전 시트 오류값 0 (발견 {len(errs)} {errs[:5]})")

    wb.Close(SaveChanges=False)
    w(f"[{time.time() - t0:.0f}s] 저장하지 않고 닫음(복사본 원본 유지)")
finally:
    excel.Quit()

w(f"\n실패 {len(FAILS)}건 · 총 경과 {time.time() - t0:.0f}s")
Path(ROOT / "scratch" / "check_sim_advance_in_excel_out.txt").write_text("\n".join(R), encoding="utf-8")
print("written check_sim_advance_in_excel_out.txt")
sys.exit(1 if FAILS else 0)
