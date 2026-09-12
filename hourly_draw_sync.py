"""매시 정각 — 방문자 유무와 무관하게 동행복권 최신 회차를 확인해 반영한다.

2026-09-07: 기존엔 "누군가 메인페이지를 열 때, 마지막 확인 후 1시간이 지났으면"
만 새로 확인하는 구조(lotto_stats._auto_sync_latest_draw_cached, ttl=3600)라,
토요일 밤처럼 방문자가 뜸한 시간대엔 실제 추첨 후에도 한참 방치될 수 있었다.
GitHub Actions에서 이 스크립트를 매시 정각 스케줄로 직접 돌려(.github/workflows/
hourly_draw_sync.yml), 방문자와 완전히 무관하게 Turso DB에 반영한다.

sync_latest_from_dhlottery()는 이미 "DB 최신 회차보다 사이트 최신 회차가 더 클
때만" 반영하고 실패해도 조용히 넘어가도록 만들어져 있어(draw_results_db.py),
이미 최신이면 이 스크립트를 몇 번을 돌려도 아무 일도 일어나지 않는다 — 그래서
요일·시간 조건 없이 매시 정각 그냥 돌리는 쪽이 "토요일 21시부터"를 코드로
따로 계산하는 것보다 더 단순하고 견고하다(자정 넘겨 발표되는 등 변수에도 안전).
"""

from __future__ import annotations

import os


def main() -> int:
    import draw_results_db

    draw_results_db.init_draw_results_table()
    new_round = draw_results_db.sync_latest_from_dhlottery()
    if new_round is not None:
        print(f"[hourly_draw_sync] {new_round}회차 당첨번호 신규 반영")
    else:
        print("[hourly_draw_sync] 변경 없음 (이미 최신이거나 아직 미발표)")
    return 0


if __name__ == "__main__":
    # 2026-09-13(GitHub Actions 실행이 몇 시간째 "진행 중"에서 안 끝나는 문제
    # 조사): db_turso.py의 _EXECUTOR(ThreadPoolExecutor)가 만드는 워커 스레드는
    # non-daemon이라, Turso 서버가 응답을 안 주는 상황(db_turso.py 2026-09-03
    # 주석 참고 — libsql_client 자체에 타임아웃이 없어 그 요청을 기다리는
    # 스레드가 예외조차 없이 영원히 멈춤)에서 foreground 쪽은 10초 만에
    # TimeoutError로 안전하게 빠져나와도, 그 멈춘 백그라운드 스레드 자체는
    # 계속 살아있어서 sys.exit()가 프로세스를 실제로 못 끝낸다(non-daemon
    # 스레드가 하나라도 살아있으면 인터프리터가 종료를 기다림) — Streamlit
    # 앱처럼 오래 떠있는 프로세스에서는 무해하지만, 한 번 돌고 끝나야 하는
    # 이 스크립트에서는 GitHub Actions job이 몇 시간이고 "진행 중"인 채로
    # 안 끝나는 원인이 된다. os._exit()로 다른 스레드를 기다리지 않고 즉시
    # 프로세스를 종료시킨다.
    exit_code = main()
    os._exit(exit_code)
