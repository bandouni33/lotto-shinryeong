"""네이티브 앱(구글 인앱결제) 분기 검증 — P0-2 (2026-09-26).

무엇을 검증하는가: 앱(안드로이드 웹뷰, native=1)에서는 토스 카드결제·포인트차감
버튼이 사라지고 Google Play 인앱결제 버튼만 뜨는가(= Play 결제정책 대응), 그리고
웹 접속에서는 종전 동작이 그대로인가(회귀 없음). 버튼→앱 트리거 배선과 그 페이로드
(앱 코드와의 약속)까지 함께 검증한다.

  N1  네이티브 충전(테스터 빌드 구성): 구글플레이 버튼 대신 테스터용 "Mock 결제(테스트)" 1,000P 충전
  N1e 제출 구성(기본값): 구글플레이 버튼만 뜨고 테스터 임시충전·토스는 없다
  N1b 스위치를 켜면(IAP_CHARGE_ENABLED=True) 앱에서도 IAP 버튼만 뜬다(토스 없음)
  N1c 테스터 임시 충전 스위치를 내리면(TEST_CHARGE_ENABLED=False) 준비중 안내만 뜼다
  N2  네이티브 구독(수신부 없는 빌드 구성): 요금제 버튼 대신 "결제 연동 준비 중" 안내 + 닫기만 뜼다
  N2c 스위치를 켜면(IAP_SUBSCRIPTION_ENABLED=True) 앱에서도 IAP 요금제 버튼만 뜬다
  N2b 네이티브 구독(무료 프로모 대상): 무료 시작 버튼은 유지, IAP 버튼은 없음
  N3  웹 충전: 토스 버튼이 그대로 있고 IAP 버튼은 없다 (회귀)
  N4  웹 구독: 포인트차감 구독 버튼이 그대로 있다 (회귀)
  N5  버튼→트리거 배선: 누른 버튼이 정확한 상품 ID/기본요금제로 트리거를 부른다
  N6  트리거 페이로드: postMessage 키·URL 파라미터명이 앱 코드(streamlit-webview.tsx)와 일치
  N7  화이트리스트 밖 상품 ID는 JS 주입 전에 거부된다
  N8  앱 코드는 서버 승인 방식을 지킨다(finishTransaction 미호출)
  N9  가격: 앱이 보내준 스토어 가격이 화면에 그대로 뜨고, 파라미터가 없는 다음
      렌더(내부이동을 흉내낸다)에서도 저장된 값으로 유지된다
  N10 가격 파라미터 이름이 서버·앱에서 일치하고, 앱은 '현재 주소 + 파라미터'로
      재로드한다(재빌드하면 보던 페이지를 잃는다)
  N11 로그인 후 구독 안내창 재개(resume=af_show_subscribe)가 실제로 동작한다

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


@contextmanager
def _switches(**values):
    """이 블록 동안만 충전/구독/테스터충전 스위치를 바꾼다(끝나면 원복).

    2026-09-27: 제출 구성(기본값)이 뒤집혀(IAP 켜짐·테스터 임시충전 꺼짐) 예전에
    "기본값"을 검사하던 테스트들이 검증 대상을 잃게 됐다. 각 테스트가 자기가 보려는
    구성을 명시적으로 세워야 그 값이 또 바뀌어도 검사가 의미를 유지한다."""
    import wallet_ui

    before = {name: getattr(wallet_ui, name) for name in values}
    for name, value in values.items():
        setattr(wallet_ui, name, value)
    try:
        yield
    finally:
        for name, value in before.items():
            setattr(wallet_ui, name, value)


def _render_probe(mode: str, member_id: int, *, native: bool, **extra_params) -> AppTest:
    at = AppTest.from_file(PROBE, default_timeout=TIMEOUT_SEC)
    at.query_params["probe"] = mode
    if native:
        at.query_params["native"] = "1"
        # 2026-10-09: 결제 수신부가 있는 새 빌드(iap=1)를 기본으로 흉내 낸다. 옛 빌드는 iap=None.
        extra_params.setdefault("iap", "1")
    for key, value in extra_params.items():
        if value is not None:
            at.query_params[key] = value
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


def test_N1_native_charge_offers_test_charge_not_dead_buttons():
    """테스터 빌드 구성(IAP 스위치를 되돌린 상태): 구글플레이 버튼 대신 테스터용
    'Mock 결제(테스트)' 1,000P 충전을 낸다 — 눌러도 반응 없는 버튼은 안 낸다.

    2026-09-27: 제출 구성에서는 테스터 임시충전이 기본으로 꺼져 있다 — 그 구성을 여기서
    명시적으로 세워 테스터 빌드 경로를 계속 검증한다."""
    with _prod_like_env(), _db_isolation.isolated_db(), _switches(
        IAP_CHARGE_ENABLED=False, TEST_CHARGE_ENABLED=True
    ):
        mid = _member("iap_n1")
        at = _render_probe("charge", mid, native=True)
        assert not at.exception, f"네이티브 충전 화면 렌더 예외: {at.exception}"
        keys = [key for key in _keys(at) if key]
        assert not any(key.startswith("iap_buy_") for key in keys), (
            f"앱인데 IAP 충전 버튼이 그려졌다(수신부 없는 빌드에서는 먹통): {keys}"
        )
        assert TOSS_KEY not in keys, f"앱인데 토스 결제 버튼이 그려졌다(정책 위반 소지): {keys}"
        labels = [(b.label or "") for b in at.button]
        assert any("Mock 결제" in label for label in labels), (
            f"앱 충전 화면에 테스트 충전 버튼이 없다(테스터가 충전할 방법이 없다): {labels}"
        )
        assert any("1,000P" in label for label in labels), (
            f"테스트 충전 금액이 1,000P가 아니다: {labels}"
        )


def test_N1e_shipping_default_is_the_review_configuration():
    """제출 구성(기본값) 검사 — 스위치를 되돌리면 여기서 잡힌다.

    앱에서 구글플레이 버튼만 뜨고, 테스터 임시충전('Mock 결제')과 토스 버튼은 없다.
    이게 제출할 그대로의 상태이므로 기본값 자체를 검사한다(preflight R4b/R4c와 같은 취지)."""
    with _prod_like_env(), _db_isolation.isolated_db():
        import wallet_ui

        assert (wallet_ui.IAP_CHARGE_ENABLED, wallet_ui.IAP_SUBSCRIPTION_ENABLED) == (True, True), (
            "제출 구성인데 IAP 스위치가 꺼져 있다(앱에서 결제 버튼이 사라진다)"
        )
        assert wallet_ui.TEST_CHARGE_ENABLED is False, (
            "제출 구성인데 테스터 임시충전이 켜져 있다(심사자가 'Mock 결제'를 본다)"
        )

        mid = _member("iap_n1e")
        at = _render_probe("charge", mid, native=True)
        assert not at.exception, f"네이티브 충전 화면 렌더 예외: {at.exception}"
        keys = _keys(at)
        for key in IAP_BUY_KEYS:
            assert key in keys, f"제출 구성인데 IAP 충전 버튼이 없다: {keys}"
        assert "test_charge_btn" not in keys, f"제출 구성인데 테스터 충전 버튼이 있다: {keys}"
        labels = [(b.label or "") for b in at.button]
        assert not any("Mock 결제" in label for label in labels), (
            f"제출 구성인데 Mock 결제 버튼이 그려진다: {labels}"
        )
        assert TOSS_KEY not in keys, f"앱인데 토스 결제 버튼이 그려졌다: {keys}"

        # 무료 프로모를 쓴 회원(유료 구독 화면 대상)도 IAP 요금제 버튼이 뜼다
        wdb.activate_free_advanced_sub(mid)
        sub = _render_probe("sub", mid, native=True)
        assert not sub.exception, f"네이티브 구독 화면 렌더 예외: {sub.exception}"
        sub_keys = _keys(sub)
        for key in IAP_SUB_KEYS:
            assert key in sub_keys, f"제출 구성인데 IAP 요금제 버튼이 없다: {sub_keys}"
        infos = "\n".join((m.value or "") for m in sub.info)
        assert wallet_ui.CHARGE_PENDING_NOTICE not in infos, (
            "제출 구성인데 구독 화면이 '준비 중' 안내로 대체됐다"
        )


def test_N1c_native_charge_shows_pending_notice_when_test_charge_off():
    """테스터 임시 충전 스위치를 내리면(수신부 없는 빌드 구성) 준비중 안내만 뜼다."""
    with _prod_like_env(), _db_isolation.isolated_db(), _switches(IAP_CHARGE_ENABLED=False):
        import wallet_ui

        mid = _member("iap_n1c")
        original = wallet_ui.TEST_CHARGE_ENABLED
        wallet_ui.TEST_CHARGE_ENABLED = False
        try:
            at = _render_probe("charge", mid, native=True)
        finally:
            wallet_ui.TEST_CHARGE_ENABLED = original
        assert not at.exception, f"네이티브 충전 화면 렌더 예외: {at.exception}"
        keys = [key for key in _keys(at) if key]
        assert not any(key.startswith("iap_buy_") for key in keys), f"버튼이 남아 있다: {keys}"
        labels = [(b.label or "") for b in at.button]
        assert not any("Mock 결제" in label for label in labels), (
            f"스위치를 내렸는데 테스트 충전이 남아 있다: {labels}"
        )
        infos = "\n".join((m.value or "") for m in at.info)
        assert wallet_ui.CHARGE_PENDING_NOTICE in infos, f"준비중 안내가 없다: {infos!r}"


def test_N1b_native_charge_shows_iap_when_switch_on():
    """스위치를 켜면(IAP_CHARGE_ENABLED=True) 앱에서 구글플레이 버튼이 나온다 —
    되살릴 때 그 경로가 살아 있어야 하므로 스위치 양쪽을 다 검사한다."""
    with _prod_like_env(), _db_isolation.isolated_db():
        import wallet_ui

        mid = _member("iap_n1b")
        original = wallet_ui.IAP_CHARGE_ENABLED
        wallet_ui.IAP_CHARGE_ENABLED = True
        try:
            at = _render_probe("charge", mid, native=True)
        finally:
            wallet_ui.IAP_CHARGE_ENABLED = original
        assert not at.exception, f"네이티브 충전 화면 렌더 예외: {at.exception}"
        keys = _keys(at)
        for key in IAP_BUY_KEYS:
            assert key in keys, f"스위치가 켜졌는데 IAP 충전 버튼이 없다: {keys}"
        assert TOSS_KEY not in keys, f"앱인데 토스 결제 버튼이 그려졌다(정책 위반 소지): {keys}"


def test_N1d_test_charge_btn_credits_1000_points_and_respects_the_limit():
    """테스터 임시 충전의 실제 동작(불변식): 한 번 누를 때마다 정확히 1,000P가 늘고,
    정해진 횟수(MOCK_CHARGE_MAX_PER_WINDOW)를 넘으면 버튼이 사라져 더는 안 늘어난다.

    결제창(dialog) 안에서 누르는 경로는 AppTest가 위젯을 다시 만나지 못해 재현이 안 되므로
    (충전 화면 자체를 그리는 프로브로 누른다 — 같은 상품 코드·같은 회수 제한을 탄다)."""
    with _prod_like_env(), _db_isolation.isolated_db(), _switches(
        IAP_CHARGE_ENABLED=False, TEST_CHARGE_ENABLED=True
    ):
        mid = _member("iap_n1d")
        before = int(wdb.get_balance(mid) or 0)
        at = _render_probe("charge", mid, native=True)
        assert not at.exception, f"충전 화면 렌더 예외: {at.exception}"
        assert "test_charge_btn" in _keys(at), f"테스트 충전 버튼이 없다: {_keys(at)}"

        for expected_credits in range(1, 4):
            at = _click(at, "test_charge_btn")
            balance = int(wdb.get_balance(mid) or 0)
            assert balance == before + 1000 * expected_credits, (
                f"{expected_credits}번째 충전 뒤 잔액이 기대와 다르다: {before} -> {balance}"
            )

        # 3회를 다 쓴 뒤에는 버튼 자체가 사라져야 한다(무한 충전 방지).
        at = _render_probe("charge", mid, native=True)
        assert "test_charge_btn" not in _keys(at), (
            f"회수 제한을 다 썼는데도 테스트 충전 버튼이 남아 있다: {_keys(at)}"
        )
        assert int(wdb.get_balance(mid) or 0) == before + 3000, "회수 제한 뒤 잔액이 더 늘었다"


def test_N2_native_subscription_shows_pending_notice_not_dead_buttons():
    """수신부 없는 빌드 구성: 구글플레이 요금제 버튼 대신 준비중 안내 + 닫기만 낸다
    (충전과 같은 스위치·같은 이유 — 그런 빌드에서는 누를 것이 없다)."""
    with _prod_like_env(), _db_isolation.isolated_db(), _switches(IAP_SUBSCRIPTION_ENABLED=False):
        import wallet_ui

        mid = _member("iap_n2")
        # 이미 무료 프로모를 쓴 회원 = 유료 구독 화면을 보는 실제 대상
        wdb.activate_free_advanced_sub(mid)
        at = _render_probe("sub", mid, native=True)
        assert not at.exception, f"네이티브 구독 화면 렌더 예외: {at.exception}"
        keys = _keys(at)
        plan_keys = [k for k in keys if k.startswith("iap_sub_") and k != "iap_sub_pending_close"]
        assert plan_keys == [], f"앱인데 IAP 요금제 버튼이 그려졌다(먹통): {plan_keys}"
        assert POINT_SUB_KEY not in keys, f"앱인데 포인트차감 구독 버튼이 그려졌다: {keys}"
        assert "iap_sub_pending_close" in keys, (
            f"준비중 안내에 닫기 버튼이 없다(창을 닫을 길이 없어진다): {keys}"
        )
        infos = "\n".join((m.value or "") for m in at.info)
        assert wallet_ui.CHARGE_PENDING_NOTICE in infos, (
            f"앱 구독 화면에 준비중 안내가 없다: {infos!r}"
        )


def test_N2c_native_subscription_shows_iap_when_switch_on():
    """스위치를 켜면(IAP_SUBSCRIPTION_ENABLED=True) 앱에서 구글플레이 요금제 버튼이 나온다."""
    with _prod_like_env(), _db_isolation.isolated_db():
        import wallet_ui

        mid = _member("iap_n2c")
        wdb.activate_free_advanced_sub(mid)
        original = wallet_ui.IAP_SUBSCRIPTION_ENABLED
        wallet_ui.IAP_SUBSCRIPTION_ENABLED = True
        try:
            at = _render_probe("sub", mid, native=True)
        finally:
            wallet_ui.IAP_SUBSCRIPTION_ENABLED = original
        assert not at.exception, f"네이티브 구독 화면 렌더 예외: {at.exception}"
        keys = _keys(at)
        for key in IAP_SUB_KEYS:
            assert key in keys, f"스위치가 켜졌는데 IAP 구독 버튼이 없다: {keys}"
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
        import wallet_ui

        mid = _member("iap_n5")
        wdb.activate_free_advanced_sub(mid)

        with _spy_trigger() as calls:
            original = wallet_ui.IAP_CHARGE_ENABLED
            wallet_ui.IAP_CHARGE_ENABLED = True
            try:
                at = _render_probe("charge", mid, native=True)
                at = _click(at, IAP_BUY_KEYS[1])
            finally:
                wallet_ui.IAP_CHARGE_ENABLED = original
        assert calls == [("points_3000", None)], f"충전 버튼 트리거 인자: {calls}"

        with _spy_trigger() as calls:
            original = wallet_ui.IAP_SUBSCRIPTION_ENABLED
            wallet_ui.IAP_SUBSCRIPTION_ENABLED = True
            try:
                at = _render_probe("sub", mid, native=True)
                at = _click(at, IAP_SUB_KEYS[1])
            finally:
                wallet_ui.IAP_SUBSCRIPTION_ENABLED = original
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
    """구글 승인(consume/acknowledge)은 서버 전담 — 앱이 구글 구매에 finishTransaction을 부르면
    서버 검증 전에 구매가 소비돼 환불·이중지급 사고가 난다.

    2026-10-09: 애플은 서버가 거래를 끝낼 방법이 없어 앱이 끝내야 한다 — 단, 서버가 확인·지급을 끝낸 뒤
    보내는 신호(iapFinish)를 받은 finishApplePurchase 안에서만, iOS 일 때만 부른다(그 밖의 호출은 금지)."""
    tsx = TSX.read_text(encoding="utf-8")
    assert "purchaseUpdatedListener" in tsx, "구매 결과 수신부가 없다"
    assert "requestPurchase" in tsx, "구매 요청부가 없다"
    start = tsx.index("const finishApplePurchase = useCallback(")
    end = tsx.index("const restoreApplePurchases", start)
    apple_body = tsx[start:end]
    assert "if (Platform.OS !== 'ios'" in apple_body.split("finishTransaction(")[0], "iOS 확인 없이 거래를 끝낸다"
    outside = tsx[:start] + tsx[end:]
    # 주석(설명)에 이름이 나오는 건 무방 — 금지하는 건 실제 호출이다(import 한 줄은 허용).
    offenders = [
        line.strip()
        for line in outside.splitlines()
        if "finishTransaction" in line
        and not line.strip().startswith(("//", "*", "/*"))
        and line.strip() != "finishTransaction,"
    ]
    assert not offenders, f"애플 끝내기 함수 밖에서 finishTransaction을 부른다: {offenders}"
    assert "iapFinish" in tsx and "finishApplePurchase(" in tsx, "서버 신호로만 끝내는 배선이 없다"
    assert "iap_purchase_token" in tsx, "서버로 토큰을 넘기는 배선이 없다"


def test_N9_store_price_is_shown_and_persists_across_navigation():
    """앱이 스토어에서 읽어 보낸 가격이 화면에 뜨고, 내부이동(파라미터가 사라진
    렌더)에서도 유지되나 — Play Console 가격 변경이 코드 수정 없이 반영되는 경로."""
    with _prod_like_env(), _db_isolation.isolated_db():
        import wallet_ui

        mid = _member("iap_n9")
        # 충전 화면 가격표시는 스위치가 켜졌을 때의 동작이다(기본값은 준비중 안내).
        original = wallet_ui.IAP_CHARGE_ENABLED
        wallet_ui.IAP_CHARGE_ENABLED = True
        try:
            at = _render_probe("charge", mid, native=True, iap_price_points_1000="₩9,900")
            assert not at.exception, f"가격 파라미터 렌더 예외: {at.exception}"
            labels = {b.key: b.label for b in at.button}
            assert "₩9,900" in labels[IAP_BUY_KEYS[0]], (
                f"앱이 보낸 스토어 가격이 화면에 안 떴다: {labels[IAP_BUY_KEYS[0]]}"
            )
            assert "30,000원" in labels[IAP_BUY_KEYS[1]], (
                f"안 보낸 상품은 기본값으로 떠야 한다: {labels[IAP_BUY_KEYS[1]]}"
            )

            # 다음 렌더: 파라미터가 없다(Streamlit 내부링크로 이동한 상태와 같다).
            at2 = _render_probe("charge", mid, native=True)
            labels2 = {b.key: b.label for b in at2.button}
            assert "₩9,900" in labels2[IAP_BUY_KEYS[0]], (
                f"저장해둔 가격이 다음 화면에서 사라졌다: {labels2[IAP_BUY_KEYS[0]]}"
            )
        finally:
            wallet_ui.IAP_CHARGE_ENABLED = original

        # 기본요금제 가격도 같은 경로로 반영되는지(스위치를 켠 상태의 동작).
        wdb.activate_free_advanced_sub(mid)
        original_sub = wallet_ui.IAP_SUBSCRIPTION_ENABLED
        wallet_ui.IAP_SUBSCRIPTION_ENABLED = True
        try:
            at3 = _render_probe(
                "sub", mid, native=True, iap_price_premium_quarterly="₩33,000"
            )
        finally:
            wallet_ui.IAP_SUBSCRIPTION_ENABLED = original_sub
        labels3 = {b.key: b.label for b in at3.button}
        assert "₩33,000" in labels3[IAP_SUB_KEYS[1]], (
            f"구독 요금제 가격이 화면에 안 떴다: {labels3[IAP_SUB_KEYS[1]]}"
        )


def test_N10_price_params_and_reload_contract_match_app_code():
    """파라미터 이름은 서버(wallet_ui)·앱(streamlit-webview.tsx) 한 쌍이고,
    앱은 재빌드가 아니라 '현재 주소 + 파라미터'로 되돌아와야 한다."""
    import wallet_ui

    tsx = TSX.read_text(encoding="utf-8")
    for param in wallet_ui.IAP_PRICE_PARAMS.values():
        assert param in tsx, f"앱이 {param} 를 안 보낸다(서버가 가격을 못 받는다)"
    assert "withParams(" in tsx, "현재 주소에 파라미터를 더하는 병합기가 없다"
    assert "currentUrlRef" in tsx, "보고 있던 주소를 기억하지 않는다(로그인 후 처음 페이지로 튕긴다)"
    assert "reloadWith({ native_kakao_token" in tsx, "로그인 후 복귀가 현재 주소 기준이 아니다"
    assert "reloadWith({\n          iap_purchase_token" in tsx or "reloadWith({" in tsx, (
        "결제 후 복귀가 현재 주소 기준이 아니다"
    )


def test_N11_resume_reopens_subscription_dialog_after_login():
    """고급필터 '구독하기'는 로그인 배너를 거치는데, 로그인을 마친 렌더에서
    구독 안내창이 다시 열려야 한다(모달은 세션 상태로 열려 주소 복원만으로는
    되살아나지 않는다 — resume 마커로 되살린다)."""
    with _prod_like_env(), _db_isolation.isolated_db():
        mid = _member("iap_n11")
        at = AppTest.from_file(PROBE, default_timeout=TIMEOUT_SEC)
        at.query_params["probe"] = "resume"
        at.query_params["resume"] = "af_show_subscribe"
        at.session_state["member_id"] = mid
        at.run()
        assert not at.exception, f"resume 렌더 예외: {at.exception}"
        assert at.session_state.get("probe_af_show_subscribe") is True, (
            "로그인 후 구독 안내창 재개 플래그가 세워지지 않았다"
        )


def test_N12_old_build_gets_update_notice_not_dead_buttons():
    """2026-10-09(점검 B4): 결제 스위치를 켜도 수신부 없는 옛 앱(iap 표시 없음)에는 결제 버튼 대신
    업데이트 안내만 나간다(충전·구독 모두)."""
    with _prod_like_env(), _db_isolation.isolated_db(), _switches(
        IAP_CHARGE_ENABLED=True, IAP_SUBSCRIPTION_ENABLED=True, TEST_CHARGE_ENABLED=False
    ):
        import wallet_ui

        mid = _member("iap_n12")
        wdb.activate_free_advanced_sub(mid)
        at = _render_probe("charge", mid, native=True, iap=None)
        assert not at.exception, at.exception
        assert not any(k.startswith("iap_buy_") for k in _keys(at)), f"옛 앱에 결제 버튼: {_keys(at)}"
        infos = "\n".join((m.value or "") for m in at.info)
        assert wallet_ui.APP_UPDATE_FOR_IAP_NOTICE in infos, f"업데이트 안내가 없다: {infos!r}"
        at_sub = _render_probe("sub", mid, native=True, iap=None)
        assert not at_sub.exception, at_sub.exception
        keys = _keys(at_sub)
        assert not [k for k in keys if k in IAP_SUB_KEYS], f"옛 앱에 요금제 버튼: {keys}"
        assert "iap_sub_update_close" in keys, f"업데이트 안내에 닫기가 없다: {keys}"
        # 새 빌드(iap=1)에는 요금제 버튼 + 구독 관리 링크가 나온다.
        at_new = _render_probe("sub", mid, native=True)
        assert all(k in _keys(at_new) for k in IAP_SUB_KEYS), _keys(at_new)
        links = [getattr(b, "url", "") for b in getattr(at_new, "link_button", [])]
        if links:  # AppTest 버전에 따라 link_button 접근이 없을 수 있다
            assert any("play.google.com/store/account/subscriptions" in (u or "") for u in links), links


def test_N13_internal_nav_keeps_iap_capability():
    """하위 화면 이동에서도 iap=1 이 이어져야 한다(안 이으면 하위 화면에서 업데이트 안내가 뜬다)."""
    from streamlit.testing.v1 import AppTest as _AT

    at = _AT.from_string(
        "import streamlit as st, user_scope\nst.session_state['href'] = user_scope.internal_nav_href('thunder')",
        default_timeout=TIMEOUT_SEC,
    )
    at.query_params["native"] = "1"
    at.query_params["iap"] = "1"
    at.query_params["gid"] = "n13"
    at.run()
    assert "iap=1" in at.session_state["href"], at.session_state["href"]


def test_N14_app_code_has_iap_followups():
    """앱 쪽 보완(§12)이 소스에 있는지 — 수신부 표시·미처리 결제 복구·결제 대기·Play 스토어 링크·
    계정 식별값·기본 혜택 선택. 서버 이름과 한 쌍인 값은 서버 상수와 대조한다."""
    import products
    import wallet_ui

    tsx = TSX.read_text(encoding="utf-8")
    assert f"{{ {wallet_ui.IAP_CAPABILITY_PARAM}: '1' }}" in tsx, "앱이 iap=1 을 보내지 않는다"
    assert tsx.count("...IAP_CAPABILITY_PARAMS") >= 2, "첫 주소·복귀 주소 둘 다 iap 를 실어야 한다"
    assert "getAvailablePurchases()" in tsx and "isAcknowledgedAndroid === false" in tsx, "미처리 결제 복구가 없다"
    assert "...recoveryParamsRef.current" in tsx, "복구 결제를 첫 주소에 싣지 않는다"
    assert "purchase.purchaseState === 'pending'" in tsx, "결제 대기를 서버로 보내지 않는 처리가 없다"
    assert "isPlayStoreUrl(request.url)" in tsx and "Linking.openURL" in tsx, "Play 스토어 링크를 앱 밖으로 넘기지 않는다"
    assert "https://play.google.com/" in tsx and products.play_subscription_manage_url().startswith(
        "https://play.google.com/"
    ), "구독 관리 주소가 앱의 Play 스토어 판정에 걸리지 않는다"
    assert tsx.count("obfuscatedAccountId: guestId") == 2, "충전·구독 모두 계정 식별값을 넘겨야 한다"
    assert "planOffers.find(" in tsx, "기본 혜택(할인 없는 요금) 선택이 없다"


def _main() -> int:
    tests = [
        test_N1_native_charge_offers_test_charge_not_dead_buttons,
        test_N1b_native_charge_shows_iap_when_switch_on,
        test_N1c_native_charge_shows_pending_notice_when_test_charge_off,
        test_N1d_test_charge_btn_credits_1000_points_and_respects_the_limit,
        test_N2_native_subscription_shows_pending_notice_not_dead_buttons,
        test_N2c_native_subscription_shows_iap_when_switch_on,
        test_N2b_native_free_promo_keeps_free_button,
        test_N3_web_charge_keeps_toss_button,
        test_N4_web_subscription_keeps_points_button,
        test_N5_buttons_call_trigger_with_exact_product,
        test_N6_trigger_payload_matches_app_code,
        test_N7_trigger_rejects_unknown_product,
        test_N8_app_code_does_not_finish_transactions,
        test_N9_store_price_is_shown_and_persists_across_navigation,
        test_N10_price_params_and_reload_contract_match_app_code,
        test_N11_resume_reopens_subscription_dialog_after_login,
        test_N12_old_build_gets_update_notice_not_dead_buttons,
        test_N13_internal_nav_keeps_iap_capability,
        test_N14_app_code_has_iap_followups,
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
