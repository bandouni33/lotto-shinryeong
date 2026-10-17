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


def active_channels() -> list[dict]:
    return [c for c in CHANNELS if c["active"]]


def links_html() -> str:
    """앱 메인 하단 '공식 채널' 한 줄(새 창으로 열림)."""
    chips = "".join(
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
