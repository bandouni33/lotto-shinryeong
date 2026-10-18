# -*- coding: utf-8 -*-
"""회차 공식 결과(등수별 당첨자 수·금액, 1등 판매점) — 2026-10-18 승인 3번(카드3 '추첨결과 · 당첨지역').

동행복권 공개 응답(2026-10-18 Actions 에서 형식 확인, weekly_content/checks/dh_probe_result.txt):
  /lt645/selectPstLt645Info.do        → data.list[0]: ltEpsd, rnk1WnNope(1등 수), rnk1WnAmt(1게임당) … rnk5, wholEpsdSumNtslAmt
  /wnprchsplcsrch/selectLtWnShp.do?srchLtEpsd=<회차>&srchWnShpRnk=1 → data.list[]: shpNm, region, shpAddr, atmtPsvYnTxt(자동/수동/반자동)
가게 전화번호 등은 담지 않는다(이름·지역·주소·구매 방식만). 실패하면 None — 게시·홈페이지는 '집계중'으로 남는다.
"""
from __future__ import annotations

from collections import Counter

BASE = "https://www.dhlottery.co.kr"
HEADERS = {"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"}


def parse(info: dict, stores: list[dict], rnd: int) -> dict:
    ranks = [{"rank": k, "count": int(info.get(f"rnk{k}WnNope") or 0), "amount": int(info.get(f"rnk{k}WnAmt") or 0)}
             for k in range(1, 6)]
    shops = [{"name": (s.get("shpNm") or "").strip(), "region": (s.get("region") or "").strip(),
              "addr": (s.get("shpAddr") or "").strip(), "kind": (s.get("atmtPsvYnTxt") or "").strip()}
             for s in stores]
    kinds = Counter(s["kind"] for s in shops if s["kind"])
    regions = Counter(s["region"] for s in shops if s["region"])
    return {"round": rnd, "ranks": ranks, "sales": int(info.get("wholEpsdSumNtslAmt") or 0),
            "first_shops": shops, "first_kinds": dict(kinds.most_common()),
            "first_regions": [[k, v] for k, v in regions.most_common()]}


def fetch(rnd: int, http=None, timeout: int = 45) -> dict | None:
    import requests

    http = http or requests
    try:
        info = http.get(f"{BASE}/lt645/selectPstLt645Info.do", timeout=timeout, headers=HEADERS).json()["data"]["list"][0]
        if int(info.get("ltEpsd")) != int(rnd) or not info.get("rnk1WnAmt"):
            return None
        st = http.get(f"{BASE}/wnprchsplcsrch/selectLtWnShp.do", params={"srchLtEpsd": rnd, "srchWnShpRnk": 1},
                      timeout=timeout, headers=HEADERS).json()
        stores = ((st or {}).get("data") or {}).get("list") or []
        res = parse(info, stores, rnd)
        if res["ranks"][0]["count"] and len(stores) < 1:
            return None   # 판매점 집계 전 — 다음 실행에서 다시
        return res
    except Exception as exc:  # noqa: BLE001
        print(f"  (동행복권 결과 조회 실패 {rnd}회: {exc})")
        return None


def eok(won: int) -> str:
    """금액 한글 표기: 1,881,025,430 → '18억 8,102만원', 1,497,334 → '149만 7,334원', 50,000 → '5만원'."""
    won = int(won)
    e, rest = divmod(won, 100_000_000)
    man, one = divmod(rest, 10_000)
    if e:
        return f"{e}억 {man:,}만원" if man else f"{e}억원"
    if man:
        return f"{man:,}만 {one:,}원" if one else f"{man:,}만원"
    return f"{won:,}원"
