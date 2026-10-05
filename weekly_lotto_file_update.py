# -*- coding: utf-8 -*-
"""
매주 일요일 9:00~14:00(KST) 사이, lotto-app 폴더의 4개 "조합생성_후보숫자_추적표" 엑셀
파일을 최신 회차로 자동 업데이트하는 스크립트.

2026-09-13: 1240회차를 수동으로 고친 작업(엑셀 재계산 → 수식을 값으로 고정 →
다음 예측행 생성)을 그대로 자동화한 것. 반드시 알아야 할 전제 3가지:

  1. 데이터 출처는 "당번" 시트(xlsb)도, 동행복권 API 직접 호출도 아니라 **DB(draw_results)**다.
     2026-09-27 교체: 예전엔 common.do?method=getLottoNumber 를 직접 두드렸는데, 그 주소는
     이제 회차와 무관하게 사이트 HTML(약 192KB)만 돌려준다(브라우저 User-Agent를 붙여도
     동일 — 실측). 그 결과 1242·1243회차가 들어오지 못한 채 "이미 최신"로 조용히 성공
     처리됐다. 앱이 쓰는 DB(draw_results)는 GitHub Actions가 토요일마다 갱신하고 회차
     결번 없이 전 회차를 갖고 있으므로 그쪽을 단일 소스로 쓴다. DB 조회가 실패하면
     "최신"으로 넘기지 않고 **비정상 종료(exit 1)** 해서 스케줄러가 실패를 드러내게 한다.

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

  3. 파일 1(샘플)의 "AUTO" 수식은 컬럼 하나당 수천 자짜리 중첩 수식 + 컬럼별
     스테이징 블록(1504~1516행)까지 필요해서, 새 컬럼을 추가하는 자동화는
     오래 "수식 손상 위험이 너무 큼"으로 제외돼 있었다. 2026-09-27(사용자 승인)
     임시 복사본 불변식 테스트(scratch/sim_sample_column_advance.py)로 190개
     불변식을 통과시켜 규칙을 실측으로 확정한 뒤 편입됐다 — 아래 "컴럼식 회차
     시트 전진" 참고. 파일 2(200회검증용)는 같은 컬럼 구조지만 사용자 지시
     범위가 아니라 아직 "전체당첨내역" 갱신까지만 한다(필요해지면
     COLUMN_ROUND_FILES에 추가하면 된다).

  4. 파일 1(샘플)의 "1차추적결과"·"2차추적결과"·"4차필터"는 회차를 '행'으로 나열한다
     (3~104행 = 102회차 창). 이 행들도 2026-09-27(사용자 승인)부터 매주 자동으로 밀린다:
     새 회차가 3행에 들어가고 맨 아래 행을 버려 창 크기를 유지한다. 값은 앱 배포
     파이프라인과 같은 정의(combo_filter_v2.compute_stage_masks)로 계산하고, 같은
     파일의 "앱자동화_대조" 시트에 회차별 "파일 계산값 vs 앱 DB 기록
     (draw_generation_stats)"과 일치 판정을 함께 적는다. 1244회차 이하는 규칙 변경 전
     배포분이라 달라도 "이력(규칙 불일치)"으로만 표시하고, 1245회차부터는 다르면 실패로
     처리한다(RULE_VINTAGE_ROUND — 규칙을 또 바꾸면 그 상수를 올려야 한다).

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
import re
import sys
import time
import urllib.request
from copy import copy as _style_copy
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter as _col_letter
from openpyxl.worksheet.formula import ArrayFormula

from env_loader import load_dotenv_file

load_dotenv_file()  # 단독 실행(작업 스케줄러)에서도 TURSO_* 환경변수를 읽게 한다

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
    # 2026-10-05(사용자 지시): 최근500표본을 복사해 2행 기준모집단만 최근300회로 바꾼 파일.
    # 구조·수식·7행 배열수식·서식은 최근500표본과 동일 — 전진 로직도 그대로 쓴다.
    "최근300표본": _TRACKER_DIR / "조합생성_후보숫자_추적표_최근300표본_윈도우비교.xlsx",
}

# 3차필터(NN회_후보) 구조를 가진 파일(= 자동 예측행 갱신까지 수행)
ADVANCE_3CHA_FILES = {"전체표본", "최근500표본", "최근300표본"}

LOG_FILE = LOTTO_APP_DIR / "weekly_update_log.txt"

# ============================== 데이터 소스 ===================================
# 2026-09-27: 정식 소스는 DB(draw_results) — 아래 find_new_rounds 참고.
# (죽은 엔드포인트 기록: https://www.dhlottery.co.kr/common.do?method=getLottoNumber —
#  현재는 어떤 헤더로도 JSON이 아닌 사이트 HTML만 돌려준다.)


def find_new_rounds(local_max_round: int, hard_limit: int = 10) -> list[dict]:
    """로컬 파일이 아직 모르는 회차를 **DB(draw_results)** 에서 오름차순으로 모아 반환.

    hard_limit: 오래 안 돌아 밀렸을 때의 안전 상한(초과분은 다음 실행이 이어받는다).
    DB에 구멍(예: 1244가 없는데 1245가 있음)이 있으면 그 자리에서 멈추지 않고 예외를
    던진다 — 조용히 뒤처진 채 다음 주로 넘어가는 것을 막기 위함(호출부가 exit 1 처리).
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

def _safe_print(line: str) -> None:
    """콘솔 인코딩(한국어 Windows 기본 cp949)에 없는 글자(em-dash 등) 때문에 print가
    UnicodeEncodeError로 죽는 것을 막는다 — 로그 한 줄 때문에 자동화 전체가 멈추면 안 된다
    (2026-09-27 실측: 시험 실행에서 이 오류로 회차 처리가 중단됐다). 파일 로그(UTF-8)는
    그대로 두고 콘솔 출력만 인코딩 가능한 형태로 바꾼다."""
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "utf-8"
        print(line.encode(enc, errors="replace").decode(enc, errors="replace"), flush=True)


def log(msg: str) -> None:
    line = f"[{datetime.datetime.now().isoformat(timespec='seconds')}] {msg}"
    _safe_print(line)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ============================== 엑셀 재계산 (win32com) =========================

