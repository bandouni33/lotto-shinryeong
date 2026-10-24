# -*- coding: utf-8 -*-
"""목요일 게시물 5장(2026-10-24 사용자 컨셉) — 장 수·첫 회차 원문·매주 변형."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from weekly_content import thursday as th  # noqa: E402


def test_five_pages_with_screens():
    assert th.TOTAL == 5 == len(th.PAGES)
    for p in th.PAGES:
        assert (th.SCREENS / f"{p['screen']}.jpg").exists()
    ims = th.build(1247)
    assert len(ims) == 5 and all(im.size == (1080, 1350) for im in ims)


def test_first_round_uses_user_text_and_rotates():
    assert th.page_text(0, 1247)[0] == ["지금 마음이 불편하신가요?"]
    assert th.page_text(1, 1247)[0] == ["아무 근거 없이", "무작위로 구매하고 계시나요?"]
    assert th.page_text(2, 1247)[0] == ["이번 주 좋은 꿈 꾸셨나요?"]
    assert th.page_text(0, 1248) != th.page_text(0, 1247)   # 매주 감정 단어가 바뀐다
