"""판매(배포) 가능 시간대 — 현재는 자동구매(page_auto.py) 전용.

2026-09-09: 원래 자동구매에만 있던 규칙이었는데, 사용자 지시로 번개조합·
안티액땜조합에도 "자동구매와 동일한 방식"으로 확정 적용했었다. 이후
2026-09-14(안티·액땜조합/page_hedge.py)와 2026-09-20(번개조합/page_thunder.py)
사용자 지시로 두 화면 다 이 제한에서 다시 제외돼, 지금은 자동구매만 이 모듈을
쓴다. 그래도 세 화면 중 하나라도 다시 시간대 제한을 걸게 되면 이 모듈을 그대로
재사용할 것 — 화면마다 규칙을 복붙해서 따로 들고 있으면 나중에 시간대가 바뀔 때
한 곳만 고치고 나머지를 빠뜨리는 사고로 이어진다.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

# 2026-10-12(사용자 지시): "화 09:00부터"를 없애고 **다음 회차 배포용 조합이 준비되는 즉시**
# (일요일 13:30 Actions 조합생성 직후) 이용 가능. 마감은 그대로 토 19:55(추첨 직전).
# 준비 전(토 19:55 ~ 조합 생성 완료)에는 "준비중입니다" 안내만 띄운다.
SALES_WINDOW_BANNER = "준비중입니다"
DRAW_CUTOFF = time(19, 55)
_ROUND1_DATE = date(2002, 12, 7)   # 1회차 추첨일(토) — 1245회 = 2026-10-10 으로 확인


def target_round_for(now: datetime | None = None) -> int:
    """지금 팔아야 할 회차 — 이번 주 토요일 19:55 전이면 그 토요일 회차, 지나면 다음 주 회차."""
    now = now or datetime.now(ZoneInfo("Asia/Seoul"))
    d = now.date()
    sat = d + timedelta(days=(5 - d.weekday()) % 7)
    if d.weekday() == 5 and now.time() >= DRAW_CUTOFF:
        sat += timedelta(days=7)
    return 1 + (sat - _ROUND1_DATE).days // 7


def is_sales_window_open(now: datetime | None = None, *, next_round: int | None = None,
                         pool_ready: bool | None = None) -> bool:
    """이용 가능 = (앱이 아는 다음 회차가 날짜로 계산한 판매 회차와 같다) and (그 회차 배포 조합이 DB에 있다).

    · 토 19:55 이후: 판매 회차가 다음 주로 넘어가는데 당첨번호 반영 전이면 앱의 다음 회차가 옛 회차 → 닫힘
    · 당첨번호 반영 뒤 ~ 일요일 조합 생성 전: 그 회차 조합이 없음 → 닫힘(준비중)
    · 조합 생성 직후 ~ 토 19:55: 열림
    조회가 실패하면 닫힘(안전 쪽)."""
    try:
        if next_round is None or pool_ready is None:
            from auto_purchase_service import check_next_draw_pool_ready

            pool = check_next_draw_pool_ready()
            next_round, pool_ready = int(pool["draw_round"]), bool(pool["ok"])
        return bool(pool_ready) and int(next_round) == target_round_for(now)
    except Exception:  # noqa: BLE001
        return False