_EXCEL_OPEN_ATTEMPTS = 3
_EXCEL_OPEN_DELAY_SEC = 3


def _open_workbook(excel, path: Path, read_only: bool = False):
    """Excel COM Workbooks.Open — 실패 시 재시도(2026-09-27 실측 대응).

    이 PC에서 하루 첫 두 번의 Excel 기동이 'Workbooks 클래스 중 Open 메서드에
    오류가 있습니다'(-2147352567)로 실패하고 그 다음부터 정상 동작하는 것을 실측했다
    (초기 모달/기동 준비 상태로 추정). 예전에는 그 한 번의 실패가 그 파일의 그 회차
    처리를 통째로 중단시켰다 — 짧게 재시도해서 일시적 실패가 자동화를 멈추지 않게 한다."""
    last = None
    for attempt in range(1, _EXCEL_OPEN_ATTEMPTS + 1):
        try:
            return excel.Workbooks.Open(str(path.resolve()), ReadOnly=read_only)
        except Exception as e:  # noqa: BLE001
            last = e
            log(f"  [주의] Excel이 파일을 열지 못했습니다(시도 {attempt}/{_EXCEL_OPEN_ATTEMPTS}): {e}")
            time.sleep(_EXCEL_OPEN_DELAY_SEC)
    raise RuntimeError(f"Excel로 파일을 열 수 없습니다(재시도 {_EXCEL_OPEN_ATTEMPTS}회 모두 실패): {last}")


def _window_from_label(label, default=None):
    """시트 라벨에서 빈도 창을 읽는다 — '기준빈도(전체)'→None(전체),
    '기준빈도(최근500회)'/'최근100회 빈도'→500/100, '최근50회 빈도(고정)'→50."""
    m = re.search(r"최근\s*(\d+)\s*회", str(label or ""))
    return int(m.group(1)) if m else default


def _python_pending_forecast(path: Path, sheet_names: list[str]) -> dict[str, list[int]]:
    """엑셀이 계산해줄 예측행(L:BD = 격차순위 1~45위)을 **파이썬으로 직접 계산** —
    엑셀 설치/COM 상태에 자동화가 매달리지 않게 하는 폴백(2026-09-27 신규).

    워크북 3차필터 시트의 수식과 완전히 같은 정의:
      2행 = 기준빈도(전체 또는 최근500회) // 3행 = 최근N회 빈도
      오차 = rank(3행) - rank(2행)  (동점은 작은 번호 우선 = RANK+COUNTIFS와 동일)
      예측 순위 = 오차 내림차순, 동점이면 번호 오름차순
    이 계산은 scratch/verify_workbook_ranking.py로 워크북 24개 시트 전부와 일치함을,
    그리고 배포 엔진(combo_filter_v2._gap_order_for_anchor)과도 완전히 같음을 확인했다.
    """
    nums = list(range(1, 46))

    def counts(draws, window):
        lo = draws[0][0] if (not window or window >= len(draws)) else draws[-1][0] - (window - 1)
        return {n: sum(1 for r, ns in draws if r >= lo and n in ns) for n in nums}

    def ranks(vals):
        return {n: (1 + sum(1 for m in nums if vals[m] > vals[n])
                    + sum(1 for m in nums if vals[m] == vals[n] and m < n)) for n in nums}

    wb = openpyxl.load_workbook(path, data_only=False, read_only=True)
    try:
        draws = []
        for row in wb["전체당첨내역"].iter_rows(min_row=2, values_only=True):
            if row[0] is None:
                continue
            draws.append((int(row[0]), [int(x) for x in row[1:7]]))
        draws.sort(key=lambda t: t[0])
        if not draws:
            raise RuntimeError("전체당첨내역에서 회차를 읽지 못했습니다")

        out: dict[str, list[int]] = {}
        for sn in sheet_names:
            ws = wb[sn]
            w2 = _window_from_label(ws.cell(2, 11).value)
            w3 = _window_from_label(ws.cell(3, 11).value)
            r2, r3 = ranks(counts(draws, w2)), ranks(counts(draws, w3))
            gap = {n: r3[n] - r2[n] for n in nums}
            out[sn] = sorted(nums, key=lambda n: (-gap[n], n))
            log(f"      {sn}: 2행창={w2 or '전체'}, 3행창={w3 or '전체'}, 최신={draws[-1][0]}회차 (파이썬 계산)")
        return out
    finally:
        wb.close()


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
        wb = _open_workbook(excel, path, read_only=True)
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
        wb = _open_workbook(excel, path)
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


# ── 컬럼식 회차 시트 전진 (2026-09-27, 사용자 승인) ─────────────────────────────
# 왜 생겼나: 샘플 파일은 회차를 '행'이 아니라 '컬럼'으로 나열한다. 예전에는 "컬럼당
# 수천 자 중첩 수식 + 컬럼별 스테이징 블록(1504~1516행)이라 손상 위험이 크다"며
# 자동화에서 빼놨었다. 임시 복사본 시뮬레이터(scratch/sim_sample_column_advance.py)로
# 190개 불변식을 통과시켜 규칙을 실측으로 확정한 뒤 편입했다:
#   · 새 회차 열 = 옛 최신 열을 '원문 그대로' 복사 — 각 열의 수식은 자기 열만 참조하므로
#     (N$4·N$1504~N$1516) 문자를 바꿀 필요가 없다.
#   · 밀려나는 열은 자기 열 참조만 +1 번역(N$4→O$4). 시트명·문자열 리터럴은 그대로 둔다.
#   · 가장 오래된 열은 내용을 비운다(열 개수 유지 = 창 크기 고정).
#   · 서식(_style)·열 너비·병합·숨김 열도 함께 옮긴다.
#   · openpyxl은 계산을 하지 않으므로 값은 저장 후 엑셀 재계산(recalc_and_save)이 채운다.
COLUMN_ROUND_FILES = {"샘플"}
COLUMN_ROUND_SHEETS = ("1차필터(7기본필터)", "2차필터(5이격수)")


