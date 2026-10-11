"""iOS 네이티브에서 결제 버튼이 전혀 뜨지 않는지 — 2026-10-03 (App Store 게시 준비).

무엇을 잠그는가: iOS 는 자체 결제수단을 쓸 수 없어(App Store 심사) 구글플레이·토스·
테스터 Mock 버튼을 하나도 띄우면 안 된다. 그리고 그것이 **안드로이드 스위치 3개를
건드리지 않고** 성립해야 한다 — 스위치는 안드로이드 라이브에 쓰이므로 값이 바뀌면
안 되고, iOS 때문에 분기를 잘못 넓히면 안드로이드가 조용히 망가진다.

  S1 서버가 앱과 같은 파라미터 이름(native_platform)을 읽는다 (교차 계약)
  S2 두 렌더 지점(충전·구독)이 모두 iOS 분기를 갖는다 (한 곳만 고치면 조용히 남는다)
  S3 iOS + 스위치 3개 8조합 전수: 충전 화면에 구글·토스·Mock 버튼 0개 + (애플 수신부 없는 옛 빌드) 업데이트 안내
  S4 iOS 구독: 구글·포인트 요금제 버튼 0개 (무료 프로모는 유지 — 무료 지급은 결제가 아니다)
  S5 대조군(안드로이드): 플랫폼 파라미터가 없으면 기존 동작 그대로 (라이브 회귀 방지)
  S6 (2026-10-09 iOS 반려 2.1(a) 대응) 애플 수신부가 있는 iOS 빌드(iap=1): 애플 결제 버튼만 뜬다,
     스위치 8조합 전부 — 구글·토스·Mock 은 여전히 0개, '준비중' 안내도 없다

DB는 _db_isolation.isolated_db()로만 만진다(운영 Turso 접촉 0). pytest 없이 돌도록
표준 assert + __main__ 러너를 둔다(AGENTS §3).
실행: venv312\\Scripts\\python.exe tests\\test_ios_payment_hidden.py
"""

from __future__ import annotations

import ast
import itertools
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
import wallet_ui  # noqa: E402

PROBE = str(TESTS_DIR / "_iap_probe.py")
WALLET_PATH = ROOT / "wallet_ui.py"
WALLET_SRC = WALLET_PATH.read_text(encoding="utf-8")
TIMEOUT_SEC = 60

PARAM = "native_platform"

# iOS 에서 하나라도 뜨면 안 되는 것들
FORBIDDEN_CHARGE = ("iap_buy_points_1000", "iap_buy_points_3000", "toss_checkout_btn",
                    "test_charge_btn")
FORBIDDEN_SUB = ("iap_sub_monthly", "iap_sub_3month", "adv_sub_confirm",
                 "toss_checkout_btn")

SWITCHES = ("IAP_CHARGE_ENABLED", "IAP_SUBSCRIPTION_ENABLED", "TEST_CHARGE_ENABLED")

_ENV_KEYS = ("KAKAO_REST_API_KEY", "TOSS_CLIENT_KEY", "TOSS_SECRET_KEY", "LOTTO_DEV_MOCK_AUTH")


def _function_source(name: str) -> str:
    tree = ast.parse(WALLET_SRC)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(WALLET_SRC, node) or ""
    raise AssertionError(f"{name} 함수를 wallet_ui.py에서 찾을 수 없다")


@contextmanager
def _prod_like_env():
    """운영과 같은 판정이 나오게 하는 최소 환경변수(끝나면 원복)."""
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


@contextmanager
def _switches(**values):
    import wallet_ui

    before = {name: getattr(wallet_ui, name) for name in values}
    for name, value in values.items():
        setattr(wallet_ui, name, value)
    try:
        yield
    finally:
        for name, value in before.items():
            setattr(wallet_ui, name, value)


def _member(handle: str) -> int:
    wdb.init_wallet_tables()
    mid, _new = wdb.get_or_create_member("kakao", handle)
    return int(mid)


def _render(mode: str, member_id: int, *, native: bool = True,
            platform: str | None = "ios", iap: bool = False) -> AppTest:
    at = AppTest.from_file(PROBE, default_timeout=TIMEOUT_SEC)
    at.query_params["probe"] = mode
    if iap:
        at.query_params["iap"] = "1"
    if native:
        at.query_params["native"] = "1"
    if platform is not None:
        at.query_params[PARAM] = platform
    at.session_state["member_id"] = member_id
    at.run()
    return at


def _keys(at: AppTest) -> list[str]:
    return [b.key for b in at.button if b.key]


def _infos(at: AppTest) -> str:
    return "\n".join((m.value or "") for m in at.info)


def _labels(at: AppTest) -> list[str]:
    return [(b.label or "") for b in at.button]


