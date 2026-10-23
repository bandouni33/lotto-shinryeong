# -*- coding: utf-8 -*-
"""홍보 영상 게시(weekly_content.promo_video) — 게시만, 순서·간격·중복 방지 계약(가짜 HTTP)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from weekly_content import promo_video as pv  # noqa: E402


class FakeHttp:
    def __init__(self):
        self.calls = []

    def post(self, url, **kw):
        self.calls.append(("POST", url, kw.get("data", {})))
        return {"id": f"id{len(self.calls)}"}

    def get(self, url, **kw):
        self.calls.append(("GET", url, kw.get("params", {})))
        f = kw.get("params", {}).get("fields")
        if f in ("status_code", "status"):
            return {f: "FINISHED"}
        return {"access_token": "newtok"}


class FakeLog:
    def __init__(self, done=()):
        self.d = set(done); self.marks = []

    def done(self, rnd, ch):
        return (rnd, ch) in self.d

    def mark(self, rnd, ch, pid):
        self.marks.append((rnd, ch, pid))

    def get_token(self, n):
        return None

    def set_token(self, n, t):
        pass


ENV = {"WEEKLY_PUBLISH_CHANNELS": "facebook,instagram,threads", "META_PAGE_ID": "p", "META_PAGE_TOKEN": "t",
       "IG_USER_ID": "ig", "THREADS_USER_ID": "th", "THREADS_TOKEN": "tt"}
URL = "https://lottoshinryeong.com/media/x.mp4"


def test_posts_all_three_in_order_with_gaps_and_only_post_endpoints():
    h, lg, slept = FakeHttp(), FakeLog(), []
    res = pv.run(1, URL, env=ENV, http=h, log=lg, sleep=slept.append)
    assert list(res["posted"]) == ["facebook", "instagram", "threads"] and not res["failed"]
    assert [m[1] for m in lg.marks] == ["facebook:promo", "instagram:promo", "threads:promo"]
    gaps = [s for s in slept if s >= 600]
    assert len(gaps) == 2, "채널 사이 10~30분 간격 2번"
    posted = [u for m, u, _ in h.calls if m == "POST"]
    allowed = ("/videos", "/media", "/media_publish", "/threads", "/threads_publish")
    assert all(u.endswith(allowed) for u in posted), f"게시 외 요청 금지: {posted}"
    assert any(d.get("media_type") == "REELS" for m, u, d in h.calls if m == "POST")


def test_already_posted_channels_are_skipped():
    h, lg = FakeHttp(), FakeLog({(1, "facebook:promo"), (1, "instagram:promo")})
    res = pv.run(1, URL, env=ENV, http=h, log=lg, sleep=lambda s: None)
    assert res["skipped"] == {"facebook": "이미 게시됨", "instagram": "이미 게시됨"} and list(res["posted"]) == ["threads"]


def test_captions_link_to_homepage():
    c = pv.captions()
    assert "https://lottoshinryeong.com/" in c["facebook"] and "https://" not in c["instagram"]
    assert len(c["threads"]) <= 500 and "당첨 보장 없음" in c["threads"]