def _round_columns(ws) -> tuple[int, int, list[int]]:
    """4행에 회차 숫자가 연속으로 놓인 '회차 열' 범위를 찾는다."""
    cols = [(c, ws.cell(4, c).value) for c in range(1, ws.max_column + 1)
            if isinstance(ws.cell(4, c).value, int)]
    if not cols:
        raise RuntimeError("회차 라벨(4행)을 찾지 못했습니다 — 시트 구조가 예상과 다릅니다")
    return cols[0][0], cols[-1][0], [v for _, v in cols]


def _cell_formula(cell):
    """셀의 수식 문자열(배열수식 포함). 수식이 아니면 None."""
    v = cell.value
    if isinstance(v, ArrayFormula):
        return v.text
    return v if isinstance(v, str) and v.startswith("=") else None


def _translate_col_refs(text: str, src: str, dst: str) -> str:
    """자기 열 참조만 한 칸 옮긴다 — 'N$4'→'O$4', 'N$1504'→'O$1504'.
    앞 글자가 영문/숫자/_/$/. 이면 다른 열 참조나 함수명이므로 건드리지 않는다."""
    return re.sub(r"(?<![A-Za-z0-9_$.!])" + src + r"(\$?\d+)", dst + r"\1", text)


def _translate_col_value(val, src: str, dst: str):
    if isinstance(val, ArrayFormula):
        return ArrayFormula(ref=_translate_col_refs(val.ref, src, dst),
                            text=_translate_col_refs(val.text, src, dst))
    if isinstance(val, str) and val.startswith("="):
        return _translate_col_refs(val, src, dst)
    return val


def _merged_inner_cells(ws) -> set[tuple[int, int]]:
    """병합 범위의 앵커가 아닌 셀 — openpyxl에서는 여기에 값을 쓸 수 없다."""
    skip: set[tuple[int, int]] = set()
    for rng in ws.merged_cells.ranges:
        for r in range(rng.min_row, rng.max_row + 1):
            for c in range(rng.min_col, rng.max_col + 1):
                if (r, c) != (rng.min_row, rng.min_col):
                    skip.add((r, c))
    return skip


def _write_cells(ws, col: int, items, max_row: int, skip: set[tuple[int, int]]) -> None:
    for r in range(1, max_row + 1):
        if (r, col) not in skip:
            ws.cell(r, col).value = None
    for r, val, style in items:
        if (r, col) in skip:
            raise RuntimeError(
                f"컬럼 전진 목적지 {_col_letter(col)}{r}이 병합 영역 안쪽입니다 — 구조 확인 필요")
        cell = ws.cell(r, col)
        cell.value = val
        cell._style = _style_copy(style)


def shift_round_columns(ws, new_label: int) -> dict:
    """회차 컬럼을 한 칸 오른쪽으로 밀고 맨 왼쪽에 새 회차 열을 만든다."""
    first, last, labels = _round_columns(ws)
    max_row = ws.max_row
    merges_before = sorted(rng.coord for rng in ws.merged_cells.ranges)
    skip = _merged_inner_cells(ws)
    inner = [f"{_col_letter(c)}{r}" for (r, c) in skip if ws.cell(r, c).value is not None]
    if inner:
        raise RuntimeError(f"병합 영역 안쪽 셀에 값이 있습니다({inner[:3]}) — 전진 전 확인 필요")

    widths = {c: (ws.column_dimensions[_col_letter(c)].width,
                  ws.column_dimensions[_col_letter(c)].bestFit)
              for c in range(first, last + 1)}
    snaps: dict[int, list] = {}
    for c in range(first, last + 1):
        items = []
        for r in range(1, max_row + 1):
            cell = ws.cell(r, c)
            if cell.value is not None:
                items.append((r, cell.value, _style_copy(cell._style)))
        snaps[c] = items

    for c in range(last, first, -1):                 # 오른쪽부터(덮어쓰기 방지)
        src_letter, dst_letter = _col_letter(c - 1), _col_letter(c)
        items = [(r, _translate_col_value(v, src_letter, dst_letter), st)
                 for r, v, st in snaps[c - 1]]
        if c == last:
            _write_cells(ws, c, [], max_row, skip)
        _write_cells(ws, c, items, max_row, skip)
        ws.column_dimensions[dst_letter].width = widths[c - 1][0]
        ws.column_dimensions[dst_letter].bestFit = widths[c - 1][1]

    _write_cells(ws, first, snaps[first], max_row, skip)   # 새 회차 열 = 옛 최신 열 원문
    ws.column_dimensions[_col_letter(first)].width = widths[first][0]
    ws.column_dimensions[_col_letter(first)].bestFit = widths[first][1]
    ws.cell(4, first).value = new_label

    if sorted(rng.coord for rng in ws.merged_cells.ranges) != merges_before:
        raise RuntimeError("컬럼 전진 중 병합 범위가 바뀌었습니다")
    return {"first": first, "last": last,
            "labels_before": labels[0], "labels_after": new_label}


def advance_round_columns(path: Path, label: str) -> dict[str, dict]:
    """회차 컬럼 시트들을 전체당첨내역 최신 회차까지 민다(이미 최신이면 그대로).

    호출 전에 전체당첨내역에 그 회차가 들어가 있어야 한다 — 새 열의 헬퍼행이
    MATCH(N$4)/(N$4-1)로 그 회차 번호를 찾기 때문이다."""
    wb = openpyxl.load_workbook(path, data_only=False)
    try:
        ws_all = wb["전체당첨내역"]
        latest = max(int(ws_all.cell(r, 1).value) for r in range(2, ws_all.max_row + 1)
                     if isinstance(ws_all.cell(r, 1).value, int))
        out: dict[str, dict] = {}
        for sn in COLUMN_ROUND_SHEETS:
            if sn not in wb.sheetnames:
                raise RuntimeError(f"{label}: 시트 '{sn}'을 찾지 못했습니다")
            ws = wb[sn]
            _, _, labels = _round_columns(ws)
            base = labels[0]
            shifts = latest - base
            if shifts < 0:
                raise RuntimeError(
                    f"{label}/{sn}: 컬럼 라벨({base})이 전체당첨내역 최신({latest})보다 "
                    f"앞서 있습니다 — 파일 상태 확인 필요")
            for i in range(shifts):
                shift_round_columns(ws, base + i + 1)
            out[sn] = {"shifts": shifts, "labels_before": base, "labels_after": base + shifts}
        if any(v["shifts"] for v in out.values()):
            wb.save(path)
        return out
    finally:
        wb.close()


