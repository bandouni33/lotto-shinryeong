"""매주 새 회차가 뜨면 1241회차부터는 사람이 손대지 않아도 다음 회차 조합이
자동 생성되도록 하는 트리거. UptimeRobot이 주기적으로 앱 URL을 핑 하는 걸
그대로 이용한다 — app.py 최상단에서 매 요청마다 호출되지만, 실제 무거운
작업(회차 조회·조합 생성)은 아래 쿨다운으로 대부분의 요청에서 건너뛴다.

이 파일 안의 모든 실패는 절대 화면에 노출되면 안 된다(사용자 페이지 렌더링과
무관한 백그라운드 관리 작업이므로) — 호출부에서 반드시 try/except로 감싼다.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

_CHECK_COOLDOWN = timedelta(minutes=30)
_WORKER_SCRIPT = os.path.join(os.path.dirname(__file__), "combo_gen_worker.py")


def _now_kst() -> datetime:
    return datetime.now(timezone(timedelta(hours=9)))


def maybe_trigger_weekly_generation() -> None:
    import app_settings
    import draw_results_db
    import marketing_db

    # 2026-09-05 확정(수정): "회차 감지되는 즉시"가 아니라 매주 일요일
    # 오후 2시대(14:00~14:59 KST)에만 생성 — 구매자 랜덤배정 자체는 이
    # 시간과 무관하게 상시 작동(자동구매는 이미 저장된 풀에서 바로
    # 배정하므로). Python weekday(): 월=0 … 일=6.
    now = _now_kst()
    if not (now.weekday() == 6 and now.hour == 14):
        return

    app_settings.init_settings_table()

    last_check_str = app_settings.get_setting("combo_gen_last_check_at", "")
    if last_check_str:
        try:
            last_check = datetime.fromisoformat(last_check_str)
            if _now_kst() - last_check < _CHECK_COOLDOWN:
                return
        except ValueError:
            pass

    # 다른 요청과 거의 동시에 들어와도 쿨다운 창을 최대한 빨리 갱신해 중복
    # 실행 가능성을 줄인다(완벽한 락은 아니지만 이 정도 빈도에선 충분하다).
    app_settings.set_setting("combo_gen_last_check_at", _now_kst().isoformat())

    draw_results_db.init_draw_results_table()
    # 2026-09-06 버그 수정: sync_latest_from_dhlottery()는 "이번 호출에서
    # 새로 발견된" 회차만 반환하고, 이미 알고 있던 회차면 None을 준다(다른
    # 경로— 시간별 자동동기화 등 —로 미리 동기화돼 있던 경우가 흔함). 예전
    # 코드는 이 None을 "할 일 없음"으로 오해해서 그 자리에서 조용히
    # 종료했는데, 그 바람에 1240회가 이미 알려진 상태였던 첫 일요일에
    # 1241회 조합 생성이 통째로 스킵됐다(실측 확인). 새로 발견됐든 이미
    # 알고 있던 회차든 상관없이, "지금 알고 있는 최신 회차" 기준으로
    # target_round를 계산해야 한다 — 아래 get_combination_count_by_draw
    # 체크가 어차피 중복 생성은 막아주므로 안전하다.
    draw_results_db.sync_latest_from_dhlottery()
    latest_round = draw_results_db.get_latest_draw_round()
    if latest_round is None:
        return

    target_round = latest_round + 1
    if marketing_db.get_combination_count_by_draw(target_round) > 0:
        return  # 이미 생성됨

    status_file = os.path.join(os.path.dirname(__file__), "combo_gen_job.status")
    if os.path.exists(status_file):
        import json

        try:
            with open(status_file, encoding="utf-8") as f:
                state = json.load(f).get("state")
            if state == "running":
                return  # 이미 실행 중인 워커가 있음
        except Exception:
            pass

    subprocess.Popen(
        [sys.executable, _WORKER_SCRIPT],
        cwd=os.path.dirname(__file__) or ".",
        close_fds=True,
    )
