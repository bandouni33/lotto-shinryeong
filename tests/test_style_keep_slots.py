# -*- coding: utf-8 -*-
"""화면 style 이 다시 그리는 동안 밀려나 풀리지 않게 (2026-10-08, 메인 먼저 — 사용자 승인 A).

  S1 split_style_blocks 는 style 블록만 순서대로 떼어 내고, 나머지 본문은 한 글자도 바꾸지 않는다.
  S2 markdown_keep_styles 는 원래 칸 수를 지킨다 — style 은 st.html(순서 무관 칸), 본문(또는 빈
     칸)은 st.markdown 1개. 칸 수가 바뀌면 화면 간격이 바뀐다.
  S3 메인 화면은 캐릭터(회전 볼)·메뉴 격자 style 을 이 함수로 그리고, 배경색은 순서 무관 칸에도 둔다.
     다른 칸과 우선순위가 얽힌 화면 틀·피드백·순위 줄 style 은 그대로 st.markdown 이다(옮기면
     시뮬레이션에서 여백·접힘 메뉴 색이 바뀌었다).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import shared_ui_styles  # noqa: E402


class StyleKeepSlotTests(unittest.TestCase):
    def test_S1_split(self):
        html = '<style>.a{x:1}</style>\n<div class="a">본문</div>\n<STYLE media="x">.b{y:2}</STYLE> 끝'
        styles, rest = shared_ui_styles.split_style_blocks(html)
        self.assertEqual(styles, '<style>.a{x:1}</style><STYLE media="x">.b{y:2}</STYLE>')
        self.assertEqual(rest, '\n<div class="a">본문</div>\n 끝')
        self.assertEqual(shared_ui_styles.split_style_blocks("<p>x</p>"), ("", "<p>x</p>"))

    def test_S2_slot_count(self):
        calls = []

        class _St:
            def html(self, body):
                calls.append(("html", body))

            def markdown(self, body, unsafe_allow_html=False):
                calls.append(("markdown", body))

        import streamlit

        real = (streamlit.html, streamlit.markdown)
        fake = _St()
        streamlit.html, streamlit.markdown = fake.html, fake.markdown
        try:
            shared_ui_styles.markdown_keep_styles("\n  <style>.a{}</style>\n  ")
            shared_ui_styles.markdown_keep_styles("<style>.b{}</style><div>x</div>")
            shared_ui_styles.markdown_keep_styles("<div>y</div>")
        finally:
            streamlit.html, streamlit.markdown = real
        self.assertEqual(calls, [
            ("html", "<style>.a{}</style>"), ("markdown", ""),
            ("html", "<style>.b{}</style>"), ("markdown", "<div>x</div>"),
            ("markdown", "<div>y</div>"),
        ])

    def test_S3_main_page_usage(self):
        src = (ROOT / "user_page.py").read_text(encoding="utf-8")
        main = src[src.index('if current_page == "main":\n    # 2026-10-08'):]
        main = main[: main.index('\nelif current_page == "thunder":')]
        self.assertIn('st.html("<style>.stApp { background-color: #12182b; }</style>")', main)
        self.assertIn("markdown_keep_styles(_menu_grid_html)", main)
        hero = main[main.index("markdown_keep_styles(f\"\"\""):][:400]
        self.assertIn("@keyframes orbitSpin", hero)
        # 우선순위가 얽힌 칸은 그대로 st.markdown
        for marker in ('.st-key-main_rank_label_badge_row_6n36s5 div[data-testid="stHorizontalBlock"]',
                       '<div class="main-feedback-section-marker" aria-hidden="true"></div>\n<style>'):
            before = main[: main.index(marker)]
            self.assertTrue(before.rstrip().rsplit("\n", 2)[-2:][0].strip().startswith("st.markdown(")
                            or "st.markdown(" in before[-120:], marker)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(StyleKeepSlotTests))
    sys.exit(0 if result.wasSuccessful() else 1)
