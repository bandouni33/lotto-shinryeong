"""판매(배포) 가능 시간대 — 자동구매/번개조합/안티·액땜조합 공통.

2026-09-09: 원래 자동구매(page_auto.py)에만 있던 규칙이었는데, 사용자 지시로
번개조합·안티액땜조합에도 "자동구매와 동일한 방식"으로 확정 적용한다. 세 화면이
각자 이 규칙을 복붙해서 갖고 있으면 나중에 시간대가 바뀔 때 한 곳만 고치고
나머지를 빠뜨리는 사고로 이어지므로, 이 모듈 하나만 고치면 세 화면 전부에
반영되게 한다.
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
