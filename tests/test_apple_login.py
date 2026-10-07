"""Apple 로그인(가이드라인 4.8) 계약 — 2026-10-06.

흐름: (1) iOS 앱 배너의 Apple 버튼 → 서버가 앱에 신호(appleNativeLogin / apple_native_trigger)
     (2) 앱이 expo-apple-authentication 으로 로그인해 identity token(JWT)을 native_apple_token 으로 실어 보냄
     (3) 서버가 애플 공개키로 서명·iss·aud(번들 ID)·exp 를 직접 검증 → finalize_login("apple", sub)

  A1. 올바른 토큰 → sub 반환.
  A2. 대상(aud)·발급자(iss)·만료(exp)·서명(다른 키)·알고리즘(none/HS256)·kid 불일치는 전부 거절.
  A3. 서버의 번들 ID 상수 == app.json ios.bundleIdentifier, app.json 에 Apple 로그인 설정이 있다.
  A4. 서버 신호 이름(메시지·URL 파라미터) == 앱 수신부 이름.
  A5. 성공 → finalize_login("apple", sub) 결과 그대로 + 완료 계측 / 실패 → None + 실패 계측(토큰 원문 없음).
  A6. 계측 이벤트는 라벨이 있고 침입 경보 집계에서 빠진다.
  A7. 배너: iOS 앱(native=1, native_platform=ios)에서만 Apple 버튼이 보이고, 누르면 신호 기록이 남는다.
      안드로이드 앱·웹에는 Apple 버튼이 없다(카카오 버튼은 그대로).
  A8. 진입점: 잘못된 native_apple_token 이 와도 화면은 살아 있고 주소에서 토큰·코드가 지워진다.
  A9. 내부이동 링크가 native_platform 을 이어 보낸다(하위 화면에서 iOS 판정이 풀리지 않게).
  A10. 앱 SDK 오류 보고(native_login_error)는 기록되고 주소에서 지워진다.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

from streamlit.testing.v1 import AppTest

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _path in (str(ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import _db_isolation  # noqa: E402

TIMEOUT_SEC = 60
ENTRY = str(ROOT / "app.py")
APP_SRC = ROOT / "LottoShinryeong" / "components" / "streamlit-webview.tsx"
APP_JSON = ROOT / "LottoShinryeong" / "app.json"
KAKAO_BTN = "auth_banner_kakao_native"
APPLE_BTN = "auth_banner_apple_native"


# ── 테스트용 RSA 키·토큰 ──────────────────────────────────────────────────
def _keypair():
    from cryptography.hazmat.primitives.asymmetric import rsa

    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


_KEY = _keypair()
_OTHER_KEY = _keypair()
_KID = "test-kid-1"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _token(claims: dict, *, key=_KEY, kid=_KID, alg="RS256") -> str:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    header = _b64(json.dumps({"alg": alg, "kid": kid}).encode())
    payload = _b64(json.dumps(claims).encode())
    signing_input = f"{header}.{payload}".encode("ascii")
    if alg == "RS256":
        sig = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    else:
        sig = b""
    return f"{header}.{payload}.{_b64(sig)}"


def _claims(**over) -> dict:
    import auth_providers as ap

    now = int(time.time())
    base = {"iss": ap.APPLE_ISSUER, "aud": ap.APPLE_BUNDLE_ID, "exp": now + 600, "iat": now, "sub": "001234.abc.0987"}
    base.update(over)
    return base


def _keys() -> dict:
    return {_KID: _KEY.public_key()}


def _rows(sql: str, params=()) -> list[tuple]:
    conn = sqlite3.connect(_db_isolation.current_path())
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _events(event_type: str) -> list[str]:
    return [r[0] for r in _rows("SELECT detail FROM security_events WHERE event_type = ?", (event_type,))]


@contextlib.contextmanager
def _patched(targets: dict):
    saved = {(mod, name): getattr(mod, name) for (mod, name) in targets}
    try:
        for (mod, name), fn in targets.items():
            setattr(mod, name, fn)
        yield
    finally:
        for (mod, name), fn in saved.items():
            setattr(mod, name, fn)


@contextlib.contextmanager
def _kakao_configured_env():
    before = {k: os.environ.get(k) for k in ("KAKAO_REST_API_KEY", "LOTTO_DEV_MOCK_AUTH")}
    os.environ["KAKAO_REST_API_KEY"] = "test-rest-key"
    os.environ["LOTTO_DEV_MOCK_AUTH"] = "0"
    try:
        yield
    finally:
        for name, value in before.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


# ── A1·A2: 토큰 검증 ──────────────────────────────────────────────────────
def test_a1_valid_token_returns_sub() -> None:
    import auth_providers as ap

    sub, err = ap.verify_apple_identity_token(_token(_claims()), public_keys=_keys())
    assert err is None and sub == "001234.abc.0987", (sub, err)


def test_a1b_jwks_parsing_and_kid_refresh() -> None:
    """애플 JWKS(JSON) → 공개키 변환과, 모르는 kid 가 오면 한 번 새로 받는 동작(네트워크는 대역)."""
    import auth_providers as ap

    pub = _KEY.public_key().public_numbers()
    jwk = {"kty": "RSA", "kid": _KID, "use": "sig", "alg": "RS256",
           "n": _b64(pub.n.to_bytes((pub.n.bit_length() + 7) // 8, "big")),
           "e": _b64(pub.e.to_bytes((pub.e.bit_length() + 7) // 8, "big"))}
    calls = []

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"keys": [jwk]}

    def _get(url, timeout=None):
        calls.append(url)
        return _Resp()

    saved = dict(ap._APPLE_JWKS_CACHE)
    ap._APPLE_JWKS_CACHE.update({"at": 0.0, "keys": {}})
    try:
        with _patched({(ap.requests, "get"): _get}):
            sub, err = ap.verify_apple_identity_token(_token(_claims()))
            assert err is None and sub == "001234.abc.0987", (sub, err)
            ap.verify_apple_identity_token(_token(_claims()))  # 캐시 사용
            assert calls == [ap.APPLE_JWKS_URL], f"캐시가 안 먹었다: {calls}"
            sub, err = ap.verify_apple_identity_token(_token(_claims(), kid="rotated"))
            assert sub is None and len(calls) == 2, "모르는 kid 에 대해 한 번 새로 받아야 한다"
    finally:
        ap._APPLE_JWKS_CACHE.clear()
        ap._APPLE_JWKS_CACHE.update(saved)


def test_a2_invalid_tokens_are_rejected() -> None:
    import auth_providers as ap

    now = int(time.time())
    cases = {
        "다른 앱(aud)": _token(_claims(aud="com.other.app")),
        "다른 발급자(iss)": _token(_claims(iss="https://evil.example.com")),
        "만료(exp)": _token(_claims(exp=now - 3600)),
        "다른 키 서명": _token(_claims(), key=_OTHER_KEY),
        "알고리즘 none": _token(_claims(), alg="none"),
        "알고리즘 HS256": _token(_claims(), alg="HS256"),
        "kid 불일치": _token(_claims(), kid="unknown-kid"),
        "sub 없음": _token(_claims(sub="")),
        "형식 오류": "abc.def",
        "빈 값": "",
    }
    for label, tok in cases.items():
        sub, err = ap.verify_apple_identity_token(tok, public_keys=_keys())
        assert sub is None and err, f"{label} 토큰이 통과했다: {sub!r}"
    # 페이로드를 바꿔치기(서명은 원본)해도 거절
    good = _token(_claims())
    h, _p, s = good.split(".")
    forged = ".".join([h, _b64(json.dumps(_claims(sub="attacker")).encode()), s])
    sub, err = ap.verify_apple_identity_token(forged, public_keys=_keys())
    assert sub is None, "페이로드 위조 토큰이 통과했다"


# ── A3·A4: 앱과 서버의 이름·설정 일치 ─────────────────────────────────────
def test_a3_bundle_id_and_app_config() -> None:
    import auth_providers as ap

    cfg = json.loads(APP_JSON.read_text(encoding="utf-8"))["expo"]
    assert cfg["ios"]["bundleIdentifier"] == ap.APPLE_BUNDLE_ID, "토큰 aud 검사 기준(번들 ID)이 앱과 다르다"
    assert cfg["ios"].get("usesAppleSignIn") is True, "app.json 에 usesAppleSignIn 이 없다(권한 미부여)"
    assert "expo-apple-authentication" in cfg["plugins"], "expo-apple-authentication 플러그인이 없다"


def test_a4_trigger_names_match_app_receivers() -> None:
    import wallet_ui

    src = APP_SRC.read_text(encoding="utf-8")
    for provider, (message, param) in wallet_ui.NATIVE_LOGIN_TRIGGERS.items():
        assert f"payload?.type === '{message}'" in src, f"앱이 {provider} 메시지({message})를 안 받는다"
        assert f"'{param}=1'" in src, f"앱이 {provider} URL 신호({param})를 안 본다"
    assert "native_apple_token:" in src and "AppleAuthentication.signInAsync" in src
    assert "requestedScopes: []" in src, "이름·이메일을 요청하면 처리방침('OAuth 프로필 보관 안 함')과 어긋난다"
    assert f"{{ {wallet_ui.APPLE_LOGIN_CAPABILITY_PARAM}: '1' }}" in src, "앱이 Apple 수신부 표시를 안 보낸다"


# ── A5·A6: 로그인 완료와 계측 ─────────────────────────────────────────────
def test_a5_finalize_success_and_failure() -> None:
    import auth_providers as ap

    calls = []
    with _db_isolation.isolated_db():
        with _patched({
            (ap, "verify_apple_identity_token"): lambda tok: ("apple_sub_1", None),
            (ap, "finalize_login"): lambda provider, uid: calls.append((provider, uid)) or (5, True, True),
        }):
            assert ap.finalize_login_with_apple_token("tok") == (5, True, True)
        assert calls == [("apple", "apple_sub_1")]
        assert len(_events("apple_native_login_ok")) == 1

        secret = "eyJ.secret.token"
        with _patched({(ap, "verify_apple_identity_token"): lambda tok: (None, "Apple 토큰 서명 불일치")}):
            assert ap.finalize_login_with_apple_token(secret) is None
        failed = _events("apple_native_login_fail")
        assert len(failed) == 1 and "서명" in failed[0] and secret not in failed[0], failed


def test_a5b_real_member_row_is_created_as_apple() -> None:
    """실제 회원 생성 경로(격리 DB) — provider='apple' 회원이 만들어지고 같은 sub 는 같은 회원이다."""
    import auth_providers as ap

    with _db_isolation.isolated_db():
        first = ap.login_member("apple", "apple_sub_xyz")
        again = ap.login_member("apple", "apple_sub_xyz")
        assert first[1] is True and again[1] is False and first[0] == again[0], (first, again)
        rows = _rows("SELECT provider FROM members WHERE id = ?", (first[0],))
        assert rows == [("apple",)], rows


def test_a6_events_labelled_and_not_alerts() -> None:
    import security_log

    events = ("apple_native_trigger", "apple_native_login_ok", "apple_native_login_fail", "native_login_error")
    with _db_isolation.isolated_db():
        for e in events:
            security_log.log_event(e, "probe")
        assert security_log.count_recent_events(hours=24) == 0, "계측 이벤트가 침입 경보로 집계됐다"
    for e in events:
        assert e in security_log.EVENT_LABELS, e


# ── A7: 배너 ──────────────────────────────────────────────────────────────
_BANNER_APP = """
from wallet_ui import open_auth_banner, render_auth_banner

