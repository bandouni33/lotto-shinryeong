# -*- coding: utf-8 -*-
"""신령엔터 45인조 — 번호 1~45를 '멤버'로 보는 주간 연재(2026-10-18 사용자 승인: 채널별 특색·신박하게).

공식 당첨번호(보너스 제외)만으로 계산한다 — 예측·추천이 아니라 '지난 기록의 이야기'.
홈페이지(site_export → data.json), 게시 문구(cards·pre_draw), 스레드 문답이 모두 이 파일 하나만 쓴다.

상태(이번 회차 기준, 우선순위 순):
  컴백        이번 회차에 나왔고, 그 직전 공백이 COMEBACK_GAP 회 이상
  연속 활동   이번 회차 포함 2회 이상 연속 출현
  이번 주 무대 이번 회차에 나옴
  공백기      HIATUS_GAP 회 이상 안 나옴
  대기 중     그 밖
포지션(최근 50회 출현 순위): 센터 1~5 · 메인 6~15 · 서브 16~30 · 히든 31~45
"""
from __future__ import annotations

from collections import Counter

COMEBACK_GAP = 10
HIATUS_GAP = 10
WINDOW = 50
FIRST_QUESTION_ROUND = 1247   # 스레드 목요일 문답을 처음 올리는 회차 — 이전 회차엔 '결과' 문구를 붙이지 않는다
POSITIONS = ((5, "센터"), (15, "메인"), (30, "서브"), (45, "히든"))


def _rounds(draws: dict[int, dict], upto: int) -> list[int]:
    return [r for r in sorted(draws) if r <= upto]


def members(draws: dict[int, dict], upto: int) -> list[dict]:
    """번호별 기록 — draws: {회차: {"nums": [...]}}"""
    rs = _rounds(draws, upto)
    seen: dict[int, list[int]] = {n: [] for n in range(1, 46)}
    pair = Counter()
    for r in rs:
        nums = sorted(draws[r]["nums"])
        for n in nums:
            seen[n].append(r)
        for i, a in enumerate(nums):
            for b in nums[i + 1:]:
                pair[(a, b)] += 1
    recent = {n: sum(1 for r in seen[n] if r > upto - WINDOW) for n in range(1, 46)}
    order = sorted(range(1, 46), key=lambda n: (-recent[n], n))
    rank = {n: i + 1 for i, n in enumerate(order)}
    out = []
    for n in range(1, 46):
        apps = seen[n]
        last = apps[-1] if apps else 0
        gap = upto - last
        gaps = [b - a for a, b in zip([0] + apps, apps)] + [gap]
        prev_gap = (apps[-1] - apps[-2]) if len(apps) >= 2 and last == upto else None
        streak = 0
        r = upto
        while r in draws and n in draws[r]["nums"]:
            streak += 1
            r -= 1
        if last == upto and prev_gap is not None and prev_gap >= COMEBACK_GAP:
            status = "컴백"
        elif streak >= 2:
            status = "연속 활동"
        elif last == upto:
            status = "이번 주 무대"
        elif gap >= HIATUS_GAP:
            status = "공백기"
        else:
            status = "대기 중"
        buddies = sorted(((c, b if a == n else a) for (a, b), c in pair.items() if n in (a, b)), key=lambda x: (-x[0], x[1]))
        pos = next(name for lim, name in POSITIONS if rank[n] <= lim)
        out.append({
            "n": n, "status": status, "position": pos, "rank": rank[n], "recent": recent[n], "total": len(apps),
            "gap": gap, "max_gap": max(gaps), "streak": streak, "prev_gap": prev_gap,
            "buddy": {"n": buddies[0][1], "count": buddies[0][0]} if buddies else None,
            "last5": apps[-5:][::-1],
            "strip": [1 if n in draws[r]["nums"] else 0 for r in range(max(1, upto - 29), upto + 1) if r in draws],
        })
    return out


def headline(draws: dict[int, dict], upto: int, ms: list[dict] | None = None) -> dict:
    """이번 주 소식 — 컴백 멤버·최장 공백·연속 활동·센터 라인업."""
    ms = ms or members(draws, upto)
    comeback = sorted((m for m in ms if m["status"] == "컴백"), key=lambda m: -m["prev_gap"])
    streak = sorted((m for m in ms if m["status"] == "연속 활동"), key=lambda m: (-m["streak"], m["n"]))
    hiatus = sorted((m for m in ms if m["gap"] > 0), key=lambda m: (-m["gap"], m["n"]))[:6]
    center = sorted((m for m in ms if m["position"] == "센터"), key=lambda m: m["rank"])
    if comeback:
        top = comeback[0]
        title = f"{top['n']}번 멤버, {top['prev_gap']}회 만에 컴백"
    elif streak:
        top = streak[0]
        title = f"{top['n']}번 멤버, {top['streak']}주 연속 무대"
    else:
        top = hiatus[0]
        title = f"{top['n']}번 멤버, {top['gap']}주째 공백기"
    return {"round": upto, "title": title, "star": top["n"],
            "comeback": [{"n": m["n"], "gap": m["prev_gap"]} for m in comeback],
            "streak": [{"n": m["n"], "weeks": m["streak"]} for m in streak],
            "hiatus": [{"n": m["n"], "gap": m["gap"]} for m in hiatus],
            "center": [m["n"] for m in center]}


def question(draws: dict[int, dict], upto: int) -> dict:
    """목요일 스레드 문답 — '이번 주 컴백할 멤버는?' 후보 = 공백기 상위 6명(재미용, 예측 아님)."""
    h = headline(draws, upto)
    return {"round": upto + 1, "candidates": [x["n"] for x in h["hiatus"]]}


def answer(draws: dict[int, dict], rnd: int) -> dict:
    """토요일 결과 — 목요일 후보(rnd-1 기준 공백기 상위 6) 중 rnd 회차에 나온 멤버."""
    q = question(draws, rnd - 1)
    hit = [n for n in q["candidates"] if n in draws.get(rnd, {}).get("nums", [])]
    return {"round": rnd, "candidates": q["candidates"], "hit": hit}
