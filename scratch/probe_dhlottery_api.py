# -*- coding: utf-8 -*-
"""동행복권 데이터 소스 접근성 진단 (읽기 전용 GET만 한다).

배경: excelt 자동 업데이트 스크립트 두 개(weekly_lotto_file_update.py,
candidate_tracker_auto_update.py)는
    https://www.dhlottery.co.kr/common.do?method=getLottoNumber&drwNo=NNNN
를 쓰는데, 2026-09-15 로그에 이 응답이 JSON이 아니라 HTML로 와서 실패한 기록이 있다.
반면 앱의 DB 동기화(draw_results_db.fetch_latest_from_dhlottery)는 다른 주소
    https://www.dhlottery.co.kr/lt645/selectPstLt645Info.do
를 쓰고 있고, 2026-09-26(토) 1243회차는 실제로 DB에 들어와 있다.

이 스크립트는 두 주소에 여러 헤더 조합으로 요청해 어느 쪽이 실제로 살아있는지 본다.
"""

from __future__ import annotations

import json
import urllib.request

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

COMMON = "https://www.dhlottery.co.kr/common.do?method=getLottoNumber&drwNo={r}"
LATEST = "https://www.dhlottery.co.kr/lt645/selectPstLt645Info.do"

HEADER_SETS = {
    "헤더없음(=weekly_lotto_file_update.py와 동일)": {},
    "브라우저UA만(=candidate_tracker_auto_update.py 수정본)": {"User-Agent": BROWSER_UA},
    "브라우저UA+Referer+Accept-Language": {
        "User-Agent": BROWSER_UA,
        "Referer": "https://www.dhlottery.co.kr/gameResult.do?method=byWin",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
    },
}


def probe(url: str, headers: dict) -> str:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status = resp.status
            ctype = resp.headers.get("Content-Type", "?")
    except Exception as e:
        return f"요청 실패: {type(e).__name__}: {e}"
    try:
        data = json.loads(body)
    except Exception:
        first = body.strip().splitlines()[:1]
        return (f"status={status} ctype={ctype} → JSON 아님 (첫 줄: "
                f"{first[0][:90] if first else ''!r} / 길이 {len(body)}B)")
    if isinstance(data, dict) and "data" in data and isinstance(data["data"], dict):
        lst = data["data"].get("list") or []
        if lst:
            item = lst[0]
            return (f"status={status} ctype={ctype} → JSON OK, 최신회차={item.get('ltEpsd')} "
                    f"번호={[item.get(f'tm{i}WnNo') for i in range(1, 7)]} 보너스={item.get('bnsWnNo')}")
        return f"status={status} ctype={ctype} → JSON OK(list 비어있음): {str(data)[:120]}"
    return f"status={status} ctype={ctype} → JSON OK: {str(data)[:160]}"


def main() -> None:
    for r in (1243, 1244):
        print(f"\n=== common.do?method=getLottoNumber&drwNo={r} ===")
        for label, headers in HEADER_SETS.items():
            print(f"  {label}\n      → {probe(COMMON.format(r=r), headers)}")

    print(f"\n=== selectPstLt645Info.do (반드시 '최신 회차'를 돌려준다) ===")
    for label, headers in HEADER_SETS.items():
        print(f"  {label}\n      → {probe(LATEST, headers)}")


if __name__ == "__main__":
    main()
