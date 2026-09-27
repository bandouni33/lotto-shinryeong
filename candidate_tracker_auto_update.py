# -*- coding: utf-8 -*-
"""
★후보숫자_추적표_표본vs최근50회.xlsx 자동 업데이트 스크립트.

매주 토요일 로또 추첨이 끝나면, 동행복권 공식 API에서 새 회차 결과를 가져와
"전체당첨내역" 시트에 추가한다. 이 파일은 weekly_lotto_file_update.py가 다루는
4개 파일(샘플/200회검증용/전체표본/최근500표본)과 구조가 다르다 — "3차필터 예측행
freeze·전진" 같은 복잡한 절차가 필요 없다:

  이 파일의 10개 "기준{W}회_후보" 시트 + 기준 500회 시트("3차필터(50회_후보)")는
  전부 `=MAX(전체당첨내역!$A$2:$A$1500)+1` 같은 수식으로 "현재 최신 회차"를 스스로
  찾아내는 구조라서, 전체당첨내역에 새 행만 추가하면 나머지는 전부 자동으로
  재계산된다. 사람이 매주 예측행을 수동으로 밀어줄 필요가 없다.

다만 딱 하나, 자동으로 안 늘어나는 보조 시트가 있다: 숨김 시트 "_calc_누적빈도"
(회차별 누적 출현횟수를 저장해 두고 빼기만 해서 구간빈도를 구하는 캐시 테이블)는
전체당첨내역과 정확히 1:1로 행이 대응해야 하므로, 새 회차를 추가할 때마다 이
시트에도 같은 회차의 누적값 행을 함께 추가해야 한다. (이 스크립트가 자동으로
처리함 — 2026-09-15에 22,950건 교차검증 + 1회차/2회차 백필 시뮬레이션으로
검증 완료.)

다만 2026-09-27에 하나 더 발견됐다: 이 파일의 "3차필터(500회_후보)" 시트는
회차·당첨번호 열이 `=MAX(전체당첨내역)` 수식이라 새 회차가 들어올 때마다 블록 행이
한 칸씩 밀리는데, 예측순위(L:BD)와 적중수(I:K)는 **고정값**이었다 — 그래서 1242·1243을
넣자 49행 중 46행이 "다른 회차의 예측 vs 이 회차의 당첨번호"를 찍어 적중수를 거짓으로
보여줬다(실측). 이 스크립트가 이제 매 실행마다 그런 블록을 회차별로 재계산해 넣는다
(같은 파일의 기준N회_후보 시트들은 L:BD가 MATCH 수식이라 자동으로 맞으므로 건드리지
않는다 — 판단은 시트 이름이 아니라 "블록의 L열이 값인지 수식인지"로 한다).

필요 사전 설치 (엑셀/WPS가 설치된 PC에서, 명령 프롬프트에서 한 번만):
    pip install openpyxl pywin32

작업 스케줄러 등록 (관리자 권한 명령 프롬프트에서 한 번만 실행 — 선택사항):
    schtasks /create /tn "로또신령_후보숫자추적표_자동업데이트" ^
        /tr "python C:\\Users\\PC\\Desktop\\lotto-app\\candidate_tracker_auto_update.py" ^
        /sc weekly /d SUN /st 09:10 /ri 60 /du 0004:50 /f

    (weekly_lotto_file_update.py와 동일한 스케줄 — 09:10부터 60분 간격으로
    4시간50분 동안 재시도. 이미 최신이면 아무것도 안 하고 조용히 종료하므로
    여러 번 실행돼도 안전함.)
"""

from __future__ import annotations

import datetime
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter

from env_loader import load_dotenv_file

load_dotenv_file()  # 단독 실행(작업 스케줄러)에서도 TURSO_* 환경변수를 읽게 한다

# ============================== CONFIG ======================================

TARGET_FILE = Path(
    r"C:\Users\PC\Desktop\lotto-app\★조합생성_후보숫자_추적표"
    r"\★후보숫자_추적표_표본vs최근50회.xlsx"
)
LOG_FILE = TARGET_FILE.parent / "candidate_tracker_update_log.txt"

