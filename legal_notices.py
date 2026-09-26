"""회원 고지·약관 문구 (UI·운영 미리보기용). 서비스 로직 미포함."""

NOTICE_VERSION = "v1.1-draft"

# ── 간편인증 유도 ──
AUTH_PROMPT_TITLE = "간편인증"
AUTH_PROMPT_BODY = """
최초 간편인증 완료 시 적립금 500P를 지급해 드립니다.
적립금은 현금 환불·전환이 불가함을 확인해 주세요.
"""

AUTH_PRIVACY_PILLARS = [
    ("보관하지 않음", "실명 · 주소 · 연락처 · 카드/계좌"),
    ("최소 보관", "OAuth 식별자 · ledger · SMS 로그"),
    ("투명 운영", "목적 외 사용·몰래 수집 없음"),
]

AUTH_CONSENT_ITEMS = [
    "개인정보처리방침에 동의",
    "조합·통계는 참고용이며 당첨을 보장하지 않음",
    "만 19세 이상, 이용약관 동의 (부정가입 시 적립금 회수)",
]

# ── 적립금 요금 (차감: 조합시작/확인 시점) ──
# 2026-09-12 수정: 예전엔 이 값들을 wallet_db.py의 실제 차감 상수와 별개로
# 리터럴로 복붙해뒀다 — 화면 안내 문구(여기)와 실제 차감액(wallet_db.py)이
# 서로 다른 파일에 따로 적혀 있어, 가격을 바꿀 때 한쪽만 고치면 "안내는
# A원인데 실제로는 B원 차감"되는 사고로 이어질 수 있는 구조였다(wallet_db.py의
# 관련 상수 옆 경고 주석 참고). wallet_db.py 값을 그대로 가져와 써서 두 곳이
# 항상 같은 값을 보게 만든다 — 가격을 바꿀 땐 wallet_db.py만 고치면 된다.
from wallet_db import (
    ADVANCED_3MONTH_COST,
    ADVANCED_MONTHLY_COST,
    AUTO_COST_PER_UNIT,
    CHARGE_WON_AMOUNTS,
    HEDGE_COST_PER_COMBO,
    TAROT_EXTRA_DRAW_COST,
    THUNDER_COST_PER_GAME,
)

PRICING = {
    "thunder_per_game": THUNDER_COST_PER_GAME,
    "hedge_per_combo": HEDGE_COST_PER_COMBO,
    "auto_per_unit": AUTO_COST_PER_UNIT,
    "tarot_extra_draw": TAROT_EXTRA_DRAW_COST,
    "advanced_monthly": ADVANCED_MONTHLY_COST,
    "advanced_3month": ADVANCED_3MONTH_COST,
}

ADVANCED_FILTER_FIRST_SUB_FREE = True  # 첫 구독 1회 무료 (마케팅)

