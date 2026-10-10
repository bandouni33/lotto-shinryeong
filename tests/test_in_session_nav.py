"""같은 세션 안 화면 이동 시험판(in_session_nav) 잠금 테스트 — 2026-10-10.

  N1 스위치를 끄면 아무것도 그리지 않는다(예전 새로 불러오기 방식 그대로).
  N2 대상 화면(메인·자동조합)에서만 숨은 버튼을 그리고, 자기 화면 버튼은 안 그린다.
  N3 숨은 버튼을 누르면 page 값만 바뀐다(다른 주소 값은 그대로).
  N4 user_page 가 current_page 확정 직후 한 곳에서만 부르고, 공용 새로 읽기 목록에 있다.
  N5 클릭 가로채기 스크립트의 안전장치(버튼 없으면 그냥 링크, 뒤로가기 처리, 12초 해제, stMain 맨 위로).

실행: python tests/test_in_session_nav.py
"""

from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from streamlit.testing.v1 import AppTest  # noqa: E402

import in_session_nav  # noqa: E402

_SCRIPT = """
import sys
sys.path.insert(0, {root!r})
import streamlit as st
import in_session_nav
in_session_nav.IN_SESSION_NAV_ENABLED = {enabled!r}
in_session_nav.render(st.query_params.get("page", "main"))
st.write("PAGE=" + st.query_params.get("page", "main"))
"""


def _app(page: str, enabled: bool = True) -> AppTest:
    at = AppTest.from_string(_SCRIPT.format(root=ROOT, enabled=enabled), default_timeout=30)
    at.query_params["page"] = page
    at.query_params["gid"] = "g-nav-test"
    return at.run()


def _button_keys(at: AppTest) -> set:
    return {b.key for b in at.button}


class InSessionNavTest(unittest.TestCase):
    def test_N1_switch_off_renders_nothing(self):
        at = _app("main", enabled=False)
        self.assertEqual(_button_keys(at), set())

    def test_N2_only_target_pages(self):
        self.assertEqual(_button_keys(_app("main")), {in_session_nav.button_key("auto")})
        self.assertEqual(_button_keys(_app("auto")), {in_session_nav.button_key("main")})
        self.assertEqual(_button_keys(_app("thunder")), set())
        self.assertEqual(in_session_nav.ENABLED_PAGES, ("main", "auto"))

    def test_N3_click_changes_only_page(self):
        at = _app("main")
        at.button(key=in_session_nav.button_key("auto")).click().run()
        self.assertEqual(at.query_params["page"], ["auto"])
        self.assertEqual(at.query_params["gid"], ["g-nav-test"])
        self.assertEqual(_button_keys(at), {in_session_nav.button_key("main")})

    def test_N4_single_call_site(self):
        src = open(os.path.join(ROOT, "user_page.py"), encoding="utf-8").read()
        self.assertEqual(src.count("_in_session_nav.render(current_page)"), 1)
        i_page = src.index('current_page = st.query_params.get("page", "main")')
        self.assertGreater(src.index("_in_session_nav.render(current_page)"), i_page)
        core = src[src.index("_CORE_RELOAD_ORDER = ("):][:400]
        self.assertIn('"in_session_nav"', core)

    def test_N5_script_safety_nets(self):
        html = in_session_nav._installer_html()
        for needle in (
            "if (!btnFor(target)) return;",  # 버튼 없으면 링크 그대로
            "popstate",  # 뒤로가기
            "history.pushState",  # 웹뷰 canGoBack 유지
            "setTimeout(finish, 12000)",  # 끝 신호를 못 받아도 화면 복구
            'stMain\\"]\'); if (m) m.scrollTop = 0',
            "__lnInSessionNavInjected",  # 한 페이지에 한 번만 설치
        ):
            self.assertIn(needle, html, needle)


if __name__ == "__main__":
    unittest.main(verbosity=2)
