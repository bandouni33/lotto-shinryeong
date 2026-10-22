# -*- coding: utf-8 -*-
"""로또신령 공식 채널 주소 — 앱 '공식 채널' 줄과 주간 리포트 카드가 같이 쓰는 단일 기준점(2026-10-17).

active=False 인 채널은 앱에서 숨긴다(카드에는 이름만 나오므로 그대로 둔다).
인스타는 10-17 검토 해제 → True.
"""
from __future__ import annotations

HANDLE = "@lottoshinryeong"

CHANNELS = [
    {"key": "blog", "name": "블로그", "url": "https://blog.naver.com/bandouni", "color": "#03c75a", "active": True},
    {"key": "facebook", "name": "페이스북", "url": "https://www.facebook.com/1447656485087383",
     "color": "#1877f2", "active": True},
    {"key": "instagram", "name": "인스타", "url": "https://www.instagram.com/lottoshinryeong",
     "color": "#d6249f", "active": True},
    {"key": "threads", "name": "스레드", "url": "https://www.threads.net/@lottoshinryeong", "color": "#9aa0b4",
     "active": True},
    {"key": "youtube", "name": "유튜브", "url": "https://www.youtube.com/@lottoshinryeong", "color": "#ff0033",
     "active": False},  # 2026-10-17 사용자 결정: 유튜브 중단(앱·카드에서 숨김)
]


SITE_URL = "https://lottoshinryeong.com"   # 홈페이지(2026-10-18 공개, 저장소 bandouni33/bandouni33.github.io · 10-21 자체 도메인)


def round_url(rnd: int) -> str:
    """홈페이지 회차 페이지 주소 — 게시 문구가 이 함수만 쓴다(사이트 build.py 의 /round/<회차>/ 와 같은 규칙)."""
    return f"{SITE_URL}/round/{int(rnd)}/"


PLAY_URL = "https://play.google.com/store/apps/details?id=com.bandouni.lottoshinryeong"
MANUAL_URL = "https://blog.naver.com/bandouni/224444112459"   # 사용설명서 글

# 네이버 블로그 사용설명 8편(2026-10-16 사용자 발행) — 홈페이지 사이드바 '사용설명서' 목록의 단일 기준점
MANUAL_POSTS = [
    ("설치·로그인·첫 가입 500P", MANUAL_URL),
    ("자동조합", "https://blog.naver.com/bandouni/224444125686"),
    ("번개조합", "https://blog.naver.com/bandouni/224444138835"),
    ("번호검증", "https://blog.naver.com/bandouni/224444193876"),
    ("고급필터", "https://blog.naver.com/bandouni/224444208405"),
    ("통계센터", "https://blog.naver.com/bandouni/224444212584"),
    ("타로", "https://blog.naver.com/bandouni/224444220906"),
    ("자주 묻는 질문", "https://blog.naver.com/bandouni/224444223272"),
]


def store_link(source: str, medium: str = "social", campaign: str = "weekly") -> str:
    """채널별 유입을 구분하는 구글 플레이 설치 링크(2026-10-18 승인 1번).
    Play 콘솔 '획득 보고서'에서 utm_source 별로 설치 수가 보인다."""
    from urllib.parse import quote

    ref = f"utm_source={source}&utm_medium={medium}&utm_campaign={campaign}"
    return f"{PLAY_URL}&referrer={quote(ref, safe='')}"


def active_channels() -> list[dict]:
    return [c for c in CHANNELS if c["active"]]


def links_html() -> str:
    """앱 메인 하단 '공식 채널' 한 줄(새 창으로 열림)."""
    # 2026-10-22(사용자 지시): 맨 앞에 '홈페이지' 칩(자체 도메인). 카드용 CHANNELS 목록에는 넣지 않는다.
    home = (f'<a class="sns-chip" href="{SITE_URL}/" target="_blank" rel="noopener noreferrer">'
            '<span class="sns-dot" style="background:#e8c770"></span>홈페이지</a>')
    chips = home + "".join(
        f'<a class="sns-chip" href="{c["url"]}" target="_blank" rel="noopener noreferrer">'
        f'<span class="sns-dot" style="background:{c["color"]}"></span>{c["name"]}</a>'
        for c in active_channels())
    return (
        '<style>'
        '.sns-row{display:flex;flex-wrap:nowrap;gap:4px;align-items:center;margin:6px 0 10px;overflow-x:auto}'
        '.sns-row .sns-title{color:#b8c2d6;font-size:12px;font-weight:700;margin-right:2px;white-space:nowrap}'
        '.sns-chip{display:inline-flex;align-items:center;gap:4px;padding:4px 7px;border-radius:999px;'
        'background:linear-gradient(145deg,#243052 0%,#1a2238 42%,#12182b 100%);'
        'border:1px solid rgba(120,100,170,.35);color:#e6e9f2 !important;font-size:11.5px;'
        'text-decoration:none !important;white-space:nowrap}'
        '.sns-dot{width:7px;height:7px;border-radius:50%;display:inline-block}'
        '</style>'
        f'<div class="sns-row"><span class="sns-title">공식 채널</span>{chips}</div>')
