# -*- coding: utf-8 -*-
"""iOS 앱에서 Streamlit iframe(about:srcdoc)이 차단되지 않는지 (2026-10-06).

react-native-webview 는 iOS 에서만 iframe 로드까지 originWhitelist 검사를 거친다.
기본값(about:blank + http/https)에는 about:srcdoc 이 없어 components.html 로 넣는
로그인 신호 스크립트·스타일·장식이 iOS 앱에서 전부 사라졌다(카카오 로그인 먹통,
이벤트창 빈칸, 타로 장식 없음, 하단 '더 보러가기' 깨짐).

  W1 WebView 에 originWhitelist 가 실제로 연결돼 있다.
  W2 목록에 about:srcdoc · http · https 가 있다.
  W3 외부 앱 스킴(kakao*, intent)은 목록 밖 — 기존처럼 외부 앱으로 넘긴다.
  W4 react-native-webview 의 판정 방식(접두사 정규식)으로 계산해도 결과가 같다.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "LottoShinryeong" / "components" / "streamlit-webview.tsx"


def _whitelist() -> list[str]:
    m = re.search(r"const WEBVIEW_ORIGIN_WHITELIST = \[([^\]]*)\];", SRC.read_text(encoding="utf-8"))
    assert m, "WEBVIEW_ORIGIN_WHITELIST 상수를 못 찾았다"
    return re.findall(r"'([^']*)'", m.group(1))


def _passes(whitelist: list[str], url: str) -> bool:
    """react-native-webview WebViewShared.passesWhitelist 와 같은 계산."""
    om = re.match(r"^[A-Za-z][A-Za-z0-9+\-.]+:(//)?[^/]*", url)
    origin = om.group(0) if om else ""
    for item in ["about:blank", *whitelist]:
        pattern = "^" + re.escape(item).replace(r"\*", ".*")
        if re.match(pattern, origin):
            return True
    return False


class OriginWhitelistTests(unittest.TestCase):
    def test_W1_prop_is_wired(self):
        src = SRC.read_text(encoding="utf-8")
        self.assertIn("originWhitelist={WEBVIEW_ORIGIN_WHITELIST}", src)

    def test_W2_srcdoc_and_web_allowed(self):
        wl = _whitelist()
        for item in ("about:srcdoc", "http://*", "https://*"):
            self.assertIn(item, wl)

    def test_W3_external_app_schemes_still_go_outside(self):
        wl = _whitelist()
        for url in ("kakaokompassauth://authorize", "kakaotalk://x", "intent://x"):
            self.assertFalse(_passes(wl, url), url)

    def test_W4_rn_webview_rule(self):
        wl = _whitelist()
        for url in ("about:srcdoc", "https://lotto-shinryeong.streamlit.app/~/+/", "about:blank"):
            self.assertTrue(_passes(wl, url), url)
        self.assertFalse(_passes(["http://*", "https://*"], "about:srcdoc"),
                         "기본값에서 about:srcdoc 이 막힌다는 전제(원인)가 깨졌다")


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(OriginWhitelistTests))
    sys.exit(0 if result.wasSuccessful() else 1)
