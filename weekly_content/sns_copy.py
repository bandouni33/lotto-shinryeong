# -*- coding: utf-8 -*-
"""SNS 게시 문구 공통 부품 — 목(타로)·금(번호 흐름)·토(주간 리포트·추첨결과) 게시가 모두 이 한 곳을 쓴다.

2026-10-22 사용자 지시:
  · "호기심을 끌 만한 심리 활용·감성 이용 등 재료를 더 고민" → 첫 줄 훅·참여 질문은 각 게시 모듈이 만들고,
    링크·해시태그·고지 문구(어느 게시에나 같아야 하는 것)는 여기서만 만든다.
  · "홈페이지에 모든 게 있으니 활용을 높이고" → 링크는 홈페이지(lottoshinryeong.com) 하나로 모은다.
    앱 설치·사용설명서·당첨번호·통계·실수령액·판매시간이 모두 홈페이지에 있다(설치 버튼도 홈페이지 맨 위).
  · "검색 키워드도 고민해서 재정비" → 해시태그를 네이버 검색량 상위 키워드(2026-10 사용자 제공 표)로 맞춘다.

채널별 규칙(노출을 깎는 요소를 빼는 방향):
  · 페이스북: 본문 링크는 1개만(외부 링크가 많으면 노출이 줄어든다).
  · 인스타그램: 본문 링크는 눌리지 않는다 → 주소 대신 '프로필 링크' 안내. 해시태그는 10~15개.
  · 스레드: 500자 제한, 해시태그 1개만 붙는 플랫폼.
SNS 자동화는 '게시'만 한다(친구 신청·팔로우·좋아요·댓글 등 다른 동작 금지 — 2026-10-22 사용자 지시).
"""
from __future__ import annotations

# 네이버 키워드 도구 월간 검색수(모바일, 2026-10 사용자 제공) 상위 — 띄어쓰기 없는 해시태그 형태.
KW_DRAW = ["로또당첨번호", "로또복권당첨번호", "복권당첨번호", "나눔로또당첨번호", "로또1등당첨번호", "LOTTO당첨번호"]
KW_PRIZE = ["로또당첨금", "로또1등당첨금", "로또1등", "로또명당"]
KW_TIME = ["로또판매시간"]
KW_STATS = ["로또번호", "로또통계", "로또번호추천"]
KW_TAROT = ["타로", "오늘의타로", "주간운세", "타로운세"]



def site(path: str = "/") -> str:
    import social_links
    return social_links.SITE_URL + path


def hashtags(rnd: int | None, *groups: list[str], channel: str) -> str:
    """채널별 해시태그 한 줄. 인스타 15개까지, 페이스북 5개까지, 스레드는 1개."""
    if channel == "threads":
        return "#로또"
    tags = ["로또"] + ([f"로또{rnd}회"] if rnd else [])   # rnd 없음 = 회차와 무관한 게시(홍보 영상 등)
    for g in groups:
        for t in g:
            if t not in tags:
                tags.append(t)
    tags.append("로또신령")
    limit = 15 if channel == "instagram" else 5
    if len(tags) > limit:
        tags = tags[: limit - 1] + ["로또신령"]
    return " ".join("#" + t for t in tags)


def footer(channel: str, path: str = "/", what: str = "") -> str:
    """링크·안내 — 홈페이지 한 곳으로 모은다. 2026-10-24(사용자 지시): 모든 게시물에 참고사항(고지 문구)을 넣지 않는다. what = 그 링크에서 볼 수 있는 것(예: '번호 통계')."""
    if channel == "instagram":
        link = "🔗 프로필 링크 → 로또신령 홈페이지" + (f"에서 {what}" if what else "")
    elif channel == "threads":
        return f"🔗 {site(path)}"
    else:
        link = f"🔗 {what + ': ' if what else ''}{site(path)}"
    return (f"{link}\n"
            "당첨번호·번호 통계·실수령액 계산·판매시간, 앱 설치·사용설명서까지 홈페이지에 다 있어요.\n"
            "첫 가입 500P로 번호 조합 무료 체험 — 구글 플레이·앱스토어 '로또신령'")


def net_prize(won: int) -> int:
    """당첨금 실수령액(홈페이지 /tools/prize/ 계산기와 같은 식): 200만원 이하 비과세,
    초과 시 (당첨금-1,000원) 중 3억까지 22%, 3억 초과분 33%."""
    won = max(0, int(won))
    if won <= 2_000_000:
        return won
    b = won - 1000
    tax = int(min(b, 300_000_000) * 0.22 + max(0, b - 300_000_000) * 0.33)
    return won - tax