# ── 계정 삭제(회원 탈퇴) 안내 — 2026-09-27 ──
# Google Play "계정 삭제" 요구사항 대응: ① 앱 내 삭제 경로(내정보 → 회원 탈퇴)
# ② 앱 밖에서 열 수 있는 URL(app.py?page=delete_account, 비로그인 공개 페이지)
# ③ 그 URL을 Play Console Data safety에 신고(콘솔 작업, 코드 아님).
# **문구의 기준점은 여기** — 아래 삭제/보관 항목은 account_deletion.DELETED_ITEMS·
# RETAINED_ITEMS와 같은 내용이어야 한다(tests/test_account_deletion.py가 대조한다).
ACCOUNT_DELETION_TITLE = "회원 탈퇴 (계정 삭제)"
ACCOUNT_DELETION_DONE = "회원 탈퇴가 완료되었습니다. 개인정보가 파기되었습니다."
ACCOUNT_DELETION_BODY = """
**탈퇴하면 즉시 파기되는 항목**
- 로그인 식별자 (간편인증 provider + 식별자 해시)
- 기기 연결 (이전에 로그인한 기기와 계정의 자동 로그인 연결)
- 등록한 생일 슬롯
- 저장한 번호 조합·구매내역, 타로 뽑기 기록
- 주문에 남아있던 연락처, 결제 고객 식별키(카드 저장용)
- 작성한 개선 의견

**법령에 따라 남는 항목 (신원과 분리된 상태로 보관)**
- 적립금 충전·차감·지급 기록
- 결제 승인 기록
- 약관·동의 기록
- 탈퇴 계정 식별자 해시 (탈퇴 후 재가입 시 가입 적립금 중복 지급을 막기 위한 목적 —
  부정가입 방지. 계정·적립금·결제 내역과 연결되지 않습니다)
- 위 항목은 전자상거래법 제6조(계약·대금결제 기록 5년)에 따른 보관이며, 위 식별자가
  계정에서 파기되므로 개인을 특정할 수 없습니다.

**탈퇴 방법**
1. 앱에서: 메인 화면 우측 상단 **[내정보] → [회원 탈퇴]** → 내용 확인 후 실행 (즉시 처리)
2. 웹에서: 이 페이지(`?page=delete_account`)에서 안내를 확인하시거나,
   이메일(bandouni@naver.com)로 요청해 주세요. 이메일 요청은 접수 후 영업일 기준
   7일 이내 처리하며, 처리 결과는 요청하신 이메일로 안내드립니다.

탈퇴 후 같은 간편인증 계정으로 다시 가입할 수 있습니다(새 계정으로 처리되며, 이전
적립금·구독은 이어지지 않고 **가입 적립금도 다시 지급되지 않습니다**).
"""

# ── 조합생성/구매 완료 안내 (2026-09-11 사용자 지시) ──
# 자동구매·번개조합·안티액땜·타로 4화면에서 조합생성(또는 뽑기)이 끝나면
# 항상 "버튼 바로 밑"에 이 안내를 보여준다(wallet_ui.render_generation_complete_notice).
# 문구를 바꿀 땐 여기 한 곳만 고치면 4화면에 한 번에 반영된다.
GENERATION_COMPLETE_NOTICES = {
    "thunder": "✅ 조합생성이 완료되었습니다. 아래 저장내역에서 확인하실 수 있습니다.",
    "hedge": "✅ 조합생성이 완료되었습니다. 아래 저장내역에서 확인하실 수 있습니다.",
    "auto": "✅ 조합생성이 완료되었습니다. 아래 저장내역에서 확인하실 수 있습니다.",
    "tarot": "✅ 카드 뽑기가 완료되었습니다.",
}

# ── 유료 버튼 클릭 시 안내 멘트 템플릿 ──
def format_thunder_points_notice(game_count: int, balance: int | None = None) -> str:
    per = PRICING["thunder_per_game"]
    amount = per * max(1, game_count)
    lines = [
        f"**선택: {game_count}게임** → 필요 적립금 **{amount:,}P** (1게임당 {per}P)",
        "**※ 조합시작 시** 적립금이 차감됩니다.",
    ]
    if balance is not None:
        lines.append(f"현재 잔액: **{balance:,}P**")
    return "\n\n".join(lines)


def format_hedge_points_notice(combo_count: int, balance: int | None = None) -> str:
    per = PRICING["hedge_per_combo"]
    amount = per * max(1, combo_count)
    lines = [
        f"**선택: {combo_count}개 조합 생성** → 필요 적립금 **{amount:,}P** (1개당 {per}P)",
        "**※ 조합시작 시** 적립금이 차감됩니다.",
    ]
    if balance is not None:
        lines.append(f"현재 잔액: **{balance:,}P**")
    return "\n\n".join(lines)


def format_tarot_points_notice(balance: int | None = None) -> str:
    amount = PRICING["tarot_extra_draw"]
    lines = [
        "오늘 무료 뽑기 1회를 이미 사용하셨습니다.",
        f"**추가 뽑기** → 필요 적립금 **{amount:,}P**",
    ]
    if balance is not None:
        lines.append(f"현재 잔액: **{balance:,}P**")
    return "\n\n".join(lines)