# ── S1 교차 계약 ─────────────────────────────────────────────
def test_S1_server_reads_the_same_parameter_name():
    assert PARAM in WALLET_SRC, (
        f"서버가 {PARAM} 을 읽지 않는다 — 앱만 보내고 아무도 안 보면 iOS 분기가 죽는다"
    )
    assert "def native_platform() -> str:" in WALLET_SRC, "native_platform() 정의가 없다"
    assert "def in_ios_native_app() -> bool:" in WALLET_SRC, "in_ios_native_app() 정의가 없다"
    # 2026-10-11: 안드로이드 스위치는 구글 결제 출시(B안)로 켰다 — 값과 무관하게 iOS 가 막히는지는 S3 가 8조합 전수로 본다.


# ── S2 두 지점 모두 막혔는가 ─────────────────────────────────
def test_S2_both_render_sites_have_the_ios_guard():
    for name in ("_render_charge_actions", "_render_iap_subscription_options"):
        body = _function_source(name)
        assert "in_ios_native_app()" in body, (
            f"{name} 에 iOS 분기가 없다 — 그 화면에서는 iOS 에 결제 버튼이 그대로 뜬다"
        )


# ── S3 스위치 8조합 전수 ─────────────────────────────────────
def test_S3_ios_charge_hides_every_payment_button_for_all_switch_combos():
    seen = []
    with _prod_like_env(), _db_isolation.isolated_db():
        mid = _member("ios_s3")
        for combo in itertools.product((False, True), repeat=len(SWITCHES)):
            config = dict(zip(SWITCHES, combo))
            with _switches(**config):
                at = _render("charge", mid, platform="ios")
            assert not at.exception, f"iOS 충전 화면 렌더 예외({config}): {at.exception}"
            keys = _keys(at)
            for key in FORBIDDEN_CHARGE:
                assert key not in keys, f"iOS 인데 {key} 가 떴다({config}): {keys}"
            assert not any("Mock 결제" in lab for lab in _labels(at)), (
                f"iOS 인데 Mock 결제 버튼이 그려진다({config}): {_labels(at)}"
            )
            assert wallet_ui.APP_UPDATE_FOR_APPLE_IAP_NOTICE in _infos(at), (
                f"애플 수신부 없는 iOS 빌드인데 업데이트 안내가 없다({config}): {_infos(at)!r}"
            )
            assert not any(k.startswith("apple_") for k in keys), f"옛 iOS 빌드에 애플 버튼이 떴다: {keys}"
            seen.append(config)
    assert len(seen) == 8, f"조합을 다 못 돌았다: {len(seen)}"


# ── S4 구독 ─────────────────────────────────────────────────
def test_S4a_ios_subscription_hides_paid_plans():
    with _prod_like_env(), _db_isolation.isolated_db():
        mid = _member("ios_s4a")
        for enabled in (False, True):
            with _switches(IAP_SUBSCRIPTION_ENABLED=enabled,
                           ADVANCED_FILTER_FIRST_SUB_FREE=False):
                at = _render("sub", mid, platform="ios")
            assert not at.exception, f"iOS 구독 화면 렌더 예외: {at.exception}"
            keys = _keys(at)
            for key in FORBIDDEN_SUB:
                assert key not in keys, (
                    f"iOS 인데 유료 구독 버튼 {key} 가 떴다(IAP_SUBSCRIPTION_ENABLED={enabled}): "
                    f"{keys}"
                )
            assert wallet_ui.APP_UPDATE_FOR_APPLE_IAP_NOTICE in _infos(at), (
                f"애플 수신부 없는 iOS 빌드인데 업데이트 안내가 없다: {_infos(at)!r}"
            )


def test_S4b_ios_keeps_the_free_promo_but_no_paid_plan():
    """무료 프로모는 결제가 아니라 무료 지급이라 iOS 에서도 유지한다(의도된 동작).

    숨기고 싶으면 이 테스트를 뒤집으면 된다 — 지금은 '유지'가 결정이다."""
    import wallet_ui

    with _prod_like_env(), _db_isolation.isolated_db():
        mid = _member("ios_s4b")
        with _switches(ADVANCED_FILTER_FIRST_SUB_FREE=True):
            eligible = bool(wallet_ui.eligible_free_advanced_sub(mid))
            at = _render("sub", mid, platform="ios")
        assert not at.exception
        keys = _keys(at)
        for key in FORBIDDEN_SUB:
            assert key not in keys, f"iOS 인데 유료 구독 버튼이 떴다: {keys}"
        print(f"    (무료 프로모 대상={eligible}, 무료 버튼 표시="
              f"{'iap_free_sub_confirm' in keys})")
        if eligible:
            assert "iap_free_sub_confirm" in keys, (
                "무료 프로모 대상인데 무료 시작 버튼이 없다 — iOS 사용자만 혜택에서 빠진다"
            )
        else:
            assert wallet_ui.APP_UPDATE_FOR_APPLE_IAP_NOTICE in _infos(at)


