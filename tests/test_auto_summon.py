# -*- coding: utf-8 -*-
"""자동조합 '조합시작' 신령 연출 + 생성 지연 (2026-10-10 사용자 지시).

'확인 후 진행'을 누르면 바로 조합하지 않고, 신령 이미지가 출렁이며 손 위의 볼이 도는 연출을
약 2.5초 보여 준 뒤 조합한다. 처리 로직(적립금 차감·결과 표시)은 예전 확인창 콜백에서 그대로 옮겼다.
복원 지점: 커밋 52c1c56f (이 기능 직전, 로컬 태그 restore-before-auto-anim-20261010).

  U1 평소 이미지는 예전과 같은 정지 원형(연출 클래스 없음), 연출 이미지는 층·문구를 갖고 마스크가 유효한 문법
  U2 대기 주문은 한 번만 처리된다(꺼낸 뒤 처리 — 새로고침·연타로 두 번 차감되지 않음)
  U3 처리 결과별 표시: 성공 → 저장내역 강조·완료 안내 / 부족 → 충전창 / 다음 회차 없음 / 그 밖 실패
  U4 적립금이 모자라면 연출 없이 곧장 처리(충전창이 2.5초 늦게 뜨지 않게)
  U5 확인창 콜백은 직접 조합하지 않고 대기 주문만 남긴다(연출 자리에서 처리)

실행: venv312\\Scripts\\python.exe -X utf8 tests\\test_auto_summon.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _p in (str(ROOT), str(TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import _db_isolation  # noqa: E402
import page_auto  # noqa: E402
import wallet_db as wdb  # noqa: E402


def test_U1_image_blocks():
    idle = page_auto._spirit2_image_block("QUJD", "auto-spirit2-slot-right")
    assert "auto-summon" not in idle and "auto-spirit2-summoning" not in idle, "평소 이미지에 연출이 섞였다"
    assert idle.count("<img") == 1
    on = page_auto._spirit2_image_block("QUJD", "auto-spirit2-slot-right", summoning=True)
    for cls in ("auto-spirit2-summoning", "auto-summon-wave", "auto-summon-orbs", "auto-summon-glow"):
        assert cls in on, f"연출 층 {cls} 가 없다"
    assert page_auto.AUTO_SUMMON_CAPTION in on
    css = page_auto._summon_css()
    assert "circle 15%" not in css and "circle {" not in css, "원 반지름 % 는 브라우저가 무시한다(볼 마스크가 사라짐)"
    assert "ellipse 15% 15% at 63% 78.5%" in css
    assert 2.0 <= page_auto.AUTO_SUMMON_SECONDS <= 3.0, "사용자 요청 2~3초"


_SCRIPT = """
import streamlit as st, page_auto, auto_purchase_service
page_auto.AUTO_SUMMON_SECONDS = 0
calls = st.session_state.setdefault('calls', [])
outcome = st.session_state['outcome']
def fake(*a, **k):
    calls.append(a)
    return dict(outcome)
auto_purchase_service.process_auto_purchase = fake
page_auto._purchase_history_entry = lambda *a, **k: {'stub': True}
page_auto._append_purchase_history = lambda entry: st.session_state.setdefault('hist', []).append(entry)
st.session_state[page_auto._AUTO_SUMMON_KEY] = {'member_id': 7, 'quantity': 5, 'method': '즉시', 'phone': '', 'sms_days': []}
st.session_state['r1'] = page_auto._run_pending_auto_purchase('QUJD')
st.session_state['r2'] = page_auto._run_pending_auto_purchase('QUJD')
"""


def _run(outcome: dict) -> AppTest:
    at = AppTest.from_string(_SCRIPT, default_timeout=60)
    at.session_state["outcome"] = outcome
    at.run()
    assert not at.exception, at.exception
    return at


def test_U2_pending_runs_once():
    at = _run({"ok": True})
    assert at.session_state["r1"] is True and at.session_state["r2"] is False
    assert len(at.session_state["calls"]) == 1, "대기 주문이 두 번 처리됐다(이중 차감)"
    assert page_auto._AUTO_SUMMON_KEY not in at.session_state
    md = " ".join(m.value for m in at.markdown)
    assert page_auto.AUTO_SUMMON_CAPTION in md, "연출을 그리지 않고 처리했다"


def test_U3_outcomes():
    at = _run({"ok": True})
    assert at.session_state["auto_generation_complete"] and at.session_state["auto_history_blink"]
    assert at.session_state["hist"] == [{"stub": True}]
    at = _run({"ok": False, "error": "insufficient_balance", "cost": 50})
    import wallet_ui

    assert at.session_state[wallet_ui.INSUFFICIENT_BALANCE_OPEN] is True
    assert at.session_state[wallet_ui.INSUFFICIENT_BALANCE_NEED] == 50
    at = _run({"ok": False, "error": "next_draw_pool_missing", "message": "다음 회차 준비 중"})
    assert at.session_state["auto_purchase_error"] == "다음 회차 준비 중"
    at = _run({"ok": False, "error": "boom"})
    assert at.session_state["auto_purchase_error"] == "구매 처리에 실패했습니다."


def test_U4_balance_precheck():
    with _db_isolation.isolated_db():
        wdb.init_wallet_tables()
        mid, _ = wdb.get_or_create_member("kakao", "summon_u4")
        need = wdb.calc_auto_cost(5)
        bal = wdb.get_balance(mid)
        assert page_auto._has_enough_points(mid, 5) == (bal >= need)
        assert page_auto._has_enough_points(mid, 10_000) is False


def test_U5_callback_defers():
    src = (ROOT / "page_auto.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    body = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_auto_dialog_close":
            body = ast.get_source_segment(src, node)
    assert body, "_auto_dialog_close 를 못 찾았다"
    assert "_AUTO_SUMMON_KEY" in body, "확인창이 연출 대기 주문을 남기지 않는다"
    assert "process_auto_purchase(" not in body, "확인창 안에서 바로 조합한다(연출 없이 즉시)"
    assert "_has_enough_points" in body and "_execute_auto_purchase(" in body
    render_src = src[src.index("def render():"):]
    assert "if _run_pending_auto_purchase(spirit2_base64):" in render_src


TESTS = [test_U1_image_blocks, test_U2_pending_runs_once, test_U3_outcomes, test_U4_balance_precheck,
         test_U5_callback_defers]


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
