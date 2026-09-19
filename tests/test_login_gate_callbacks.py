"""P0-A 검증 — 로그인 게이트 판정을 st.button(on_click=...) 콜백으로 옮긴 변경의 계약.

바뀐 계약(이 테스트가 지켜야 할 불변식):
  C1. login_gate()는 스스로 st.rerun()을 부르지 않는다(계측: 앱 실행 횟수).
  C2. 게이트 콜백은 렌더 도중 rerun을 하지 않는다 — 배너 플래그만 세우고,
      그 플래그가 세워진 렌더에서 배너 렌더러가 실제로 배너를 그린다.
  C3. 미로그인일 때 원래 동작(확정창 열기/스캐너 요청)은 세팅되지 않는다.
  C4. 로그인된 상태(테스트 기간 자동로그인 포함)면 콜백이 원래 동작을 세팅한다.
  C5. 로그인 완료 후 resume="open_hedge_qr_scan"이 hedge_qr_request를 세운다.
  C6. QR 요청은 한 번만 소비된다(다음 렌더에서 다시 열리지 않는다).
  C7. 5개 지점 전부 st.button(..., on_click=...) 형태이고, 그 콜백 안에는
      st.rerun() 호출이 없다(정적 검사 — DB 없이도 확인 가능한 부분).

환경 제약(중요): 이 샌드박스에는 TURSO_DATABASE_URL / TURSO_AUTH_TOKEN이 없어
`init_wallet_tables()`가 RuntimeError로 죽는다(db_turso.py:239-251). 그래서 실제
진입점 user_page.py는 여기서 실행할 수 없고(= render_wallet_bar를 통한 배너 렌더
전체를 한 번에 보는 테스트는 불가), 그 부분은 standalone 페이지 실행 + 배너
렌더러 단독 실행으로 나눠서 확인한다.

pytest 없이도 돌도록 표준 assert + __main__ 러너를 함께 둔다.
"""

from __future__ import annotations

import ast
import os
import sys
from contextlib import contextmanager
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
# from_string 앱은 임시 디렉터리에서 실행되어 저장소 루트가 sys.path에 없다 —
# 그러면 앱 안의 `from wallet_ui import ...`가 ModuleNotFoundError로 죽는다.
# (첫 실행에서 실제로 이 이유로 테스트가 실패했다.)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TIMEOUT_SEC = 60
THUNDER_PAGE = str(ROOT / "page_thunder.py")
HEDGE_PAGE = str(ROOT / "page_hedge.py")

THUNDER_START_BTN = "th_generate_btn"
HEDGE_QR_BTN = "hedge_qr_scan_btn"
BANNER_CLOSE_BTN = "auth_banner_close_x_btn"  # 배너 폼의 × (배너가 그려졌다는 증거)


def _ss(at: AppTest, key: str, default=None):
    """AppTest의 session_state 프록시에는 .get()이 없다(1.61.1에서 AttributeError) —
    getitem + KeyError로 같은 일을 한다."""
    try:
        return at.session_state[key]
    except KeyError:
        return default


@contextmanager
def _mock_auth_off():
    """테스트 기간 자동로그인(_testing_period_active)을 끈다 — 배너 경로를 태우기 위해.
    이 값은 호출 시점에 os.environ에서 읽히므로 앱 실행 전에 바꾸면 된다."""
    before = os.environ.get("LOTTO_DEV_MOCK_AUTH")
    os.environ["LOTTO_DEV_MOCK_AUTH"] = "0"
    try:
        yield
    finally:
        if before is None:
            os.environ.pop("LOTTO_DEV_MOCK_AUTH", None)
        else:
            os.environ["LOTTO_DEV_MOCK_AUTH"] = before


# ── C1: login_gate가 더 이상 rerun하지 않는다 ─────────────────────────────
_GATE_APP = """
import streamlit as st
st.session_state["runs"] = st.session_state.get("runs", 0) + 1
from wallet_ui import login_gate

if st.button("gate", key="gate"):
    login_gate()
"""

_RERUN_CONTROL_APP = """
import streamlit as st
st.session_state["runs"] = st.session_state.get("runs", 0) + 1
if st.button("gate", key="gate"):
    st.rerun()
"""


def test_run_counter_detects_reruns() -> None:
    """계측 자체의 검출력(대조군) — st.rerun()이 있으면 실행 횟수가 하나 더 늘어난다.

    클릭 한 번은 AppTest에서 (초기 실행 1 + 클릭으로 인한 실행 1)을 만들고,
    핸들러 안의 st.rerun()이 실행을 한 번 더 만든다 → 3.
    """
    at = AppTest.from_string(_RERUN_CONTROL_APP, default_timeout=TIMEOUT_SEC)
    at.run()
    assert at.session_state["runs"] == 1, f"initial runs={at.session_state['runs']}"
    at.button(key="gate").click().run()
    assert at.session_state["runs"] == 3, (
        f"rerun control not detected: runs={at.session_state['runs']} (expected 3)"
    )


