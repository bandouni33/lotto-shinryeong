"""상품·가격·기간 기준점(products.py) 계약 검증 — 2026-09-26.

배경: 같은 상품 정보가 파이썬 4개 파일 + 앱(TS) 1개 파일에 나뉘어 있어, 가격 하나
바꾸려면 5곳을 손대야 했고 한 곳만 고치면 화면에 옛 금액이 남았다. 이제 정의는
products.py 한 곳이고 나머지는 파생값만 쓴다 — 어긋나면 이 테스트가 실패한다.

  P1 일회성 상품 전수: 지급 포인트 · 금액 · 표시 문자열이 환산 기준과 맞는다
  P2 구독 요금제 전수: 기간 · 포인트 가격 · 표시 문자열 · 무료 프로모 기간 관계
  P3 중복 정의 금지: 기준이 되는 정의·상품 ID 리터럴이 다른 파일에 없다
  P4 파생 일치: wallet_db / google_play_pg / wallet_ui / legal_notices 값이 products와 같다
  P5 앱(TS) 일치: 파라미터명·SKU가 서버와 같다
  P6 표시 경로 일치: 화면 기본 표시 가격이 products 계산값과 같다

pytest 없이 돌도록 표준 assert + __main__ 러너를 둔다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _path in (str(ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import products  # noqa: E402

TSX = ROOT / "LottoShinryeong" / "components" / "streamlit-webview.tsx"
DEPENDENT_FILES = ("wallet_db.py", "google_play_pg.py", "wallet_ui.py", "legal_notices.py")


def test_P1_points_products_are_consistent():
    assert products.POINTS_PRODUCTS, "일회성 상품 정의가 비어 있다"
    for product_id, points in products.POINTS_PRODUCTS.items():
        assert points > 0, f"{product_id}: 지급 포인트가 0 이하다"
        won = products.points_to_won(points)
        assert products.won_to_points(won) == points, f"{product_id}: 왕복 환산이 어긋난다"
        label = products.points_product_price_label(product_id)
        assert label == f"{won:,}원", f"{product_id}: 표시 금액이 환산값과 다르다({label})"
        assert products.IAP_PRICE_FALLBACK[product_id] == label, (
            f"{product_id}: 화면 기본 표시 가격과 계산값이 다르다"
        )
        assert products.IAP_PRICE_PARAMS[product_id].endswith(product_id) or (
            product_id.replace("_", "") in products.IAP_PRICE_PARAMS[product_id]
        ), f"{product_id}: 스토어 가격 파라미터 이름이 상품을 가리키지 않는다"


def test_P2_subscription_plans_are_consistent():
    assert products.SUBSCRIPTION_BASE_PLAN_DAYS, "구독 기본요금제 정의가 비어 있다"
    for base_plan_id, days in products.SUBSCRIPTION_BASE_PLAN_DAYS.items():
        assert days > 0, f"{base_plan_id}: 기간이 0 이하다"
        cost = products.SUBSCRIPTION_POINTS_COST[base_plan_id]
        assert cost > 0, f"{base_plan_id}: 포인트 가격이 0 이하다"
        label = products.subscription_price_label(base_plan_id)
        assert label == f"{products.points_to_won(cost):,}원", (
            f"{base_plan_id}: 표시 금액이 환산값과 다르다({label})"
        )
        assert products.IAP_PRICE_FALLBACK[base_plan_id] == label
        assert products.IAP_PRICE_PARAMS[base_plan_id]
        assert products.SUBSCRIPTION_LABELS[base_plan_id]
    assert products.FREE_PROMO_DAYS == products.SUBSCRIPTION_BASE_PLAN_DAYS["premium-monthly"], (
        "무료 프로모 기간이 월간 요금제와 어긋난다(의도적으로 같은 값으로 맞춘다)"
    )
    assert dict(products.SUBSCRIPTION_PLAN_KEYS) == {
        "monthly": "premium-monthly",
        "3month": "premium-quarterly",
    }, "화면 plan_key ↔ 기본요금제 매핑이 바뀌었다(화면 버튼 키가 깨진다)"
    assert set(products.all_product_keys()) == set(products.IAP_PRICE_PARAMS), (
        "가격 표시 키와 파라미터 키 집합이 다르다(한쪽만 늘면 반영이 안 된다)"
    )


def _code_only(body: str) -> str:
    """주석을 뗀 코드만 — 주석에 단가·상품 ID를 예로 적어둔 것은 중복 정의가 아니다."""
    return "\n".join(line.split("#", 1)[0] for line in body.splitlines())


def test_P3_no_duplicate_definitions_outside_products():
    offenders: list[str] = []
    for rel in DEPENDENT_FILES:
        body = _code_only((ROOT / rel).read_text(encoding="utf-8", errors="replace"))
        if re.search(r"^\s*WON_PER_POINT\s*=\s*\d", body, re.M):
            offenders.append(f"{rel}: WON_PER_POINT을 숫자로 다시 정의했다")
        if re.search(r"^\s*SUBSCRIPTION_BASE_PLAN_DAYS\s*=\s*\{", body, re.M):
            offenders.append(f"{rel}: 구독 기간 표를 다시 정의했다")
        if re.search(r"^\s*POINTS_PRODUCTS\s*=\s*\{", body, re.M):
            offenders.append(f"{rel}: 상품 표를 다시 정의했다")
        if re.search(r"^\s*CHARGE_WON_AMOUNTS\s*=\s*\(", body, re.M):
            offenders.append(f"{rel}: 충전 금액 후보를 다시 정의했다")
        for literal in ("points_1000", "points_3000", "premium-monthly", "premium-quarterly"):
            if literal in body:
                offenders.append(f"{rel}: 상품 ID 리터럴 {literal} 이 남아 있다(products에서 파생시킬 것)")
    assert not offenders, "; ".join(offenders)


def test_P4_dependent_modules_match_products():
    import google_play_pg
    import legal_notices
    import wallet_db
    import wallet_ui

    assert wallet_db.WON_PER_POINT == products.WON_PER_POINT
    assert wallet_db.CHARGE_WON_AMOUNTS == products.CHARGE_WON_AMOUNTS
    assert wallet_db.won_to_points(10000) == products.won_to_points(10000)
    assert wallet_db.FREE_SUB_DAYS == products.FREE_PROMO_DAYS
    assert wallet_db.ADVANCED_MONTHLY_COST == products.SUBSCRIPTION_POINTS_COST["premium-monthly"]
    assert wallet_db.ADVANCED_3MONTH_COST == products.SUBSCRIPTION_POINTS_COST["premium-quarterly"]
    assert wallet_db.ADVANCED_3MONTH_DAYS == products.SUBSCRIPTION_BASE_PLAN_DAYS["premium-quarterly"]

    assert google_play_pg.POINTS_PRODUCTS == products.POINTS_PRODUCTS
    assert google_play_pg.SUBSCRIPTION_BASE_PLAN_DAYS == products.SUBSCRIPTION_BASE_PLAN_DAYS
    assert google_play_pg.SUBSCRIPTION_PRODUCT == products.SUBSCRIPTION_PRODUCT

    assert wallet_ui.IAP_POINTS_PRODUCT_IDS == products.points_product_ids()
    assert wallet_ui.IAP_SUBSCRIPTION_PLANS == products.subscription_plans()
    assert wallet_ui.IAP_PRICE_PARAMS == products.IAP_PRICE_PARAMS
    assert wallet_ui.IAP_PRICE_FALLBACK == products.IAP_PRICE_FALLBACK
    assert wallet_ui._iap_points_products() == products.POINTS_PRODUCTS

    assert legal_notices.PRICING["advanced_monthly"] == products.SUBSCRIPTION_POINTS_COST["premium-monthly"]
    assert legal_notices.PRICING["advanced_3month"] == products.SUBSCRIPTION_POINTS_COST["premium-quarterly"]


def test_P5_app_typescript_matches_products():
    tsx = TSX.read_text(encoding="utf-8")
    for param in products.IAP_PRICE_PARAMS.values():
        assert param in tsx, f"앱이 {param} 를 안 보낸다(서버가 스토어 가격을 못 받는다)"
    for product_id in products.points_product_ids():
        assert f"'{product_id}'" in tsx, f"앱 SKU 목록에 {product_id} 가 없다"
    assert products.SUBSCRIPTION_PRODUCT in tsx, "앱이 구독 상품 ID를 모른다"


def test_P6_display_path_uses_products_labels():
    import wallet_ui

    # 화면이 쓰는 기본 표시 가격이 products 계산값과 문자 단위로 같아야 한다
    # (한쪽만 바뀌어 "12,000원"과 "12000원"이 섞이는 일 방지).
    for key, label in products.IAP_PRICE_FALLBACK.items():
        assert wallet_ui.IAP_PRICE_FALLBACK[key] == label
    for base_plan_id in products.SUBSCRIPTION_BASE_PLAN_DAYS:
        assert products.IAP_PRICE_FALLBACK[base_plan_id] == products.subscription_price_label(base_plan_id)


def _main() -> int:
    tests = [
        test_P1_points_products_are_consistent,
        test_P2_subscription_plans_are_consistent,
        test_P3_no_duplicate_definitions_outside_products,
        test_P4_dependent_modules_match_products,
        test_P5_app_typescript_matches_products,
        test_P6_display_path_uses_products_labels,
    ]
    failed = 0
    for test in tests:
        try:
            test()
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001 — 러너이므로 무엇이든 보고하고 계속
            failed += 1
            print(f"ERROR {test.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
        sys.stdout.flush()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
