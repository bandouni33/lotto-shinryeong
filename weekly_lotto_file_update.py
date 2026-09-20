# -*- coding: utf-8 -*-
"""
매주 일요일 9:00~14:00(KST) 사이, lotto-app 폴더의 4개 "조합생성_후보숫자_추적표" 엑셀
파일을 최신 회차로 자동 업데이트하는 스크립트.

2026-09-13: 1240회차를 수동으로 고친 작업(엑셀 재계산 → 수식을 값으로 고정 →
다음 예측행 생성)을 그대로 자동화한 것. 반드시 알아야 할 전제 3가지:

  1. 데이터 출처는 "당번" 시트(xlsb)가 아니라 동행복권 공식 API다.
     "당번" 시트/xlsb 경로는 2026-09-01에 이미 폐기됐고(draw_results_db.py 주석 참고),
     그 이후로는 갱신된 적이 없다. 이 스크립트는 앱(draw_results_db.py)이 실제로
     쓰는 것과 동일한 공식 API를 직접 두드린다.

  2. "전체당첨내역" 시트에 새 회차를 추가하는 것만으로는 부족하다.
     파일 3(전체표본_윈도우비교)·4(최근500표본_윈도우비교)의 "3차필터(NN회_후보)"
     시트들은 "예측이 맞았는지 채점표" 구조라서, 매주 다음 3단계를 반드시 순서대로
     거쳐야 한다:
       a) 현재 대기 중인 예측행(7행)의 수식 결과값(L~BD열, 45개 후보 순위)을
          "지금 이 순간" 값으로 고정(freeze) — 전체당첨내역을 건드리기 전에 해야
          정확하다. 나중에 건드리면 수식이 재계산되면서 그 사이에 값이 달라진다.
       b) 그 고정값 vs 이번 주 실제 당첨번호로 적중횟수(상위/중위/하위) 계산해서
          채워넣고, 맨 위에서 8행으로 밀어낸다.
       c) 새 7행(다음 회차 예측 대상)을 만들고 동일한 배열수식을 복사해 넣는다 —
          이 수식은 행 번호에 의존하지 않는 구조라(L$1:BD$1, L$4:BD$4처럼 항상
          고정된 1~4행만 참조) 그대로 복사해도 안전하다(2026-09-13에 직접 검증함).
     이 전체 과정에 엑셀 재계산이 두 번 필요해서(1240 처리 후 한 번, 1241 처리 후
     한 번 — 밀린 회차 수만큼) 단순 openpyxl만으로는 불가능하고, 엑셀 COM 자동화
     (win32com)로 실제 엑셀을 백그라운드로 띄워서 재계산시킨다.

  3. 파일 1(샘플)·2(200회검증용)은 "3차필터" 구조가 아니라 회차를 컬럼으로 나열하는
     완전히 다른 구조이고, 그중 파일 1의 "AUTO" 수식은 컬럼 하나당 수천 자짜리
     중첩 수식 + 컬럼별 스테이징 블록(1504~1516행)까지 필요해서, 새 컬럼을 추가하는
     자동화는 이번에 넣지 않았다(수식 손상 위험이 너무 큼). 이 스크립트는 파일
     1·2에는 "전체당첨내역" 갱신까지만 하고, 컬럼 확장은 손으로 하거나 별도로
     요청해야 한다 — 실행 후 로그에 이 사실을 매번 남긴다.

필요 사전 설치 (엑셀이 설치된 그 PC에서, 명령 프롬프트에서 한 번만):
    pip install openpyxl pywin32

사용 전 CONFIG 아래 FILE_PATHS를 실제 lotto-app 폴더 경로로 수정할 것.

작업 스케줄러 등록 (관리자 권한 명령 프롬프트에서 한 번만 실행):
    schtasks /create /tn "로또신령_주간엑셀업데이트" /tr "python C:\\경로\\weekly_lotto_file_update.py" ^
        /sc weekly /d SUN /st 09:10 /ri 60 /du 0004:50 /f

    (/ri 60 /du 0004:50 = 09:10부터 60분 간격으로 4시간50분 동안, 즉 09:10~14:00
    사이에 최대 6번 재시도. 스크립트 자체가 "이미 최신이면 아무것도 안 하고 종료"
    하므로 여러 번 실행돼도 안전함 — 동행복권 발표가 늦어지는 경우에 대한 안전망.)
"""