# ── 행식 회차 시트 전진 + 앱 기록 대조 (2026-09-27, 사용자 승인) ────────────────
# 왜 생겼나: 샘플 파일은 회차를 컬럼(1차필터·2차필터)과 행(추적결과 시트) 양쪽으로
# 나열한다. 컬럼은 위에서 전진하게 했지만, 행 시트(1차추적결과·2차추적결과·4차필터)는
# 1241회차에서 멈춰 있었다. 임시 복사본 시뮬레이터(scratch/sim_sample_row_advance.py)로
# 21개 불변식을 통과시켜 규칙을 실측으로 확정한 뒤 편입했다:
#   · 새 회차는 3행(맨 위)에 들어가고 맨 아래 행을 버려 창 크기(102행)를 유지한다.
#   · 밀린 회차는 오래된 것부터 차례로 3행에 쌓는다(최신이 맨 위).
#   · J열(=SUM(K:M))은 자기 행 번호를 쓰므로 밀린 행 전부 다시 쓴다.
#   · H열은 그 단계의 '입력' 조합수 사슬(1차입력=전체 → 2차입력=1차 → 4차입력=2차).
# 값 정의는 앱 배포 파이프라인과 같은 곳(combo_filter_v2.compute_stage_masks)을 쓴다 —
# 그래야 아래 대조 시트가 "파일 계산값 vs 앱 실제 배포 기록"을 비교하는 표가 된다.
ROW_ROUND_FILES = {"샘플"}
ROW_ROUND_SHEETS = ("1차추적결과", "2차추적결과", "4차필터")
ROW_FIRST, ROW_LAST = 3, 104           # 3~104행 = 102회차 창
ROW_WINDOW = ROW_LAST - ROW_FIRST + 1

# 대조 시트 — 회차별로 '파일 계산값'과 '앱 DB 기록(draw_generation_stats)'을 나란히 적고
# 일치 여부를 판정한다. 샘플 파일 안에만 만든다(다른 시트는 건드리지 않는다).
DAEJO_SHEET = "앱자동화_대조"
DAEJO_HEADERS = ("회차", "파일_1차통과", "파일_2차통과", "파일_4차통과",
                 "앱_stage2", "앱_stage4", "앱_top5", "2차_판정", "4차_판정", "비고")

# 규칙 빈티지 경계 — 이 회차 **이상**부터는 파일 계산값과 앱 기록이 같아야 한다(다르면 실패).
# 1244회차 이하는 규칙 변경 전 배포분이라 달라도 이력일 뿐이다. 규칙을 또 바꾸면(예: 새 필터
# 규칙을 1250회차부터 적용) 이 값을 그 첫 배포 회차로 올려야 한다 — 그러지 않으면 바뀌기 전에
# 생성된 회차들이 '불일치(실패)'로 잘못 잡힌다.
RULE_VINTAGE_ROUND = 1245
DAEJO_VINTAGE_NOTE = (f"{RULE_VINTAGE_ROUND - 1}회차 이하 = 규칙 변경 전 배포분(차이 나도 정상)")

_TRACKING_BASE: dict | None = None


def _tracking_base() -> dict:
    """회차 무관 마스크(전체 조합·고정 378·이격수 48)를 프로세스당 한 번만 만든다 —
    여러 회차를 처리할 때 회차마다 수십 초를 다시 쓰지 않게(실측)."""
    global _TRACKING_BASE
    if _TRACKING_BASE is None:
        import combo_filter_v2 as cf

        log("  [추적계산] 회차 무관 마스크(전체 조합·1차 고정 378·2차 이격수 48) 계산 중...")
        _TRACKING_BASE = cf.build_base_masks()
    return _TRACKING_BASE


def _draws_asc_from_sheet(ws_all) -> list[dict]:
    """전체당첨내역 → [{'draw_round','nums','bonus'}...] 오름차순.

    회차·번호는 이 시트에서 값으로 읽는다(수식이 아니어야 한다) — 수식이 섞여 있으면
    조용히 건너뛰지 않고 여기서 멈춘다(그러지 않으면 계산 기준 회차가 조용히 어긋난다).
    """
    out: list[dict] = []
    for r in range(2, ws_all.max_row + 1):
        rr = ws_all.cell(r, 1).value
        if not isinstance(rr, int):
            continue
        vals = [ws_all.cell(r, c).value for c in range(2, 9)]
        if any(not isinstance(v, int) for v in vals):
            raise RuntimeError(
                f"전체당첨내역 {r}행({rr}회차)의 번호칸에 수식/빈칸이 있습니다: {vals} "
                f"— 값으로 읽을 수 있어야 행 전진 기준을 세울 수 있습니다"
            )
        out.append({"draw_round": rr, "nums": sorted(int(v) for v in vals[:6]),
                    "bonus": int(vals[6])})
    out.sort(key=lambda h: h["draw_round"])
    if not out:
        raise RuntimeError("전체당첨내역에서 회차를 하나도 읽지 못했습니다")
    return out


def _rule_violations(nums, static_rules) -> str:
    """당첨 조합이 1차 고정 규칙에서 벗어난 항목 — 추적표 S열 표기 형식 그대로
    (예: '3(row37)3개/허용0~2; 10단 기본(row28)4개/허용0~3')."""
    parts = []
    for rule in static_rules:
        tgt = set(int(t) for t in rule["targets"])
        c = sum(1 for n in nums if n in tgt)
        if c < rule["min"] or c > rule["max"]:
            nm = f"{rule['name']}" if rule.get("name") else ""
            parts.append(f"{nm}(row{rule['row']}){c}개/허용{rule['min']}~{rule['max']}")
    return "; ".join(parts)


