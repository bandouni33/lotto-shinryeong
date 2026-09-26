"""방금 저장한 조합이 화면에서 보이는가 (2026-09-26 사용자 지시).

신고: 자동조합·번개조합·타로에서 조합이 자동저장되는데 아무 반응이 없어서
"방금 한 게 저장된 게 맞나" 의문이 든다 → 가장 최근 저장본을 2~3번 깜빡이게.

기준점은 combo_history_ui 한 곳(카드 HTML + CSS + 플래그 1회 소비)이다.
불변식:
  H1. 방금 저장(blink) 직후에는 패널이 펼쳐지고, 여러 배치 중 **가장 최신 배치
      1개에만** history-just-saved 클래스가 붙는다.
  H2. 그 표시는 1회성이다 — 다시 그리면(새로고침) 붙지 않는다.
  H3. 자동조합(자체 카드 렌더러)도 같은 클래스·같은 CSS를 쓴다.

DB는 _db_isolation.isolated_db()로만 만진다.
"""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

from streamlit.testing.v1 import AppTest

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _path in (str(ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import _db_isolation  # noqa: E402
import marketing_db as mdb  # noqa: E402

TIMEOUT_SEC = 60
BLINK_FLAG = "thunder_history_blink"

# 실제 화면(번개조합)과 같은 경로로 저장내역을 그린다 — 버튼(플래그 소비) →
# 패널(내용) 순서까지 공용 진입점 render_history_section 하나로 돈다.
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


def _marked(at: AppTest) -> list[str]:
    """깜빡임 클래스가 **카드에 붙은** markdown 블록만 고른다.

    history_css()의 <style> 블록에도 같은 문자열(.history-just-saved)이 들어있어서
    단순히 클래스 이름으로 걸러내면 CSS 블록까지 세어진다 — 카드 쪽은
    class="... history-just-saved"> 로 끝나므로 닫는 따옴표까지 포함해 구분한다."""
    needle = f'{mdb_combo_module().JUST_SAVED_CLASS}"'
    return [(m.value or "") for m in at.markdown if needle in (m.value or "")]


def mdb_combo_module():
    import combo_history_ui

    return combo_history_ui


def test_H1_H2_only_the_newest_card_blinks_and_only_once():
    with _db_isolation.isolated_db():
        gid = "hj" + uuid.uuid4().hex[:8]
        mdb.init_marketing_tables()
        # 예전 저장본(다른 회차) → 잠시 뒤 최신 저장본. 최신순 판정은 created_at
        # (마이크로초)이라 순서가 뒤집히지 않도록 최소 간격만 둔다.
        mdb.save_guest_generated_combos(gid, "thunder", 1241, [[11, 12, 13, 14, 15, 16]])
        time.sleep(0.02)
        mdb.save_guest_generated_combos(gid, "thunder", 1242, [[1, 2, 3, 4, 5, 6]])

        at = AppTest.from_string(_PANEL_APP, default_timeout=TIMEOUT_SEC)
        at.query_params["gid"] = gid
        at.session_state["member_id"] = 424242
        at.session_state[BLINK_FLAG] = True
        at.run()
        assert not at.exception, f"저장내역 렌더 예외: {at.exception}"
        assert at.session_state[f"{BLINK_FLAG}_panel_open"] is True, (
            "방금 저장했는데 저장내역 패널이 안 펼쳐졌다"
        )

        marked = _marked(at)
        assert len(marked) == 1, f"깜빡임 표시가 정확히 1개가 아니다: {len(marked)}"
        assert ">01<" in marked[0], "가장 최근 저장본이 아니라 다른 카드가 깜빡인다"
        assert ">11<" not in marked[0], "예전 카드가 깜빡였다"

        at.run()
        assert not at.exception, f"두 번째 렌더 예외: {at.exception}"
        again = _marked(at)
        assert again == [], (
            f"깜빡임이 1회성이 아니다(새로고침마다 다시 깜빡인다): {len(again)}개"
        )
        print(f"  (최신 카드 1개만 표시, 재렌더 시 {len(again)}개)")


def test_H3_auto_cards_use_the_same_class_and_css():
    import combo_history_ui as chu
    import page_auto

    css = chu.history_css()
    assert "@keyframes historyJustSavedBlink" in css, "깜빡임 키프레임이 공용 CSS에 없다"
    assert f".{chu.JUST_SAVED_CLASS}" in css, "깜빡임 클래스 규칙이 공용 CSS에 없다"

    item = {
        "draw_round": 1242,
        "combo_count": 1,
        "cost": 100,
        "allocated": [{"combo": [1, 2, 3, 4, 5, 6]}],
        "purchase_method": "즉시",
        "sms_days": [],
        "order_id": 7,
    }
    marked = page_auto._purchase_banner_html(item, compact=True, highlight=True)
    plain = page_auto._purchase_banner_html(item, compact=True)
    assert chu.JUST_SAVED_CLASS in marked, "자동조합 카드에 깜빡임 클래스가 안 붙는다"
    assert chu.JUST_SAVED_CLASS not in plain, "평소에도 깜빡임 클래스가 붙는다"

    pair_marked = page_auto._history_pair_card_html(item, item, highlight=True)
    pair_plain = page_auto._history_pair_card_html(item, item)
    assert chu.JUST_SAVED_CLASS in pair_marked, "자동조합 짝 카드에 클래스가 안 붙는다"
    assert chu.JUST_SAVED_CLASS not in pair_plain
    print("  (자동조합 카드도 같은 클래스·같은 CSS 사용)")


# 자동조합(자체 렌더러)의 배선 확인 — 저장내역 내용을 그리는 함수 하나로 돈다.
# 데이터 조회만 스텁으로 바꾸고(구매 자체를 재현할 필요는 없다), 플래그 소비는
# 실제 화면과 같이 저장내역 버튼(_resolve_history_panel_state)을 거친다.
_AUTO_APP = r"""
import streamlit as st
import combo_history_ui as chu
import page_auto

items = [
    {
        "draw_round": 1242,
        "combo_count": 1,
        "cost": 100,
        "allocated": [{"combo": [1, 2, 3, 4, 5, 6]}],
        "purchase_method": "즉시",
        "sms_days": [],
        "order_id": 7,
    },
    {
        "draw_round": 1241,
        "combo_count": 1,
        "cost": 100,
        "allocated": [{"combo": [11, 12, 13, 14, 15, 16]}],
        "purchase_method": "즉시",
        "sms_days": [],
        "order_id": 6,
    },
]
page_auto._collect_purchase_history_items = lambda mid: (items, False)

st.session_state["auto_history_blink"] = True
chu.render_history_button(
    container_key="auto_purchase_history_zone_6n36s5", blink_flag_key="auto_history_blink"
)
page_auto._render_auto_history_content()
"""


def test_H4_auto_renderer_marks_only_the_newest_card():
    at = AppTest.from_string(_AUTO_APP, default_timeout=TIMEOUT_SEC)
    at.session_state["member_id"] = 424242
    at.run()
    assert not at.exception, f"자동조합 저장내역 렌더 예외: {at.exception}"

    marked = _marked(at)
    assert len(marked) == 1, f"깜빡임 표시가 정확히 1개가 아니다: {len(marked)}"
    assert ">01<" in marked[0], "자동조합: 가장 최근 저장본이 아니라 다른 카드가 깜빡인다"
    assert ">11<" not in marked[0], "자동조합: 예전 카드가 깜빡였다"
    print("  (자동조합도 최신 카드 1개만 표시)")


def _main() -> int:
    tests = [
        test_H1_H2_only_the_newest_card_blinks_and_only_once,
        test_H3_auto_cards_use_the_same_class_and_css,
        test_H4_auto_renderer_marks_only_the_newest_card,
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
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
