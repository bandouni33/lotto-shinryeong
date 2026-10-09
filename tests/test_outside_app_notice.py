# -*- coding: utf-8 -*-
"""앱 주소가 브라우저(크롬)에서 열렸을 때 — 2026-10-09 테스터 신고("앱인데 크롬 화면·QR 안 됨").

서버 기록(10-09 13:34~13:36): native_param='1' wv=0 으로 카카오 로그인 신호만 6번, 응답 0 —
새 창 링크가 앱 주소를 크롬으로 넘겼고, 크롬에는 앱 기능(QR 카메라·카카오 앱 로그인)이 없다.

  O1 판정: 웹 접속·안드로이드 크롬(native=1, 웹뷰 표시 없음)은 '앱 밖', 안드로이드 웹뷰·iOS 앱·UA 없음은 '앱 안'
  O2 번호검증 QR: 앱 밖에서 누르면 스캐너 신호 대신 안내가 뜨고, 앱 안에서는 기존대로(로그인 안내/스캐너)
  O3 카카오 앱 로그인 버튼: 앱 밖에서 누르면 신호 대신 안내, 앱 안에서는 신호를 보낸다
  O4 앱: 새 창 링크(onOpenWindow)는 우리 서버 주소면 앱 안에서, Play 스토어는 Play 앱, 나머지만 외부 브라우저

실행: venv312\\Scripts\\python.exe -X utf8 tests\\test_outside_app_notice.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _p in (str(ROOT), str(TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import _db_isolation  # noqa: E402
import wallet_ui  # noqa: E402

ANDROID_WEBVIEW = "Mozilla/5.0 (Linux; Android 14; SM-S918N Build/UP1A; wv) AppleWebKit/537.36 Chrome/129.0 Mobile Safari/537.36"
ANDROID_CHROME = "Mozilla/5.0 (Linux; Android 14; SM-S918N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Mobile Safari/537.36"
IPHONE_APP = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"

PROBE = """
import streamlit as st, wallet_ui
st.session_state['outside'] = wallet_ui.outside_app_browser()
"""


def _with_ua(ua):
    saved = wallet_ui._user_agent
    wallet_ui._user_agent = lambda: ua
    return saved


def _outside(ua: str, native: bool) -> bool:
    saved = _with_ua(ua)
    try:
        at = AppTest.from_string(PROBE, default_timeout=60)
        if native:
            at.query_params["native"] = "1"
        at.run()
        return bool(at.session_state["outside"])
    finally:
        wallet_ui._user_agent = saved


def test_O1_detection():
    assert _outside(ANDROID_CHROME, native=False) is True, "웹 접속은 앱 밖"
    assert _outside(ANDROID_CHROME, native=True) is True, "앱 주소가 크롬에서 열린 경우는 앱 밖"
    assert _outside(ANDROID_WEBVIEW, native=True) is False, "안드로이드 앱 웹뷰는 앱 안"
    assert _outside(IPHONE_APP, native=True) is False, "iOS 앱은 앱 안(오판으로 막지 않는다)"
    assert _outside("", native=True) is False, "UA 를 못 읽으면 앱 안으로 본다"


def _hedge(ua: str, native: bool, member: int | None):
    saved = _with_ua(ua)
    try:
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
        at.query_params["page"] = "hedge"
        at.query_params["gid"] = "outside_app_test"
        if native:
            at.query_params["native"] = "1"
        if member:
            at.session_state["member_id"] = member
        at.run()
        assert not at.exception, at.exception
        btn = [b for b in at.button if b.key == "hedge_qr_scan_btn"]
        assert btn, "QR스캔 버튼이 없다"
        btn[0].click().run()
        assert not at.exception, at.exception
        return at
    finally:
        wallet_ui._user_agent = saved


def test_O2_hedge_qr_button():
    import wallet_db

    with _db_isolation.isolated_db():
        wallet_db.init_wallet_tables()
        mid, _ = wallet_db.get_or_create_member("kakao", "outside_o2")
        at = _hedge(ANDROID_CHROME, native=True, member=mid)
        errors = " ".join(e.value or "" for e in at.error)
        assert wallet_ui.APP_ONLY_FEATURE_NOTICE in errors, f"크롬에서 QR 을 눌렀는데 안내가 없다: {errors!r}"
        assert not at.session_state["hedge_qr_request"] if "hedge_qr_request" in at.session_state else True
        at_app = _hedge(ANDROID_WEBVIEW, native=True, member=mid)
        errors_app = " ".join(e.value or "" for e in at_app.error)
        assert wallet_ui.APP_ONLY_FEATURE_NOTICE not in errors_app, "앱 안에서도 안내가 떴다(기존 동작 훼손)"


def test_O3_kakao_native_button():
    src = (ROOT / "wallet_ui.py").read_text(encoding="utf-8")
    body = src[src.index("def _fire_native_login_trigger"):src.index("def _fire_kakao_native_login_trigger")]
    guard = body.index("if outside_app_browser():")
    assert guard < body.index("components.html("), "앱 밖 확인이 신호 보내기보다 먼저여야 한다"
    assert "st.warning(APP_ONLY_FEATURE_NOTICE)" in body[guard:body.index("components.html(")]


def test_O4_app_open_window_policy():
    tsx = (ROOT / "LottoShinryeong" / "components" / "streamlit-webview.tsx").read_text(encoding="utf-8")
    assert "onOpenWindow={onOpenWindow}" in tsx, "새 창 요청을 앱이 처리하지 않는다(크롬으로 샌다)"
    handler = tsx[tsx.index("const onOpenWindow = useCallback("):]
    handler = handler[: handler.index("const goToStreamlitHome")]
    assert "isOwnServerUrl(url)" in handler and "setWebViewUri(" in handler, "우리 서버 주소를 앱 안에서 열지 않는다"
    assert "native: '1'" in handler and "...IAP_CAPABILITY_PARAMS" in handler, "앱 신호를 다시 싣지 않는다"
    assert "isPlayStoreUrl(request.url)" in tsx, "Play 스토어 주소 처리(onShouldStartLoad)가 없다"


TESTS = [test_O1_detection, test_O2_hedge_qr_button, test_O3_kakao_native_button, test_O4_app_open_window_policy]


def _main() -> int:
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_main())