def format_auto_points_notice(quantity: int, balance: int | None = None) -> str:
    per = PRICING["auto_per_unit"]
    amount = per * max(1, quantity)
    lines = [
        f"**선택: {quantity}개** → 필요 적립금 **{amount:,}P** (1개당 {per}P)",
        "**※ 조합시작 시** 적립금이 차감됩니다.",
        "본 서비스는 **현금 직접 결제를 지원하지 않습니다.** (적립금 충전 후 이용)",
    ]
    if balance is not None:
        lines.append(f"현재 잔액: **{balance:,}P**")
    return "\n\n".join(lines)


def format_advanced_points_notice(
    plan: str = "monthly",
    has_free_sub: bool = False,
    balance: int | None = None,
) -> str:
    lines = []
    if ADVANCED_FILTER_FIRST_SUB_FREE and has_free_sub:
        lines.append("**고급필터: 첫 구독 1회 무료** (마케팅) 혜택이 적용됩니다.")
    elif plan == "3month":
        lines.append(f"**고급필터 3개월 이용권: {PRICING['advanced_3month']:,}P**")
    else:
        lines.append(f"**고급필터 월간 이용: {PRICING['advanced_monthly']:,}P**")
    lines.append("**※ 결제 확정 시 즉시** 적립금이 차감되고 이용 기간이 시작됩니다.")
    if balance is not None:
        lines.append(f"현재 잔액: **{balance:,}P**")
    return "\n\n".join(lines)


