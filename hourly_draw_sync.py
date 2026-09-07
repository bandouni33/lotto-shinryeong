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

import sys


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
    sys.exit(main())