open_auth_banner()
render_auth_banner()
"""


def _banner(platform: str | None, native: bool = True, capable: bool = True) -> AppTest:
    at = AppTest.from_string(_BANNER_APP, default_timeout=TIMEOUT_SEC)
    at.query_params["page"] = "main"
    at.query_params["gid"] = "gidapple" + (platform or "web") + ("c" if capable else "n")
    if native:
        at.query_params["native"] = "1"
    if platform:
        at.query_params["native_platform"] = platform
    if capable and platform == "ios":
        at.query_params["apple_login"] = "1"
    at.run()
    return at


def test_a7_apple_button_only_on_ios_app() -> None:
    with _kakao_configured_env():
        with _db_isolation.isolated_db():
            ios = _banner("ios")
            keys = [b.key for b in ios.button]
            assert KAKAO_BTN in keys and APPLE_BTN in keys, f"iOS 앱에 두 버튼이 다 있어야 한다: {keys}"
            ios.button(key=APPLE_BTN).click().run()
            assert len(ios.exception) == 0, ios.exception
            assert len(_events("apple_native_trigger")) == 1, "Apple 신호 기록이 없다"
            assert _events("kakao_native_trigger") == [], "Apple 을 눌렀는데 카카오 신호가 나갔다"

            android = _banner("android")
            keys = [b.key for b in android.button]
            assert KAKAO_BTN in keys and APPLE_BTN not in keys, f"안드로이드에 Apple 버튼이 보인다: {keys}"

            old_build = _banner(None)  # 플랫폼 정보를 안 보내는 구버전 앱
            assert APPLE_BTN not in [b.key for b in old_build.button]

            # 심사 중 build 8·TestFlight build 10 처럼 Apple 수신부가 없는 iOS 빌드: 버튼이 없어야 한다
            ios_old = _banner("ios", capable=False)
            keys = [b.key for b in ios_old.button]
            assert KAKAO_BTN in keys and APPLE_BTN not in keys, f"수신부 없는 빌드에 Apple 버튼: {keys}"


# ── A8·A10: 진입점 ────────────────────────────────────────────────────────
def test_a8_bad_apple_token_keeps_entry_alive() -> None:
    import auth_providers as ap

    with _kakao_configured_env():
        with _db_isolation.isolated_db():
            with _patched({(ap, "verify_apple_identity_token"): lambda tok: (None, "Apple 토큰 만료")}):
                at = AppTest.from_file(ENTRY, default_timeout=TIMEOUT_SEC)
                at.query_params["page"] = "main"
                at.query_params["gid"] = "applefail" + os.urandom(3).hex()
                at.query_params["native"] = "1"
                at.query_params["native_platform"] = "ios"
                at.query_params["native_apple_token"] = "bad.token.value"
                at.query_params["native_apple_code"] = "code123"
                at.run()
            assert len(at.exception) == 0, at.exception
            body = "\n".join((m.value or "") for m in at.markdown)
            assert "점검 중" not in body
            assert at.query_params.get("native_apple_token") in (None, []), "토큰이 주소에 남았다"
            assert at.query_params.get("native_apple_code") in (None, []), "코드가 주소에 남았다"
            assert len(_events("apple_native_login_fail")) == 1


def test_a10_native_login_error_is_recorded() -> None:
    with _kakao_configured_env():
        with _db_isolation.isolated_db():
            at = AppTest.from_file(ENTRY, default_timeout=TIMEOUT_SEC)
            at.query_params["page"] = "main"
            at.query_params["gid"] = "apperr" + os.urandom(3).hex()
            at.query_params["native"] = "1"
            at.query_params["native_login_error"] = "kakao:E001:sdk failure"
            at.run()
            assert len(at.exception) == 0, at.exception
            assert at.query_params.get("native_login_error") in (None, [])
            recorded = _events("native_login_error")
            assert recorded == ["kakao:E001:sdk failure"], recorded


# ── A9: 내부이동 링크 ─────────────────────────────────────────────────────
_NAV_APP = """
import streamlit as st
from user_scope import internal_nav_href
st.markdown(internal_nav_href("thunder"))
"""


def test_a9_internal_links_keep_native_platform() -> None:
    with _db_isolation.isolated_db():
        at = AppTest.from_string(_NAV_APP, default_timeout=TIMEOUT_SEC)
        at.query_params["gid"] = "gidnav1"
        at.query_params["native"] = "1"
        at.query_params["native_platform"] = "ios"
        at.query_params["apple_login"] = "1"
        at.run()
        href = at.markdown[0].value
        assert "native=1" in href and "native_platform=ios" in href and "apple_login=1" in href, href

        web = AppTest.from_string(_NAV_APP, default_timeout=TIMEOUT_SEC)
        web.query_params["gid"] = "gidnav2"
        web.run()
        assert "native_platform" not in web.markdown[0].value, "웹 접속에 플랫폼 값이 생겼다"


def _main() -> int:
    tests = [
        test_a1_valid_token_returns_sub,
        test_a1b_jwks_parsing_and_kid_refresh,
        test_a2_invalid_tokens_are_rejected,
        test_a3_bundle_id_and_app_config,
        test_a4_trigger_names_match_app_receivers,
        test_a5_finalize_success_and_failure,
        test_a5b_real_member_row_is_created_as_apple,
        test_a6_events_labelled_and_not_alerts,
        test_a7_apple_button_only_on_ios_app,
        test_a8_bad_apple_token_keeps_entry_alive,
        test_a9_internal_links_keep_native_platform,
        test_a10_native_login_error_is_recorded,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"ERROR {t.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"PASS {t.__name__}")
        sys.stdout.flush()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
