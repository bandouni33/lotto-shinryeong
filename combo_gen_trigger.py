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

    # 2026-09-05 확정: "회차 감지되는 즉시"가 아니라 매주 월요일 오전
    # 10시대(10:00~10:59 KST)에만 생성 — 구매자 랜덤배정 자체는 이 시간과
    # 무관하게 상시 작동(자동구매는 이미 저장된 풀에서 바로 배정하므로).
    now = _now_kst()
    if not (now.weekday() == 0 and now.hour == 10):
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
    new_round = draw_results_db.sync_latest_from_dhlottery()
    if new_round is None:
        return

    target_round = new_round + 1
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
