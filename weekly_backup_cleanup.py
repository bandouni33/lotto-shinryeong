# -*- coding: utf-8 -*-
"""주간 백업 폴더 **조건부** 정리 — 두 자동화 체인이 모두 정상 완료된 주에만 삭제한다.

왜 조건부인가 (2026-09-27 사용자 지시):
  ★조합생성_후보숫자_추적표/_backup_20260927(엑셀 5개 원본)와 _backup_20260927_formulas
  (수식 수리 직전 2개)는 3차필터 정합화·엑셀 업데이트 수정 전 상태의 **롤백 수단**이다.
  "다음 실행 때 삭제"처럼 무조건 지우면 그 실행이 실패한 주에도 롤백 수단이 함께 사라진다.
  그래서 아래 게이트를 **모두** 통과할 때만 지우고, 하나라도 실패하면 백업을 그대로 두고
  그 사실을 백업 폴더 안에 보류 메모(_SKIPPED_*.md)로 남긴다 — 사람이 원인을 확인할 때까지
  자동 삭제가 재개되지 않는다(메모를 지워야 재개).

게이트(모두 통과해야 삭제):
  G1 오늘이 일요일(KST)
  G2 엑셀 자동업데이트 두 작업의 '마지막 실행'이 오늘이고 결과코드 0
  G3 GitHub Actions 주간 조합생성(weekly_combo_gen.yml)의 최근 실행이 '오늘(KST)' success
  G4 백업 폴더 안에 보류 메모(_SKIPPED_*)가 없다
  G5 대상 회차 조합 풀이 실제로 생성됐다 — 개수 ≥ 1 **그리고** 그 회차 생성기록이 최근
     FRESH_HOURS 이내 (2026-09-27 사용자 승인, P2·P3). Actions가 success여도 워커가
     "이미 있음"으로 스킵하고 exit 0 했을 수 있어(combo_gen_worker.py) 성공만으로는 부족하다.

안전장치:
  · 기본은 미리보기 — 실제 삭제는 --apply 를 붙였을 때만.
  · 미리보기는 **상태를 바꾸지 않는다**: 삭제도, 보류 메모 작성도 하지 않는다(게이트 결과만 보고한다).
    (미리보기가 메모를 남기면 그 메모가 G4에 걸려 다음 주 자동 삭제를 막아버린다.)
  · 삭제 대상은 아래 BACKUP_DIRS 두 경로로 고정(부모가 추적표 폴더이고 이름이 _backup_* 인지 확인).
  · 삭제 **직전에** 언제·뭘로 검증했는지 로그 한 줄을 남긴다(backup_cleanup_log.txt).

실행(스케줄러는 --apply 로 등록):
    venv312\\Scripts\\python.exe weekly_backup_cleanup.py            # 미리보기
    venv312\\Scripts\\python.exe weekly_backup_cleanup.py --apply    # 실제 삭제(게이트 통과 시)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))

TRACKER_DIR = ROOT / "★조합생성_후보숫자_추적표"
BACKUP_DIRS = (
    TRACKER_DIR / "_backup_20260927",
    TRACKER_DIR / "_backup_20260927_formulas",
)
LOG_FILE = ROOT / "backup_cleanup_log.txt"
SKIP_MARKER_PREFIX = "_SKIPPED_"

EXCEL_TASKS = ("로또신령_주간엑셀업데이트", "로또신령_후보숫자추적표_자동업데이트")
# G5: 대상 회차 풀이가 이 시간 안에 생성됐어야 한다. 48시간인 이유는 pool_gate() 설명 참고
# (Actions 러너=UTC, 이 PC=KST로 생성기록이 남아 같은 실행이 9시간 차이로 보인다).
FRESH_HOURS = 48
ACTIONS_WORKFLOW = "weekly_combo_gen.yml"
GITHUB_REPO = "bandouni33/lotto-shinryeong"


def now_kst() -> datetime:
    return datetime.now(KST)


def log(msg: str) -> None:
    line = f"[{now_kst().isoformat(timespec='seconds')}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ───────────────────────── 게이트 ─────────────────────────

def task_last_run(name: str) -> tuple[str, int]:
    """작업 스케줄러에서 (마지막 실행시각 'YYYY-MM-DDTHH:MM:SS', 결과코드)를 읽는다."""
    ps = (
        f"$i = Get-ScheduledTask -TaskName '{name}' -ErrorAction Stop | Get-ScheduledTaskInfo; "
        "$r = if ($i.LastRunTime) { $i.LastRunTime.ToString('yyyy-MM-ddTHH:mm:ss') } else { '' }; "
        "@{ run = $r; result = [int]$i.LastTaskResult } | ConvertTo-Json -Compress"
    )
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                         capture_output=True, encoding="utf-8", errors="replace", timeout=60)
    text = (out.stdout or "").strip()
    if out.returncode != 0 or not text.startswith("{"):
        raise RuntimeError(f"작업 조회 실패({name}): {text or (out.stderr or '').strip()}")
    data = json.loads(text)
    return str(data.get("run") or ""), int(data.get("result", -1))


def excel_gate(today: str) -> tuple[bool, str]:
    """G2: 두 엑셀 작업의 마지막 실행이 '오늘'이고 결과코드 0."""
    parts, ok = [], True
    for name in EXCEL_TASKS:
        try:
            run, result = task_last_run(name)
        except Exception as e:  # noqa: BLE001
            return False, f"{name}: 조회 실패({type(e).__name__}: {e})"
        good = run.startswith(today) and result == 0
        ok = ok and good
        parts.append(f"{name}: 최근실행={run or '없음'} 결과코드=0x{result:08X}{'' if good else ' ← 실패'}")
    return ok, " · ".join(parts)


def actions_gate(today: str) -> tuple[bool, str]:
    """G3: Actions 주간 조합생성의 최근 실행이 '오늘(KST)'이고 결론이 success."""
    url = (f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/"
           f"{ACTIONS_WORKFLOW}/runs?branch=main&per_page=10")
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "lotto-app-backup-cleanup",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        return False, f"GitHub API 조회 실패({type(e).__name__}: {e})"
    runs = data.get("workflow_runs") or []
    if not runs:
        return False, "실행 기록 없음"
    latest = runs[0]                      # API가 최신순으로 준다
    created, conclusion = latest.get("created_at", ""), latest.get("conclusion")
    try:
        dt = datetime.fromisoformat(str(created).replace("Z", "+00:00")).astimezone(KST)
        run_day, run_time = dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")
    except Exception:  # noqa: BLE001
        run_day, run_time = "", "?"
    ok = run_day == today and conclusion == "success"
    return ok, f"최근실행={run_day} {run_time}(KST) 결론={conclusion} (id={latest.get('id')})"


def pool_gate() -> tuple[bool, str]:
    """G5: 대상 회차(=최신 추첨+1) 조합 풀이 **이번 생성 흐름에서** 만들어졌는가.

    2026-09-27 사용자 승인(P2·P3)으로 "참고근거"에서 **게이트로 승격**했다.
      왜 필요한가: combo_gen_worker.py는 대상 회차에 이미 조합이 있으면 status="skipped"로
      **exit 0(성공)** 한다. 그래서 G3("Actions가 오늘 success")만 보면 "워크플로는 성공으로
      기록됐는데 그 주 조합은 안 만들어졌다"를 통과시킨다:
        · 대상 회차 풀이 0개 (P3)
        · 최신 추첨 동기화가 밀려 워커가 **한 회차 전**을 대상으로 계산 → "이미 있음" → 스킵
          → 성공. 그 회차에 남아 있는 건 지난주 풀 (P2)
      그래서 (a) 풀 개수 ≥ 1, (b) 그 회차 생성기록(draw_pattern_counts.recorded_at)이 최근
      FRESH_HOURS 이내 — 둘을 함께 본다.
      (b)를 경과 시간으로 보는 이유: recorded_at은 실행한 기계의 로컬시각이라 Actions 러너는
      UTC, 이 PC는 KST로 쓰인다 — 같은 실행도 9시간 차이가 나서 날짜 일치로 비교하면 정상
      실행을 실패로 오판한다. 반면 지난주 잔여물은 7일 전이라 48시간 창으로 확실히 걸린다.
      대상 회차 규칙은 워커와 **같은 함수**(combo_filter_v2.peek_target_round)를 쓴다 — 규칙
      사본을 만들면 워커가 만든 회차와 게이트가 보는 회차가 어긋난다.
    조회 실패·기록 없음·형식 오류는 모두 실패로 닫는다(백업을 남기는 쪽이 안전하다).
    """
    try:
        import env_loader

        env_loader.load_dotenv_file()
        import combo_filter_v2
        import draw_results_db
        import marketing_db

        target = combo_filter_v2.peek_target_round(draw_results_db.get_all_draw_results())
        count = marketing_db.get_combination_count_by_draw(target)
        recorded = marketing_db.get_pattern_recorded_at(target)
    except Exception as e:  # noqa: BLE001
        return False, f"조회 실패({type(e).__name__}: {e}) — 풀 생성 여부를 확인할 수 없다"

    if count <= 0:
        return False, f"대상 {target}회차 풀=0개(이번 주 조합이 생성되지 않았다)"

    if not recorded:
        return False, (f"대상 {target}회차 풀={count:,}개지만 생성기록이 없다"
                       f"(지난주 잔여물일 수 있어 통과시키지 않는다)")

    try:
        recorded_dt = datetime.fromisoformat(str(recorded))
    except ValueError:
        return False, f"대상 {target}회차 생성기록을 읽을 수 없다({recorded!r})"

    if recorded_dt.tzinfo is not None:            # tz가 붙은 값이면 로컬 naive로 맞춰 비교한다
        recorded_dt = recorded_dt.astimezone().replace(tzinfo=None)
    age = datetime.now() - recorded_dt
    age_hours = age.total_seconds() / 3600
    detail = (f"대상 {target}회차 풀={count:,}개 · 생성기록="
              f"{recorded_dt.isoformat(timespec='seconds')}({age_hours:+.1f}시간 전)")
    return abs(age) <= timedelta(hours=FRESH_HOURS), detail


def marker_files() -> list[Path]:
    found: list[Path] = []
    for d in BACKUP_DIRS:
        if d.is_dir():
            found.extend(sorted(d.glob(SKIP_MARKER_PREFIX + "*")))
    return found


def write_skip_marker(reason: str, evidence: str) -> list[Path]:
    """자동 삭제를 보류한 사실을 백업 폴더 안에 남긴다(사람이 지워야 재개된다)."""
    written = []
    stamp = now_kst().strftime("%Y-%m-%d")
    body = (
        f"# 자동 삭제 보류 ({stamp})\n\n"
        f"사유: {reason}\n\n"
        f"확인 근거: {evidence}\n\n"
        "이 파일이 있는 동안 weekly_backup_cleanup.py는 자동 삭제를 하지 않습니다.\n"
        "원인을 확인해 백업이 더 필요 없다고 판단되면 이 파일을 지우세요.\n"
    )
    for d in BACKUP_DIRS:
        if d.is_dir():
            p = d / f"{SKIP_MARKER_PREFIX}{stamp}.md"
            p.write_text(body, encoding="utf-8")
            written.append(p)
    return written


def safe_to_delete(path: Path) -> bool:
    """삭제 허용 목록 방어 — 부모가 추적표 폴더이고 이름이 _backup_* 인 경우만."""
    return path.parent == TRACKER_DIR and path.name.startswith("_backup_")


# ───────────────────────── 메인 ─────────────────────────

def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    apply = "--apply" in argv
    now = now_kst()
    today = now.strftime("%Y-%m-%d")

    targets = [d for d in BACKUP_DIRS if d.is_dir()]
    log(f"정리 점검 시작 (오늘={today} {now.strftime('%H:%M')} KST, 모드={'적용' if apply else '미리보기'})")
    if not targets:
        log("삭제 대상 없음(백업 폴더가 이미 없음) — 종료")
        return 0

    if now.weekday() != 6:                                    # G1
        log(f"보류: 일요일이 아님(weekday={now.weekday()}) — 백업 유지")
        return 0

    markers = marker_files()                                  # G4
    if markers:
        log(f"보류: 백업 폴더에 사람이 확인해야 할 메모가 있음 → {[p.name for p in markers]} — 백업 유지")
        return 0

    excel_ok, excel_detail = excel_gate(today)                # G2
    actions_ok, actions_detail = actions_gate(today)          # G3
    pool_ok, pool_detail = pool_gate()                        # G5
    log(f"G2 엑셀업데이트: {'통과' if excel_ok else '실패'} · {excel_detail}")
    log(f"G3 조합생성(Actions): {'통과' if actions_ok else '실패'} · {actions_detail}")
    log(f"G5 대상회차 풀이: {'통과' if pool_ok else '실패'} · {pool_detail}")

    if not (excel_ok and actions_ok and pool_ok):
        reason = (f"게이트 실패 — 엑셀 {'OK' if excel_ok else 'FAIL'} / "
                  f"Actions {'OK' if actions_ok else 'FAIL'} / 풀 {'OK' if pool_ok else 'FAIL'}")
        evidence = f"{excel_detail} · {actions_detail} · {pool_detail}"
        # 2026-09-27 수정: 보류 메모는 **--apply(실제 삭제를 시도한 실행)에서만** 남긴다.
        # 미리보기가 메모를 남기면 (a) 미리보기가 상태를 바꾸게 되고 (b) 그 메모가 G4에 걸려
        # 정작 다음 주 정상 완료 때의 자동 삭제를 막아버린다 — 진단용 드라이런을 돌렸더니
        # 실제 백업 폴더에 메모가 생겨 이 문제가 드러났다(실측).
        if apply:
            written = write_skip_marker(reason, evidence)
            log(f"보류: {reason} — 백업을 그대로 두고 보류 메모를 남겼습니다(사람 확인 필요): {[p.name for p in written]}")
        else:
            log(f"보류: {reason} — 백업 유지(미리보기라 메모는 남기지 않습니다: 미리보기는 상태를 바꾸지 않는다)")
        return 0

    evidence = (f"엑셀 두 작업 오늘 결과코드 0({excel_detail}) · "
                f"Actions {ACTIONS_WORKFLOW} 오늘 success({actions_detail}) · "
                f"대상회차 풀이({pool_detail})")

    if not apply:
        log(f"[미리보기] 게이트 전부 통과 → 지금 --apply 였다면 삭제할 대상: {[str(d) for d in targets]}")
        log(f"[미리보기] 삭제 시 기록될 근거: {evidence}")
        return 0

    # 되돌릴 수 없는 작업 — 근거를 먼저 기록하고(이 로그가 삭제보다 먼저 남는다) 지운다.
    log(f"삭제 실행 · 근거: {evidence}")
    for d in targets:
        if not safe_to_delete(d):
            log(f"건너뜀(허용 목록 밖): {d}")
            continue
        shutil.rmtree(d)
        log(f"삭제 완료: {d}")
    log("정리 종료")
    return 0


if __name__ == "__main__":
    # 2026-09-27 실측: os._exit는 버퍼를 흘려보내지 않는다. 콘솔이 아닌 stdout(파이프·리다이렉트,
    # 예: `weekly_backup_cleanup.py > out.txt`)은 블록 버퍼라 진행 줄이 통째로 사라졌다 — 같은
    # 실행에서 로그 파일에는 줄이 남았는데 화면에는 0줄이었다(그래서 원인 진단이 안 된다).
    _code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_code)  # db_turso의 non-daemon 스레드가 종료를 붙잡는 문제 회피(선례: hourly_draw_sync.py)
