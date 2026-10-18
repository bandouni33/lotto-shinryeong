# -*- coding: utf-8 -*-
"""동행복권 공개 응답 형식 확인(2026-10-18, 카드3 당첨자 수·금액·명당 작업 준비) — 공개 데이터만 기록."""
import json
import re
import sys

import requests

out = []
H = {"User-Agent": "Mozilla/5.0"}
try:
    r = requests.get("https://www.dhlottery.co.kr/lt645/selectPstLt645Info.do", timeout=45, headers=H)
    d = r.json()
    item = d["data"]["list"][0]
    out.append(f"[selectPstLt645Info] status={r.status_code} keys(data)={list(d['data'])}")
    out.append(json.dumps(item, ensure_ascii=False))
except Exception as e:  # noqa: BLE001
    out.append(f"[selectPstLt645Info] 실패 {e}")

for url in ("https://www.dhlottery.co.kr/store.do?method=topStore&pageGubun=L645",
            "https://www.dhlottery.co.kr/wnprchsplcsrch/home",
            "https://www.dhlottery.co.kr/lt645/result"):
    try:
        r = requests.get(url, timeout=45, headers=H, allow_redirects=True)
        t = r.text
        out.append(f"\n[{url}] status={r.status_code} final={r.url} len={len(t)}")
        for m in sorted(set(re.findall(r"[\"']((?:/[\w.-]+)+\.do[^\"'\s]*)[\"']", t)))[:60]:
            out.append("  do: " + m)
        for m in sorted(set(re.findall(r"[\"']((?:/[\w.-]+)+\.js)[\"']", t)))[:30]:
            out.append("  js: " + m)
    except Exception as e:  # noqa: BLE001
        out.append(f"[{url}] 실패 {e}")

open(sys.argv[1], "w", encoding="utf-8").write("\n".join(out) + "\n")
print("\n".join(out))