def row_advance_values(wb, label: str) -> dict[int, dict]:
    """행 전진에 쓸 회차별 계산값 — **대상 회차는 파일 상태에서 스스로 찾는다**
    (추적결과 창의 최신 라벨보다 뒤에 추첨된 회차 = 아직 행이 없는 회차).

    회차를 인자로 받지 않는 이유: 밀린 회차가 둘 이상이면 그 사이에 구멍이 남지 않게
    전부 채워야 하기 때문이다(창 최신 1241 · 전체당첨내역 1243이면 1242·1243을 함께 채운다).

    회차 R의 값은 R-1(직전 회차)까지의 이력으로 만든 그 회차의 배포 풀에서 나온다:
      1차 통과 = 고정 378 + AUTO 4            ← 1차추적결과 I열
      2차 통과 = 1차 + 이격수 48               ← 2차추적결과 I열 · 앱 DB stage2_count와 같아야 함
      4차 통과 = 2차 + 상중하·top5             ← 4차필터 I열    · 앱 DB stage4_count와 같아야 함
      K/L/M   = 당첨 6개가 격차순위 상위/중위/하위(각 15개)에 든 개수
      N~R     = 그 단계 통과 풀에서 실제 당첨번호와 1~5등으로 맞은 조합 수
      S       = 당첨 조합이 위반한 1차 고정 규칙 목록
    """
    import combo_filter_v2 as cf

    if label not in ROW_ROUND_FILES:
        raise RuntimeError(f"{label}: 행 전진 대상 파일이 아닙니다")
    draws = _draws_asc_from_sheet(wb["전체당첨내역"])
    by_round = {h["draw_round"]: h for h in draws}

    windows: dict[str, int] = {}
    for sn in ROW_ROUND_SHEETS:
        if sn not in wb.sheetnames:
            raise RuntimeError(f"{label}: 시트 '{sn}'을 찾지 못했습니다(행 전진 대상)")
        have = [wb[sn].cell(r, 1).value for r in range(ROW_FIRST, ROW_LAST + 1)]
        have = [x for x in have if isinstance(x, int)]
        if not have:
            raise RuntimeError(f"{label}/{sn}: 회차 라벨(1열)을 찾지 못했습니다")
        windows[sn] = max(have)
    if len(set(windows.values())) != 1:
        raise RuntimeError(f"{label}: 추적결과 시트 창 최신이 서로 다릅니다 {windows} — 확인 필요")

    newest = list(windows.values())[0]
    targets = [h["draw_round"] for h in draws if h["draw_round"] > newest]
    if not targets:
        log(f"    (행 전진 대상 없음 — 추적결과 창 최신 {newest}회차가 전체당첨내역 최신입니다)")
        return {}
    if targets != list(range(newest + 1, newest + 1 + len(targets))):
        raise RuntimeError(f"{label}: 전진 대상 회차에 구멍이 있습니다 {targets} — 중단")
    if len(targets) > ROW_WINDOW:
        raise RuntimeError(
            f"{label}: 밀린 회차가 {len(targets)}개(창 {ROW_WINDOW}행)입니다 — 한 번에 창을 "
            f"통째로 갈아치우는 상황이라 자동 처리를 중단합니다. 파일 상태를 확인해 주세요."
        )

    # 2026-09-27: 회차 무관 마스크(전체 조합·1차 고정 378·2차 이격수 48)는 **실제로 밀
    # 회차가 있을 때만** 만든다. 예전엔 이 함수 맨 앞에서 만들어서, 이미 최신인 주에도
    # 대상이 없는데 130초를 쓰고 끝났다(실측: 진입점 1회 253초의 절반 이상).
    base = _tracking_base()
    combo_oh = base["combo_oh"]

    out: dict[int, dict] = {}
    for rnd in targets:
        masks = cf.compute_stage_masks(draws, rnd - 1, base)
        m1, m2, m4 = masks["stage1_mask"], masks["stage2_mask"], masks["stage4_mask"]
        order = masks["gap_order"]
        drawn = by_round[rnd]
        nums, bonus = drawn["nums"], drawn["bonus"]
        got = set(nums)
        out[rnd] = {
            "stage1": int(m1.sum()), "stage2": int(m2.sum()), "stage4": int(m4.sum()),
            "K": len(got & set(order[:15])), "L": len(got & set(order[15:30])),
            "M": len(got & set(order[30:45])),
            "tiers1": cf.tier_counts(combo_oh[m1], nums, bonus),
            "tiers2": cf.tier_counts(combo_oh[m2], nums, bonus),
            "tiers4": cf.tier_counts(combo_oh[m4], nums, bonus),
            "S": _rule_violations(nums, base["static_rules"]),
        }
        log(f"    {rnd}회차 계산: 1차={out[rnd]['stage1']:,} 2차={out[rnd]['stage2']:,} "
            f"4차={out[rnd]['stage4']:,} "
            f"상중하={out[rnd]['K']}/{out[rnd]['L']}/{out[rnd]['M']}")
    return out


