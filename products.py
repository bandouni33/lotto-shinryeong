"""상품(포인트 충전·구독)·가격·기간의 **단일 기준점** (2026-09-26).

왜 필요한가: 같은 상품 정보(상품 ID·지급 포인트·금액·구독 기간·표시 가격)가
`wallet_db.py`(WON_PER_POINT·CHARGE_WON_AMOUNTS·구독 기간), `google_play_pg.py`
(POINTS_PRODUCTS·SUBSCRIPTION_BASE_PLAN_DAYS), `wallet_ui.py`(IAP_*), `legal_notices.py`
(PRICING), `LottoShinryeong/components/streamlit-webview.tsx`(SKU·파라미터)에 나뉘어
있었다 — 가격 하나 바꾸려면 두 언어 5개 파일을 손대야 했고, 한 곳만 고치면 화면에
옛 금액이 남는다.

규칙 — `tests/test_products_definition.py`가 강제한다
  1. 상품 ID·포인트·일수·금액은 이 파일에만 있다. 다른 파일은 여기서 파생시켜 쓴다
     (예: `wallet_db.ADVANCED_MONTHLY_COST = SUBSCRIPTION_POINTS_COST["premium-monthly"]`).
  2. 금액과 포인트는 항상 `WON_PER_POINT`로 환산 관계가 맞아야 한다(테스트가 전수 검사).
  3. 앱(TS)은 파이썬을 import할 수 없으므로 SKU·파라미터명을 자기 파일에 복사해 두는데,
     이 파일의 값과 이름이 어긋나면 테스트가 실패한다(양쪽 이름 동일이 계약).
"""

from __future__ import annotations

# 앱 패키지(번들) 이름 — Play 결제 검증 API·구독 관리 링크가 같이 쓴다(2026-10-09).
ANDROID_PACKAGE_NAME = "com.bandouni.lottoshinryeong"

# 10원 = 1P. 이 값이 돈↔포인트 환산의 유일한 기준이다(예전 wallet_db에서 이사).
WON_PER_POINT = 10

# 토스(웹) 충전 화면이 제시하는 금액 후보.
CHARGE_WON_AMOUNTS: tuple[int, ...] = (10000, 30000, 50000)

# 일회성(소모성) 상품 — Play 상품 ID → 지급 포인트.
POINTS_PRODUCTS: dict[str, int] = {
    "points_1000": 1000,
    "points_3000": 3000,
}

# 정기결제 상품 — Play 상품 ID는 하나이고, 기간은 '기본요금제 ID'로 구분한다.
SUBSCRIPTION_PRODUCT = "premium"
# 기본요금제 ID는 여기서 한 번만 문자열로 쓴다 — 다른 파일은 이 상수를 참조한다.
BASE_PLAN_MONTHLY = "premium-monthly"
BASE_PLAN_QUARTERLY = "premium-quarterly"
SUBSCRIPTION_BASE_PLAN_DAYS: dict[str, int] = {
    BASE_PLAN_MONTHLY: 30,
    BASE_PLAN_QUARTERLY: 90,
}
# 같은 요금제를 웹에서 포인트로 살 때의 포인트 가격(월 1,200P / 3개월 3,000P).
SUBSCRIPTION_POINTS_COST: dict[str, int] = {
    BASE_PLAN_MONTHLY: 1200,
    BASE_PLAN_QUARTERLY: 3000,
}
SUBSCRIPTION_LABELS: dict[str, str] = {
    BASE_PLAN_MONTHLY: "1개월",
    BASE_PLAN_QUARTERLY: "3개월",
}
# 화면(구독 안내창)의 plan_key → 기본요금제 ID 매핑.
SUBSCRIPTION_PLAN_KEYS: tuple[tuple[str, str], ...] = (
    ("monthly", BASE_PLAN_MONTHLY),
    ("3month", BASE_PLAN_QUARTERLY),
)
# 첫 구독 무료 프로모 기간 — 월간 요금제와 같은 기간으로 맞춘다(테스트가 검사).
FREE_PROMO_DAYS = 30

# 앱이 스토어에서 읽은 실제 가격을 서버로 넘길 때 쓰는 파라미터 이름.
# (streamlit-webview.tsx의 IAP_PRICE_PARAMS와 이름이 같아야 한다 — 테스트가 검사)
IAP_PRICE_PARAMS: dict[str, str] = {
    "points_1000": "iap_price_points_1000",
    "points_3000": "iap_price_points_3000",
    "premium-monthly": "iap_price_premium_monthly",
    "premium-quarterly": "iap_price_premium_quarterly",
}
# 스토어 가격을 못 받았을 때(웹 접속·스토어 조회 실패) 화면에 쓸 기본 표시 가격.
IAP_PRICE_FALLBACK: dict[str, str] = {
    "points_1000": "10,000원",
    "points_3000": "30,000원",
    "premium-monthly": "12,000원",
    "premium-quarterly": "30,000원",
}