ALL_SHEET = "전체당첨내역"
CUM_SHEET = "_calc_누적빈도"
ANCHOR_SHEET = "_calc_라운드기준"
SAMPLE_CHECK_SHEET = "기준100회_후보"  # 사후 검증용 표본 시트 1개

# ============================== 데이터 소스 ===================================
# 2026-09-27: 동행복권 common.do?method=getLottoNumber 직접 호출은 폐기 — 이제 어떤
# 헤더로도 JSON이 아닌 사이트 HTML만 돌려준다(실측). 앱과 같은 DB(draw_results)를 쓴다.


def find_new_rounds(local_max_round: int, hard_limit: int = 10) -> list[dict]:
    """로컬 파일이 아직 모르는 회차를 **DB(draw_results)** 에서 오름차순으로 모아 반환.

    2026-09-15의 User-Agent 우회 수정도 함께 폐기한다 — 그 수정을 넣은 뒤에도 응답은
    계속 HTML이었고(같은 로그에 남아 있음), 주소 자체가 죽었기 때문이다.
    회차 구멍이 있으면 예외를 던져 호출부가 실패로 끝내게 한다(조용한 밀림 방지).
    """
    import draw_results_db

    rows = draw_results_db.get_all_draw_results()
    by_round = {int(r["draw_round"]): r for r in rows}
    if not by_round:
        raise RuntimeError("draw_results에서 회차를 하나도 읽지 못했습니다(DB 접속 실패 또는 빈 테이블)")
    latest = max(by_round)

    out: list[dict] = []
    r = int(local_max_round) + 1
    while len(out) < hard_limit and r <= latest:
        rec = by_round.get(r)
        if rec is None:
            raise RuntimeError(
                f"DB에 {r}회차가 없습니다(최신 {latest}회차) — 회차 구멍이 있으면 파일이 "
                f"그 지점에서 조용히 멈추므로 자동 처리를 중단합니다"
            )
        out.append({
            "round": r,
            "nums": sorted(int(x) for x in rec["numbers"]),
            "bonus": int(rec["bonus"]),
        })
        r += 1
    return out


# ============================== 로깅 =========================================

def log(msg: str) -> None:
    line = f"[{datetime.datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ============================== 엑셀 재계산 (win32com) =========================

def _open_tracker_workbook(excel, path: Path, attempts: int = 3, delay: float = 3.0):
    """Excel COM Workbooks.Open 재시도 — 이 PC에서 하루 첫 두 번의 Excel 기동이
    'Workbooks 클래스 중 Open 메서드에 오류가 있습니다'(-2147352567)로 실패하는 것을
    실측(2026-09-27). 한 번의 실패로 파일 업데이트가 멈추지 않게 재시도한다."""
    last = None
    for attempt in range(1, attempts + 1):
        try:
            return excel.Workbooks.Open(str(path.resolve()))
        except Exception as e:  # noqa: BLE001
            last = e
            log(f"  [주의] Excel이 파일을 열지 못했습니다(시도 {attempt}/{attempts}): {e}")
            time.sleep(delay)
    raise RuntimeError(f"Excel로 파일을 열 수 없습니다(재시도 {attempts}회 모두 실패): {last}")


