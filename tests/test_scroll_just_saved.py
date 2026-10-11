"""조합 완료 후 방금 저장한 카드 5줄 보이기 + 고급필터 안내창 같은 세션 닫기 (2026-10-11 사용자 지시).

  S1 공용 함수(combo_history_ui.render_scroll_to_just_saved)가 깜박임 클래스 카드를 겨냥하고 앱 문서(parent)에 심는다.
  S2 자동·번개·번호검증 세 화면이 화면별 사본 없이 공용 함수만 부른다(옛 block:'start' 스크립트 없음).
  S3 고급필터 안내창 닫기는 숨은 버튼(on_click=_save_af_notice_dismiss_today)으로 처리하고, 링크는 남겨 둔다.
  S4 화면 이동 시간 기록은 세션당 10회.
  S5 번호검증 '저장내역' 펼침 → 버튼을 위로 올려 내역이 보이게(공용 함수, 번호검증만 켬).
  S6 타로는 바깥 stApp 만 어둡게(앱 '다 그렸다' 판정 통과) + 보이는 배경은 원래 색.
실측(로컬): 카드 아래 끝이 화면 아래 16px 에 맞춰짐(top 1103→658), 안내창 ✕ 뒤 새로 불러오기 없음.

실행: python tests/test_scroll_just_saved.py
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _src(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


class ScrollJustSavedTest(unittest.TestCase):
    def test_S1_helper(self):
        src = _src("combo_history_ui.py")
        self.assertIn("def render_scroll_to_just_saved", src)
        body = src.split("def render_scroll_to_just_saved", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("JUST_SAVED_CLASS", body)
        body = src.split("def _render_scroll_script", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("window.parent.document", body)
        self.assertNotIn("window.top", body)

    def test_S2_three_screens_use_helper(self):
        for name in ("page_auto.py", "page_thunder.py", "page_hedge.py"):
            src = _src(name)
            self.assertIn("render_scroll_to_just_saved()", src, name)
            self.assertIsNone(
                re.search(r"history_zone_6n36s5'\);\"\s*\+\s*\"if\(el\)\{el\.scrollIntoView", src),
                f"{name}: 옛 저장내역 칸 스크롤 사본이 남아 있다",
            )

    def test_S3_af_notice_in_session(self):
        src = _src("admin_filter.py")
        self.assertIn("_render_af_notice_in_session_dismiss()", src)
        self.assertIn("on_click=_save_af_notice_dismiss_today", src)
        self.assertIn('internal_nav_href("advanced", af_notice="dismiss")', src)

    def test_S5_hedge_scroll_on_open(self):
        ui = _src("combo_history_ui.py")
        self.assertIn("def render_scroll_to_history_top", ui)
        self.assertIn("scroll_on_open: bool = False", ui)
        self.assertIn("scroll_on_open=True", _src("page_hedge.py"))
        for name in ("page_auto.py", "page_thunder.py"):
            self.assertNotIn("scroll_on_open=True", _src(name), name)

    def test_S6_tarot_page_ready_background(self):
        src = _src("user_page.py")
        self.assertIn('== "tarot"', src)
        self.assertIn('[data-testid="stAppViewContainer"]{background-color:#FAF8FF;}', src)

    def test_S4_render_timing_cap(self):
        self.assertRegex(_src("user_page.py"), r"_LN_RT_MAX_PER_SESSION = 10\b")


if __name__ == "__main__":
    unittest.main(verbosity=2)
