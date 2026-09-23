"""화면 라벨에 보이지 않는 문자(zero-width space 등)가 섞이지 않는지 고정한다.

배경(2026-09-24): 심사 대비 문구 정리 중 UI 라벨 8곳에 U+200B가 박힌 걸 발견해 제거했다.
그때의 조건을 회귀 테스트로 남긴다 — 보이는 글자는 그대로여야 하고, 글자 사이에
보이지 않는 문자가 끼어 있어서는 안 된다.

불변식(모든 유효 입력에 성립해야 하는 것)
  L1 — 대상 세 파일의 **모든 문자열 리터럴**에 U+200B(ZWSP)·U+FEFF(BOM/ZWNBSP)·
       U+2060(word joiner)이 없다. 소스에 이스케이프로 적혀 있어도(\\u200b) 런타임
       값은 같은 문자이므로, AST로 파싱한 리터럴 값과 원문 텍스트를 둘 다 본다.
       ※ U+200C/U+200D는 제외 — 이모지 결합(ZWJ sequence)처럼 정당한 용도가 있다.
  L2 — 대상 라벨은 **어떤 위치에서도** ZWSP로 쪼갠 형태가 존재하지 않는다.
       삽입 위치를 1..len-1 전부 시도해 확인한다("번개조합"은 "번<ZWSP>개조합"도 아니고
       "번개<ZWSP>조합"도 아니다).
  L3 — 실제 진입점(app.py)을 사용자가 여는 방식 그대로 렌더했을 때 화면에 나가는
       텍스트에도 같은 문자가 없고, 라벨이 온전한 글자로 보인다.

실행: venv312\\Scripts\\python.exe -X utf8 tests\\test_ui_label_invisibles.py
"""

