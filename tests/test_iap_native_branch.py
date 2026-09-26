"""네이티브 앱(구글 인앱결제) 분기 검증 — P0-2 (2026-09-26).

무엇을 검증하는가: 앱(안드로이드 웹뷰, native=1)에서는 토스 카드결제·포인트차감
버튼이 사라지고 Google Play 인앱결제 버튼만 뜨는가(= Play 결제정책 대응), 그리고
웹 접속에서는 종전 동작이 그대로인가(회귀 없음). 버튼→앱 트리거 배선과 그 페이로드
(앱 코드와의 약속)까지 함께 검증한다.

  N1  네이티브 충전: IAP 버튼만 있고 토스 버튼은 없다
  N2  네이티브 구독: IAP 구독 버튼만 있고 포인트차감 "구독하기"는 없다
  N2b 네이티브 구독(무료 프로모 대상): 무료 시작 버튼은 유지, IAP 버튼은 없음
  N3  웹 충전: 토스 버튼이 그대로 있고 IAP 버튼은 없다 (회귀)
  N4  웹 구독: 포인트차감 구독 버튼이 그대로 있다 (회귀)
  N5  버튼→트리거 배선: 누른 버튼이 정확한 상품 ID/기본요금제로 트리거를 부른다
  N6  트리거 페이로드: postMessage 키·URL 파라미터명이 앱 코드(streamlit-webview.tsx)와 일치
  N7  화이트리스트 밖 상품 ID는 JS 주입 전에 거부된다
  N8  앱 코드는 서버 승인 방식을 지킨다(finishTransaction 미호출)

DB는 _db_isolation.isolated_db()로만 만진다(운영 Turso 접촉 0). 환경변수는 테스트가
직접 세팅/복구한다 — 실제 운영 구성을 재현하려면 카카오 키가 있어야
_testing_period_active()가 꺼지고(= 구독 안내창의 실제 분기가 열림), 토스 키가
있어야 pg_configured()가 True가 된다(그래야 "숨겨졌는지"를 볼 수 있다).
pytest 없이 돌도록 표준 assert + __main__ 러너를 함께 둔다.
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path

from streamlit.testing.v1 import AppTest

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _path in (str(ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import _db_isolation  # noqa: E402
import wallet_db as wdb  # noqa: E402

PROBE = str(TESTS_DIR / "_iap_probe.py")
TSX = ROOT / "LottoShinryeong" / "components" / "streamlit-webview.tsx"
TIMEOUT_SEC = 60

IAP_BUY_KEYS = ("iap_buy_points_1000", "iap_buy_points_3000")
IAP_SUB_KEYS = ("iap_sub_monthly", "iap_sub_3month")
TOSS_KEY = "toss_checkout_btn"
POINT_SUB_KEY = "adv_sub_confirm"

_ENV_KEYS = ("KAKAO_REST_API_KEY", "TOSS_CLIENT_KEY", "TOSS_SECRET_KEY", "LOTTO_DEV_MOCK_AUTH")


@contextmanager
def _prod_like_env():
    """운영과 같은 판정이 나오게 하는 최소 환경변수(끝나면 전부 원복).

    · KAKAO_REST_API_KEY  → _testing_period_active()를 끈다(구독 안내창의 실제 분기)
    · TOSS_CLIENT_KEY/SECRET → pg_configured() True(웹 화면의 토스 버튼이 그려짐)
    · LOTTO_DEV_MOCK_AUTH=0 → mock 로그인 분기 배제
    """
    before = {key: os.environ.get(key) for key in _ENV_KEYS}
    os.environ["KAKAO_REST_API_KEY"] = "test_kakao_key"
    os.environ["TOSS_CLIENT_KEY"] = "test_client_key"
    os.environ["TOSS_SECRET_KEY"] = "test_secret_key"
    os.environ["LOTTO_DEV_MOCK_AUTH"] = "0"
    try:
        yield
    finally:
        for key, value in before.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _member(handle: str) -> int:
    wdb.init_wallet_tables()
    mid, _new = wdb.get_or_create_member("kakao", handle)
    return int(mid)


def _render_probe(mode: str, member_id: int, *, native: bool) -> AppTest:
    at = AppTest.from_file(PROBE, default_timeout=TIMEOUT_SEC)
    at.query_params["probe"] = mode
    if native:
        at.query_params["native"] = "1"
    at.session_state["member_id"] = member_id
    at.run()
    return at


def _keys(at: AppTest) -> list[str]:
    return [b.key for b in at.button]


def _click(at: AppTest, key: str) -> AppTest:
    """AppTest 버전에 따라 at.button(key=...) 호출 지원 여부가 달라서,
    키로 직접 찾아 클릭한다(못 찾으면 그 자리에서 실패한다)."""
    for button in at.button:
        if button.key == key:
            return button.click().run()
    raise AssertionError(f"버튼을 찾지 못했다: {key} (있던 키: {_keys(at)})")


@contextmanager
def _spy_trigger():
    """wallet_ui._fire_iap_purchase_trigger를 가로채 호출 인자를 기록한다
    (실제 JS 주입/결제는 일어나지 않는다)."""
    import wallet_ui

    calls: list[tuple] = []
    original = wallet_ui._fire_iap_purchase_trigger

    def fake(product_id, base_plan_id=None):
        calls.append((product_id, base_plan_id))

    wallet_ui._fire_iap_purchase_trigger = fake
    try:
        yield calls
    finally:
        wallet_ui._fire_iap_purchase_trigger = original


def test_N1_native_charge_shows_only_iap():
    with _prod_like_env(), _db_isolation.isolated_db():
        mid = _member("iap_n1")
        at = _render_probe("charge", mid, native=True)
        assert not at.exception, f"네이티브 충전 화면 렌더 예외: {at.exception}"
        keys = _keys(at)
        for key in IAP_BUY_KEYS:
            assert key in keys, f"앱인데 IAP 충전 버튼이 없다: {keys}"
        assert TOSS_KEY not in keys, f"앱인데 토스 결제 버튼이 그려졌다(정책 위반 소지): {keys}"


def test_N2_native_subscription_shows_only_iap():
    with _prod_like_env(), _db_isolation.isolated_db():
        mid = _member("iap_n2")
        # 이미 무료 프로모를 쓴 회원 = 유료 구독 화면을 보는 실제 대상
        wdb.activate_free_advanced_sub(mid)
        at = _render_probe("sub", mid, native=True)
        assert not at.exception, f"네이티브 구독 화면 렌더 예외: {at.exception}"
        keys = _keys(at)
        for key in IAP_SUB_KEYS:
            assert key in keys, f"앱인데 IAP 구독 버튼이 없다: {keys}"
        assert POINT_SUB_KEY not in keys, f"앱인데 포인트차감 구독 버튼이 그려졌다: {keys}"


def test_N2b_native_free_promo_keeps_free_button():
    with _prod_like_env(), _db_isolation.isolated_db():
        mid = _member("iap_n2b")
        assert wdb.eligible_free_advanced_sub(mid), "테스트 전제: 아직 무료 프로모 대상이어야 한다"
        at = _render_probe("sub", mid, native=True)
        assert not at.exception, f"네이티브 무료 프로모 화면 예외: {at.exception}"
        keys = _keys(at)
        assert "iap_free_sub_confirm" in keys, f"무료 프로모 버튼이 사라졌다(혜택 상실): {keys}"
        assert not any(key.startswith("iap_sub_") for key in keys), (
            f"무료 프로모 대상자에게 유료 IAP 버튼까지 떴다: {keys}"
        )


def test_N3_web_charge_keeps_toss_button():
    with _prod_like_env(), _db_isolation.isolated_db():
        mid = _member("iap_n3")
        at = _render_probe("charge", mid, native=False)
        assert not at.exception, f"웹 충전 화면 렌더 예외: {at.exception}"
        keys = _keys(at)
        assert TOSS_KEY in keys, f"웹인데 토스 버튼이 사라졌다(회귀): {keys}"
        assert not any(key.startswith("iap_buy_") for key in keys), (
            f"웹인데 IAP 버튼이 떴다: {keys}"
        )


def test_N4_web_subscription_keeps_points_button():
    with _prod_like_env(), _db_isolation.isolated_db():
        mid = _member("iap_n4")
        wdb.activate_free_advanced_sub(mid)
        at = _render_probe("sub", mid, native=False)
        assert not at.exception, f"웹 구독 화면 렌더 예외: {at.exception}"
        keys = _keys(at)
        assert POINT_SUB_KEY in keys, f"웹인데 포인트차감 구독 버튼이 사라졌다(회귀): {keys}"
        assert not any(key.startswith("iap_sub_") for key in keys), (
            f"웹인데 IAP 구독 버튼이 떴다: {keys}"
        )


def test_N5_buttons_call_trigger_with_exact_product():
    with _prod_like_env(), _db_isolation.isolated_db():
        mid = _member("iap_n5")
        wdb.activate_free_advanced_sub(mid)

        with _spy_trigger() as calls:
            at = _render_probe("charge", mid, native=True)
            at = _click(at, IAP_BUY_KEYS[1])
        assert calls == [("points_3000", None)], f"충전 버튼 트리거 인자: {calls}"

        with _spy_trigger() as calls:
            at = _render_probe("sub", mid, native=True)
            at = _click(at, IAP_SUB_KEYS[1])
        assert calls == [("premium", "premium-quarterly")], f"구독 버튼 트리거 인자: {calls}"


def test_N6_trigger_payload_matches_app_code():
    import wallet_ui

    captured: list[str] = []
    original_html = wallet_ui.components.html
    wallet_ui.components.html = lambda html, **kwargs: captured.append(html)
    try:
        wallet_ui._fire_iap_purchase_trigger("premium", "premium-quarterly")
        wallet_ui._fire_iap_purchase_trigger("points_1000")
    finally:
        wallet_ui.components.html = original_html

    assert len(captured) == 2, "트리거가 JS를 정확히 2번 주입해야 한다"
    sub_js, points_js = captured
    assert "{type:'iapPurchase',productId:'premium',basePlanId:'premium-quarterly'}" in sub_js, (
        "구독 트리거의 postMessage 페이로드가 앱 수신부와 어긋난다"
    )
    assert "{type:'iapPurchase',productId:'points_1000',basePlanId:null}" in points_js, (
        "소모성 트리거의 postMessage 페이로드가 앱 수신부와 어긋난다"
    )
    for js, sku, plan in (
        (sub_js, "premium", "premium-quarterly"),
        (points_js, "points_1000", None),
    ):
        assert "window.ReactNativeWebView" in js, "브릿지 경로가 없다"
        assert f"iap_buy', '{sku}'" in js, f"URL 폴백의 상품 ID가 다르다: {sku}"
        if plan:
            assert f"iap_plan', '{plan}'" in js, f"URL 폴백의 기본요금제가 다르다: {plan}"
        else:
            assert "iap_plan" not in js, "소모성 상품인데 기본요금제 파라미터가 실렸다"

    # 앱 수신부(streamlit-webview.tsx)가 같은 이름을 읽는지 — 한쪽만 바꾸면 결제가 안 뜬다.
    tsx = TSX.read_text(encoding="utf-8")
    for token in ("'iapPurchase'", "iap_buy", "iap_plan", "productId", "basePlanId"):
        assert token in tsx, f"앱 코드에 {token} 수신부가 없다(프로토콜 불일치)"


def test_N7_trigger_rejects_unknown_product():
    import wallet_ui

    captured: list[str] = []
    original_html = wallet_ui.components.html
    wallet_ui.components.html = lambda html, **kwargs: captured.append(html)
    try:
        for bad_product in ("points_9999", "premium_monthly", ""):
            try:
                wallet_ui._fire_iap_purchase_trigger(bad_product)
            except ValueError:
                pass
            else:
                raise AssertionError(f"허용 목록 밖 상품 ID가 통과했다: {bad_product!r}")
        try:
            wallet_ui._fire_iap_purchase_trigger("premium", "premium-yearly")
        except ValueError:
            pass
        else:
            raise AssertionError("허용 목록 밖 기본요금제가 통과했다")
        assert captured == [], "거부된 요청이 JS를 주입했다"
    finally:
        wallet_ui.components.html = original_html


def test_N8_app_code_does_not_finish_transactions():
    """승인(consume/acknowledge)은 서버 전담 — 앱이 finishTransaction을 부르면
    서버 검증 전에 구매가 소비돼 환불·이중지급 사고가 난다."""
    tsx = TSX.read_text(encoding="utf-8")
    assert "purchaseUpdatedListener" in tsx, "구매 결과 수신부가 없다"
    assert "requestPurchase" in tsx, "구매 요청부가 없다"
    # 주석(설명)에 이름이 나오는 건 무방 — 금지하는 건 실제 호출/import다.
    offenders = [
        line.strip()
        for line in tsx.splitlines()
        if "finishTransaction" in line and not line.strip().startswith(("//", "*", "/*"))
    ]
    assert not offenders, f"앱이 finishTransaction을 호출·import하고 있다: {offenders}"
    assert "iap_purchase_token" in tsx, "서버로 토큰을 넘기는 배선이 없다"


def _main() -> int:
    tests = [
        test_N1_native_charge_shows_only_iap,
        test_N2_native_subscription_shows_only_iap,
        test_N2b_native_free_promo_keeps_free_button,
        test_N3_web_charge_keeps_toss_button,
        test_N4_web_subscription_keeps_points_button,
        test_N5_buttons_call_trigger_with_exact_product,
        test_N6_trigger_payload_matches_app_code,
        test_N7_trigger_rejects_unknown_product,
        test_N8_app_code_does_not_finish_transactions,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001 — 러너이므로 무엇이든 보고하고 계속
            failed += 1
            print(f"ERROR {t.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"PASS {t.__name__}")
        sys.stdout.flush()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.stdout.flush()
    # db_turso.py가 import 시점에 만드는 비데몬 스레드풀 때문에 프로세스가 스스로
    # 끝나지 않는다 — 결과를 다 낸 뒤 즉시 종료한다.
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