# ── S5 안드로이드 대조군 ─────────────────────────────────────
def test_S5_android_without_platform_param_is_unchanged():
    """플랫폼 파라미터를 안 보내는 요청(= 안드로이드 라이브·구버전 빌드)은 기존 동작.

    이게 깨지면 iOS 대응이 안드로이드 결제를 꺼버린 것이다."""
    with _prod_like_env(), _db_isolation.isolated_db(), _switches(
        IAP_CHARGE_ENABLED=False, TEST_CHARGE_ENABLED=True,
    ):
        mid = _member("ios_s5")
        at = _render("charge", mid, native=True, platform=None)
        assert not at.exception
        keys = _keys(at)
        assert "test_charge_btn" in keys, (
            f"안드로이드(플랫폼 파라미터 없음)인데 테스터 충전 버튼이 사라졌다: {keys}"
        )
        assert "toss_checkout_btn" not in keys, "앱인데 토스 버튼이 떴다"
        # android 를 명시해 보내도 iOS 분기를 타면 안 된다.
        at2 = _render("charge", mid, native=True, platform="android")
        assert "test_charge_btn" in _keys(at2), "android 인데 iOS 분기를 탔다"


# ── S6 애플 수신부가 있는 iOS 빌드 ─────────────────────────────
def test_S6_ios_with_apple_receiver_shows_only_apple_buttons():
    with _prod_like_env(), _db_isolation.isolated_db():
        mid = _member("ios_s6")
        for combo in itertools.product((False, True), repeat=len(SWITCHES)):
            config = dict(zip(SWITCHES, combo))
            with _switches(**config):
                at = _render("charge", mid, platform="ios", iap=True)
            assert not at.exception, f"iOS(애플) 충전 렌더 예외({config}): {at.exception}"
            keys = _keys(at)
            for key in FORBIDDEN_CHARGE:
                assert key not in keys, f"iOS 인데 {key} 가 떴다({config}): {keys}"
            assert {"apple_buy_points_1000", "apple_buy_points_3000"} <= set(keys), (
                f"애플 결제 버튼이 없다({config}): {keys}"
            )
            assert wallet_ui.CHARGE_PENDING_NOTICE not in _infos(at), "'준비중' 안내가 남았다(반려 사유)"
        with _switches(ADVANCED_FILTER_FIRST_SUB_FREE=False, IAP_SUBSCRIPTION_ENABLED=False):
            at = _render("sub", mid, platform="ios", iap=True)
        assert not at.exception, at.exception
        keys = _keys(at)
        for key in FORBIDDEN_SUB:
            assert key not in keys, f"iOS 구독에 {key} 가 떴다: {keys}"
        assert {"apple_sub_monthly", "apple_sub_3month", "apple_restore"} <= set(keys), keys
        # 2026-10-09(결정 A): 첫 구독 무료 대상이어도 iOS 는 애플 유료 요금제를 함께 보여 준다(심사관이 찾을 수 있게).
        with _switches(ADVANCED_FILTER_FIRST_SUB_FREE=True):
            eligible = bool(wallet_ui.eligible_free_advanced_sub(mid))
            at = _render("sub", mid, platform="ios", iap=True)
        assert not at.exception, at.exception
        keys = _keys(at)
        if eligible:
            assert "iap_free_sub_confirm" in keys, f"무료 시작 버튼이 사라졌다: {keys}"
        assert {"apple_sub_monthly", "apple_sub_3month", "apple_restore"} <= set(keys), (
            f"무료 대상 iOS 화면에 유료 요금제가 없다(심사관이 구독 상품을 못 찾음): {keys}"
        )
        for key in FORBIDDEN_SUB:
            assert key not in keys, f"iOS 구독에 {key} 가 떴다: {keys}"
        assert len([k for k in keys if k in ("iap_free_sub_cancel", "iap_sub_cancel")]) == 1, f"취소 버튼이 겹친다: {keys}"
        with _switches(APPLE_IAP_ENABLED=False):
            at = _render("charge", mid, platform="ios", iap=True)
        assert wallet_ui.CHARGE_PENDING_NOTICE in _infos(at), "iOS 스위치를 끄면 준비중 안내로 돌아가야 한다"
        assert not any(k.startswith("apple_") for k in _keys(at))


def _main() -> int:
    import os as _os

    tests = [
        test_S1_server_reads_the_same_parameter_name,
        test_S2_both_render_sites_have_the_ios_guard,
        test_S3_ios_charge_hides_every_payment_button_for_all_switch_combos,
        test_S4a_ios_subscription_hides_paid_plans,
        test_S4b_ios_keeps_the_free_promo_but_no_paid_plan,
        test_S5_android_without_platform_param_is_unchanged,
        test_S6_ios_with_apple_receiver_shows_only_apple_buttons,
    ]
    failed = 0
    for test in tests:
        try:
            test()
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"ERROR {test.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
        sys.stdout.flush()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.stdout.flush()
    _os._exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
