"""회원 고지·약관 문구 (UI·운영 미리보기용). 서비스 로직 미포함."""

NOTICE_VERSION = "v1.1-draft"

# ── 간편인증 유도 ──
AUTH_PROMPT_TITLE = "간편인증"
AUTH_PROMPT_SUBTITLE = "안전한 간편인증으로 로또신령을 시작하세요"
AUTH_PROMPT_BODY = """
최초 간편인증 완료 시 적립금 5,000P를 지급해 드립니다.
적립금은 현금 환불·전환이 불가함을 확인해 주세요.
"""

AUTH_PRIVACY_PILLARS = [
    ("보관하지 않음", "실명 · 주소 · 연락처 · 카드/계좌"),
    ("최소 보관", "OAuth 식별자 · ledger · SMS 로그"),
    ("투명 운영", "목적 외 사용·몰래 수집 없음"),
]

AUTH_CONSENT_ITEMS = [
    "적립금 5,000P 지급 및 환불 불가에 동의합니다.",
    "최소 보관 항목(OAuth·ledger·SMS) 및 개인정보 처리방침을 확인했습니다.",
    "로또 조합·통계가 당첨을 보장하지 않음을 확인했습니다.",
    "만 19세 이상이며, 이용약관(부정가입 확인 시 적립금 회수 포함)에 동의합니다.",
]

# ── 적립금 요금 (차감: 결과 생성 성공 후) ──
PRICING = {
    "thunder_per_5": 1000,
    "thunder_per_10": 2000,
    "auto_per_5": 1000,
    "auto_per_10": 2000,
    "auto_per_15": 3000,
    "auto_per_20": 4000,
    "advanced_monthly": 15000,
}

ADVANCED_FILTER_FIRST_SUB_FREE = True  # 첫 구독 1회 무료 (마케팅)