def test_login_gate_does_not_rerun() -> None:
    """C1 — 미로그인 게이트 판정은 추가 스크립트 실행(rerun)을 일으키지 않는다."""
    with _mock_auth_off():
        at = AppTest.from_string(_GATE_APP, default_timeout=TIMEOUT_SEC)
        at.run()
        assert len(at.exception) == 0, f"gate app raised on first run: {at.exception}"
        assert at.session_state["runs"] == 1, f"initial runs={at.session_state['runs']}"
        at.button(key="gate").click().run()
        assert len(at.exception) == 0, f"gate app raised: {at.exception}"
        assert at.session_state["runs"] == 2, (
            "login_gate caused an extra script run (rerun) — "
            f"runs={at.session_state['runs']} (expected 2: initial + click)"
        )
        assert _ss(at, "auth_banner_open") is True, "banner flag not set"


# ── C2: 콜백이 세운 플래그를 배너 렌더러가 같은 렌더에서 그린다 ───────────────
_BANNER_APP = """
import streamlit as st
from wallet_ui import open_auth_banner, render_auth_banner

if st.button("gated", key="gated", on_click=lambda: open_auth_banner(resume="open_thunder_dialog")):
    pass

render_auth_banner()
"""


def test_callback_banner_is_rendered_in_same_run() -> None:
    """C2 — on_click 콜백에서 플래그를 세우면, 별도 rerun 없이 그 렌더에서 배너가 그려진다."""
    with _mock_auth_off():
        at = AppTest.from_string(_BANNER_APP, default_timeout=TIMEOUT_SEC)
        at.run()
        assert len(at.exception) == 0, f"banner app raised: {at.exception}"
        assert not any(b.key == BANNER_CLOSE_BTN for b in at.button), (
            "banner must not be drawn before the gated click"
        )

        at.button(key="gated").click().run()
        assert len(at.exception) == 0, f"banner app raised after click: {at.exception}"
        assert _ss(at, "auth_banner_open") is True, "banner flag not set"
        assert any(b.key == BANNER_CLOSE_BTN for b in at.button), (
            "C2: banner was not rendered in the same run as the callback"
        )


# ── C3: 실제 페이지의 게이트 버튼 (미로그인) ─────────────────────────────────
def test_thunder_gate_click_does_not_open_dialog_when_logged_out() -> None:
    """번개조합 조합시작 — 미로그인이면 배너 플래그만 서고 확정창은 열리지 않는다."""
    with _mock_auth_off():
        at = AppTest.from_file(THUNDER_PAGE, default_timeout=TIMEOUT_SEC)
        at.run()
        assert len(at.exception) == 0, f"page render raised: {at.exception}"
        assert any(b.key == THUNDER_START_BTN for b in at.button), "start button not mounted"

        at.button(key=THUNDER_START_BTN).click().run()
        assert len(at.exception) == 0, f"gated click raised: {at.exception}"
        assert _ss(at, "auth_banner_open") is True, (
            "C2/C3: gate did not request the banner in the click run"
        )
        assert not _ss(at, "open_thunder_dialog"), (
            "C3: points dialog must not open while logged out"
        )


def test_hedge_qr_click_does_not_request_scan_when_logged_out() -> None:
    """안티·액땜 QR스캔 — 미로그인이면 스캐너 요청이 세워지지 않는다."""
    with _mock_auth_off():
        at = AppTest.from_file(HEDGE_PAGE, default_timeout=TIMEOUT_SEC)
        at.run()
        assert len(at.exception) == 0, f"page render raised: {at.exception}"
        assert any(b.key == HEDGE_QR_BTN for b in at.button), "QR button not mounted"

        at.button(key=HEDGE_QR_BTN).click().run()
        assert len(at.exception) == 0, f"QR click raised: {at.exception}"
        assert _ss(at, "auth_banner_open") is True, (
            "gate did not request the banner in the click run"
        )
        assert not _ss(at, "hedge_qr_request"), (
            "C3: scanner must not be requested while logged out"
        )


# ── C4/C6: 로그인된 상태의 QR 요청이 한 번만 실행된다 ───────────────────────
def test_hedge_qr_request_fires_exactly_once() -> None:
    """QR스캔(로그인 상태) — 콜백이 요청을 세우고 소비부가 한 번만 집어간다."""
    at = AppTest.from_file(HEDGE_PAGE, default_timeout=TIMEOUT_SEC)
    at.run()
    assert len(at.exception) == 0, f"page render raised: {at.exception}"
    assert any(b.key == HEDGE_QR_BTN for b in at.button), "QR button not mounted"

    at.button(key=HEDGE_QR_BTN).click().run()
    assert len(at.exception) == 0, f"QR click raised: {at.exception}"
    assert not _ss(at, "hedge_qr_request"), (
        "C4/C6: request must be consumed (fired) in the click run, not left pending"
    )

    at.run()  # 사용자가 아무것도 안 누른 다음 렌더
    assert not _ss(at, "hedge_qr_request"), (
        "C6: scanner request must not be re-armed by a plain rerun"
    )