# ── 탭별 고지 본문 (메인 하단 미리보기) ──
NOTICES = {
    "business": {
        "title": "사업자 정보",
        "body": """
- 상호(회사명): 로또신령
- 대표자: 이남수
- 사업자등록번호: 313-21-02253
- 통신판매업 신고번호: `[통신판매업 신고 완료 후 기재]`
- 사업장 주소: 경기도 안산시 단원구 원선1로 61, 109동 20층 2005호(원곡동, 경남아너스빌아파트)
- 고객센터 연락처 / 이메일: 010-7303-6365 / bandouni@naver.com

※ 전자상거래 등에서의 소비자보호에 관한 법률에 따라, 통신판매업 신고번호는 신고가
완료되는 즉시 실제 값으로 채워 정식 게시해야 합니다. 이 항목이 비어 있는 상태로는
정식 결제(PG) 연동을 시작할 수 없습니다.
        """,
    },
    "terms": {
        "title": "이용약관 (요약)",
        "body": """
1. 로또신령은 번호 조합·필터·통계 **참고 서비스**이며 당첨을 보장하지 않습니다.
2. 결제는 **적립금**으로만 이루어지며, **현금 환불·전환 불가**합니다.
3. **조합시작(구매확정) 시** 요금표에 따라 적립금이 차감되며, 조합 생성에 실패하거나 0건이면 차감된 적립금이 **즉시 재적립**됩니다.
4. 고급필터 **첫 구독 1회 무료** 후 월 1,200P(3개월 3,000P) 등 정책이 적용됩니다.
5. **만 19세 미만은 이용할 수 없습니다.** (본인인증 단계에서 확인)
6. **청약철회 관련**: 적립금은 충전 후 실제 서비스(추출·SMS 등) 이용 전까지는 전자상거래법에
   따라 철회를 요청할 수 있습니다. 단, 결과 생성 등 디지털 콘텐츠 제공이 **이미 시작된 부분**은
   법령이 정한 예외(사전 고지 및 이용자 동의)에 따라 철회가 제한됩니다.
7. **부정가입 방지**: 동일인이 여러 계정으로 가입해 가입 적립금을 중복 수령한 사실이 확인되면,
   회사는 사전 통지 후 해당 적립금을 회수하거나 계정 이용을 제한할 수 있습니다.
8. **탈퇴 후 재가입**: 탈퇴한 계정과 같은 간편인증 계정으로 다시 가입하는 경우, 가입 적립금은
   다시 지급되지 않습니다.
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

**문의 및 탈퇴·삭제 요청:**
- 앱 내 즉시 처리: 메인 화면 우측 상단 **[내정보] → [회원 탈퇴]** (2026-09-27 추가 —
  로그인 식별자·기기 연결·생일·구매내역·연락처가 즉시 파기됩니다)
- 이메일: bandouni@naver.com
- 회원 탈퇴, 보관 중인 개인정보(위 최소 보관 항목)의 열람·삭제를 원하시면 위 경로로 요청해 주세요.
- 접수 후 영업일 기준 7일 이내 처리하며, 처리 결과는 요청하신 이메일로 안내드립니다.
        """,
    },
    "points": {
        "title": "적립금·환불정책",
        "body": """
- 최초 간편인증: **500P 1회** 지급
- **현금 환불 불가**
- 번개조합: **1게임당 10P**, 안티/액땜조합: **1개당 10P**, 자동조합: **1개당 10P**, 타로점: 1일 1회 무료 후 **추가 1회당 50P**
- 고급필터: **첫 구독 1회 무료**, 이후 월 **1,200P** (3개월권 **3,000P**)
- 차감 시점: **조합시작(구매확정) 시**. 조합 생성에 실패하거나 0건이면 차감된 적립금이 **즉시 재적립**됩니다.
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


# ── PG(토스페이먼츠) 계약 심사 제출용 공개 페이지 — 2026-09-18 ──
# 결제 상품/환불정책/사업자정보를 비로그인으로 볼 수 있는 URL이 필요해서 추가.
# (사업자정보 문구는 위 NOTICES["business"]와 같은 값을 씀 — 두 군데 따로 안 두고
#  하나만 고치면 되게.)
def _format_charge_amounts() -> str:
    return " / ".join(f"{amt:,}원" for amt in CHARGE_WON_AMOUNTS)


PG_PRODUCT_INFO = f"""
로또신령은 **적립금(포인트) 충전** 방식으로 결제하며, 충전한 적립금으로
아래 기능들을 이용합니다.

**적립금 충전 금액**: {_format_charge_amounts()} (10원당 1P 지급)

**적립금 사용처**
- 번개조합: 1게임당 {PRICING['thunder_per_game']}P
- 안티/액땜조합: 1개당 {PRICING['hedge_per_combo']}P
- 자동조합: 1개당 {PRICING['auto_per_unit']}P
- 타로점: 1일 1회 무료 후 추가 1회당 {PRICING['tarot_extra_draw']}P
- 고급필터 정기구독: 월 {PRICING['advanced_monthly']:,}P (3개월권 {PRICING['advanced_3month']:,}P, 첫 구독 1회 무료)

결제·서비스 제공은 **결제 즉시(당일) 개시**되며, 별도 배송이 없는 디지털
서비스입니다.
"""

PG_REFUND_POLICY = """
**환불정책**

1. 결제로 충전한 적립금 중 **미사용 잔액**은 전액 환불 요청이 가능합니다.
2. 이미 서비스(번호조합 생성, 통계조회 등)에 사용된 적립금은 전자상거래법상
   디지털 콘텐츠 제공이 개시된 것으로 보아 환불 대상에서 제외됩니다.
3. 환불 요청은 이메일(bandouni@naver.com)로 접수하며, 접수 후 영업일 기준
   3영업일 이내 결제수단으로 환불 처리합니다.
4. 서비스 오류로 조합 생성이 실패하거나 0건인 경우, 차감된 적립금은
   **즉시 재적립**됩니다(현금 환불이 아닌 적립금 복원).
5. 고급필터 정기구독은 결제 즉시 서비스가 개시되며, 이용 개시 후에는
   잔여 기간에 대한 환불이 제한될 수 있습니다. 단, 결제 후 7일 이내이며
   서비스를 전혀 이용하지 않은 경우 전액 환불합니다.
"""


def render_notice_preview():
    """Streamlit: 메인 하단 운영자용 고지 미리보기 (st 없이 markdown 문자열만 반환 가능)."""
    import streamlit as st

    st.caption(f"고지 문서 버전: {NOTICE_VERSION} · 상세: docs/legal/MEMBER_NOTICES.md")
    _tab_keys = ("business", "terms", "privacy", "points", "disclaimer", "auth")
    tabs = st.tabs([NOTICES[k]["title"] for k in _tab_keys])
    for tab, key in zip(tabs, _tab_keys):
        with tab:
            st.markdown(NOTICES[key]["body"])
