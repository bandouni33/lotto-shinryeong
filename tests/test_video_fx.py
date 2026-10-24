# -*- coding: utf-8 -*-
"""목·토 SNS 영상 공통 연출(2026-10-24 사용자 지시: 토요일도 목요일과 같은 방식)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from weekly_content import video_fx as fx  # noqa: E402


def test_saturday_plan_one_minute_varied():
    p = fx.plan([9, 12, 16, 13, 10], 0, offset=2)
    assert abs(sum(p["secs"]) - p["xf"] * 4 - fx.VIDEO_SEC) < 0.5
    assert len(set(p["trans"])) == 4
    assert all(a != b for a, b in zip(p["styles"], p["styles"][1:]))
    assert p["secs"][2] == max(p["secs"])   # 숫자 분석 장이 가장 길다


def test_thursday_and_saturday_differ_same_week():
    thu, sat = fx.plan([1] * 5, 0), fx.plan([1] * 5, 0, offset=2)
    assert thu["trans"] != sat["trans"] and thu["styles"] != sat["styles"]
