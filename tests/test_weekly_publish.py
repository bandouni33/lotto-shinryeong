"""주간 리포트 자동 게시(weekly_content/publish.py) — 실제 API 대신 가짜 응답으로 흐름만 검사.

  P1 스위치가 비어 있으면 아무것도 올리지 않고 계획만 남긴다
  P2 네 채널 모두 켜면 페북 비공개 사진 → 페북·인스타·스레드·유튜브 순으로 올리고 기록한다
  P3 같은 회차를 다시 돌리면 이미 올린 채널은 건너뛴다(중복 게시 방지)
  P4 키가 없는 채널은 건너뛰고, 한 채널 실패가 다른 채널을 막지 않는다
  P5 스레드 토큰은 갱신해 DB 에 저장한다
  P6 채널별 문구는 cards.captions_all 한 곳에서 — 스레드 500자 이내, 유튜브 제목 100자 이내

실행: python tests/test_weekly_publish.py
"""
from __future__ import annotations

import json
import random
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from weekly_content import cards, publish as pub  # noqa: E402


class Resp:
    def __init__(self, data, status=200, headers=None):
        self._d, self.status_code, self.headers, self.text = data, status, headers or {}, json.dumps(data)

    def json(self):
        return self._d


class FakeSession:
    def __init__(self, fail=()):
        self.calls, self.fail, self.n = [], set(fail), 0

    def _id(self):
        self.n += 1
        return f"id{self.n}"

    def get(self, url, **kw):
        self.calls.append(("GET", url))
        if "refresh_access_token" in url:
            return Resp({"access_token": "TNEW"})
        if kw.get("params", {}).get("fields") == "images":
            return Resp({"images": [{"width": 1080, "source": f"https://cdn/{url.rsplit('/', 1)[1]}.jpg"}]})
        return Resp({"status_code": "FINISHED"})

    def post(self, url, **kw):
        self.calls.append(("POST", url))
        for f in self.fail:
            if f in url:
                return Resp({"error": {"message": "boom"}}, 400)
        if "oauth2" in url:
            return Resp({"access_token": "YT"})
        if "upload/youtube" in url:
            return Resp({}, 200, {"Location": "https://upload/session"})
        return Resp({"id": self._id()})

    def put(self, url, **kw):
        self.calls.append(("PUT", url))
        return Resp({"id": "yt1"})


def _out(tmp: Path, rnd=1246) -> Path:
    r = random.Random(3)
    d = {}
    for i in range(1, rnd + 1):
        nums = sorted(r.sample(range(1, 46), 6))
        d[i] = {"nums": nums, "bonus": next(b for b in range(1, 46) if b not in nums)}
    for i in range(1, 6):
        Image.new("RGB", (40, 50), (i * 20, 0, 0)).save(tmp / f"{rnd}_{i}.png")
    (tmp / f"{rnd}_shorts.mp4").write_bytes(b"mp4")
    (tmp / f"{rnd}_captions.json").write_text(json.dumps(cards.captions_all(d, rnd), ensure_ascii=False),
                                             encoding="utf-8")
    return tmp


ALL_ENV = {"WEEKLY_PUBLISH_CHANNELS": "facebook,instagram,threads,youtube", "META_PAGE_ID": "PG",
           "META_PAGE_TOKEN": "PT", "IG_USER_ID": "IG", "THREADS_USER_ID": "TH", "THREADS_TOKEN": "TOLD",
           "YT_CLIENT_ID": "c", "YT_CLIENT_SECRET": "s", "YT_REFRESH_TOKEN": "r"}


def _log():
    conn = sqlite3.connect(":memory:")
    return pub.PostLog(connect=lambda: conn)


class PublishTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        _out(self.tmp)

    def test_P1_switch_off(self):
        s = FakeSession()
        res = pub.publish(self.tmp, env={}, http=pub.Http(s), log=_log())
        self.assertEqual(res["posted"], {})
        self.assertEqual(s.calls, [])
        self.assertTrue((self.tmp / "1246_publish_plan.json").exists())

    def test_P2_all_channels(self):
        s, log = FakeSession(), _log()
        res = pub.publish(self.tmp, env=ALL_ENV, http=pub.Http(s), log=log, sleep=lambda *_: None)
        self.assertEqual(set(res["posted"]), {"facebook", "instagram", "threads", "youtube"}, res)
        self.assertEqual(res["failed"], {})
        photos = [c for c in s.calls if c[0] == "POST" and c[1].endswith("/PG/photos")]
        self.assertEqual(len(photos), 5)
        self.assertTrue(any(c[1].endswith("/IG/media_publish") for c in s.calls))
        self.assertTrue(any(c[1].endswith("/TH/threads_publish") for c in s.calls))
        self.assertTrue(all(log.done(1246, c) for c in pub.CHANNELS))

    def test_P3_no_duplicate(self):
        log = _log()
        pub.publish(self.tmp, env=ALL_ENV, http=pub.Http(FakeSession()), log=log, sleep=lambda *_: None)
        s2 = FakeSession()
        res = pub.publish(self.tmp, env=ALL_ENV, http=pub.Http(s2), log=log, sleep=lambda *_: None)
        self.assertEqual(res["posted"], {})
        self.assertEqual(set(res["skipped"]), set(pub.CHANNELS))
        self.assertFalse(any("photos" in c[1] or "media" in c[1] for c in s2.calls))

    def test_P7_predraw_kind_separate_log(self):
        """목·금 콘텐츠(kind=thu): 카드 2장만 올리고, 게시 기록 키가 '채널:thu' 라 토요일 게시와 섞이지 않음."""
        log = _log()
        pub.publish(self.tmp, env=ALL_ENV, http=pub.Http(FakeSession()), log=log, sleep=lambda *_: None)
        s = FakeSession()
        res = pub.publish(self.tmp, env=ALL_ENV, http=pub.Http(s), log=log, sleep=lambda *_: None, kind="thu")
        self.assertEqual(set(res["posted"]), set(pub.CHANNELS), res)
        photos = [c for c in s.calls if c[0] == "POST" and c[1].endswith("/PG/photos")]
        self.assertEqual(len(photos), 2)
        self.assertTrue(all(log.done(1246, f"{c}:thu") for c in pub.CHANNELS))
        res2 = pub.publish(self.tmp, env=ALL_ENV, http=pub.Http(FakeSession()), log=log, sleep=lambda *_: None,
                           kind="thu")
        self.assertEqual(res2["posted"], {})

    def test_P8_talisman_instagram_first(self):
        """회차 부적이 있으면 사진 6장 업로드, 인스타 캐러셀 6장(부적이 첫 장), 페북·스레드는 카드 5장."""
        Image.new("RGB", (40, 50), (9, 9, 9)).save(self.tmp / "1246_talisman.png")
        s = FakeSession()
        res = pub.publish(self.tmp, env=ALL_ENV, http=pub.Http(s), log=_log(), sleep=lambda *_: None)
        self.assertEqual(res["failed"], {})
        photos = [c for c in s.calls if c[0] == "POST" and c[1].endswith("/PG/photos")]
        self.assertEqual(len(photos), 6)
        ig_items = [c for c in s.calls if c[0] == "POST" and c[1].endswith("/IG/media")]
        th_items = [c for c in s.calls if c[0] == "POST" and c[1].endswith("/TH/threads")]
        self.assertEqual(len(ig_items), 6 + 1)    # 캐러셀 항목 6 + 캐러셀 1
        self.assertEqual(len(th_items), 5 + 1)

    def test_P9_channel_gap(self):
        """채널 사이 5분 간격: 4채널 게시면 대기 3번(각 300초)."""
        waits = []
        pub.publish(self.tmp, env=ALL_ENV, http=pub.Http(FakeSession()), log=_log(), sleep=waits.append)
        self.assertEqual([w for w in waits if w == pub.CHANNEL_GAP_SEC], [300, 300, 300])

    def test_P4_missing_keys_and_failure_isolated(self):
        env = dict(ALL_ENV)
        del env["YT_REFRESH_TOKEN"]
        s = FakeSession(fail=("/IG/media",))
        res = pub.publish(self.tmp, env=env, http=pub.Http(s), log=_log(), sleep=lambda *_: None)
        self.assertIn("instagram", res["failed"])
        self.assertIn("youtube", res["skipped"])
        self.assertEqual(set(res["posted"]), {"facebook", "threads"})

    def test_P5_threads_token_refreshed(self):
        log = _log()
        pub.publish(self.tmp, env=dict(ALL_ENV, WEEKLY_PUBLISH_CHANNELS="threads"), http=pub.Http(FakeSession()),
                    log=log, sleep=lambda *_: None)
        self.assertEqual(log.get_token("threads"), "TNEW")

    def test_P6_caption_limits(self):
        caps = json.loads((self.tmp / "1246_captions.json").read_text(encoding="utf-8"))
        self.assertLessEqual(len(caps["threads"]), 500)
        self.assertLessEqual(len(caps["youtube_title"]), 100)
        for k in ("instagram", "facebook", "threads", "youtube_description"):
            self.assertIn("당첨을 보장" if k != "threads" else "당첨 보장 없음", caps[k])


if __name__ == "__main__":
    unittest.main(verbosity=2)