# ── 유료 버튼 클릭 시 안내 멘트 템플릿 ──
def format_thunder_points_notice(game_count: int, balance: int | None = None) -> str:
    amount = (game_count // 5) * 1000 if game_count >= 5 else 1000
    if game_count % 5 != 0:
        amount = ((game_count + 4) // 5) * 1000
    lines = [
        f"**선택: {game_count}게임** → 필요 적립금 **{amount:,}P** (5게임당 1,000P)",
        "**※ 조합 결과가 표시된 후** 적립금이 차감됩니다.",
    ]
    if balance is not None:
        lines.append(f"현재 잔액: **{balance:,}P**")
    return "\n\n".join(lines)


def format_auto_points_notice(quantity: int, balance: int | None = None) -> str:
    table = {5: 1000, 10: 2000, 15: 3000, 20: 4000}
    amount = table.get(quantity, (quantity // 5) * 1000)
    lines = [
        f"**선택: {quantity}개** → 필요 적립금 **{amount:,}P**",
        "**※ 추출·발송 처리 완료(결과 생성) 후** 적립금이 차감됩니다.",
        "본 서비스는 **현금 직접 결제를 지원하지 않습니다.** (적립금 충전 후 이용)",
    ]
    if balance is not None:
        lines.append(f"현재 잔액: **{balance:,}P**")
    return "\n\n".join(lines)


def format_advanced_points_notice(has_free_sub: bool = False, balance: int | None = None) -> str:
    lines = []
    if ADVANCED_FILTER_FIRST_SUB_FREE and has_free_sub:
        lines.append("**고급필터: 첫 구독 1회 무료** (마케팅) 혜택이 적용됩니다.")
    else:
        lines.append(f"**고급필터 월간 이용: {PRICING['advanced_monthly']:,}P**")
    lines.append("**※ 최종 조합 산출 성공 후** (또는 구독 갱신 시) 적립금이 차감됩니다.")
    if balance is not None:
        lines.append(f"현재 잔액: **{balance:,}P**")
    return "\n\n".join(lines)


# ── 탭별 고지 본문 (메인 하단 미리보기) ──
NOTICES = {
    "business": {
        "title": "사업자 정보",
        "body": """
- 상호(회사명): `[사업자등록 완료 후 기재]`
- 대표자: `[사업자등록 완료 후 기재]`
- 사업자등록번호: `[사업자등록 완료 후 기재]`
- 통신판매업 신고번호: `[통신판매업 신고 완료 후 기재]`
- 사업장 주소: `[사업자등록 완료 후 기재]`
- 고객센터 연락처 / 이메일: `[기재 예정]`

※ 전자상거래 등에서의 소비자보호에 관한 법률에 따라, 위 정보는 사업자등록·통신판매업
신고가 완료되는 즉시 실제 값으로 채워 정식 게시해야 합니다. 이 항목이 비어 있는 상태로는
정식 결제(PG) 연동을 시작할 수 없습니다.
        """,
    },
    "terms": {
        "title": "이용약관 (요약)",
        "body": """
1. 로또신령은 번호 조합·필터·통계 **참고 서비스**이며 당첨을 보장하지 않습니다.
2. 결제는 **적립금**으로만 이루어지며, **현금 환불·전환 불가**합니다.
3. 조합·추출 **결과 생성 성공 후** 요금표에 따라 적립금이 차감됩니다.
4. 고급필터 **첫 구독 1회 무료** 후 월 15,000P 등 정책이 적용됩니다.
5. **만 19세 미만은 이용할 수 없습니다.** (본인인증 단계에서 확인)
6. **청약철회 관련**: 적립금은 충전 후 실제 서비스(추출·SMS 등) 이용 전까지는 전자상거래법에
   따라 철회를 요청할 수 있습니다. 단, 결과 생성 등 디지털 콘텐츠 제공이 **이미 시작된 부분**은
   법령이 정한 예외(사전 고지 및 이용자 동의)에 따라 철회가 제한됩니다.
7. **부정가입 방지**: 동일인이 여러 계정으로 가입해 가입 적립금을 중복 수령한 사실이 확인되면,
   회사는 사전 통지 후 해당 적립금을 회수하거나 계정 이용을 제한할 수 있습니다.
        """,
    },
    "privacy": {
        "title": "개인정보 처리방침 (요약)",
        "body": """
**보관하지 않음:** 실명, 주소, 연락처, 카드·계좌 등 결제정보, OAuth 프로필(닉네임·이메일 등).

**최소 보관 (투명·목적 외 사용·몰래 보관 없음):**
- OAuth provider + 식별자(해시) — 로그인·중복가입 방지  
- 적립금 ledger — 충전·차감·보너스 증빙  
- SMS 발송 로그 — 발송 증빙  
- 약관·동의 기록 — 법적 증빙  

위탁: 카카오, PASS, 금융인증, PG, SMS 대행 — 위탁 목록은 정식 약관에 기재.
        """,
    },
    "points": {
        "title": "적립금·환불정책",
        "body": """
- 최초 간편인증: **5,000P 1회** 지급
- **현금 환불 불가**
- 번개/자동: 5단위 **1,000P**, 10단위 **2,000P** …
- 고급필터: **첫 구독 1회 무료**, 이후 월 **15,000P**
- 차감 시점: **결과 생성 성공 후** (실패·0건 시 미차감)
- **유효기간**: 지급일로부터 **1년**. 만료 7일 전 앱 내 알림으로 별도 안내합니다.
- **부정 취득 회수**: 중복가입·어뷰징 등으로 부정하게 지급받은 적립금은 사전 통지 후 회수될 수 있습니다.
        """,
    },
    "disclaimer": {
        "title": "당첨·통계 면책",
        "body": """
본 통계·조합은 과거 데이터 집계·규칙 필터 결과이며,  
로또는 **완전 무작위 추첨**으로 **다음 회차 당첨을 보장하지 않습니다.**
        """,
    },
    "auth": {
        "title": "간편인증·가입 혜택",
        "body": AUTH_PROMPT_BODY,
    },
}


def render_notice_preview():
    """Streamlit: 메인 하단 운영자용 고지 미리보기 (st 없이 markdown 문자열만 반환 가능)."""
    import streamlit as st

    st.caption(f"고지 문서 버전: {NOTICE_VERSION} · 상세: docs/legal/MEMBER_NOTICES.md")
    _tab_keys = ("business", "terms", "privacy", "points", "disclaimer", "auth")
    tabs = st.tabs([NOTICES[k]["title"] for k in _tab_keys])
    for tab, key in zip(tabs, _tab_keys):
        with tab:
            st.markdown(NOTICES[key]["body"])
