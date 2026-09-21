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

from datetime import datetime, time
from zoneinfo import ZoneInfo

SALES_WINDOW_BANNER = (
    "배포 가능 시간이 아닙니다. "
    "매주 화요일 09:00부터 토요일 19:55까지만 구매(배포)할 수 있습니다."
)


def is_sales_window_open(now: datetime | None = None) -> bool:
    """KST — 화 09:00 ~ 토 19:55 (그 외 구매·조합생성 불가)."""
    now = now or datetime.now(ZoneInfo("Asia/Seoul"))
    weekday = now.weekday()  # 월=0 … 일=6
    clock = now.time()
    if weekday in (6, 0):  # 일, 월
        return False
    if weekday == 1:  # 화
        return clock >= time(9, 0)
    if weekday == 5:  # 토
        return clock <= time(19, 55)
    return weekday in (2, 3, 4)  # 수, 목, 금
