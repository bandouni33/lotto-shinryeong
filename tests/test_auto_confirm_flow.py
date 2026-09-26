"""자동조합 '확인 후 진행' 뒤에 화면이 어디로 가는지 (2026-09-26 실기기 신고).

신고: 자동조합 화면에서 적립금 이용안내창이 뜨고 '확인 후 진행'을 누르면
      자동조합 화면으로 돌아오지 않고 **메인화면**이 보인다. 문구는 아무것도 없다.

핵심 확인점: 이 앱의 화면은 전부 주소의 page 파라미터로 갈린다
(user_page.py: current_page = st.query_params.get("page", "main")) —
**page가 사라지면 조용히 메인화면이 그려진다**(문구 없음). 그래서 '확인 후 진행' 뒤에
 (1) page가 그대로인지, (2) 자동조합 화면 요소가 그대로 있는지를 실제 진입점에서 본다.

신고 흐름을 그대로 재현하기 위해 조합시작을 누르지 않고 안내창 열림 플래그만 세워둔다
(사용자 제보: "조합시작도 안 했는데 안내창이 떴다"). DB는 isolated_db()로만 만진다.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

from streamlit.testing.v1 import AppTest

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _path in (str(ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import _db_isolation  # noqa: E402
import wallet_db as wdb  # noqa: E402

ENTRY = str(ROOT / "app.py")
TIMEOUT_SEC = 60
AUTO_START_KEY = "auto_purchase_confirm_6n36s5"


def _member_with_points(handle: str, points: int = 50000) -> int:
    wdb.init_wallet_tables()
    mid, _new = wdb.get_or_create_member("kakao", handle)
    mid = int(mid)
    balance = int(wdb.get_balance(mid) or 0)
    if balance < points:
        wdb.charge_points(
            mid, points - balance, f"test:autoflow:{mid}:{uuid.uuid4().hex[:8]}"
        )
    return mid


def _keys(at: AppTest) -> list[str]:
    return [b.key for b in at.button]


def _safe(text: str) -> str:
    """콘솔(cp949)에서 못 찍는 문자(—, ❌ 등) 때문에 테스트 출력이 죽는 것을 막는다."""
    return str(text).encode("ascii", "replace").decode("ascii")


def _messages(at: AppTest) -> str:
    parts = []
    for attr in ("info", "error", "warning", "success", "markdown"):
        for element in getattr(at, attr, []):
            value = getattr(element, "value", None)
            if value:
                parts.append(str(value))
    return " | ".join(parts)


def test_A1_confirm_keeps_the_auto_screen():
    with _db_isolation.isolated_db():
        mid = _member_with_points("auto_flow")
        gid = "autoflow01"

        at = AppTest.from_file(ENTRY, default_timeout=TIMEOUT_SEC)
        at.query_params["page"] = "auto"
        at.query_params["gid"] = gid
        at.query_params["native"] = "1"
        at.session_state["member_id"] = mid
        at.session_state["_guest_id"] = gid
        # 신고 흐름: 조합시작을 누르지 않았는데 적립금 이용안내창이 떠 있는 상태
        at.session_state["auto_show_points"] = True
        at.run()

        assert not at.exception, f"자동조합 렌더 예외: {at.exception}"
        assert AUTO_START_KEY in _keys(at), (
            f"자동조합 화면이 아니다(조합시작 버튼 없음): {_keys(at)}"
        )
        assert "pn_confirm_auto" in _keys(at), (
            f"적립금 이용안내창이 떠 있지 않다: {_keys(at)}"
        )

        # '확인 후 진행' 클릭
        for button in at.button:
            if button.key == "pn_confirm_auto":
                at = button.click().run()
                break
        assert not at.exception, f"확인 후 진행에서 예외: {at.exception}"

        page = at.query_params.get("page")
        page_value = page[0] if isinstance(page, (list, tuple)) else page
        keys = _keys(at)
        assert page_value == "auto", (
            f"확인 후 진행 뒤 page가 바뀌었다(사라지면 메인화면이 그려진다): {page_value!r}"
        )
        assert AUTO_START_KEY in keys, (
            "확인 후 진행 뒤 자동조합 화면이 아니라 다른 화면이 그려졌다: "
            f"버튼={keys} / 문구={_messages(at)!r}"
        )
        print(_safe(f"  (확인 후 진행 뒤 page={page_value!r}, 화면 문구={_messages(at)[:160]!r})"))


def test_A2_confirm_without_login_shows_the_login_hint():
    """로그인 없이 '확인 후 진행'을 누르면 아무 문구도 없던 결함 (2026-09-26).

    page_auto._auto_dialog_close는 current_member_id()가 없으면 조용히 return했다 -
    창만 닫히고 화면에는 아무 안내도 남지 않아 "눌러도 반응이 없다"로 보였다.
    번개조합(page_thunder.py)·안티액땜조합(page_hedge.py)은 같은 자리에서 이미
    login_gate.GATE_INLINE_HINT를 남기고 있었다 - 자동구매만 무음이었다.

    이 테스트는 수정 전에는 실패한다(문구가 없다).
    """
    with _db_isolation.isolated_db():
        gid = "autoflow02"

        at = AppTest.from_file(ENTRY, default_timeout=TIMEOUT_SEC)
        at.query_params["page"] = "auto"
        at.query_params["gid"] = gid
        at.query_params["native"] = "1"
        at.session_state["_guest_id"] = gid
        # 로그인 정보 없음(member_id를 세우지 않는다) - 신고 흐름 그대로.
        at.session_state["auto_show_points"] = True
        at.run()

        assert not at.exception, f"자동조합 렌더 예외: {at.exception}"
        assert "pn_confirm_auto" in _keys(at), (
            f"적립금 이용안내창이 떠 있지 않다: {_keys(at)}"
        )

        for button in at.button:
            if button.key == "pn_confirm_auto":
                at = button.click().run()
                break
        assert not at.exception, f"확인 후 진행에서 예외: {at.exception}"

        page = at.query_params.get("page")
        page_value = page[0] if isinstance(page, (list, tuple)) else page
        assert page_value == "auto", (
            f"확인 후 진행 뒤 page가 바뀌었다: {page_value!r}"
        )
        messages = _messages(at)
        assert "로그인이 필요합니다" in messages, (
            "로그인 없이 확인 후 진행을 눌렀는데 안내 문구가 없다(무음 return): "
            f"화면 문구={messages!r}"
        )
        print(_safe(f"  (로그인 없이 확인 후 진행 뒤 문구={messages[:160]!r})"))


def _main() -> int:
    tests = [
        test_A1_confirm_keeps_the_auto_screen,
        test_A2_confirm_without_login_shows_the_login_hint,
    ]
    failed = 0
    for test in tests:
        try:
            test()
        except AssertionError as exc:
            failed += 1
            print(_safe(f"FAIL {test.__name__}: {exc}"))
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(_safe(f"ERROR {test.__name__}: {type(exc).__name__}: {exc}"))
        else:
            print(f"PASS {test.__name__}")
        sys.stdout.flush()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.stdout.flush()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