def recalc_and_save(path: Path) -> None:
    """구조 편집이 끝난 파일을 열어 강제 전체 재계산 후 그대로 저장 — 캐시된 값을
    최신으로 구워넣어서, 나중에 파일을 열었을 때 재계산 전에도 바로 올바른 값이
    보이게 한다. (openpyxl은 수식을 계산하지 않고 텍스트만 저장하기 때문에 필수.)"""
    import win32com.client

    excel = win32com.client.DispatchEx("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    try:
        wb = _open_tracker_workbook(excel, path)
        try:
            excel.CalculateFullRebuild()
            wb.Save()
        finally:
            wb.Close(SaveChanges=True)
    finally:
        excel.Quit()


# ============================== 엑셀 오류값 스캔 ================================

_ERR = {"#N/A", "#REF!", "#VALUE!", "#DIV/0!", "#NAME?", "#NULL!", "#NUM!"}


def scan_errors(path: Path) -> list[tuple[str, str]]:
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    found = []
    for sn in wb.sheetnames:
        ws = wb[sn]
        for row in ws.iter_rows():
            for cell in row:
                v = cell.value
                if isinstance(v, str) and v.strip() in _ERR:
                    found.append((sn, f"{cell.coordinate}={v}"))
    wb.close()
    return found


def verify_after_update(path: Path, expected_max_round: int) -> None:
    """저장·재계산 후 파일을 다시 열어, 자동 재계산이 실제로 제대로 됐는지
    독립적으로 확인한다. 문제가 있으면 예외를 던져 이후 처리를 멈춘다."""
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)

    anchor = wb[ANCHOR_SHEET].cell(2, 1).value
    if anchor is None:
        # 2026-09-27: 엑셀 재계산이 안 돼 캐시값이 비어 있을 수 있다(파일은 정상이며
        # 엑셀로 열면 자동 계산된다) — 캐시 없음은 실패로 처리하지 않고 경고만 남긴다.
        log(f"  [경고] {ANCHOR_SHEET}!A2 캐시값이 없습니다(엑셀 재계산 미반영) — 이 항목은 건너뜁니다.")
    elif anchor != expected_max_round + 1:
        raise RuntimeError(
            f"검증 실패: {ANCHOR_SHEET}!A2(다음 예측 회차)={anchor}, "
            f"기대값={expected_max_round + 1}. 재계산이 반영 안 된 것으로 보임."
        )

    ws_sample = wb[SAMPLE_CHECK_SHEET]
    l1bd1 = [ws_sample.cell(1, c).value for c in range(12, 57)]
    if sorted(v for v in l1bd1 if v is not None) != list(range(1, 46)):
        raise RuntimeError(
            f"검증 실패: {SAMPLE_CHECK_SHEET}!L1:BD1(후보숫자 순위표)이 "
            f"1~45 전체를 담고 있지 않음 -> {l1bd1}"
        )

    wb.close()

    mismatched = _block_mismatch_rows(path)
    if mismatched:
        raise RuntimeError(
            f"검증 실패: 3차필터 블록에서 예측순위와 적중수가 어긋난 행 {mismatched}개 "
            f"(회차·당첨번호는 밀리는데 예측·적중이 고정된 상태)"
        )
    log("  블록 정합성 확인(예측순위↔적중수 일치).")


# ============================== 3차필터 블록 정합화 ============================
# 2026-09-27 (발견 B): 위 docstring 참고. 블록의 회차·당첨번호가 =MAX() 수식으로 밀리는데
# 예측순위(L:BD)·적중수(I:K)가 고정값인 시트를, 그 회차 직전까지의 이력으로 다시 계산한다.
# (weekly_lotto_file_update.py의 _python_pending_forecast와 같은 정의의 계산 — 두 스크립트는
#  서로를 import하지 않는 독립 실행 파일이라 각자 갖고 있고, 양쪽 모두 워크북/검증기로
#  같은 값을 내는지 확인한다.)
_NUMS = list(range(1, 46))


def _window_from_label(label, default=None):
    m = re.search(r"최근\s*(\d+)\s*회", str(label or ""))
    return int(m.group(1)) if m else default


def _counts(draws, window):
    lo = draws[0][0] if (not window or window >= len(draws)) else draws[-1][0] - (window - 1)
    return {n: sum(1 for r, ns in draws if r >= lo and n in ns) for n in _NUMS}


def _ranks(vals):
    return {n: (1 + sum(1 for m in _NUMS if vals[m] > vals[n])
                + sum(1 for m in _NUMS if vals[m] == vals[n] and m < n)) for n in _NUMS}


def _prediction_for(draws, target_round, w2, w3):
    """target_round 직전까지의 이력만으로 만든 격차순위 1~45위(= 그 회차의 예측)."""
    hist = [(r, ns) for r, ns in draws if r < target_round]
    if not hist:
        return None
    r2, r3 = _ranks(_counts(hist, w2)), _ranks(_counts(hist, w3))
    gap = {n: r3[n] - r2[n] for n in _NUMS}
    return sorted(_NUMS, key=lambda n: (-gap[n], n))


def _hits(ranking, drawn) -> tuple[int, int, int]:
    return tuple(sum(1 for d in drawn if d in set(ranking[i * 15:(i + 1) * 15])) for i in range(3))