# ── 애플(App Store) 인앱결제 — 2026-10-09 App Store Connect 등록값 ─────────────────
# 적립금(소모성)은 구글과 **같은 상품 ID**(POINTS_PRODUCTS)를 쓴다 — 지급 포인트도 같은 표.
# 구독은 애플 제품 ID에 하이픈을 쓸 수 없어 밑줄로 등록했다. 서버는 애플 제품 ID를 구글 기본요금제
# ID로 바꿔 같은 권한·기간 규칙(SUBSCRIPTION_BASE_PLAN_DAYS 등)을 그대로 쓴다.
# (`premium_quarterly`·`premium_3month`는 ASC에서 잘못 만들었다 지운 ID라 다시 쓸 수 없다.)
APPLE_SUBSCRIPTION_PRODUCTS: dict[str, str] = {
    "premium_monthly": BASE_PLAN_MONTHLY,
    "premium_3months": BASE_PLAN_QUARTERLY,
}
# ASC 구독 그룹 '로또신령 프리미엄' — 두 구독은 같은 그룹이라 동시에 결제되지 않는다(요금제 변경만).
APPLE_SUBSCRIPTION_GROUP_ID = "22457283"
# 애플 가격표(KRW)에는 10,000원·12,000원·30,000원이 없어 한 단계 아래 가격으로 등록했다
# (2026-10-09 사용자 결정). 지급량은 상품 ID로 정해지므로(1000P/3000P·1개월/3개월) 가격만 다르다.
# 화면 표시는 앱이 App Store에서 읽은 가격이 우선이고, 이 값은 못 받았을 때의 기본값이다.
IAP_PRICE_FALLBACK_IOS: dict[str, str] = {
    "points_1000": "9,900원",
    "points_3000": "29,000원",
    BASE_PLAN_MONTHLY: "11,000원",
    BASE_PLAN_QUARTERLY: "29,000원",
}
# 애플 구독 관리(해지) 화면 — 앱 안에 이 길을 둔다(App Store 심사 지침 3.1.2).
APPLE_SUBSCRIPTION_MANAGE_URL = "https://apps.apple.com/account/subscriptions"


def apple_product_for_plan(base_plan_id: str) -> str:
    """구글 기본요금제 ID → 애플 구독 제품 ID."""
    for apple_id, plan in APPLE_SUBSCRIPTION_PRODUCTS.items():
        if plan == base_plan_id:
            return apple_id
    raise KeyError(base_plan_id)


def apple_product_ids() -> tuple[str, ...]:
    """애플에 등록된 제품 ID 전체(적립금 + 구독)."""
    return points_product_ids() + tuple(APPLE_SUBSCRIPTION_PRODUCTS)


def points_product_ids() -> tuple[str, ...]:
    return tuple(POINTS_PRODUCTS)


def subscription_plans() -> tuple[tuple[str, str], ...]:
    return SUBSCRIPTION_PLAN_KEYS


def all_product_keys() -> tuple[str, ...]:
    """가격 표시 키 전체 — 포인트 상품 ID + 구독 기본요금제 ID."""
    return points_product_ids() + tuple(SUBSCRIPTION_BASE_PLAN_DAYS)


def won_to_points(won: int) -> int:
    return int(won) // WON_PER_POINT


def points_to_won(points: int) -> int:
    return int(points) * WON_PER_POINT


def points_product_price_label(product_id: str) -> str:
    """포인트 상품의 기본 표시 금액(스토어 가격을 못 받았을 때 쓰는 값)."""
    return f"{points_to_won(POINTS_PRODUCTS[product_id]):,}원"


def subscription_price_label(base_plan_id: str) -> str:
    """구독 요금제의 기본 표시 금액(포인트 가격을 원으로 환산)."""
    return f"{points_to_won(SUBSCRIPTION_POINTS_COST[base_plan_id]):,}원"


def play_subscription_manage_url() -> str:
    """구글 정기 결제 관리(해지·결제수단 변경) 화면 주소 — 구글 정기결제 정책상 앱 안에 이 길을 둔다."""
    return (
        "https://play.google.com/store/account/subscriptions"
        f"?sku={SUBSCRIPTION_PRODUCT}&package={ANDROID_PACKAGE_NAME}"
    )