from __future__ import annotations

import datetime
import json
import sys
import time
import urllib.request
from pathlib import Path

import openpyxl
from openpyxl.worksheet.formula import ArrayFormula

# ============================== CONFIG ======================================

LOTTO_APP_DIR = Path(r"C:\Users\PC\Desktop\lotto-app")

# 2026-09-20(사용자 지시): 4개 엑셀 파일이 lotto-app 폴더 바로 밑에서
# "★조합생성_후보숫자_추적표" 하위 폴더로 이동됨 — 경로만 반영, 파일명·구조는
# 그대로다(candidate_tracker_auto_update.py의 TARGET_FILE도 동일한 폴더를 쓴다).
_TRACKER_DIR = LOTTO_APP_DIR / "★조합생성_후보숫자_추적표"

FILE_PATHS = {
    "샘플": _TRACKER_DIR / "조합생성_후보숫자_추적표_샘플.xlsx",
    "200회검증용": _TRACKER_DIR / "조합생성_후보숫자_추적표_샘플_200회검증용.xlsx",
    "전체표본": _TRACKER_DIR / "조합생성_후보숫자_추적표_전체표본_윈도우비교.xlsx",
    "최근500표본": _TRACKER_DIR / "조합생성_후보숫자_추적표_최근500표본_윈도우비교.xlsx",
}

# 3차필터(NN회_후보) 구조를 가진 파일(= 자동 예측행 갱신까지 수행)
ADVANCE_3CHA_FILES = {"전체표본", "최근500표본"}

LOG_FILE = LOTTO_APP_DIR / "weekly_update_log.txt"

# ============================== 데이터 소스 ===================================
# 2026-09-01 이후 정식 소스: 동행복권 공식 API (draw_results_db.py와 동일)
_DHLOTTERY_ROUND_URL = "https://www.dhlottery.co.kr/common.do?method=getLottoNumber&drwNo={round}"


def fetch_round_from_dhlottery(round_no: int) -> dict | None:
    """특정 회차의 당첨번호를 동행복권 공식 API에서 가져온다.
    아직 추첨 전이거나 존재하지 않는 회차면 None을 반환한다(returnValue=="fail")."""
    url = _DHLOTTERY_ROUND_URL.format(round=round_no)
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        log(f"  [경고] {round_no}회차 조회 실패(네트워크/응답 오류): {e}")
        return None

    if data.get("returnValue") != "success":
        return None

    nums = sorted(
        int(data[f"drwtNo{i}"]) for i in range(1, 7)
    )
    return {"round": round_no, "nums": nums, "bonus": int(data["bnusNo"])}


def find_new_rounds(local_max_round: int, hard_limit: int = 10) -> list[dict]:
    """local_max_round 다음 회차부터 순서대로 조회해서, 존재하는(=이미 추첨된)
    회차를 모두 리스트로 반환한다. hard_limit: 한 번에 너무 많이 밀렸을 때(버그로
    오래 안 돌았거나 한 경우) 무한루프 방지용 상한."""
    out = []
    r = local_max_round + 1
    while len(out) < hard_limit:
        rec = fetch_round_from_dhlottery(r)
        if rec is None:
            break
        out.append(rec)
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