def advance_row_sheets(wb, label: str, values: dict[int, dict]) -> dict[str, dict]:
    """행식 회차 시트들을 새 회차까지 전진시킨다(이미 앞서 있으면 그대로)."""
    draws = {h["draw_round"]: h for h in _draws_asc_from_sheet(wb["전체당첨내역"])}
    for sn in ROW_ROUND_SHEETS:
        if sn not in wb.sheetnames:
            raise RuntimeError(f"{label}: 시트 '{sn}'을 찾지 못했습니다(행 전진 대상)")

    plans: dict[str, dict] = {}
    for sn in ROW_ROUND_SHEETS:
        ws = wb[sn]
        have = [ws.cell(r, 1).value for r in range(ROW_FIRST, ROW_LAST + 1)]
        have = [x for x in have if isinstance(x, int)]
        if not have:
            raise RuntimeError(f"{label}/{sn}: 회차 라벨(1열)을 찾지 못했습니다")
        # 전체당첨내역에 실제로 들어 있는 회차만 민다(없는 회차를 밀어넣으면 그 행의
        # 당첨번호를 쓸 수 없어 KeyError가 난다 — 값이 뭘 담고 있든 창은 여기서 지킨다).
        targets = sorted(r for r in values if r > max(have) and r in draws)
        plans[sn] = {"ws": ws, "newest": max(have), "targets": targets}

    if not any(p["targets"] for p in plans.values()):
        # 2026-09-27: 밀 회차가 하나도 없으면 회차 무관 마스크를 만들지 않는다 —
        # 진입점이 '이미 최신'인 주에 대상도 없이 수십 초를 태우던 원인(실측 130초).
        return {sn: {"advanced": [], "labels_before": p["newest"], "labels_after": p["newest"]}
                for sn, p in plans.items()}

    base = _tracking_base()
    total_combos = int(base["combos"].shape[0])
    out: dict[str, dict] = {}
    for sn, p in plans.items():
        ws = p["ws"]
        targets = p["targets"]
        have_max = p["newest"]
        for rnd in targets:
            ws.insert_rows(ROW_FIRST, amount=1)
            row = ROW_FIRST
            v = values[rnd]
            ws.cell(row, 1).value = rnd
            for i, n in enumerate(draws[rnd]["nums"][:6]):
                ws.cell(row, 2 + i).value = n
            if sn == "1차추적결과":
                ws.cell(row, 8).value = total_combos
                ws.cell(row, 9).value = v["stage1"]
                tiers = v["tiers1"]
            elif sn == "2차추적결과":
                ws.cell(row, 8).value = v["stage1"]
                ws.cell(row, 9).value = v["stage2"]
                tiers = v["tiers2"]
            else:
                ws.cell(row, 8).value = v["stage2"]
                ws.cell(row, 9).value = v["stage4"]
                tiers = v["tiers4"]
            ws.cell(row, 10).value = f"=SUM(K{row}:M{row})"
            ws.cell(row, 11).value = v["K"]
            ws.cell(row, 12).value = v["L"]
            ws.cell(row, 13).value = v["M"]
            for i, key in enumerate(("t1", "t2", "t3", "t4", "t5")):
                ws.cell(row, 14 + i).value = tiers[key]
            if sn != "4차필터":
                ws.cell(row, 19).value = v["S"]
        for r in range(ROW_FIRST, ROW_LAST + 1):        # J는 자기 행 번호를 쓴다
            if isinstance(ws.cell(r, 1).value, int):
                ws.cell(r, 10).value = f"=SUM(K{r}:M{r})"
        ws.delete_rows(ROW_LAST + 1, amount=len(targets))   # 창 크기 유지
        out[sn] = {"advanced": targets, "labels_before": have_max,
                   "labels_after": have_max + len(targets)}
    return out


def _daejo_app_record(rnd: int) -> dict | None:
    """앱 자동화 기록(DB draw_generation_stats) — 읽기 전용. 없으면 None."""
    import marketing_db

    return marketing_db.get_draw_generation_stats(rnd)


def daejo_verdict(rnd: int, file_val, app_val) -> str:
    """파일 계산값 vs 앱 DB 기록 판정.

    · 같으면 "일치"
    · 앱 기록이 없으면 "앱_미기록"(그 회차 풀이 자동 생성되지 않았다는 뜻)
    · 다르면 — RULE_VINTAGE_ROUND 미만은 "이력(규칙 불일치)"(그 회차 배포 당시의 규칙이
      지금과 달라 생기는 정상적인 차이. 실패 아님),
      RULE_VINTAGE_ROUND 이상은 "불일치"(기대값과 다름 → 실패로 본다).
    """
    if app_val is None:
        return "앱_미기록"
    if int(file_val) == int(app_val):
        return "일치"
    return "이력(규칙 불일치)" if rnd < RULE_VINTAGE_ROUND else "불일치"


def write_daejo_sheet(wb, label: str, values: dict[int, dict]) -> list[str]:
    """대조 시트를 갱신하고 '실패로 볼 문제' 목록을 돌려준다(비어 있으면 정상).

    같은 회차가 이미 있으면 그 행을 갱신한다(재실행 멱등). 행 수는 추적표와 같은
    102행(ROW_WINDOW)으로 묶어 최신이 위로 오게 유지한다.
    """
    ws = wb[DAEJO_SHEET] if DAEJO_SHEET in wb.sheetnames else wb.create_sheet(DAEJO_SHEET)
    for i, h in enumerate(DAEJO_HEADERS, start=1):
        ws.cell(1, i).value = h
    known: dict[int, list] = {}
    for r in range(2, ws.max_row + 1):
        rnd = ws.cell(r, 1).value
        if isinstance(rnd, int):
            known[rnd] = [ws.cell(r, c).value for c in range(1, len(DAEJO_HEADERS) + 1)]

    problems: list[str] = []
    for rnd in sorted(values):
        v = values[rnd]
        app = _daejo_app_record(rnd)
        a2 = app["stage2_count"] if app else None
        a4 = app["stage4_count"] if app else None
        verdict2, verdict4 = daejo_verdict(rnd, v["stage2"], a2), daejo_verdict(rnd, v["stage4"], a4)
        if app is None:
            top5 = "미기록"
        elif app.get("top5_numbers"):
            top5 = " ".join(str(x) for x in app["top5_numbers"])
        else:
            top5 = "(top3까지만 기록)"
        known[rnd] = [rnd, v["stage1"], v["stage2"], v["stage4"],
                      a2 if app else "미기록", a4 if app else "미기록", top5,
                      verdict2, verdict4,
                      DAEJO_VINTAGE_NOTE if rnd < RULE_VINTAGE_ROUND else ""]
        for what, verdict, fv, av in (("2차", verdict2, v["stage2"], a2),
                                      ("4차", verdict4, v["stage4"], a4)):
            if verdict == "불일치":
                problems.append(f"{label} {rnd}회차 {what} 불일치: 파일={fv:,} 앱={av:,}")
        if app is None:
            problems.append(f"{label} {rnd}회차: 앱 자동화 기록(draw_generation_stats)이 없습니다")

    ordered = sorted(known, reverse=True)[:ROW_WINDOW]
    for r in range(2, max(ws.max_row, len(ordered) + 1) + 1):
        for c in range(1, len(DAEJO_HEADERS) + 1):
            ws.cell(r, c).value = None
    for i, rnd in enumerate(ordered):
        for c, val in enumerate(known[rnd], start=1):
            ws.cell(2 + i, c).value = val
    log(f"    {DAEJO_SHEET}: {len(ordered)}행 기록(최신 {ordered[0] if ordered else '-'}회차, "
        f"기대일치 = {RULE_VINTAGE_ROUND}회차부터)")
    return problems


