# -*- coding: utf-8 -*-
"""목요일 게시물 5장(2026-10-24 사용자 컨셉) — 장 수·첫 회차 원문·매주 변형."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from weekly_content import thursday as th  # noqa: E402


def test_five_pages_with_screens():
    assert th.TOTAL == 5 == len(th.PAGES)
    for p in th.PAGES:
        assert len(p["screens"]) >= 2   # 기능마다 화면 여러 장(매주 다른 화면)
        for sc in p["screens"]:
            assert (th.SCREENS / f"{sc}.jpg").exists()
    assert th.screen_for(4, 1247) == "adv" and th.screen_for(4, 1248) == "adv_2"
    assert len({th.screen_for(2, r) for r in range(1247, 1253)}) == 6   # 번개조합 6주 연속 모두 다른 화면
    ims = th.build(1247)
    assert len(ims) == 5 and all(im.size == (1080, 1350) for im in ims)


def test_first_round_uses_user_text_and_rotates():
    assert th.page_text(0, 1247)[0] == ["지금 마음이 불편하신가요?"]
    assert th.page_text(1, 1247)[0] == ["아무 근거 없이", "무작위로 구매하고 계시나요?"]
    assert th.page_text(2, 1247)[0] == ["이번 주 좋은 꿈 꾸셨나요?"]
    assert th.page_text(0, 1248) != th.page_text(0, 1247)   # 매주 감정 단어가 바뀐다


def test_video_plan_about_one_minute_and_weekly_variety():
    p1, p2 = th.video_plan(1247), th.video_plan(1248)
    for p in (p1, p2):
        total = sum(p["secs"]) - p["xf"] * (th.TOTAL - 1)
        assert abs(total - th.VIDEO_SEC) < 0.5                  # 약 1분
        assert p["secs"][4] > p["secs"][0]                       # 글자 많은 장(고급필터)이 더 길다
        assert len(set(p["trans"])) == th.TOTAL - 1              # 한 영상 안에서 넘김 효과가 모두 다름
        assert all(a != b for a, b in zip(p["styles"], p["styles"][1:]))   # 이웃한 장은 다른 음악
    assert p1["trans"] != p2["trans"] and p1["styles"] != p2["styles"]      # 매주 바뀜
    assert th.video_plan(1247) == p1                             # 같은 회차 = 같은 연출


def test_bgm_styles_render():
    from weekly_content import bgm
    for name in th.MUSIC_ORDER:
        a = bgm.render_style(2.0, "t", name)
        assert a.shape == (int(2.0 * bgm.SR), 2) and abs(a).max() > 0.1
