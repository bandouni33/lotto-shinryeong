"""저장내역 2열 배치를 "5개 조각(chunk) 단위"로 바꾼 것의 불변식 (2026-10-04 사용자 지시).

바뀐 것:
  · combo_history_ui: 같은 회차·같은 소스의 조합을 **저장 묶음(batch) 경계와 무관하게**
    5개씩 끊어(CHUNK_SIZE) 순서대로 좌/우로 짝짓는다.
  · page_auto: `allocated[:5]` 로 잘라 앞 5개만 그리던 것을 없앴다 — 5개 초과분이 화면에서
    통째로 사라지던 데이터 누락의 원인이었다(배치 문제가 아니라 렌더 절단).

이 테스트가 고정하는 것:
  C1 조각 규칙(모든 입력): 임의 개수 n에 대해 순서 보존·전부 1회씩·조각 크기 ≤5·
     왼쪽 조각은 비지 않음·오른쪽이 비는 건 그 쌍이 홀수 조각일 때뿐.
  C2 강조 규칙: 가장 최근 저장분에서만 나온 조각만 True(섞인 조각·옛 조각은 False).
  C3 5개씩 따로 2번 저장(회귀): 조각이 배치와 그대로 맞아 **예전과 같은 모양**이고,
     강조는 새로 저장된 배치의 조각에만 붙는다.
  C4 15개 한 번에: 5+5+5 세 조각이 전부 나오고(데이터 누락 없음) 셋 다 강조된다.
  C5 7+3처럼 섞인 경우: 두 번째 조각은 강조하지 않는다(일부만 새것인 카드 방지).
  C6 page_auto 렌더 절단 제거: 15개를 넘겨도 15줄이 나온다(카드·페어카드 양쪽).
  C7 조립(번개조합): 실제 저장 데이터로 패널을 띄워 15개가 **화면 마크다운에 전부** 있고
     강조 조각 수가 기대와 같은지.
  C8 조립(자동조합): 위와 같은 성질을 page_auto 저장내역에서.
  C9 안티/액땜(2소스) 분기는 그대로: 배지(전체/개별)가 붙은 짝 카드 경로가 살아 있다
     (이번 변경이 그쪽 페어링을 건드리지 않았음을 잠근다).
  C10 진입점(app.py)을 사용자가 열듯 띄워 15개가 전부 보이는지.
  C11 조각이 원본 배치의 회차(draw_round)를 물려받아 **당첨번호·보너스 동그라미**가
     살아남는지(조각이 메타를 잃으면 동그라미가 조용히 사라진다).
  C12 조각의 `combo_count`(= "N개 배정" 라벨값)가 **실제 조각 크기**와 같은지.
  C13 짝 카드 강조는 왼쪽·오른쪽 조각을 **각각 독립 판정**한다(2026-10-05) — 왼쪽만
     새것이면 왼쪽 열만, 양쪽 다 새것이면 카드 전체(예전 모양), 둘 다 아니면 없음.
  C8(2026-10-05 보강) 자동구매도 같은 규칙 — 최신 구매(왼쪽) 열만 강조, 카드 전체 X.
  C14 조립(번개조합): 5개씩 2번 저장 → 짝 카드에서 새 저장분(왼쪽) 열만 강조되고
     옛 저장분(오른쪽)은 강조되지 않는다(예전엔 카드 전체가 깜박였다).

2026-10-05 정정:
  · __main__ 러너가 TestCase를 그대로 호출해 실패를 삼켰다(전부 PASS로 찍힘) →
    unittest 러너로 교체. 그 결과 드러난 실패를 아래처럼 원인별로 고쳤다.
  · C4: 테스트 자체 계산 오류(15개면 마지막 쌍의 오른쪽이 비는데 그걸 조각으로 셌다).
  · C10/C11: 격리 문제가 아니라 **시험 데이터 결함** — _combo(11)이 [11,11,…]로 번호가
    중복돼 DB가 그 조합을 버렸고(15→14, C10), 화면엔 보너스 11이 한 줄에 2번 찍혔다
    (15→16, C11). 채움 번호를 21~45로 바꿔 1~15와 겹치지 않게 했다.
    데이터를 고치자 C10에서 계산 오류가 하나 더 드러났다 — 줄 수를 클래스 이름으로
    세서 <style> 안의 CSS 선택자까지 잡혔다(15→21). 실제 줄 div만 세도록 고쳤다.
  · 강조 개수는 "강조된 마크다운 덩어리 수"가 아니라 **강조된 조각 수**로 센다
    (짝 카드 1개 = 조각 2개라 덩어리 수로는 실제 강조 범위를 못 본다).
  C15 `_chunk_batch` 자체의 불변식(모든 회차값·조각 크기): 카드 함수가 먹는 모양이고,
     회차를 잃지 않고, 조합 순서가 그대로다.
  C16 여러 구매 건에 걸친 조각(한 조각이 두 구매분을 섮는 경우) 보존: 화면에 그려진
     조합이 구매 순서 그대로 정확히 1회씩, 조각 크기 ≤ 5, 라벨값 = 조각 크기.

DB는 _db_isolation.isolated_db()로만 만진다. 실행:
  venv312\\Scripts\\python.exe -X utf8 tests\\test_history_chunk_pairing.py
"""

from __future__ import annotations

import os
import sys
import time
import unittest
import uuid
from pathlib import Path