import ast
import os
import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _path in (str(ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import _db_isolation  # noqa: E402
import draw_results_db  # noqa: E402
import lotto_stats  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

ZWSP = "\u200b"
FORBIDDEN = {
    "U+200B ZWSP": "\u200b",
    "U+FEFF ZWNBSP": "\ufeff",
    "U+2060 WORD JOINER": "\u2060",
}
# 런타임에 위 문자로 바뀌는 소스 이스케이프 표기
ESCAPE_TEXTS = ("\\u200b", "\\u200B", "\\U0000200b", "\\U0000200B")

UI_FILES = ("user_page.py", "page_thunder.py", "admin_filter.py")

# L2 대상 — 이번에 ZWSP를 제거한 라벨(보이는 글자 그대로)
EXPECTED_LABELS = {
    "user_page.py": ["로또신령", "번개조합"],
    "page_thunder.py": ["번개조합", "삭제수", "고정수", "행운수"],
    "admin_filter.py": ["프리미엄 패턴 분석 세팅", "나만의 고급필터 (2단계 전용)"],
}


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


class L1NoInvisibleCharsInStringLiterals(unittest.TestCase):
    """소스 레벨 불변식 — 어떤 리터럴에도 보이지 않는 문자가 없다."""

    def test_no_forbidden_chars_in_any_string_literal(self):
        checked = 0
        for rel in UI_FILES:
            tree = ast.parse(_read(rel), filename=rel)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                    continue
                checked += 1
                for name, ch in FORBIDDEN.items():
                    self.assertNotIn(
                        ch, node.value,
                        f"{rel}:{node.lineno} 문자열 리터럴에 {name}가 들어 있다",
                    )
        self.assertGreater(checked, 50, "리터럴을 거의 못 봤다 — 파싱 방식이 틀렸다")

    def test_no_escaped_zwsp_left_in_raw_source(self):
        for rel in UI_FILES:
            text = _read(rel)
            for esc in ESCAPE_TEXTS:
                self.assertNotIn(
                    esc, text,
                    f"{rel} 원문에 {esc} 이스케이프가 남아 있다(런타임 값이 ZWSP가 된다)",
                )


class L2LabelsAreContiguous(unittest.TestCase):
    """비헤이비어 불변식 — 라벨이 쪼개진 형태가 어떤 삽입 위치에도 없다."""

    def test_labels_exist_and_are_never_split_by_zwsp(self):
        for rel, labels in EXPECTED_LABELS.items():
            text = _read(rel)
            for label in labels:
                self.assertIn(label, text, f"{rel}에 '{label}'이 온전한 형태로 없다")
                for i in range(1, len(label)):
                    split = label[:i] + ZWSP + label[i:]
                    self.assertNotIn(
                        split, text,
                        f"{rel}: '{label}'이 {i}번째 글자에서 ZWSP로 쪼개진 형태가 남아 있다",
                    )


class L3RenderedTextHasNoInvisibleChars(unittest.TestCase):
    """조립 검증 — 실제 진입점이 내보내는 텍스트에 같은 문제가 없는지."""

    TIMEOUT_SEC = 90

    def setUp(self):
        # 격리 없이 돌리면 렌더가 운영 Turso에 흔적을 남긴다(tests/_db_isolation.py).
        self._iso = _db_isolation.isolated_db()
        self._iso.__enter__()
        self.addCleanup(self._iso.__exit__, None, None, None)
        draw_results_db.init_draw_results_table()

        original_sync = draw_results_db.sync_latest_from_dhlottery
        draw_results_db.sync_latest_from_dhlottery = lambda: None
        self.addCleanup(setattr, draw_results_db, "sync_latest_from_dhlottery", original_sync)

        for cached in (
            lotto_stats._auto_sync_latest_draw_cached,
            lotto_stats._load_lotto_data_db_cached,
            lotto_stats._number_weights_cached,
        ):
            cached.clear()

        import combo_gen_trigger

        original_trigger = combo_gen_trigger.maybe_trigger_weekly_generation
        combo_gen_trigger.maybe_trigger_weekly_generation = lambda: None
        self.addCleanup(
            setattr, combo_gen_trigger, "maybe_trigger_weekly_generation", original_trigger
        )

    def open_app(self, page: str | None = None) -> AppTest:
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=self.TIMEOUT_SEC)
        if page is not None:
            at.query_params["page"] = page
        at.query_params["gid"] = "invis" + os.urandom(6).hex()
        at.run()
        return at

    @staticmethod
    def _markdown_blob(at: AppTest) -> str:
        return "\n".join((m.value or "") for m in at.markdown)

    def _assert_clean(self, blob: str, where: str) -> None:
        for name, ch in FORBIDDEN.items():
            self.assertNotIn(ch, blob, f"{where} 렌더 결과에 {name}가 들어 있다")

    def test_main_screen_labels_are_plain(self):
        at = self.open_app()
        self.assertEqual(len(at.exception), 0, f"진입점이 예외로 죽었다: {at.exception}")
        blob = self._markdown_blob(at)
        self._assert_clean(blob, "기본 화면")
        self.assertIn("번개조합", blob, "기본 화면에 '번개조합' 라벨이 온전한 글자로 없다")

    def test_thunder_screen_labels_are_plain(self):
        # 탭 라벨(삭제수/고정수/행운수)은 components.html로 내려간다 — 스파이로 모은다.
        # AppTest 하네스 특성상 스파이는 예열 1회 뒤부터 잡힌다(기존 테스트와 동일).
        warm = self.open_app(page="thunder")
        self.assertEqual(len(warm.exception), 0, f"예열 렌더가 예외로 죽었다: {warm.exception}")

        import streamlit.components.v1 as c1

        seen: list[str] = []
        original_html = c1.html
        c1.html = lambda html, **kw: (seen.append(html or ""), original_html(html, **kw))[1]
        try:
            at = self.open_app(page="thunder")
            self.assertEqual(len(at.exception), 0, f"번개조합 화면이 예외로 죽었다: {at.exception}")
            blob = self._markdown_blob(at) + "\n" + "\n".join(seen)
        finally:
            c1.html = original_html

        self._assert_clean(blob, "번개조합 화면")
        self.assertIn("번개조합", blob, "번개조합 화면에 제목 라벨이 온전한 글자로 없다")
        tabs = [t for t in ("삭제수", "고정수", "행운수") if t in blob]
        self.assertEqual(
            tabs, ["삭제수", "고정수", "행운수"],
            f"탭 라벨이 온전한 글자로 안 나온다(잡힌 것: {tabs}, 페이로드 {len(seen)}건)",
        )


if __name__ == "__main__":
    unittest.main()
