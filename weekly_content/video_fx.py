# -*- coding: utf-8 -*-
"""SNS 영상 연출 공통(목요일·토요일이 같은 방식 — 2026-10-24 사용자 지시 "토요일도 목요일 진행 건처럼 방식 똑같게").

약 1분 · 장 넘김 '슥' 소리 · PPT 같은 넘김 효과 · 장마다 다른 음악(비트) · 장마다 살짝 줌 · 빛줄기.
매주 회차(week)로 ① 넘김 효과 ② 장별 음악 장르 ③ 줌 방향이 돌아가며 바뀐다(같은 회차 = 항상 같은 연출).
offset 으로 같은 주의 목요일·토요일 연출이 서로 다르게 시작한다. 실제 그리기는 run_weekly.make_shorts(plan=...).
"""
from __future__ import annotations

VIDEO_SEC = 60.0
XF = 1.2
# PPT 느낌 넘김 효과(ffmpeg xfade) — 한 영상 안에서는 서로 다른 것만
TRANSITIONS = ["circleopen",   # 중앙에서 둥글게 열리며 등장
               "fadewhite",    # 빛이 번쩍하며 넘어감(+'반짝' 소리)
               "smoothup",     # 아래에서 떠오름
               "zoomin",       # 확 다가오며 전환
               "radial",       # 시계 방향으로 쓸어 넘김
               "horzopen",     # 가운데에서 위아래로 펼쳐짐
               "coverup",      # 다음 장이 아래에서 날아 들어와 덮음
               "dissolve"]     # 반짝이는 입자로 스며듦
LIGHT = {"fadewhite"}
# 이웃한 장끼리 장조↔단조·느림↔빠름이 엇갈리는 순서(bgm.STYLES). 매주 시작점만 돈다.
MUSIC_ORDER = ["dreamy", "bright", "chill", "epic", "funky"]
MOTIONS = ["in", "in_top", "out"]   # 살짝 줌인 / 글자 쪽으로 줌인 / 살짝 줌아웃


def plan(weights: list[float], week: int, offset: int = 0, total_sec: float = VIDEO_SEC) -> dict:
    """weights = 장별 상대 길이(글자 수 등) → 넘김 겹침을 뺀 전체가 total_sec 이 되게 나눈다."""
    n = len(weights)
    w = (week + offset) % 1000
    scale = (total_sec + XF * (n - 1)) / sum(weights)
    secs = [round(x * scale, 2) for x in weights]
    trans = [TRANSITIONS[(w * 3 + i) % len(TRANSITIONS)] for i in range(n - 1)]
    styles = [MUSIC_ORDER[(w + i) % len(MUSIC_ORDER)] for i in range(n)]
    motions = [MOTIONS[(w + i) % len(MOTIONS)] for i in range(n)]
    return {"secs": secs, "xf": XF, "trans": trans, "styles": styles, "motions": motions, "light": sorted(LIGHT)}