def _advance_rows_in_wb(wb, label: str) -> tuple[dict[str, dict], list[str]]:
    """(이미 열린 워크북에 대해) 행 전진 + 대조 시트 갱신.
    반환: (시트별 전진 결과, 대조가 찾은 문제). 이미 최신이면 ({}, []) — 아무것도 건드리지 않는다.

    신규 회차가 있는 경로(process_one_round_for_file)와 없는 경로(main의 '이미 최신'
    분기)가 같은 함수를 쓴다 — 회차가 하나도 안 들어오는 주에 창이 밀린 채 방치되면
    다음 주에 회차가 들어올 때까지 파일이 어긋난 채로 남기 때문이다."""
    values = row_advance_values(wb, label)
    if not values:
        return {}, []
    stats = advance_row_sheets(wb, label, values)
    for sn, st in stats.items():
        log(f"    {sn}: 회차 행 전진 {st['advanced']} "
            f"({st['labels_before']}→{st['labels_after']})")
    problems = write_daejo_sheet(wb, label, values)
    for p in problems:
        log(f"    [대조] {p}")
    return stats, problems


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


def process_one_round_for_file(path: Path, label: str, rec: dict) -> list[str]:
    """파일 하나에 회차 하나(rec)를 반영.
    3차필터 구조 파일이면 예측행도, 컬럼식 파일이면 회차 컬럼도, 행식 추적결과 시트가
    있으면 그 행들도 같이 전진한다.

    반환: 대조 시트가 찾아낸 '실패로 볼 문제' 목록(비어 있으면 정상)."""
    needs_3cha = label in ADVANCE_3CHA_FILES
    needs_columns = label in COLUMN_ROUND_FILES
    needs_rows = label in ROW_ROUND_FILES

    if needs_3cha:
        wb_peek = openpyxl.load_workbook(path, data_only=False, read_only=True)
        sheet_names = [sn for sn in wb_peek.sheetnames if sn.startswith("3차필터")]
        wb_peek.close()
        log(f"  [{label}] {rec['round']}회차 처리 전 재계산으로 예측행(L:BD) 확보 중...")
        try:
            forecasts = recalc_and_read_pending_row(path, sheet_names)
        except Exception as e:  # noqa: BLE001
            log(f"  [경고] Excel 재계산 실패 → 파이썬 계산으로 대체합니다: {e}")
            forecasts = _python_pending_forecast(path, sheet_names)

    wb = openpyxl.load_workbook(path, data_only=False)
    ws_all = wb["전체당첨내역"]

    if needs_3cha:
        for sn in sheet_names:
            hit_top, hit_mid, hit_low = advance_3cha_sheet(wb[sn], sn, forecasts[sn], rec)
            log(f"    {sn}: {rec['round']}회차 확정 (상위{hit_top}/중위{hit_mid}/하위{hit_low}), "
                f"다음 예측대상 -> {rec['round']+1}")
    elif needs_columns:
        log(f"  [{label}] {rec['round']}회차: 3차필터 구조가 아니므로 전체당첨내역 갱신 + "
            f"회차 컬럼 전진(밀기)을 수행")
    else:
        log(f"  [{label}] {rec['round']}회차: 3차필터 구조가 아니므로 전체당첨내역만 갱신")

    append_draw_result(ws_all, rec)

    row_problems: list[str] = []
    if needs_rows:
        # 행 전진과 대조 시트는 전체당첨내역에 이 회차가 들어간 '뒤', 저장 '전'에 같은
        # 워크북에서 처리한다(로드/저장이 한 번에 끝난다). 여기서 예외가 나면 아직 저장
        # 전이므로 이 회차는 파일에 아무것도 반영되지 않는다 — 다시 시도하면 된다.
        _, row_problems = _advance_rows_in_wb(wb, label)

    wb.save(path)

    if needs_columns:
        # 순서 주의: 컬럼 전진은 전체당첨내역에 이 회차가 들어간 '뒤'에 해야 한다 —
        # 새 열의 헬퍼행이 MATCH(N$4)/(N$4-1)로 그 회차 번호를 찾기 때문이다.
        col_stats = advance_round_columns(path, label)
        for sn, st in col_stats.items():
            log(f"    {sn}: 회차 컬럼 {st['shifts']}칸 전진 "
                f"({st['labels_before']}→{st['labels_after']})")
        if not any(st["shifts"] for st in col_stats.values()):
            log("    (회차 컬럼은 이미 최신 — 전진 없음)")

    log(f"  [{label}] 저장 완료. 재계산 + 캐시값 굽기 중...")
    try:
        recalc_and_save(path)
    except Exception as e:  # noqa: BLE001
        # 구조 편집(위 wb.save)은 이미 끝났다 — 여기서 죽는 건 "캐시값 굽기"뿐이라
        # 그 회차를 통째로 중단시킬 이유가 없다(엑셀로 열면 자동 재계산된다).
        log(f"  [경고] 엑셀 재계산(캐시값 굽기)을 건너뜁니다: {e}")
        log("         파일 내용은 정상입니다 — 엑셀로 열면 자동 재계산됩니다.")
    return row_problems


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

        # 2026-09-27: 조회 실패와 "정말 최신"을 구분한다. 예전엔 조회가 실패하면
        # find_new_rounds가 빈 리스트를 돌려주고 아래 "이미 최신"으로 빠져 exit 0이
        # 됐다 — 스케줄러 재시도가 전부 성공으로 남아 아무도 모르게 밀렸다.
        try:
            new_rounds = find_new_rounds(local_max)
        except Exception as e:
            log(f"[오류] {label}: 회차 조회 실패 -> {e}")
            log("       조회 실패는 '최신'이 아닙니다 — 이번 실행을 실패로 끝냅니다(스케줄러가 재시도).")
            any_error = True
            continue
        if not new_rounds:
            # 2026-09-27 신규: 신규 회차가 없어도 오류값 스캔은 한다. 이 경로로 들어오는
            # 파일이 바로 컬럼식 구조인 샘플·200회검증용이다(3차필터 전진 대상이 아니라
            # 예전엔 여기서 continue해 오류값 점검이 한 번도 돌지 않았다 — 그래서 두 파일만
            # 서식오류가 생겨도 아무도 모르게 남았다). scan_errors는 읽기 전용이다.
            try:
                errs_now = scan_errors(path)
                if errs_now:
                    log(f"[경고] {label}: 오류값 {len(errs_now)}개 발견 -> {errs_now[:5]}")
                    any_error = True
                else:
                    log(f"[{label}] 오류값 없음 확인(신규 회차 없음).")
            except Exception as e:  # noqa: BLE001
                log(f"[경고] {label}: 오류값 스캔 실패 -> {e}")
                any_error = True
            if label in ROW_ROUND_FILES:
                # 2026-09-27: 신규 회차가 없어도 추적결과 창이 뒤처져 있으면 채운다. 이 경로로
                # 들어오는 파일(샘플)은 3차필터 전진 대상이 아니라 예전엔 여기서 "이미 최신"으로
                # 끝나, 창이 밀린 채로 남았다(실측: 창 최신 1241 · 전체당첨내역 1243).
                try:
                    wb_rows = openpyxl.load_workbook(path, data_only=False)
                    try:
                        stats, problems = _advance_rows_in_wb(wb_rows, label)
                        if stats:
                            wb_rows.save(path)
                            for sn, st in stats.items():
                                log(f"[{label}] {sn}: 추적결과 창을 {st['labels_after']}회차까지 "
                                    f"채움(전진 {st['advanced']})")
                            try:
                                recalc_and_save(path)
                            except Exception as e:  # noqa: BLE001
                                log(f"  [경고] 엑셀 재계산(캐시값 굽기)을 건너뜁니다: {e}")
                    finally:
                        wb_rows.close()
                    for p in problems:
                        log(f"[경고] {p}")
                        any_error = True
                except Exception as e:  # noqa: BLE001
                    log(f"[오류] {label}: 추적결과 행 전진 실패 -> {e}")
                    any_error = True
            log(f"[{label}] 이미 최신 상태입니다 (전체당첨내역 최신회차={local_max}). 건너뜀.")
            continue

        log(f"[{label}] 현재 {local_max}회차까지 반영됨 -> "
            f"{[r['round'] for r in new_rounds]}회차 새로 반영 시작")

        for rec in new_rounds:
            try:
                for p in (process_one_round_for_file(path, label, rec) or []):
                    log(f"[경고] {p}")
                    any_error = True
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


