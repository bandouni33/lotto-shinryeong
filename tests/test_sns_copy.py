# -*- coding: utf-8 -*-
"""SNS 문구 공통 부품(weekly_content.sns_copy) — 2026-10-22 개편 계약."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from weekly_content import pre_draw, sns_copy as sc  # noqa: E402


def _draws():
    d = json.loads((ROOT / "site_data" / "data.json").read_text(encoding="utf-8"))
    return {r[0]: {"round": r[0], "nums": r[2:8], "bonus": r[8]} for r in d["draws"]}, d["latest_round"]


def test_net_prize_matches_homepage_calculator():
    # 홈페이지 /tools/prize/ 와 같은 식: 200만원 이하 비과세, (당첨금-1000) 중 3억까지 22%, 초과분 33%
    assert sc.net_prize(5000) == 5000
    assert sc.net_prize(2_000_000) == 2_000_000
    b = 1_881_025_430 - 1000
    assert sc.net_prize(1_881_025_430) == 1_881_025_430 - int(3e8 * 0.22 + (b - 3e8) * 0.33)


def test_hashtag_limits_per_channel():
    ig = sc.hashtags(1247, sc.KW_DRAW, sc.KW_PRIZE, sc.KW_STATS, channel="instagram").split()
    fb = sc.hashtags(1247, sc.KW_DRAW, channel="facebook").split()
    assert len(ig) <= 15 and len(fb) <= 5 and ig[-1] == fb[-1] == "#로또신령"
    assert sc.hashtags(1247, sc.KW_DRAW, channel="threads") == "#로또"


def test_links_go_to_homepage_only():
    draws, latest = _draws()
    for kind in ("thu", "fri"):
        c = pre_draw.captions(kind, draws, latest)
        assert "play.google.com" not in c["facebook"] and "blog.naver.com" not in c["facebook"]
        assert c["facebook"].count("https://") == 1, "페이스북 본문 링크는 1개"
        assert "https://" not in c["instagram"], "인스타 본문 링크는 눌리지 않는다 — 프로필 링크 안내"
        assert len(c["threads"]) <= 500
        assert all("참고·재미용" not in c[k] for k in ("instagram", "facebook", "threads")), "참고사항 넣지 않음(10-24)"