def _draws_from_sheet(ws_all) -> list[tuple[int, list[int]]]:
    draws = []
    for row in ws_all.iter_rows(min_row=2, values_only=True):
        if row[0] is None:
            continue
        draws.append((int(row[0]), [int(x) for x in row[1:7]]))
    draws.sort(key=lambda t: t[0])
    return draws


def _block_start(ws):
    """블록 첫 행 = 회차 열이 '수식(=MAX(...))'이고 L열이 1~45 정수인 첫 행.

    즉 "회차·당첨번호는 수식으로 밀리는데 예측순위는 고정값"인 시트만 정합화 대상이다.
    (a) 회차 열이 값으로 고정된 시트는 대상이 아니다 — 손으로 관리하는 표나 계산 시트를
        건드리지 않기 위해 일부러 좁게 잡는다. (넓게 잡았다가 고정시트까지 재작성되는 걸
        테스트가 잡아냈고, 그대로 두면 실물 파일의 _calc_* 계산 시트를 덮어쓸 수 있었다.)
    (b) 기준N회_후보 시트들은 L열이 MATCH 수식이라 걸리지 않는다 → 건드리지 않는다.
    """
    for r in range(2, min(ws.max_row, 20) + 1):
        a, l = ws.cell(r, 1).value, ws.cell(r, 12).value
        if isinstance(a, str) and a.startswith("=") and isinstance(l, int) and 1 <= l <= 45:
            return r
    return None


def _block_offset(ws, start: int) -> int:
    """블록 첫 행이 '대기행(MAX+1)'이면 1, '최신회차행(MAX)'이면 0."""
    return 1 if "+1" in str(ws.cell(start, 1).value) else 0


def realign_sliding_blocks(wb, draws) -> list[str]:
    """밀리는 블록의 예측순위(L:BD)·적중수(I:K)를 각 회차 기준으로 재계산해 넣는다."""
    latest = draws[-1][0]
    fixed = []
    for sn in wb.sheetnames:
        ws = wb[sn]
        start = _block_start(ws)
        if start is None:
            continue
        off = _block_offset(ws, start)
        w2 = _window_from_label(ws.cell(2, 11).value)
        w3 = _window_from_label(ws.cell(3, 11).value)
        rows = 0
        for r in range(start, ws.max_row + 1):
            a = ws.cell(r, 1).value
            # 회차는 A셀 값이 회차번호면 그걸, 수식이면(캐시는 안 믿고) 위치로 유도한다.
            rnd = a if (isinstance(a, int) and a >= 1000) else latest + off - (r - start)
            ranking = _prediction_for(draws, rnd, w2, w3)
            if ranking is None:
                continue
            for i, n in enumerate(ranking):
                ws.cell(r, 12 + i, n)
            drawn = next((ns for rr, ns in draws if rr == rnd), None)
            if drawn is None:            # 아직 추첨 전(대기행) → 적중수는 비워 둔다
                for c in (9, 10, 11):
                    ws.cell(r, c, None)
                continue
            for c, h in zip((9, 10, 11), _hits(ranking, drawn)):
                ws.cell(r, c, h)
            rows += 1
        if rows:
            fixed.append(f"{sn}({rows}행)")
    return fixed


