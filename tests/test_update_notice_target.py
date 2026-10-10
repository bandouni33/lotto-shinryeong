"""업데이트 안내 배너 대상 판정(wallet_ui.is_outdated_android_app) — 2026-10-10 사용자 승인 B.

안드로이드 구버전 앱(56 이하: native=1 인데 native_platform 없음)에만 True. 웹·iOS·새 빌드는 False.
실행: python tests/test_update_notice_target.py
"""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st  # noqa: E402

import wallet_ui  # noqa: E402

ANDROID_WV = "Mozilla/5.0 (Linux; Android 14; SM-M166S Build/UP1A; wv) AppleWebKit/537.36 Chrome/129 Mobile Safari/537.36"
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148"
DESKTOP = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/129 Safari/537.36"


def _judge(native: str | None, platform: str | None, ua: str) -> bool:
    params = {}
    if native is not None:
        params["native"] = native
    if platform is not None:
        params["native_platform"] = platform

    class _Ctx:
        headers = {"User-Agent": ua}

    with mock.patch.object(wallet_ui.st, "query_params", params), mock.patch.object(wallet_ui.st, "context", _Ctx()):
        return wallet_ui.is_outdated_android_app()


def test_U1_old_android_app_is_target():
    assert _judge("1", None, ANDROID_WV) is True


def test_U2_new_android_app_is_not_target():
    assert _judge("1", "android", ANDROID_WV) is False


def test_U3_ios_apps_are_not_target():
    assert _judge("1", "ios", IPHONE) is False
    assert _judge("1", None, IPHONE) is False  # iOS 구버전도 Play 안내는 맞지 않음


def test_U4_web_is_not_target():
    assert _judge(None, None, ANDROID_WV) is False
    assert _judge(None, None, DESKTOP) is False


def test_U5_user_page_uses_the_single_judge():
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "user_page.py"), encoding="utf-8").read()
    assert "is_outdated_android_app()" in src
    assert 'if _update_notice and _update_notice["version"]:' in src


def _main() -> int:
    tests = [test_U1_old_android_app_is_target, test_U2_new_android_app_is_not_target,
             test_U3_ios_apps_are_not_target, test_U4_web_is_not_target, test_U5_user_page_uses_the_single_judge]
    ok = 0
    for t in tests:
        try:
            t()
            print("PASS", t.__name__)
            ok += 1
        except Exception as e:  # noqa: BLE001
            print("FAIL", t.__name__, repr(e))
    print(f"\n{ok}/{len(tests)} passed")
    return 0 if ok == len(tests) else 1


if __name__ == "__main__":
    sys.exit(_main())
