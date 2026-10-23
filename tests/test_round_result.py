"""회차 공식 결과·'결과 정리' 게시물(2026-10-18 승인 3번).

  R1 parse: 등수별 수·금액, 1등 판매점(이름·지역·주소·구매방식만 — 전화번호 등 미포함), 방식·지역 집계
  R2 eok 금액 표기
  R3 fetch: 최신 회차가 아니거나 판매점 집계 전이면 None, 정상이면 결과
  R4 result_post.build: 카드 2장·문구(채널 3종)·결과 json
실행: python tests/test_round_result.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from weekly_content import result_post, round_result as rr  # noqa: E402

INFO = {"ltEpsd": 1246, "rnk1WnNope": 16, "rnk1WnAmt": 1881025430, "rnk2WnNope": 64, "rnk2WnAmt": 78376060,
        "rnk3WnNope": 3350, "rnk3WnAmt": 1497334, "rnk4WnNope": 155108, "rnk4WnAmt": 50000,
        "rnk5WnNope": 2608922, "rnk5WnAmt": 5000, "wholEpsdSumNtslAmt": 121857105000}
STORES = [{"shpNm": "가게A", "region": "서울", "shpAddr": "서울 중구 1", "atmtPsvYnTxt": "수동", "shpTelno": "02-000"},
          {"shpNm": "가게B", "region": "경기", "shpAddr": "경기 수원 2", "atmtPsvYnTxt": "자동", "shpTelno": "031-000"},
          {"shpNm": "가게C", "region": "경기", "shpAddr": "경기 화성 3", "atmtPsvYnTxt": "자동"},
          {"shpNm": "인터넷 복권판매사이트", "region": "서울", "shpAddr": "동행복권(dhlottery.co.kr)", "atmtPsvYnTxt": "자동"}]


class R:
    def __init__(self, d):
        self.d = d

    def json(self):
        return self.d


class Http:
    def __init__(self, info, stores):
        self.info, self.stores = info, stores

    def get(self, url, **kw):
        if "selectPstLt645Info" in url:
            return R({"data": {"list": [self.info]}})
        return R({"data": {"total": len(self.stores), "list": self.stores}})


class RoundResultTest(unittest.TestCase):
    def test_R1_parse(self):
        res = rr.parse(INFO, STORES, 1246)
        self.assertEqual(res["ranks"][0], {"rank": 1, "count": 16, "amount": 1881025430})
        self.assertEqual(res["first_kinds"], {"자동": 3, "수동": 1})
        self.assertEqual(res["first_shops"][3]["region"], "인터넷")
        self.assertEqual(res["first_regions"][0], ["경기", 2])
        self.assertEqual(set(res["first_shops"][0]), {"name", "region", "addr", "kind"})
        self.assertNotIn("02-000", json.dumps(res))

    def test_R2_eok(self):
        self.assertEqual([rr.eok(x) for x in (1881025430, 78376060, 50000, 5000)],
                         ["18억 8,102만원", "7,837만 6,060원", "5만원", "5,000원"])

    def test_R3_fetch(self):
        self.assertIsNone(rr.fetch(1247, http=Http(INFO, STORES)))
        self.assertIsNone(rr.fetch(1246, http=Http(INFO, [])))
        self.assertEqual(rr.fetch(1246, http=Http(INFO, STORES))["round"], 1246)

    def test_R4_build(self):
        tmp = Path(tempfile.mkdtemp())
        paths = result_post.build(rr.parse(INFO, STORES, 1246), tmp)
        self.assertEqual([p.name for p in paths], ["1246_1.png", "1246_2.png"])
        caps = json.loads((tmp / "1246_captions.json").read_text(encoding="utf-8"))
        self.assertIn("1등 16명", caps["facebook"])
        self.assertLessEqual(len(caps["threads"]), 500)
        # 2026-10-22: 링크는 홈페이지 하나로(인스타는 본문 링크가 안 눌려 '프로필 링크' 안내, 페북은 회차 페이지 주소 1개)
        self.assertIn("프로필 링크", caps["instagram"])
        self.assertIn("https://lottoshinryeong.com/round/1246/", caps["facebook"])
        self.assertIn("세금 떼면", caps["facebook"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