def _block_mismatch_rows(path: Path) -> int:
    """블록이 어긋나 있는지(읽기 전용) 검산 — 판단 불가한 행은 건너뜀.

    구조(어느 행이 블록인가·회차 열이 수식인가)는 **수식 읽기**로, 숫자는 **값 읽기**로
    본다. 한 가지 읽기로 몰아 하던 예전 판은 (a) 값 읽기에서는 A열이 캐시 숫자로 나와
    블록을 못 찾았고(정합화가 한 번 건너뜀), (b) 수식 읽기에서는 엑셀이 아직 재계산하지
    않은 파일의 값을 못 봤다 — 두 번 다 실측으로 걸렸다.
    회차번호는 A셀에 캐시값이 있으면 그걸, 없으면 블록 위치로 유도한다(유도 규칙은
    realign_sliding_blocks와 동일).
    """
    wf = openpyxl.load_workbook(path, data_only=False, read_only=True)
    wv = openpyxl.load_workbook(path, data_only=True, read_only=True)
    bad = 0
    try:
        latest = None
        if ALL_SHEET in wv.sheetnames:
            ints = [row[0] for row in wv[ALL_SHEET].iter_rows(min_row=2, max_col=1, values_only=True)
                    if isinstance(row[0], int)]
            latest = max(ints) if ints else None

        for sn in wf.sheetnames:
            if sn not in wv.sheetnames:
                continue
            wsf, wsv = wf[sn], wv[sn]
            start = _block_start(wsf)
            if start is None:
                continue
            off = _block_offset(wsf, start)
            for idx, row in enumerate(wsv.iter_rows(min_row=start, max_col=56, values_only=True),
                                      start=start):
                a, drawn = row[0], list(row[1:7])
                ranking, got = list(row[11:56]), [row[8], row[9], row[10]]
                rnd = a if (isinstance(a, int) and a >= 1000) else (
                    latest + off - (idx - start) if latest is not None else None)
                if (rnd is None or any(v is None for v in drawn)
                        or any(not isinstance(v, int) for v in ranking) or len(set(ranking)) != 45):
                    continue
                exp = list(_hits(ranking, drawn))
                if exp != got or sum(exp) != 6:
                    bad += 1
    finally:
        wf.close()
        wv.close()
    return bad


def heal_if_inconsistent(path: Path, latest_round: int) -> None:
    """새 회차가 없어도 블록이 어긋나 있으면 고친다(매 실행 자기치유).

    정상이면 파일을 열지도 않는다 — 어긋난 행이 있을 때만 저장·재계산한다."""
    bad = _block_mismatch_rows(path)
    if not bad:
        return
    log(f"  [정합화] 3차필터 블록에서 어긋난 행 {bad}개 발견 → 재계산합니다")
    wb = openpyxl.load_workbook(path, data_only=False)
    try:
        fixed = realign_sliding_blocks(wb, _draws_from_sheet(wb[ALL_SHEET]))
        wb.save(path)
    finally:
        wb.close()
    log(f"  [정합화] 완료: {', '.join(fixed) if fixed else '(대상 없음)'}")
    try:
        recalc_and_save(path)
    except Exception as e:  # noqa: BLE001
        log(f"  [경고] 엑셀 재계산(캐시값 굽기)을 건너뜁니다: {e}")
    verify_after_update(path, expected_max_round=latest_round)


# ============================== 구조 편집 (openpyxl) ===========================

def append_draw_result(ws_all, rec: dict) -> int:
    next_row = ws_all.max_row + 1
    ws_all.cell(next_row, 1, rec["round"])
    for i, n in enumerate(rec["nums"]):
        ws_all.cell(next_row, 2 + i, n)
    ws_all.cell(next_row, 8, rec["bonus"])
    return next_row


def append_cumfreq_row(ws_cum, round_no: int, all_row_num: int) -> int:
    """_calc_누적빈도에 회차 하나의 누적 출현횟수 행을 추가한다. all_row_num은
    전체당첨내역에 방금 추가된 행 번호(두 시트는 항상 행 번호가 1:1로 대응해야 함)."""
    next_row = ws_cum.max_row + 1
    prev_row = next_row - 1
    ws_cum.cell(next_row, 1, round_no)
    for c in range(2, 47):
        col_letter = get_column_letter(c)
        num = c - 1
        formula = (
            f"={col_letter}{prev_row}+COUNTIF("
            f"{ALL_SHEET}!$B{all_row_num}:$G{all_row_num},{num})"
        )
        ws_cum.cell(next_row, c, formula)
    return next_row


def get_current_max_round(path: Path) -> int:
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb[ALL_SHEET]
    val = ws.cell(ws.max_row, 1).value
    wb.close()
    return int(val)