# ============================== 실행 전 자기 갱신 (2026-10-05) =====================
# 왜: 이 스크립트는 PC에 있는 코드로 돈다. 클라우드 세션이 GitHub에 고친 내용(예: 새
# 추적표 파일 등록)은 누가 PC에서 git pull을 해줘야만 반영됐다 — 잊으면 일요일 업데이트가
# 옛 코드로 돈다. 그래서 예약 작업이 이 파일을 직접 실행할 때만(테스트가 main()을 부를 때는
# 아님) 시작하자마자 GitHub 최신 코드를 받아오고, 바뀌었으면 새 코드로 한 번 다시 실행한다.
#   · --ff-only: PC에 충돌하는 수정이 있으면 git이 아무것도 바꾸지 않고 실패한다 → 기록만
#     남기고 지금 코드 그대로 업데이트를 계속한다(자기 갱신 실패가 주간 업데이트를 막지 않음).
#   · 서버 재시작은 하지 않는다(위험). 끄려면 환경변수 LOTTO_SKIP_SELF_UPDATE=1.

_SELF_UPDATED_ENV = "LOTTO_SELF_UPDATED"


def _git(args: list[str], repo: Path, timeout: int = 180):
    import os
    import subprocess

    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")  # 비밀번호 입력창이 떠서 멈추는 것 방지
    return subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True,
                          timeout=timeout, env=env)


def self_update_from_github(repo: Path = LOTTO_APP_DIR) -> bool:
    """GitHub main을 fast-forward로만 받아온다. 코드가 실제로 바뀌었으면 True."""
    import os

    if os.environ.get("LOTTO_SKIP_SELF_UPDATE") == "1" or os.environ.get(_SELF_UPDATED_ENV) == "1":
        return False
    if not (repo / ".git").exists():
        return False
    try:
        before = _git(["rev-parse", "HEAD"], repo).stdout.strip()
        r = _git(["pull", "--ff-only", "origin", "main"], repo)
        after = _git(["rev-parse", "HEAD"], repo).stdout.strip()
    except Exception as e:  # noqa: BLE001 — git 없음·시간초과 등: 기록만 하고 계속
        log(f"[자기갱신] git pull 실행 실패 → 지금 코드로 계속합니다: {e}")
        return False
    if r.returncode != 0:
        msg = (r.stderr or r.stdout or "").strip().replace("\n", " | ")[:400]
        log(f"[자기갱신] git pull 실패(코드 {r.returncode}) → 지금 코드로 계속합니다: {msg}")
        return False
    if before and after and before != after:
        log(f"[자기갱신] 최신 코드 받음 {before[:7]} → {after[:7]} — 새 코드로 다시 실행합니다")
        return True
    log(f"[자기갱신] 이미 최신({after[:7]})")
    return False


if __name__ == "__main__":
    import os as _os

    if self_update_from_github():
        import subprocess as _sp

        _env = dict(_os.environ, **{_SELF_UPDATED_ENV: "1"})
        _os._exit(_sp.call([sys.executable, _os.path.abspath(__file__), *sys.argv[1:]], env=_env))

    # 2026-09-27: 회차 조회를 DB(draw_results)로 바꾸면서 db_turso의 non-daemon 스레드가
    # 프로세스 종료를 붙잡게 됐다 — 마지막 줄을 다 찍고도 프로세스가 안 끝나서(실측)
    # 스케줄러가 종료코드를 못 받고, 뒤이어 돌릴 작업이 시작조차 못 한다.
    # hourly_draw_sync.py가 같은 이유로 os._exit()를 쓰고 있으니 그 방식을 따른다.
    _os._exit(main())