from streamlit.testing.v1 import AppTest

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _path in (str(ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import _db_isolation  # noqa: E402
import combo_history_ui as chu  # noqa: E402

TIMEOUT_SEC = 60
BLINK_FLAG = "thunder_history_blink"
NEEDLE = 'history-just-saved"'

_PANEL_APP = r"""
import streamlit as st
import combo_history_ui as chu

gid = st.query_params.get("gid")
if isinstance(gid, (list, tuple)):
    gid = gid[0] if gid else ""
chu.render_history_section(
    container_key="hh_zone_6n36s5",
    blink_flag_key="thunder_history_blink",
    guest_id=gid,
    sources=["thunder"],
)
"""

_HEDGE_PANEL_APP = r"""
import streamlit as st
import combo_history_ui as chu

gid = st.query_params.get("gid")
if isinstance(gid, (list, tuple)):
    gid = gid[0] if gid else ""
chu.render_history_section(
    container_key="hh_zone_6n36s5",
    blink_flag_key="thunder_history_blink",
    guest_id=gid,
    sources=["aekddaem", "anti"],
)
"""


def _combo(first: int) -> list[int]:
    """첫 번호로 구분되는 6개 조합 — 화면에 그 번호가 나오는지로 확인한다.

    채움 번호(21·22·33·44·45)는 first(1~15)와 절대 겹치지 않아야 한다 — 예전엔 11을
    채움에 써서 _combo(11)=[11,11,…]이 무효 조합이 됐다(2026-10-05 C10/C11 원인)."""
    assert 1 <= first <= 20, first
    return [first, 21, 22, 33, 44, 45]


def _marked(at: AppTest) -> list[str]:
    return [(m.value or "") for m in at.markdown if NEEDLE in (m.value or "")]


def _highlighted_chunks(at: AppTest) -> int:
    """화면에서 '방금 저장' 강조가 붙은 **조각 수**.

    · 열(column) 하나에 붙은 강조 = 조각 1개
    · 짝 카드 전체에 붙은 강조 = 조각 2개(양쪽 다 새것일 때만 카드에 붙는다)
    · 단일 카드에 붙은 강조 = 조각 1개
    """
    total = 0
    for value in ((m.value or "") for m in at.markdown):
        n = value.count(NEEDLE)
        n += value.count("pair-card " + NEEDLE)  # 카드 전체 강조는 조각 2개
        total += n
    return total


def _all_markup(at: AppTest) -> str:
    return "\n".join((m.value or "") for m in at.markdown)


class ChunkMathTests(unittest.TestCase):
    """C1·C2·C3·C4·C5 — 순수 조각 규칙(모든 입력에 대해)."""

    def test_C1_chunk_pairs_never_loses_or_reorders_items(self):
        for n in range(1, 42):
            items = list(range(n))
            pairs = chu.chunk_pairs(items)
            flat = [x for left, right in pairs for x in (left + right)]
            self.assertEqual(flat, items, f"n={n}: 순서가 바뀌거나 빠졌다")
            for left, right in pairs:
                self.assertTrue(left, f"n={n}: 빈 왼쪽 조각")
                self.assertLessEqual(len(left), chu.CHUNK_SIZE, f"n={n}: 왼쪽 조각 초과")
                self.assertLessEqual(len(right), chu.CHUNK_SIZE, f"n={n}: 오른쪽 조각 초과")
            chunks = [c for left, right in pairs for c in ((left,) if not right else (left, right))]
            self.assertEqual(len(chunks), (n + chu.CHUNK_SIZE - 1) // chu.CHUNK_SIZE,
                             f"n={n}: 조각 개수가 개수/5 와 다르다")

    def test_C2_highlight_only_for_chunks_entirely_from_the_newest_save(self):
        newest_only = [("a", 0), ("b", 0)]
        older_only = [("c", 1), ("d", 1)]
        mixed = [("e", 0), ("f", 1)]
        self.assertTrue(chu.chunk_is_from_newest(newest_only))
        self.assertFalse(chu.chunk_is_from_newest(older_only))
        self.assertFalse(chu.chunk_is_from_newest(mixed), "일부만 새것인 조각을 강조했다")
        self.assertFalse(chu.chunk_is_from_newest([]))

    def test_C3_two_saves_of_five_still_line_up_with_the_batches(self):
        # 회귀: 5개씩 따로 2번 저장 → 조각이 배치와 정확히 일치(예전과 같은 모양),
        # 강조는 새로 저장된 배치(index 0)의 조각에만.
        flat = [(_combo(i + 1), 0) for i in range(5)] + [(_combo(i + 11), 1) for i in range(5)]
        pairs = chu.chunk_pairs(flat)
        self.assertEqual(len(pairs), 1, f"5+5는 한 쌍이어야 한다: {len(pairs)}")
        left, right = pairs[0]
        self.assertTrue(chu.chunk_is_from_newest(left), "새 배치 조각이 강조되지 않았다")
        self.assertFalse(chu.chunk_is_from_newest(right), "옛 배치 조각이 강조됐다")

    def test_C4_fifteen_at_once_shows_three_chunks_all_highlighted(self):
        flat = [(_combo(i + 1), 0) for i in range(15)]
        pairs = chu.chunk_pairs(flat)
        self.assertEqual([len(left) + len(right) for left, right in pairs], [10, 5],
                         "15개는 5+5 / 5 로 나뉘어야 한다")
        chunks = [c for left, right in pairs for c in (left, right) if c]
        self.assertEqual([len(c) for c in chunks], [5, 5, 5])
        self.assertTrue(all(chu.chunk_is_from_newest(c) for c in chunks),
                        "한 번에 저장한 15개 조각이 강조되지 않았다")

    def test_C5_mixed_chunk_is_not_highlighted(self):
        # 7개 + 3개 저장 → 두 번째 조각은 2 + 3 으로 섞인다.
        flat = [(_combo(i + 1), 0) for i in range(7)] + [(_combo(i + 11), 1) for i in range(3)]
        pairs = chu.chunk_pairs(flat)
        self.assertEqual(len(pairs), 1)
        left, right = pairs[0]
        self.assertTrue(chu.chunk_is_from_newest(left))
        self.assertFalse(chu.chunk_is_from_newest(right), "섞인 조각을 강조했다")


class RenderLevelTests(unittest.TestCase):
    """C6·C7·C8·C9 — 실제 렌더 함수/조립된 화면."""

    def test_C6_page_auto_no_longer_truncates_to_five(self):
        import page_auto

        allocated = [{"combo": _combo(i + 1)} for i in range(15)]
        item = {"draw_round": 1245, "combo_count": 15, "cost": 150,
                "allocated": allocated, "purchase_method": "즉시", "order_id": 7}

        rows = page_auto._history_grid_rows_html(item)
        self.assertEqual(rows.count("auto-banner-ball-row"), 15,
                         f"페어카드 줄이 15개가 아니다: {rows.count('auto-banner-ball-row')}")

        banner = page_auto._purchase_banner_html(item, compact=True)
        self.assertEqual(banner.count("auto-banner-ball-row"), 15,
                         f"단일 카드 줄이 15개가 아니다: {banner.count('auto-banner-ball-row')}")

        for i in range(15):
            self.assertIn(f">{i + 1:02d}<", banner, f"{i + 1}번 조합이 카드에 없다")

    def test_C7_thunder_panel_shows_fifteen_and_highlights_three_chunks(self):
        import marketing_db as mdb

        with _db_isolation.isolated_db():
            gid = "ch" + uuid.uuid4().hex[:8]
            mdb.init_marketing_tables()
            mdb.save_guest_generated_combos(
                gid, "thunder", 1245, [_combo(i + 1) for i in range(15)])
            at = AppTest.from_string(_PANEL_APP, default_timeout=TIMEOUT_SEC)
            at.query_params["gid"] = gid
            at.session_state["member_id"] = 424242
            at.session_state[BLINK_FLAG] = True
            at.run()
            self.assertFalse(at.exception, f"렌더 예외: {at.exception}")
            markup = _all_markup(at)
            missing = [i + 1 for i in range(15) if f">{i + 1:02d}<" not in markup]
            self.assertEqual(missing, [], f"화면에 안 나온 조합: {missing}")
            hl = _highlighted_chunks(at)
            self.assertEqual(hl, 3, f"한 번에 저장한 15개 = 3조각 모두 강조여야 한다: {hl}")

            at.run()  # 새로고침 — 강조는 1회성
            self.assertEqual(_marked(at), [],
                             "강조가 1회성이 아니다(새로고침마다 깜빡인다)")

    def test_C8_auto_history_shows_all_and_highlights_newest_chunk_only(self):
        # 5개씩 2번 구매한 상태(회귀): 10개 전부 보이고 강조는 최신 1조각만.
        app = r"""
import streamlit as st
import combo_history_ui as chu
import page_auto

items = [
    {"draw_round": 1245, "combo_count": 5, "cost": 50, "purchase_method": "즉시",
     "order_id": 7, "allocated": [{"combo": [1, 11, 22, 33, 44, 45]},
                                  {"combo": [2, 11, 22, 33, 44, 45]},
                                  {"combo": [3, 11, 22, 33, 44, 45]},
                                  {"combo": [4, 11, 22, 33, 44, 45]},
                                  {"combo": [5, 11, 22, 33, 44, 45]}]},
    {"draw_round": 1245, "combo_count": 5, "cost": 50, "purchase_method": "즉시",
     "order_id": 6, "allocated": [{"combo": [6, 11, 22, 33, 44, 45]},
                                  {"combo": [7, 11, 22, 33, 44, 45]},
                                  {"combo": [8, 11, 22, 33, 44, 45]},
                                  {"combo": [9, 11, 22, 33, 44, 45]},
                                  {"combo": [10, 11, 22, 33, 44, 45]}]},
]
page_auto._collect_purchase_history_items = lambda mid: (items, False)
st.session_state["auto_history_blink"] = True
chu.render_history_button(
    container_key="auto_purchase_history_zone_6n36s5", blink_flag_key="auto_history_blink"
)
page_auto._render_auto_history_content()
"""
        at = AppTest.from_string(app, default_timeout=TIMEOUT_SEC)
        at.session_state["member_id"] = 424242
        at.run()
        self.assertFalse(at.exception, f"렌더 예외: {at.exception}")
        markup = _all_markup(at)
        missing = [i + 1 for i in range(10) if f">{i + 1:02d}<" not in markup]
        self.assertEqual(missing, [], f"화면에 안 나온 조합: {missing}")
        hl = _highlighted_chunks(at)
        self.assertEqual(hl, 1, f"최신 구매의 조각 1개만 강조여야 한다: {hl}")
        # 2026-10-05: 강조가 붙은 곳이 **최신 구매(왼쪽) 열**이어야 한다(카드 전체 X).
        self.assertNotIn("auto-history-pair-card " + NEEDLE, markup,
                         "자동구매 카드 전체가 강조됐다 — 옛 구매분(오른쪽)까지 깜박인다")
        card = next(v for v in (m.value or "" for m in at.markdown)
                    if '<div class="auto-history-pair-card' in v)
        left_html, right_html = card.split('<div class="auto-history-pair-col', 2)[1:]
        self.assertIn(NEEDLE, left_html, "최신 구매(왼쪽) 열이 강조되지 않았다")
        self.assertIn(">01<", left_html)
        self.assertNotIn(NEEDLE, right_html, "옛 구매(오른쪽) 열이 강조됐다")

    def test_C9_hedge_two_source_pairing_is_untouched(self):
        import marketing_db as mdb

        with _db_isolation.isolated_db():
            gid = "hd" + uuid.uuid4().hex[:8]
            mdb.init_marketing_tables()
            mdb.save_guest_generated_combos(gid, "aekddaem", 1245,
                                            [_combo(i + 1) for i in range(5)])
            time.sleep(0.02)
            mdb.save_guest_generated_combos(gid, "anti", 1245,
                                            [_combo(i + 11) for i in range(5)])
            at = AppTest.from_string(_HEDGE_PANEL_APP, default_timeout=TIMEOUT_SEC)
            at.query_params["gid"] = gid
            at.session_state["member_id"] = 424242
            at.run()
            self.assertFalse(at.exception, f"렌더 예외: {at.exception}")
            markup = _all_markup(at)
            self.assertIn("전체", markup, "전체(액땜) 배지가 사라졌다 — 2소스 짝짓기가 깨졌다")
            self.assertIn("개별", markup, "개별(안티) 배지가 사라졌다")
            self.assertIn("hedge-pair-card", markup, "2소스 짝 카드가 안 그려졌다")


_AUTO_APP_FOR_COUNT = r"""
import streamlit as st
import combo_history_ui as chu
import page_auto

count = __N__
items = [
    {"draw_round": 1245, "combo_count": count, "cost": 10 * count,
     "purchase_method": "즉시", "order_id": 7,
     "allocated": [{"combo": [i + 1, 21, 22, 33, 44, 45]} for i in range(count)]},
]
page_auto._collect_purchase_history_items = lambda mid: (items, False)
st.session_state["auto_history_blink"] = True
chu.render_history_button(
    container_key="auto_purchase_history_zone_6n36s5", blink_flag_key="auto_history_blink"
)
page_auto._render_auto_history_content()
"""


def _expected_chunks(count: int) -> int:
    return (count + chu.CHUNK_SIZE - 1) // chu.CHUNK_SIZE


class CountCasesTests(unittest.TestCase):
    """사용자 지시의 5/10/15개를 각각, 두 화면(번개조합·자동구매)에서."""

    def _assert_all_shown(self, markup: str, count: int, where: str):
        missing = [i + 1 for i in range(count) if f">{i + 1:02d}<" not in markup]
        self.assertEqual(missing, [], f"{where}: 화면에 안 나온 조합 {missing}")

    def test_thunder_5_10_15_at_once(self):
        import marketing_db as mdb

        for count in (5, 10, 15):
            with _db_isolation.isolated_db():
                gid = "cn" + uuid.uuid4().hex[:8]
                mdb.init_marketing_tables()
                mdb.save_guest_generated_combos(
                    gid, "thunder", 1245, [_combo(i + 1) for i in range(count)])
                at = AppTest.from_string(_PANEL_APP, default_timeout=TIMEOUT_SEC)
                at.query_params["gid"] = gid
                at.session_state["member_id"] = 424242
                at.session_state[BLINK_FLAG] = True
                at.run()
                self.assertFalse(at.exception, f"{count}개 렌더 예외: {at.exception}")
                self._assert_all_shown(_all_markup(at), count, f"번개조합 {count}개")
                self.assertEqual(_highlighted_chunks(at), _expected_chunks(count),
                                 f"번개조합 {count}개: 강조 조각 수가 {_expected_chunks(count)}가 아니다")

    def test_auto_5_10_15_at_once(self):
        for count in (5, 10, 15):
            at = AppTest.from_string(_AUTO_APP_FOR_COUNT.replace("__N__", str(count)),
                                     default_timeout=TIMEOUT_SEC)
            at.session_state["member_id"] = 424242
            at.run()
            self.assertFalse(at.exception, f"{count}개 렌더 예외: {at.exception}")
            self._assert_all_shown(_all_markup(at), count, f"자동구매 {count}개")
            self.assertEqual(_highlighted_chunks(at), _expected_chunks(count),
                             f"자동구매 {count}개: 강조 조각 수가 {_expected_chunks(count)}가 아니다")


REPORT_NAME = "저장내역_5개조각_배치_2026-10-04.txt"


def _report_text() -> str:
    path = ROOT / REPORT_NAME
    assert path.exists(), f"보고서가 없다: {path}"
    return path.read_text(encoding="utf-8")


class ChangeContractTests(unittest.TestCase):
    """이번 변경의 계약 — 보고서가 주장한 것을 코드에서 직접 확인한다.

    보고서는 "기준점은 CHUNK_SIZE=5", "page_auto 절단 제거", "안티/액땜 분기는 그대로",
    "공용 CSS 클래스가 늘지 않았다"고 적고 있다. 문서 주장이 코드와 어긋나는 것은
    이 저장소에서 실제로 반복된 사고라 글로만 두지 않고 코드로 잠근다.
    """

    def test_report_exists_and_states_the_change(self):
        text = _report_text()
        for needle in ("CHUNK_SIZE", "5개", "절단", "안티/액땜"):
            self.assertIn(needle, text, f"보고서에 {needle} 설명이 없다")

    def test_chunk_size_is_the_single_reference_point(self):
        self.assertEqual(chu.CHUNK_SIZE, 5)
        # 두 화면이 같은 값을 쓰는가 — 한쪽에 5를 따로 박으면 조각이 어긋난다.
        ui_src = (ROOT / "combo_history_ui.py").read_text(encoding="utf-8")
        auto_src = (ROOT / "page_auto.py").read_text(encoding="utf-8")
        self.assertIn("chunk_pairs", ui_src)
        self.assertIn("from combo_history_ui import chunk_is_from_newest, chunk_pairs", auto_src)
        self.assertNotIn("range(0, len(items), 10)", auto_src,
                         "page_auto 가 조각 크기를 따로 계산한다(기준점이 둘로 갈라진다)")

    def test_page_auto_never_truncates_the_allocated_list_again(self):
        auto_src = (ROOT / "page_auto.py").read_text(encoding="utf-8")
        self.assertNotIn("allocated[:5]", auto_src, "allocated[:5] 절단이 다시 들어왔다")
        for func in ("_history_grid_rows_html", "_purchase_banner_html"):
            body = auto_src.split(f"def {func}")[1].split("\ndef ")[0]
            self.assertNotIn("[:5]", body,
                             f"{func} 안에 5개 절단이 남아 있다 — 데이터가 다시 사라진다")

    def test_hedge_two_source_branch_still_pairs_by_batch(self):
        ui_src = (ROOT / "combo_history_ui.py").read_text(encoding="utf-8")
        self.assertIn("paired_batch_card_html(", ui_src,
                      "안티/액땜 2소스 짝짓기가 사라졌다")
        # 예전 "배치 2개를 통째로 짝짓기" 호출 패턴이 되살아나면 잡는다.
        self.assertNotIn("same_source_pair_card_html(\n                                group[i], group[i + 1]",
                         ui_src)

    def test_shared_css_classes_did_not_grow(self):
        ui_src = (ROOT / "combo_history_ui.py").read_text(encoding="utf-8")
        auto_src = (ROOT / "page_auto.py").read_text(encoding="utf-8")
        self.assertIn("hedge-pair-card", ui_src, "헤지 카드 클래스가 사라졌다")
        self.assertIn("auto-history-pair-card", auto_src)
        # 새 짝 카드 클래스를 만들지 않았는가(공용 클래스가 늘면 화면 간 간섭 위험).
        import re

        found = set()
        for src in (ui_src, auto_src):
            found |= set(re.findall(r"[a-z-]*pair-card", src))
        self.assertEqual(found, {"hedge-pair-card", "auto-history-pair-card"},
                         f"짝 카드 클래스가 늘었다: {sorted(found)}")


class EntryPointTests(unittest.TestCase):
    """조립 검증 — 진입점(app.py)을 사용자가 열듯 띄워서 15개가 다 보이는지.

    앞의 테스트들은 렌더 함수를 직접 부르거나 데이터를 스텁으로 바꿔 확인했다.
    여기서는 **실제 구매 데이터**(auto_orders + lotto_combinations 배정)를 심고
    app.py?page=auto 를 띄운다 — 조각 배치가 실패하면 5개 초과분이 화면에서
    사라지는데, 그건 렌더 함수 단위 테스트로는 안 잡히는 종류의 고장이다.
    """

    def test_C10_entry_point_shows_all_fifteen_of_one_purchase(self):
        import marketing_db as mdb
        import wallet_db as wdb

        with _db_isolation.isolated_db():
            wdb.init_wallet_tables()
            mdb.init_marketing_tables()
            mid, _new = wdb.get_or_create_member("kakao", "chunk_entry")
            mid = int(mid)
            combos = [_combo(i + 1) for i in range(15)]
            mdb.bulk_insert_lotto_combinations(1245, combos)
            order_id = wdb.create_auto_order(mid, 15, "즉시", "", "", "test:chunk:entry")
            claimed = mdb.allocate_lotto_combinations(1245, 15, order_id)
            self.assertEqual(len(claimed or []), 15, "15개 배정 준비가 안 됐다")
            wdb.complete_auto_order(order_id, 0, 1245, 15)

            at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=TIMEOUT_SEC)
            at.query_params["page"] = "auto"
            at.query_params["gid"] = "chunkentry15"
            at.query_params["native"] = "1"
            at.session_state["member_id"] = mid
            at.session_state["_guest_id"] = "chunkentry15"
            at.session_state["auto_history_blink"] = True
            at.run()
            self.assertFalse(at.exception, f"진입점 렌더 예외: {at.exception}")
            self.assertTrue(at.session_state.get("auto_history_blink_panel_open"),
                            "방금 구매했는데 저장내역 패널이 안 펼쳐졌다")

            markup = _all_markup(at)
            missing = [i + 1 for i in range(15) if f">{i + 1:02d}<" not in markup]
            self.assertEqual(missing, [], f"화면에 안 나온 조합: {missing}")
            # 실제 줄(div)만 센다 — 클래스 이름만 세면 <style> 안의 CSS 선택자까지 잡혀
            # 21로 나온다(2026-10-05 C10 정정: 시험 데이터를 고치자 드러난 계산 오류).
            rows = markup.count('<div class="auto-banner-ball-row">')
            self.assertEqual(rows, 15, f"번호 줄이 15개가 아니다: {rows}(예전엔 5에서 잘렸다)")
            self.assertGreaterEqual(len(_marked(at)), 1,
                                    "방금 구매한 15개가 강조되지 않았다")


_LABEL_PROBE_APP = r"""
import streamlit as st
import combo_history_ui as chu
import page_auto

count = __N__
seen = []
_orig_pair = page_auto._history_pair_card_html
_orig_banner = page_auto._purchase_banner_html


def _pair(left, right, **kwargs):
    seen.append((left, right))
    return _orig_pair(left, right, **kwargs)


def _banner(item, **kwargs):
    seen.append((item, None))
    return _orig_banner(item, **kwargs)


page_auto._history_pair_card_html = _pair
page_auto._purchase_banner_html = _banner
items = [
    {"draw_round": 1245, "combo_count": count, "cost": 10 * count,
     "purchase_method": "즉시", "order_id": 7,
     "allocated": [{"combo": [i + 1, 21, 22, 33, 44, 45]} for i in range(count)]},
]
page_auto._collect_purchase_history_items = lambda mid: (items, False)
st.session_state["auto_history_blink"] = True
page_auto._render_auto_history_content()
st.session_state["_label_probe"] = [
    tuple(
        (None if item is None else (item.get("combo_count"), len(item.get("allocated") or [])))
        for item in pair
    )
    for pair in seen
]
"""


class ChunkMetadataTests(unittest.TestCase):
    """C11·C15 — 조각이 원본 배치의 메타를 물려받는가.

    `_chunk_batch`는 조각을 기존 카드 함수가 먹는 모양으로 감싼다. 그때 회차
    (`draw_round`)를 안 넘기면 `_combo_rows_html`이 당첨번호를 못 찾아 동그라미가
    조용히 사라진다(예외도 로그도 없이 숫자만 남는다) — 그래서 화면 마크다운에서
    직접 센다.
    """

    def test_C11_chunk_keeps_draw_round_so_winner_circles_survive(self):
        import draw_results_db as drdb
        import lotto_stats
        import marketing_db as mdb

        with _db_isolation.isolated_db():
            gid = "dr" + uuid.uuid4().hex[:8]
            mdb.init_marketing_tables()
            drdb.init_draw_results_table()
            drdb.upsert_draw_result(1245, [1, 2, 3, 4, 5, 6], 21)
            # 캐시 키가 (건수, 최신회차)라 다른 테스트와 겹칠 수 있다 — 방금 넣은
            # 당첨번호가 반드시 보이도록 비운다.
            lotto_stats._load_lotto_data_db_cached.clear()
            # 1~6번 조합은 당첨번호를 1개씩(줄 6개), 나머지 9줄은 0개.
            # 21은 보너스번호라(_combo의 채움 번호) 15줄 전부에 정확히 1번씩 붙는다.
            mdb.save_guest_generated_combos(gid, "thunder", 1245,
                                            [_combo(i + 1) for i in range(15)])

            at = AppTest.from_string(_PANEL_APP, default_timeout=TIMEOUT_SEC)
            at.query_params["gid"] = gid
            at.session_state["member_id"] = 424242
            at.session_state[BLINK_FLAG] = True
            at.run()
            self.assertFalse(at.exception, f"렌더 예외: {at.exception}")
            markup = _all_markup(at)
            self.assertEqual(markup.count('<div class="auto-banner-ball-row">'), 15,
                             "조각 렌더가 15줄이 아니다")
            self.assertEqual(markup.count('class="auto-banner-ball auto-banner-ball-hit"'), 6,
                             "당첨 동그라미가 6개가 아니다 — _chunk_batch가 회차를 잃었을 수 있다")
            self.assertEqual(markup.count('class="auto-banner-ball auto-banner-ball-bonus"'), 15,
                             "보너스 동그라미가 15개가 아니다 — 회차·보너스가 조각에 안 실렸다")

    def test_C15_chunk_batch_keeps_round_and_order_for_every_input(self):
        """C11의 일반화 — 화면 한 케이스가 아니라 **모든 회차값·조각 크기**에서.

        `_combo_rows_html`이 읽는 건 draw_round와 combos 둘뿐이므로, 이 둘이 모든
        입력에서 그대로 전달되면 당첨 동그라미도 모든 입력에서 살아남는다.
        """
        for draw_round in (1245, "1245", 0, ""):
            for count in (0, 1, 5, 6, 13):
                part = [(_combo(i + 1), i % 2) for i in range(count)]
                chunk = chu._chunk_batch(draw_round, part)
                self.assertEqual(set(chunk), {"draw_round", "combos"},
                                 "카드 함수가 먹는 배치 모양이 아니다")
                self.assertEqual(chunk["draw_round"], draw_round,
                                 f"회차가 조각에 안 실렸다: {draw_round!r}")
                self.assertEqual(chunk["combos"], [combo for combo, _idx in part],
                                 f"조합 순서가 바뀌거나 빠졌다: {draw_round!r}/{count}")


class ChunkLabelTests(unittest.TestCase):
    """C12 — 조각의 "N개 배정" 라벨값이 실제 조각 크기와 같은가.

    조각을 만들 때 `combo_count`를 안 고치면 "15개 배정"이라 써 놓고 화면엔 5줄만
    나오는 어긋남이 생긴다. 라벨이 그려지는 곳이든 아니든, 카드 함수가 받은 dict의
    (combo_count, 실제 줄 수) 쌍을 그대로 가로채 확인한다.
    """

    def test_C12_chunk_label_matches_the_real_chunk_size(self):
        cases = {5: [(5, 5)], 7: [(5, 5), (2, 2)], 15: [(5, 5), (5, 5), (5, 5)]}
        for count, expected in cases.items():
            at = AppTest.from_string(_LABEL_PROBE_APP.replace("__N__", str(count)),
                                     default_timeout=TIMEOUT_SEC)
            at.session_state["member_id"] = 424242
            at.run()
            self.assertFalse(at.exception, f"{count}개 렌더 예외: {at.exception}")
            probe = at.session_state["_label_probe"]
            flat = [item for pair in probe for item in pair if item is not None]
            self.assertEqual(flat, expected,
                             f"{count}개: 조각별 (라벨값, 실제 줄수)가 기대와 다르다")
            self.assertEqual(sum(rows for _label, rows in flat), count,
                             f"{count}개: 조각 줄 수 합이 구매 개수와 다르다")
            for label, rows in flat:
                self.assertEqual(label, rows, f"{count}개: 라벨값과 실제 줄 수가 어긋난다")
            self.assertNotIn("개 배정", _all_markup(at),
                             "저장내역 카드에 배정 개수 라벨이 생겼다 — 라벨 위치가 바뀌었으면 "
                             "이 테스트도 함께 고쳐야 한다(지금은 구매 완료 배너에만 있다)")


class IndependentHighlightTests(unittest.TestCase):
    """C13·C14 — 짝 카드의 왼쪽·오른쪽 강조를 각각 독립 판정(2026-10-05)."""

    @staticmethod
    def _card(hl_left, hl_right) -> str:
        left = {"draw_round": 1245, "combos": [{"combo": _combo(1)}]}
        right = {"draw_round": 1245, "combos": [{"combo": _combo(2)}]}
        return chu.same_source_pair_card_html(
            left, right, highlight_left=hl_left, highlight_right=hl_right)

    def test_C13_pair_card_highlights_each_side_independently(self):
        card_hl = "hedge-pair-card " + NEEDLE
        left_hl = "hedge-pair-col hedge-pair-col-left " + NEEDLE
        right_hl = '<div class="hedge-pair-col ' + NEEDLE

        html = self._card(True, False)  # 왼쪽만 새것 — 이번 버그의 정확한 재현
        self.assertIn(left_hl, html, "왼쪽 열이 강조되지 않았다")
        self.assertNotIn(card_hl, html, "카드 전체가 강조됐다 — 옛 저장분(오른쪽)까지 깜박인다")
        self.assertNotIn(right_hl, html, "오른쪽(옛 저장분)이 강조됐다")
        self.assertEqual(html.count(NEEDLE), 1)

        html = self._card(False, True)
        self.assertIn(right_hl, html)
        self.assertNotIn(left_hl, html)
        self.assertNotIn(card_hl, html)

        html = self._card(True, True)  # 양쪽 다 새것 → 예전과 같은 모양(카드 1개, 배지 1개)
        self.assertIn(card_hl, html)
        self.assertEqual(html.count(NEEDLE), 1, "양쪽 강조인데 배지가 여러 개 생겼다")

        self.assertNotIn(NEEDLE, self._card(False, False))

        # 기존 호출 호환: highlight=True 는 양쪽 모두 = 카드 전체
        legacy = chu.same_source_pair_card_html(
            {"draw_round": 1245, "combos": [{"combo": _combo(1)}]},
            {"draw_round": 1245, "combos": [{"combo": _combo(2)}]}, highlight=True)
        self.assertIn(card_hl, legacy)

    def test_C14_two_saves_highlight_only_the_new_side(self):
        import marketing_db as mdb

        with _db_isolation.isolated_db():
            gid = "ih" + uuid.uuid4().hex[:8]
            mdb.init_marketing_tables()
            mdb.save_guest_generated_combos(gid, "thunder", 1245,
                                            [_combo(i + 11) for i in range(5)])  # 옛 저장
            time.sleep(0.02)
            mdb.save_guest_generated_combos(gid, "thunder", 1245,
                                            [_combo(i + 1) for i in range(5)])  # 새 저장
            at = AppTest.from_string(_PANEL_APP, default_timeout=TIMEOUT_SEC)
            at.query_params["gid"] = gid
            at.session_state["member_id"] = 424242
            at.session_state[BLINK_FLAG] = True
            at.run()
            self.assertFalse(at.exception, f"렌더 예외: {at.exception}")
            cards = [m.value or "" for m in at.markdown if "hedge-pair-card" in (m.value or "")
                     and "<style" not in (m.value or "")]
            self.assertEqual(len(cards), 1, f"5+5는 짝 카드 1장이어야 한다: {len(cards)}")
            card = cards[0]
            self.assertNotIn("hedge-pair-card " + NEEDLE, card,
                             "카드 전체가 강조됐다 — 옛 저장분까지 깜박인다(이번 버그)")
            left_html, right_html = card.split('<div class="hedge-pair-col', 2)[1:]
            self.assertIn(NEEDLE, left_html, "새 저장분(왼쪽) 열이 강조되지 않았다")
            self.assertIn(">01<", left_html, "왼쪽 열이 새 저장분이 아니다")
            self.assertNotIn(NEEDLE, right_html, "옛 저장분(오른쪽) 열이 강조됐다")
            self.assertIn(">11<", right_html, "오른쪽 열이 옛 저장분이 아니다")
            self.assertEqual(_highlighted_chunks(at), 1)


_MIXED_ITEMS_APP = r"""
import streamlit as st
import combo_history_ui as chu
import page_auto

counts = [__COUNTS__]
seen = []
_orig_pair = page_auto._history_pair_card_html
_orig_banner = page_auto._purchase_banner_html


def _pair(left, right, highlight=False):
    seen.append((left, right))
    return _orig_pair(left, right, highlight=highlight)


def _banner(item, **kwargs):
    seen.append((item, None))
    return _orig_banner(item, **kwargs)


page_auto._history_pair_card_html = _pair
page_auto._purchase_banner_html = _banner

items = []
for order_idx, count in enumerate(counts):
    base = 20 * order_idx
    items.append(
        {
            "draw_round": 1245,
            "combo_count": count,
            "cost": 10 * count,
            "purchase_method": "즉시",
            "order_id": 100 - order_idx,
            "allocated": [
                {"combo": [base + i + 1, 11, 22, 33, 44, 45]} for i in range(count)
            ],
        }
    )

page_auto._collect_purchase_history_items = lambda mid: (items, False)
st.session_state["auto_history_blink"] = True
page_auto._render_auto_history_content()


def _snap(item):
    if item is None:
        return None
    return (
        item.get("combo_count"),
        [tuple(alloc.get("combo") or []) for alloc in (item.get("allocated") or [])],
    )


st.session_state["_chunks"] = [tuple(_snap(one) for one in pair) for pair in seen]
st.session_state["_expected"] = [
    tuple(alloc["combo"]) for item in items for alloc in item["allocated"]
]
"""


class CrossItemChunkTests(unittest.TestCase):
    """C16 — 한 조각이 두 구매분을 섮을 때도 보존되는가(일반 입력).

    C12는 구매 1건씩 따로 본다. 실제로는 여러 건이 같은 회차에 쌓이므로 5의 배수가
    아닌 크기를 이어 붙이면 **한 조각이 두 구매분을 섮는다**(예: 7+2 → 마지막 조각이
    4개). 그때도 화면에 나온 조합이 구매 순서 그대로 정확히 1회씩인지, 라벨값이
    실제 조각 크기인지, 조각이 5개를 넘지 않는지를 화면에 들어간 dict로 확인한다.
    """

    def test_C16_cross_item_chunks_lose_nothing_and_keep_the_order(self):
        counts = [15, 7, 2]
        at = AppTest.from_string(_MIXED_ITEMS_APP.replace("__COUNTS__", ", ".join(map(str, counts))),
                                 default_timeout=TIMEOUT_SEC)
        at.session_state["member_id"] = 424242
        at.run()
        self.assertFalse(at.exception, f"렌더 예외: {at.exception}")

        chunks = [one for pair in at.session_state["_chunks"] for one in pair if one is not None]
        expected = [tuple(combo) for combo in at.session_state["_expected"]]
        total = sum(counts)

        for label, combos in chunks:
            self.assertEqual(label, len(combos),
                             f"라벨값({label})과 실제 조각 크기({len(combos)})가 다르다")
            self.assertGreaterEqual(len(combos), 1)
            self.assertLessEqual(len(combos), chu.CHUNK_SIZE,
                                 f"조각이 {chu.CHUNK_SIZE}개를 넘었다")

        rendered = [combo for _label, combos in chunks for combo in combos]
        self.assertEqual(len(rendered), total, "화면에 나온 조합 수가 구매 개수와 다르다")
        self.assertEqual(rendered, expected,
                         "조각 배치가 조합을 빠뜨리거나 중복시키거나 순서를 바꿨다")
        self.assertEqual(len(chunks), -(-total // chu.CHUNK_SIZE),
                         "조각 개수가 ceil(전체 개수/5)가 아니다")
        # 이 케이스(15+7+2=24)의 마지막 조각은 4개고, 그 안에 두 구매분이 섮인다.
        # (번호가 base+1..base+count, base=20*구매순서라 (n-1)//20 이 구매 순서다.)
        origin_counts = [len({(combo[0] - 1) // 20 for combo in combos}) for _label, combos in chunks]
        self.assertGreaterEqual(max(origin_counts), 2,
                                "한 조각이 두 구매분을 섮는 경우가 안 만들어졌다(테스트가 헛돌았다)")


def _main() -> int:
    tests = [
        ChunkMathTests("test_C1_chunk_pairs_never_loses_or_reorders_items"),
        ChunkMathTests("test_C2_highlight_only_for_chunks_entirely_from_the_newest_save"),
        ChunkMathTests("test_C3_two_saves_of_five_still_line_up_with_the_batches"),
        ChunkMathTests("test_C4_fifteen_at_once_shows_three_chunks_all_highlighted"),
        ChunkMathTests("test_C5_mixed_chunk_is_not_highlighted"),
        RenderLevelTests("test_C6_page_auto_no_longer_truncates_to_five"),
        RenderLevelTests("test_C7_thunder_panel_shows_fifteen_and_highlights_three_chunks"),
        RenderLevelTests("test_C8_auto_history_shows_all_and_highlights_newest_chunk_only"),
        RenderLevelTests("test_C9_hedge_two_source_pairing_is_untouched"),
        CountCasesTests("test_thunder_5_10_15_at_once"),
        CountCasesTests("test_auto_5_10_15_at_once"),
        ChangeContractTests("test_report_exists_and_states_the_change"),
        ChangeContractTests("test_chunk_size_is_the_single_reference_point"),
        ChangeContractTests("test_page_auto_never_truncates_the_allocated_list_again"),
        ChangeContractTests("test_hedge_two_source_branch_still_pairs_by_batch"),
        ChangeContractTests("test_shared_css_classes_did_not_grow"),
        EntryPointTests("test_C10_entry_point_shows_all_fifteen_of_one_purchase"),
        ChunkMetadataTests("test_C11_chunk_keeps_draw_round_so_winner_circles_survive"),
        ChunkMetadataTests("test_C15_chunk_batch_keeps_round_and_order_for_every_input"),
        ChunkLabelTests("test_C12_chunk_label_matches_the_real_chunk_size"),
        IndependentHighlightTests("test_C13_pair_card_highlights_each_side_independently"),
        IndependentHighlightTests("test_C14_two_saves_highlight_only_the_new_side"),
        CrossItemChunkTests("test_C16_cross_item_chunks_lose_nothing_and_keep_the_order"),
    ]
    # 2026-10-05: 예전엔 test()를 직접 불렀는데, TestCase.__call__ 은 실패를 결과 객체에
    # 담고 예외를 올리지 않아 **실패가 전부 PASS로 찍혔다**. 반드시 결과 객체로 판정한다.
    failed = 0
    for test in tests:
        result = unittest.TestResult()
        test.run(result)
        problems = [("FAIL", tb) for _t, tb in result.failures] + \
                   [("ERROR", tb) for _t, tb in result.errors]
        if result.testsRun != 1:
            problems.append(("ERROR", f"testsRun={result.testsRun}"))
        if problems:
            failed += 1
            for kind, tb in problems:
                last = tb.strip().splitlines()[-1] if tb.strip() else tb
                print(f"{kind} {test._testMethodName}: {last}")
        else:
            print(f"PASS {test._testMethodName}")
        sys.stdout.flush()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.stdout.flush()
    # db_turso 등이 import 시점에 만드는 비데몬 스레드 때문에 프로세스가 스스로 끝나지
    # 않는다(다른 테스트 파일과 같은 현상) — 결과를 다 낸 뒤 즉시 종료한다.
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
