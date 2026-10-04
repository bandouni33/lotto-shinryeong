"""동시접속 부하테스트용 **측정 전용** 로컬 서버 (운영 DB·네트워크 안 건드림).

왜 이 파일이 필요한가(2026-10-04 조사 지시 1번):
  세션 1개당 RSS·CPU 증가분을 구하려면 "서버 프로세스의 자원"을 재야 하는데,
  scripts/load_test_concurrency.py는 클라이언트가 본 지연만 잰다. 그래서 같은 코드를
  이 PC에서 한 번 띄워 놓고(측정 대상), scratch/monitor_streamlit_resources.py로
  그 프로세스의 RSS·CPU를 샘플링한 뒤, 부하테스트를 이 주소로 돌린다.

운영과 다른 점(그래서 숫자를 읽을 때 같이 봐야 하는 것):
  * DB는 tests/_db_isolation의 임시 sqlite — 운영 Turso에 아무것도 쓰지 않는다.
  * dhlottery 동기화와 주간 조합생성 트리거는 꺼둔다(측정 중 외부 요인 차단).
    즉 여기서 나온 "렌더 1회 비용"은 Turso 왕복 지연을 **포함하지 않는다**.
  * 최신 확정 회차를 비히트로 심어 이벤트 배너가 뜨지 않게 한다(모든 세션에 같은
    창이 하나씩 더 붙으면 세션당 메모리가 실제보다 커진다).

실행(백그라운드): venv312\\Scripts\\python.exe -u -X utf8 scratch\\serve_for_concurrency.py
  * `--cap N` 을 주면 **이 격리 DB에만** 동시접속 상한을 N으로 저장한다(운영 Turso의 설정은
    건드리지 않는다). 상한이 60인 상태로 100/150을 밀면 초과분이 입장 제한 화면(짧은 문서)을
    받아 CPU가 실제보다 싸게 나온다 — 그 왜곡을 빼고 서버 능력을 보려는 플래그다.
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

PORT = 8598
ROUNDS = 1245


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--cap", type=int, default=0,
                    help="이 격리 DB에 저장할 동시접속 상한(0이면 코드 기본값 60 그대로)")
    args = ap.parse_args()

    ctx = _db_isolation.isolated_db()
    db_path = ctx.__enter__()
    print(f"[serve] 격리 DB {db_path}", flush=True)

    import combo_gen_trigger
    import draw_results_db
    import marketing_db as mdb

    draw_results_db.init_draw_results_table()
    numbers = [3, 11, 19, 27, 35, 44]
    for draw_round in range(1, ROUNDS + 1):
        draw_results_db.upsert_draw_result(draw_round, numbers, 7)

    mdb.init_marketing_tables()
    # 최신 확정 회차는 비히트 → 이벤트 배너가 세션마다 붙지 않는다(측정 잡음 제거).
    mdb.set_reference_ranks(ROUNDS, (0, 0, 0, 5, 12))
    mdb.snapshot_round_stats(ROUNDS, 6465)
    mdb.finalize_round_stats(ROUNDS)
    print(f"[serve] 최신 확정 회차 = {ROUNDS} · 배너 대상 = "
          f"{mdb.get_latest_win_event_round()}", flush=True)

    draw_results_db.sync_latest_from_dhlottery = lambda: None
    combo_gen_trigger.maybe_trigger_weekly_generation = lambda: None

    import app_settings

    app_settings.init_settings_table()
    cap = args.cap or app_settings.get_max_concurrent_sessions(default=60)
    if args.cap:
        app_settings.set_max_concurrent_sessions(args.cap)
    print(f"[serve] 동시접속 상한 = {cap} (이 격리 DB에만 적용)", flush=True)

    from streamlit.web import bootstrap

    flags = {
        "server.port": args.port,
        "server.headless": True,
        "server.address": "127.0.0.1",
        "browser.gatherUsageStats": False,
        "global.developmentMode": False,
        "server.fileWatcherType": "none",
    }
    bootstrap.load_config_options(flag_options=flags)
    print(f"[serve] http://127.0.0.1:{args.port}/?page=main", flush=True)
    bootstrap.run(str(ROOT / "app.py"), False, [], flags)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
