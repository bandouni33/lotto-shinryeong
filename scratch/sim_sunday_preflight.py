# -*- coding: utf-8 -*-
"""로또신령 — "일요일 14:00 다음회차 배포용 조합생성" 절차 사전점검 시뮬레이터.

전부 읽기 전용을 목표로 한다: DB 데이터 변경 없음, 파일 쓰기 없음,
워커(combo_gen_worker) 프로세스 실행 없음.

실제 트리거 함수(combo_gen_trigger.maybe_trigger_weekly_generation)는
  1) app_settings.set_setting()            → 시각 기록(쓰기)
  2) draw_results_db.sync_latest_from_dhlottery() → DB 쓰기
  3) subprocess.Popen()                    → 워커 실행
을 하므로 그대로 부르면 안 된다. 그래서 **그 세 가지만 스텁으로 바꾸고
트리거 함수 자체는 진짜 코드를 그대로 호출**한다 — 게이트 조건(요일/시각/
쿨다운/중복생성 판정)을 여기서 복제하지 않으므로 시뮬레이션과 실동작이
어긋날 수 없다. 시각은 combo_gen_trigger._now_kst 를 바꿔 주입한다.

실행 (프로젝트 루트에서):
    venv312\\Scripts\\python.exe scratch\\sim_sunday_preflight.py
    venv312\\Scripts\\python.exe scratch\\sim_sunday_preflight.py 2026-09-27T14:00
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

KST = timezone(timedelta(hours=9))


def _sim_now() -> datetime:
    if len(sys.argv) > 1:
        return datetime.fromisoformat(sys.argv[1]).replace(tzinfo=KST)
    return datetime.now(KST)


SIM_NOW = _sim_now()

FINDINGS: list[tuple[str, str, str]] = []


def finding(level: str, where: str, msg: str) -> None:
    FINDINGS.append((level, where, msg))
    print(f"    {level:4} | {where} | {msg}")


def section(title: str) -> None:
    print()
    print("=" * 78)
    print(f"■ {title}")
    print("=" * 78)


def _load_env():
    import env_loader

    env_loader.load_dotenv_file()


# ─────────────────────────────────────────────────────────────
# 1) 지금 시각 / 트리거 게이트 조건
# ─────────────────────────────────────────────────────────────
def check_time_gate() -> None:
    section("1) 기준 시각과 트리거 시간 게이트 (일요일 14:00~14:59)")
    print(f"    현재 실제 시각 : {datetime.now(KST):%Y-%m-%d %H:%M:%S} KST (weekday={datetime.now(KST).weekday()})")
    print(f"    시뮬레이션 시각: {SIM_NOW:%Y-%m-%d %H:%M:%S} KST (weekday={SIM_NOW.weekday()})")
    import combo_gen_trigger as t

    gate_label = {0: "월", 1: "화", 2: "수", 3: "목", 4: "금", 5: "토", 6: "일"}
    ok = SIM_NOW.weekday() == 6 and SIM_NOW.hour == 14
    print(f"    시간 게이트(일 14시대): {'통과' if ok else '미통과'} "
          f"(weekday={gate_label[SIM_NOW.weekday()]}, hour={SIM_NOW.hour})")
    print(f"    쿨다운 상수: {t._CHECK_COOLDOWN}")
    if not ok:
        finding("WARN", "시간게이트", "시뮬레이션 시각이 일요일 14시대가 아니라 트리거가 즉시 return한다"
                                    " — 14시로 맞춰 다시 돌릴 것(예: ... sim_sunday_preflight.py 2026-09-27T14:00)")


# ─────────────────────────────────────────────────────────────
# 2) DB 현황 (draw_results / lotto_combinations / app_settings)
# ─────────────────────────────────────────────────────────────
def check_db_state() -> dict:
    section("2) DB 현황 — 당첨번호 / 배포용 조합 풀 / 트리거 기록")
    import app_settings
    import draw_results_db
    import marketing_db

    state: dict = {}
    try:
        latest = draw_results_db.get_latest_draw_round()
        count = draw_results_db.get_draw_results_count()
        state["latest_round"] = latest
        print(f"    draw_results 최신 회차: {latest} / 총 {count}건")
        hist = draw_results_db.get_all_draw_results()
        for h in hist[:4]:
            print(f"      - {h['draw_round']}회차 {h['numbers']} +{h['bonus']}")
    except Exception as e:
        finding("FAIL", "draw_results", f"최신 회차 조회 실패: {type(e).__name__}: {e}")
        return state

    target = (latest or 0) + 1
    state["target_round"] = target
    print(f"    → 이번에 생성해야 할 target_round = {target}")

    print("    lotto_combinations(배포용 풀) 회차별 등록 수:")
    for r in range(target - 2, target + 2):
        try:
            n = marketing_db.get_combination_count_by_draw(r)
        except Exception as e:
            print(f"      {r}회차: 조회 실패({e})")
            continue
        mark = ""
        if r == target:
            mark = "  <-- 오늘 만들 대상"
        elif r == latest:
            mark = "  (지난주 만든 것: 오늘 판매에 쓰임)"
        print(f"      {r}회차: {n:,}개{mark}")
        state.setdefault("pool", {})[r] = n

    if state.get("pool", {}).get(target, 0) > 0:
        finding("WARN", "중복생성", f"{target}회차 풀이 이미 {state['pool'][target]:,}개 있다"
                                    " — 14시 트리거는 '이미 있음'으로 판단해 워커를 띄우지 않는다(정상 동작)")
    elif state.get("pool", {}).get(latest, 0) == 0:
        finding("FAIL", "풀없음", f"{latest}회차(오늘 판매에 쓰여야 하는 풀) 조합이 0개다")

    print("    app_settings(트리거/필터 기록):")
    for key in (
        "combo_gen_last_check_at",
        "combo_gen_last_round",
        "combo_gen_last_count",
        "latest_filter_pattern_count",
    ):
        try:
            print(f"      {key} = {app_settings.get_setting(key, '(없음)')!r}")
        except Exception as e:
            print(f"      {key} = 조회 실패({e})")

    for name in ("combo_gen_job.status", "filter_job.status"):
        p = ROOT / name
        if p.exists():
            print(f"    {name} (mtime={datetime.fromtimestamp(p.stat().st_mtime):%Y-%m-%d %H:%M}): {p.read_text(encoding='utf-8')[:200]}")
        else:
            print(f"    {name}: 파일 없음")
    return state


# ─────────────────────────────────────────────────────────────
# 3) 14시 트리거 시뮬레이션 (진짜 함수 호출, 부작용만 스텁)
# ─────────────────────────────────────────────────────────────
def check_trigger_simulation() -> None:
    section("3) 14시 트리거 시뮬레이션 — combo_gen_trigger 실제 함수 실행")
    import app_settings
    import combo_gen_trigger as t
    import draw_results_db

    launched: list = []
    orig_now = t._now_kst
    orig_set = app_settings.set_setting
    orig_sync = draw_results_db.sync_latest_from_dhlottery
    orig_popen = subprocess.Popen

    class _Recorder:
        def __init__(self, args, **kw):
            launched.append((args, kw))

    t._now_kst = lambda: SIM_NOW
    app_settings.set_setting = lambda *a, **k: None
    draw_results_db.sync_latest_from_dhlottery = lambda: None  # "새 회차 없음" 상황 재현
    subprocess.Popen = _Recorder
    try:
        t.maybe_trigger_weekly_generation()
    finally:
        t._now_kst = orig_now
        app_settings.set_setting = orig_set
        draw_results_db.sync_latest_from_dhlottery = orig_sync
        subprocess.Popen = orig_popen

    if launched:
        print(f"    결과: 워커 실행 O → {launched[0][0]}")
        finding("INFO", "트리거", "게이트 통과, 워커를 띄운다(위 명령)")
    else:
        print("    결과: 워커 실행 X (게이트/쿨다운/중복생성 중 하나에서 조기 return)")
    print("    주의: sync_latest_from_dhlottery()는 '새 회차 못 찾음(None)'으로 스텁했다 —"
          " 실제로는 여기서 토요일 당첨번호를 API로 다시 확인한다.")
    print("          그 결과 최신 회차가 1 늘면 target_round도 1 늘어난다(2)의 target과 달라질 수 있음).")


# ─────────────────────────────────────────────────────────────
# 4) 엑셀 5개 파일 최신 상태
# ─────────────────────────────────────────────────────────────
def check_excel(expected_round: int | None) -> None:
    section("4) 엑셀 후보숫자 추적표 5개 파일 — 다음회차 반영 여부")
    try:
        import openpyxl
    except Exception as e:
        finding("FAIL", "openpyxl", f"openpyxl import 실패: {e}")
        return

    tracker = ROOT / "★조합생성_후보숫자_추적표"
    files = {
        "샘플": tracker / "조합생성_후보숫자_추적표_샘플.xlsx",
        "200회검증용": tracker / "조합생성_후보숫자_추적표_샘플_200회검증용.xlsx",
        "전체표본": tracker / "조합생성_후보숫자_추적표_전체표본_윈도우비교.xlsx",
        "최근500표본": tracker / "조합생성_후보숫자_추적표_최근500표본_윈도우비교.xlsx",
        "표본vs최근50회": tracker / "★후보숫자_추적표_표본vs최근50회.xlsx",
    }
    for label, path in files.items():
        if not path.exists():
            finding("FAIL", f"엑셀/{label}", f"파일 없음 → {path}")
            continue
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        try:
            wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        except Exception as e:
            finding("FAIL", f"엑셀/{label}", f"열기 실패: {e}")
            continue
        try:
            ws = wb["전체당첨내역"]
            last = ws.cell(ws.max_row, 1).value
            last_round = int(last) if last is not None else None
            verdict = ""
            if expected_round is not None and last_round is not None:
                if last_round == expected_round:
                    verdict = "OK(최신)"
                else:
                    verdict = f"!! {expected_round - last_round}회차 밀림"
                    finding("FAIL", f"엑셀/{label}",
                            f"전체당첨내역 최신회차={last_round}, 기대={expected_round} ({expected_round - last_round}회차 미반영)")
            print(f"    {label:12} 최신회차={last_round}  (파일 수정 {mtime:%Y-%m-%d %H:%M})  {verdict}")

            sheets3 = [sn for sn in wb.sheetnames if sn.startswith("3차필터")]
            if sheets3:
                ws3 = wb[sheets3[0]]
                a7 = ws3.cell(7, 1).value
                vals = [ws3.cell(7, c).value for c in range(12, 57)]
                distinct = len({v for v in vals if v is not None})
                print(f"                 {sheets3[0]}!A7(다음 예측대상)={a7}, L7:BD7 캐시값 {distinct}/45개"
                      f"{'  <-- 재계산 필요(캐시 없음)' if distinct < 45 else ''}")
                if distinct < 45:
                    finding("WARN", f"엑셀/{label}", f"{sheets3[0]}!L7:BD7 캐시값이 {distinct}/45 — 엑셀 재계산(win32com)이 안 돈 흔적")
            if label == "표본vs최근50회":
                anchor = wb["_calc_라운드기준"].cell(2, 1).value
                print(f"                 _calc_라운드기준!A2(자동 다음 예측회차)={anchor}")
        finally:
            wb.close()

    for logname in ("weekly_update_log.txt", tracker / "candidate_tracker_update_log.txt"):
        p = Path(logname)
        if not p.exists():
            finding("WARN", "엑셀로그", f"{p.name} 없음 — 해당 스크립트가 이 PC에서 한 번도 로그를 남기지 않았다")
            continue
        lines = p.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        print(f"    {p.name}: {len(lines)}줄, 마지막 기록 {lines[-1][:160] if lines else '(빈 파일)'}")


# ─────────────────────────────────────────────────────────────
# 5) 필터 규칙 준비 상태 (DB 우선 + 로컬 폴백)
# ─────────────────────────────────────────────────────────────
def check_filter_rules() -> None:
    section("5) 배포용 4차 필터 규칙 준비 (1차 378고정+3AUTO / 2차 48 이격수)")
    try:
        import app_settings
        import combo_filter_v2 as cf
    except Exception as e:
        finding("FAIL", "필터규칙", f"모듈 import 실패: {e}")
        return

    try:
        db1 = bool(app_settings.get_filter_rules_json(1))
        db2 = bool(app_settings.get_filter_rules_json(2))
    except Exception as e:
        finding("FAIL", "필터규칙", f"DB 규칙 조회 실패: {e}")
        db1 = db2 = False
    print(f"    DB 저장 여부: 1차={db1}, 2차={db2}")
    if not (db1 and db2):
        finding("WARN", "필터규칙", "DB에 규칙이 없다 → combo_filter_v2가 로컬 JSON 파일로 폴백한다"
                                    "(동작은 하지만 저장소에서 파일을 지우면 그때 죽는다)")

    try:
        static_rules, auto_rules, stage2 = cf._load_rules()
        print(f"    실제 로드: 1차 고정 {len(static_rules)}개 + AUTO {len(auto_rules)}개, 2차 {len(stage2)}개")
    except Exception as e:
        finding("FAIL", "필터규칙", f"_load_rules() 실패: {type(e).__name__}: {e}")
        return

    try:
        with open(cf._STAGE1_FILE, encoding="utf-8") as f:
            f1 = json.load(f)
        with open(cf._STAGE2_FILE, encoding="utf-8") as f:
            f2 = json.load(f)
        file_result = ([r for r in f1 if not r["is_auto"]], [r for r in f1 if r["is_auto"]], f2)
        same = file_result == (static_rules, auto_rules, stage2)
        print(f"    로컬 JSON 파일과 완전 일치: {same}")
        if not same:
            finding("FAIL", "필터규칙", "DB 규칙과 로컬 파일 규칙이 다르다 — 어느 쪽이 진짜인지 확인 필요")
    except Exception as e:
        finding("WARN", "필터규칙", f"로컬 파일 비교 실패(파일이 없거나 형식 오류): {e}")

    auto_names = sorted(r["name"] for r in auto_rules)
    print(f"    AUTO 규칙: {auto_names}")
    # 2026-09-27(사용자 결정): 파일(행 484)의 '후보패턴 이웃수(200회)'를 앱에도 추가했으므로
    # 기대 집합이 4개가 됐다.
    expected_auto = sorted(["전 출현번호", "이웃수", "후보패턴 이웃수", "후보패턴 이웃수(200회)"])
    if auto_names != expected_auto:
        finding("WARN", "필터규칙",
                f"AUTO 규칙 4개(전 출현번호/이웃수/후보패턴 이웃수/후보패턴 이웃수(200회)) "
                f"구성이 다르다: {auto_names}")

    for name in ("combo_filter_rules_stage1.json", "combo_filter_rules_stage2.json"):
        p = ROOT / name
        if p.exists():
            print(f"    {name}: {p.stat().st_size:,}B (수정 {datetime.fromtimestamp(p.stat().st_mtime):%Y-%m-%d %H:%M})")

    stage1_file = ROOT / "saved_filters.pkl"
    if stage1_file.exists():
        print(f"    3종필터 원본(saved_filters.pkl): {stage1_file.stat().st_size:,}B "
              f"(수정 {datetime.fromtimestamp(stage1_file.stat().st_mtime):%Y-%m-%d %H:%M})")
    xlsx = ROOT / "3종필터.xlsx"
    if xlsx.exists():
        print(f"    3종필터.xlsx: 수정 {datetime.fromtimestamp(xlsx.stat().st_mtime):%Y-%m-%d %H:%M}")


# ─────────────────────────────────────────────────────────────
# 6) 판매(배포) 시간대
# ─────────────────────────────────────────────────────────────
def check_sales_window() -> None:
    section("6) 판매(배포) 가능 시간대 — 화 09:00 ~ 토 19:55")
    import sales_window

    print(f"    지금({datetime.now(KST):%a %H:%M}): {'열림' if sales_window.is_sales_window_open() else '닫힘'}")
    for label, dt in (
        ("오늘 14:00(생성 시점)", SIM_NOW.replace(hour=14, minute=0)),
        ("화 09:00(배포 시작)", SIM_NOW.replace(hour=9, minute=0) + timedelta(days=(1 - SIM_NOW.weekday()) % 7)),
        ("토 19:55(배포 끝)", SIM_NOW.replace(hour=19, minute=55) + timedelta(days=(5 - SIM_NOW.weekday()) % 7)),
    ):
        print(f"    {label}: {'열림' if sales_window.is_sales_window_open(dt) else '닫힘'}  ({dt:%Y-%m-%d %a %H:%M})")


# ─────────────────────────────────────────────────────────────
# 7) 동행복권 API 접근성 (엑셀/DB 자동 업데이트의 단일 데이터 소스)
# ─────────────────────────────────────────────────────────────
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


def _fetch_round(round_no: int, ua: str | None) -> str:
    url = (
        "https://www.dhlottery.co.kr/common.do?method=getLottoNumber&drwNo=%d" % round_no
    )
    headers = {"User-Agent": ua} if ua else {}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"요청 실패: {type(e).__name__}: {e}"
    try:
        data = json.loads(raw)
    except Exception:
        return f"JSON 아님(앞 60자): {raw[:60]!r}"
    if data.get("returnValue") != "success":
        return f"returnValue={data.get('returnValue')} (아직 추첨 전이면 정상)"
    nums = sorted(int(data[f"drwtNo{i}"]) for i in range(1, 7))
    return f"success {nums} +{data['bnusNo']}"


def check_dhlottery_api(rounds: list[int]) -> None:
    section("7) 동행복권 공식 API 접근성 (엑셀·DB 자동 업데이트 공통 소스)")
    for r in rounds:
        no_ua = _fetch_round(r, None)
        with_ua = _fetch_round(r, _BROWSER_UA)
        print(f"    {r}회차  기본UA(Python-urllib): {no_ua}")
        print(f"    {r}회차  브라우저UA            : {with_ua}")
        if no_ua.startswith("JSON 아님") and with_ua.startswith("success"):
            finding("FAIL", "동행복권API",
                    f"{r}회차는 브라우저UA로만 받아진다 — 기본 User-Agent로 요청하는 "
                    "weekly_lotto_file_update.py는 이 회차를 영영 못 가져온다")
        elif no_ua.startswith("JSON 아님") and with_ua.startswith("JSON 아님"):
            finding("WARN", "동행복권API", f"{r}회차는 두 방식 다 JSON이 아니다(차단/점검 가능성)")


# ─────────────────────────────────────────────────────────────
def main() -> int:
    _load_env()
    print(f"로또신령 일요일 14시 배포준비 시뮬레이션 — 기준시각 {SIM_NOW:%Y-%m-%d %H:%M} KST")
    check_time_gate()
    state = check_db_state()
    check_trigger_simulation()
    expected = state.get("latest_round")
    check_excel(expected)
    check_filter_rules()
    check_sales_window()
    rounds = [r for r in (state.get("latest_round"), state.get("latest_round", 0) + 1) if r]
    check_dhlottery_api(rounds)

    section("요약 — 발견된 문제")
    if not FINDINGS:
        print("    문제 없음")
    for level, where, msg in FINDINGS:
        print(f"    {level:4} | {where} | {msg}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