# ── C5: 로그인 완료 후 resume 분기 ─────────────────────────────────────────
_RESUME_APP = """
import streamlit as st
from wallet_ui import _resume_after_auth

st.session_state["auth_resume_flag"] = st.query_params.get("resume")
_resume_after_auth()
st.write("resumed")
"""


def test_resume_open_hedge_qr_scan_sets_request() -> None:
    """C5 — 로그인을 마친 뒤 resume="open_hedge_qr_scan"이 스캐너 요청을 세운다."""
    at = AppTest.from_string(_RESUME_APP, default_timeout=TIMEOUT_SEC)
    at.query_params["resume"] = "open_hedge_qr_scan"
    at.run()
    assert len(at.exception) == 0, f"resume app raised: {at.exception}"
    assert _ss(at, "hedge_qr_request") is True, (
        "C5: open_hedge_qr_scan resume did not set hedge_qr_request"
    )
    assert _ss(at, "auth_resume_flag") is None, (
        "resume flag must be consumed (popped), not left set"
    )


# ── C7: 정적 검사(DB 없이 확인 가능한 부분) ─────────────────────────────────
BUTTON_ONCLICK = {
    "page_thunder.py": "th_generate_btn",
    "page_hedge.py": "hedge_qr_scan_btn",
    "combo_history_ui.py": "_open_btn",
    "wallet_ui.py": "my_info_trigger_btn",
}
CALLBACKS = {
    "page_thunder.py": "_thunder_start_clicked",
    "page_hedge.py": "_hedge_qr_scan_clicked",
    "combo_history_ui.py": "_toggle_history_panel",
    "wallet_ui.py": "_request_my_info_login",
}


def _parse(name: str) -> ast.Module:
    return ast.parse((ROOT / name).read_text(encoding="utf-8"))


def test_gated_buttons_use_on_click_and_callbacks_never_rerun() -> None:
    """C7 — 5개 지점 전부 on_click 형태이고, 콜백 본문에 st.rerun()이 없다."""
    for filename, marker in BUTTON_ONCLICK.items():
        tree = _parse(filename)
        matched = []
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr != "button":
                continue
            key_kw = next((kw for kw in node.keywords if kw.arg == "key"), None)
            if key_kw is None or marker not in ast.unparse(key_kw.value):
                continue
            matched.append(node)
        assert matched, f"{filename}: key에 {marker!r}를 쓰는 st.button을 찾지 못했다"
        assert any(any(kw.arg == "on_click" for kw in n.keywords) for n in matched), (
            f"{filename}: {marker!r} 버튼이 on_click 콜백을 쓰지 않는다"
        )

    for filename, func_name in CALLBACKS.items():
        tree = _parse(filename)
        funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == func_name]
        assert funcs, f"{filename}: 콜백 {func_name!r}을 찾지 못했다"
        reruns = [
            n for n in ast.walk(funcs[0]) if isinstance(n, ast.Call) and ast.unparse(n.func) == "st.rerun"
        ]
        assert not reruns, f"{filename}: 콜백 {func_name!r}이 렌더 도중 st.rerun()을 부른다"


def test_login_gate_rerun_is_scoped_to_page_level_gate_only() -> None:
    """C1(정적) — login_gate 안의 rerun은 dismiss_redirect 분기 하나뿐이어야 한다."""
    tree = _parse("wallet_ui.py")
    funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "login_gate"]
    assert funcs, "wallet_ui.py: login_gate를 찾지 못했다"
    func = funcs[0]
    reruns = [
        n for n in ast.walk(func) if isinstance(n, ast.Call) and ast.unparse(n.func) == "st.rerun"
    ]
    assert len(reruns) == 1, (
        f"login_gate 안의 st.rerun() 호출이 {len(reruns)}건이다 (1건이어야 함)"
    )
    guarded = [
        n for n in ast.walk(func) if isinstance(n, ast.If) and "dismiss_redirect" in ast.unparse(n.test)
    ]
    assert len(guarded) == 1, "login_gate에 dismiss_redirect 분기가 없다"
    assert any(r in ast.walk(guarded[0]) for r in reruns), (
        "남은 st.rerun()이 dismiss_redirect(페이지 전체 게이트) 분기 밖에 있다"
    )


def _main() -> int:
    tests = [
        test_run_counter_detects_reruns,
        test_login_gate_does_not_rerun,
        test_callback_banner_is_rendered_in_same_run,
        test_thunder_gate_click_does_not_open_dialog_when_logged_out,
        test_hedge_qr_click_does_not_request_scan_when_logged_out,
        test_hedge_qr_request_fires_exactly_once,
        test_resume_open_hedge_qr_scan_sets_request,
        test_gated_buttons_use_on_click_and_callbacks_never_rerun,
        test_login_gate_rerun_is_scoped_to_page_level_gate_only,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001 — 러너이므로 무엇이든 보고하고 계속
            failed += 1
            print(f"ERROR {t.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"PASS {t.__name__}")
        sys.stdout.flush()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.stdout.flush()
    # db_turso.py가 import 시점에 만드는 비데몬 스레드풀 때문에 프로세스가 스스로
    # 끝나지 않는다 — 결과를 다 낸 뒤 즉시 종료한다.
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