def process_new_rounds(path: Path, new_rounds: list[dict]) -> None:
    wb = openpyxl.load_workbook(path, data_only=False)
    ws_all = wb[ALL_SHEET]
    ws_cum = wb[CUM_SHEET]

    last_round = None
    for rec in new_rounds:
        all_row = append_draw_result(ws_all, rec)
        cum_row = append_cumfreq_row(ws_cum, rec["round"], all_row)
        if all_row != cum_row:
            raise RuntimeError(
                f"{ALL_SHEET}와 {CUM_SHEET}의 행 번호가 어긋남"
                f"(all_row={all_row}, cum_row={cum_row}) — 두 시트가 이미 1:1로 "
                f"안 맞는 상태인 것으로 보임. 자동 처리를 중단합니다."
            )
        last_round = rec["round"]

    fixed = realign_sliding_blocks(wb, _draws_from_sheet(ws_all))
    if fixed:
        log(f"  3차필터 블록 정합화(예측순위·적중수 재계산): {', '.join(fixed)}")

    wb.save(path)
    log(f"  저장 완료({len(new_rounds)}개 회차 반영). 재계산 + 캐시값 굽는 중...")
    try:
        recalc_and_save(path)
    except Exception as e:  # noqa: BLE001
        log(f"  [경고] 엑셀 재계산(캐시값 굽기)을 건너뜁니다: {e}")
        log("         행 추가는 이미 저장됐습니다 — 엑셀로 열면 자동 재계산됩니다.")

    verify_after_update(path, expected_max_round=last_round)
    log("  재계산 후 검증 통과(다음 예측 회차 자동 갱신 확인, 후보숫자 순위표 정상).")


# ============================== 메인 =========================================

def main() -> int:
    log("=" * 70)
    log("★후보숫자_추적표_표본vs최근50회 자동 업데이트 시작")

    if not TARGET_FILE.exists():
        log(f"[오류] 파일을 찾을 수 없음 -> {TARGET_FILE} (CONFIG의 TARGET_FILE 확인 필요)")
        return 1

    try:
        local_max = get_current_max_round(TARGET_FILE)
    except Exception as e:
        log(f"[오류] 현재 최신 회차 확인 실패 -> {e}")
        return 1

    # 2026-09-27: 조회 실패와 "정말 최신"을 구분 — 실패를 최신으로 넘기면 스케줄러가
    # 전부 성공으로 보고 조용히 밀린다(실제로 9/15 이후 그렇게 밀려 있었다).
    try:
        new_rounds = find_new_rounds(local_max)
    except Exception as e:
        log(f"[오류] 회차 조회 실패 -> {e}")
        log("      조회 실패는 '최신'이 아닙니다 — 이번 실행을 실패로 끝냅니다(스케줄러가 재시도).")
        log("=" * 70)
        return 1
    if not new_rounds:
        # 2026-09-27: 새 회차가 없어도(또는 전에 밀린 상태가 남아 있으면) 블록을 점검해 고친다.
        try:
            heal_if_inconsistent(TARGET_FILE, local_max)
        except Exception as e:  # noqa: BLE001
            log(f"  [경고] 블록 정합화 점검/보정 실패: {e}")
        log(f"이미 최신 상태입니다(전체당첨내역 최신회차={local_max}). 종료.")
        log("=" * 70)
        return 0

    log(f"현재 {local_max}회차까지 반영됨 -> "
        f"{[r['round'] for r in new_rounds]}회차 새로 반영 시작")

    try:
        process_new_rounds(TARGET_FILE, new_rounds)
    except Exception as e:
        log(f"[오류] 처리 중 예외 발생: {e}")
        log("      원인 확인 후 재실행 필요.")
        return 1

    try:
        errs = scan_errors(TARGET_FILE)
        if errs:
            log(f"[경고] 저장 후 오류값 {len(errs)}개 발견 -> {errs[:5]}")
            log("주간 업데이트 종료 (오류/경고 있음 — 위 로그 확인 필요)")
            log("=" * 70)
            return 1
        log("저장 후 오류값 없음 확인 완료.")
    except Exception as e:
        log(f"[경고] 오류값 스캔 실패 -> {e}")

    log("주간 업데이트 종료 (정상)")
    log("=" * 70)
    return 0


if __name__ == "__main__":
    # 2026-09-27: DB(draw_results) 조회를 쓰게 되면서 db_turso의 non-daemon 스레드가
    # 프로세스 종료를 붙잡는다 — 스케줄러가 종료코드를 못 받고 프로세스가 계속 남는다.
    # hourly_draw_sync.py와 동일하게 os._exit()로 즉시 종료한다.
    import os as _os

    _os._exit(main())
