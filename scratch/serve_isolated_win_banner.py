"""로컬 검증 서버 — 이벤트 배너를 **실제 브라우저**로 보기 위한 것 (운영 DB 안 건드림).

왜 필요한가(2026-10-04): 구름님이 "제목 가운데 정렬·버튼 한 줄·빈 공간"이 실기기에서
반영되지 않았다고 보고했다. 지금까지의 검증(AppTest)은 **DOM이 없어** CSS 선택자가
실제로 어느 요소에 걸리는지 알 수 없었다 — 그래서 잘못된 선택자를 통과시켰다.
여기서는 격리 DB로 앱을 띄우고 Playwright로 진짜 DOM을 읽어 계측한다.

운영 Turso를 절대 건드리지 않는다: 앱 스크립트가 이 프로세스의 스레드에서 실행되므로
tests/_db_isolation.isolated_db()의 db_turso.connect 패치가 그대로 적용된다.

실행(백그라운드): venv312\\Scripts\\python.exe -u -X utf8 scratch\\serve_isolated_win_banner.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from env_loader import load_dotenv_file  # noqa: E402

load_dotenv_file()

import _db_isolation  # noqa: E402

PORT = 8599
GUEST = "probe_wev"
HIT_ROUND = 1245
STAGE4 = 939_330
RANKS = (0, 1, 18, 169, 1157)


def main() -> int:
    ctx = _db_isolation.isolated_db()
    db_path = ctx.__enter__()
    print(f"[serve] 격리 DB {db_path}", flush=True)

    import combo_gen_trigger
    import draw_results_db
    import marketing_db as mdb
    import user_scope

    draw_results_db.init_draw_results_table()
    for draw_round in range(1241, HIT_ROUND):
        draw_results_db.upsert_draw_result(draw_round, [2, 11, 25, 33, 41, 45], 7)
    mdb.init_marketing_tables()
    mdb.set_reference_ranks(HIT_ROUND, RANKS)
    mdb.snapshot_round_stats(HIT_ROUND, 6465)
    mdb.finalize_round_stats(HIT_ROUND)
    mdb.record_draw_generation_stats(HIT_ROUND, 2_000_000, STAGE4, (34, 14, 45, 33, 40))
    print(f"[serve] 배너 조건 = {mdb.get_latest_win_event_round()}", flush=True)

    # 화면이 새 게스트를 만들거나 외부로 나가지 않게 고정(운영 DB·네트워크 접촉 차단).
    user_scope.get_or_create_guest_id = lambda: GUEST
    draw_results_db.sync_latest_from_dhlottery = lambda: None
    combo_gen_trigger.maybe_trigger_weekly_generation = lambda: None

    from streamlit.web import bootstrap

    flags = {
        "server.port": PORT,
        "server.headless": True,
        "server.address": "127.0.0.1",
        "browser.gatherUsageStats": False,
        "global.developmentMode": False,
        "server.fileWatcherType": "none",
    }
    bootstrap.load_config_options(flag_options=flags)
    print(f"[serve] http://127.0.0.1:{PORT}/?page=main", flush=True)
    bootstrap.run(str(ROOT / "app.py"), False, [], flags)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