def recalc_and_read_pending_row(path: Path, sheet_names: list[str]) -> dict[str, list[int]]:
    """실제 엑셀을 백그라운드로 띄워 해당 파일을 열고, 강제 전체 재계산 후
    각 시트의 7행(현재 대기 중인 예측행) L~BD열(45개 후보 순위값)을 읽어서 반환한다.
    저장하지 않고 닫는다(구조 편집은 이 함수 호출 뒤 openpyxl로 별도 진행)."""
    import win32com.client

    result: dict[str, list[int]] = {}
    excel = win32com.client.DispatchEx("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    try:
        wb = excel.Workbooks.Open(str(path.resolve()), ReadOnly=True)
        try:
            excel.CalculateFullRebuild()
            for sn in sheet_names:
                ws = wb.Sheets(sn)
                row7_label = ws.Range("A7").Value
                vals = ws.Range("L7:BD7").Value2  # tuple of tuples, 1행 x 45열
                flat = [int(v) for v in vals[0]]
                if len(flat) != 45 or len(set(flat)) != 45:
                    raise RuntimeError(
                        f"{path.name}/{sn}: L7:BD7 재계산 결과가 이상함(45개의 "
                        f"서로 다른 숫자가 아님) — row7 회차라벨={row7_label}, 값={flat}"
                    )
                result[sn] = flat
        finally:
            wb.Close(SaveChanges=False)
    finally:
        excel.Quit()
    return result


def recalc_and_save(path: Path) -> None:
    """구조 편집이 끝난 파일을 열어 강제 재계산 후 그대로 저장 — 캐시된 값을
    최신으로 구워넣어서, 사용자가 나중에 파일을 열었을 때 재계산 전에도 바로
    올바른 값이 보이게 한다."""
    import win32com.client

    excel = win32com.client.DispatchEx("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    try:
        wb = excel.Workbooks.Open(str(path.resolve()))
        try:
            excel.CalculateFullRebuild()
            wb.Save()
        finally:
            wb.Close(SaveChanges=True)
    finally:
        excel.Quit()


# ============================== 엑셀 오류값 스캔 ================================

_ERR = {"#N/A", "#REF!", "#VALUE!", "#DIV/0!", "#NAME?", "#NULL!", "#NUM!"}


def scan_errors(path: Path) -> list[tuple[str, str, str]]:
    """저장된 파일을 읽기 전용으로 열어 모든 시트의 캐시값 중 엑셀 오류값이
    있는지 스캔한다. (경로, 시트명, 셀좌표+값) 리스트 반환 — 비어있으면 정상."""
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    found = []
    for sn in wb.sheetnames:
        ws = wb[sn]
        for row in ws.iter_rows():
            for cell in row:
                v = cell.value
                if isinstance(v, str) and v.strip() in _ERR:
                    found.append((path.name, sn, f"{cell.coordinate}={v}"))
    wb.close()
    return found


# ============================== 구조 편집 (openpyxl) ===========================

def append_draw_result(ws_all, rec: dict) -> None:
    next_row = ws_all.max_row + 1
    ws_all.cell(next_row, 1, rec["round"])
    for i, n in enumerate(rec["nums"]):
        ws_all.cell(next_row, 2 + i, n)
    ws_all.cell(next_row, 8, rec["bonus"])


def advance_3cha_sheet(ws, sheet_name: str, forecast45: list[int], actual_rec: dict) -> tuple[int, int, int]:
    """7행(대기 중인 예측행)을 8행으로 확정(수식→값 고정 + 실제결과/적중수 채움)
    시키고, 맨 아래 행을 하나 지워서 창 크기를 유지하며, 새 7행(다음 회차 대기)을
    만든다. 2026-09-13 1240/1241 수동 처리 때 검증된 것과 동일한 로직."""
    max_row_before = ws.max_row

    formula_texts = {}
    for c in range(12, 57):
        v = ws.cell(7, c).value
        formula_texts[c] = v.text if isinstance(v, ArrayFormula) else v

    t1, t2, t3 = set(forecast45[0:15]), set(forecast45[15:30]), set(forecast45[30:45])
    a = set(actual_rec["nums"])
    hit_top, hit_mid, hit_low = len(a & t1), len(a & t2), len(a & t3)
    if hit_top + hit_mid + hit_low != 6:
        raise RuntimeError(f"{sheet_name}: 적중수 합계가 6이 아님({hit_top}+{hit_mid}+{hit_low})")

    ws.insert_rows(7, amount=1)
    ws.delete_rows(max_row_before + 1, amount=1)

    for i, c in enumerate(range(12, 57)):
        ws.cell(8, c).value = forecast45[i]
    for i, n in enumerate(actual_rec["nums"]):
        ws.cell(8, 2 + i).value = n
    ws.cell(8, 8).value = actual_rec["bonus"]
    ws.cell(8, 9).value = hit_top
    ws.cell(8, 10).value = hit_mid
    ws.cell(8, 11).value = hit_low
    if ws.cell(8, 1).value != actual_rec["round"]:
        raise RuntimeError(
            f"{sheet_name}: 8행 회차라벨({ws.cell(8,1).value})이 예상 "
            f"회차({actual_rec['round']})와 다름 — 파일이 예상 구조와 어긋남, 중단."
        )

    next_round = actual_rec["round"] + 1
    ws.cell(7, 1).value = next_round
    for c in range(12, 57):
        ws.cell(7, c).value = ArrayFormula(ref=ws.cell(7, c).coordinate, text=formula_texts[c])
    for c in range(2, 12):
        ws.cell(7, c).value = None

    return hit_top, hit_mid, hit_low


def get_current_max_round(path: Path) -> int:
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb["전체당첨내역"]
    val = ws.cell(ws.max_row, 1).value
    wb.close()
    return int(val)


def process_one_round_for_file(path: Path, label: str, rec: dict) -> None:
    """파일 하나에 회차 하나(rec)를 반영. 3차필터 구조 파일이면 예측행도 같이 전진."""
    needs_3cha = label in ADVANCE_3CHA_FILES

    if needs_3cha:
        wb_peek = openpyxl.load_workbook(path, data_only=False, read_only=True)
        sheet_names = [sn for sn in wb_peek.sheetnames if sn.startswith("3차필터")]
        wb_peek.close()
        log(f"  [{label}] {rec['round']}회차 처리 전 재계산으로 예측행(L:BD) 확보 중...")
        forecasts = recalc_and_read_pending_row(path, sheet_names)

    wb = openpyxl.load_workbook(path, data_only=False)
    ws_all = wb["전체당첨내역"]

    if needs_3cha:
        for sn in sheet_names:
            hit_top, hit_mid, hit_low = advance_3cha_sheet(wb[sn], sn, forecasts[sn], rec)
            log(f"    {sn}: {rec['round']}회차 확정 (상위{hit_top}/중위{hit_mid}/하위{hit_low}), "
                f"다음 예측대상 -> {rec['round']+1}")
    else:
        log(f"  [{label}] {rec['round']}회차: 3차필터 구조가 아니므로 전체당첨내역만 갱신"
            f"(컬럼식 예측 구조 확장은 자동화 범위 밖 — 필요하면 별도로 요청할 것)")

    append_draw_result(ws_all, rec)
    wb.save(path)

    log(f"  [{label}] 저장 완료. 재계산 + 캐시값 굽기 중...")
    recalc_and_save(path)


def main() -> int:
    log("=" * 70)
    log("주간 로또신령 엑셀 파일 업데이트 시작")

    any_error = False

    for label, path in FILE_PATHS.items():
        if not path.exists():
            log(f"[오류] {label}: 파일을 찾을 수 없음 -> {path} (CONFIG의 LOTTO_APP_DIR 확인 필요)")
            any_error = True
            continue

        try:
            local_max = get_current_max_round(path)
        except Exception as e:
            log(f"[오류] {label}: 현재 최신 회차 확인 실패 -> {e}")
            any_error = True
            continue

        new_rounds = find_new_rounds(local_max)
        if not new_rounds:
            log(f"[{label}] 이미 최신 상태입니다 (전체당첨내역 최신회차={local_max}). 건너뜀.")
            continue

        log(f"[{label}] 현재 {local_max}회차까지 반영됨 -> "
            f"{[r['round'] for r in new_rounds]}회차 새로 반영 시작")

        for rec in new_rounds:
            try:
                process_one_round_for_file(path, label, rec)
            except Exception as e:
                log(f"[오류] {label} {rec['round']}회차 처리 중 예외 발생: {e}")
                log(f"       이 파일은 {rec['round']}회차 이후 회차를 이어서 처리하지 않고 중단합니다"
                    f"(다음 회차 예측 기준이 어긋날 수 있어 안전하게 멈춤). 원인 확인 후 재실행 필요.")
                any_error = True
                break

        try:
            errs = scan_errors(path)
            if errs:
                log(f"[경고] {label}: 저장 후 오류값 {len(errs)}개 발견 -> {errs[:5]}")
                any_error = True
            else:
                log(f"[{label}] 저장 후 오류값 없음 확인 완료.")
        except Exception as e:
            log(f"[경고] {label}: 오류값 스캔 실패 -> {e}")

    log("주간 업데이트 종료" + (" (오류/경고 있음 — 위 로그 확인 필요)" if any_error else " (정상)"))
    log("=" * 70)
    return 1 if any_error else 0


if __name__ == "__main__":
    sys.exit(main())
