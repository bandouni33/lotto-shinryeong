"""내정보 '충전' 버튼 → 충전창이 실제로 열리는지 (2026-09-26 실기기 신고 #1).

신고: 내정보 창에는 '충전' 버튼이 보이는데 눌러도 아무 일도 없다(충전창이 안 뜬다).

이 파일은 그 경로를 **실제 진입점(app.py)** 으로 그대로 밟아 본다 — 내정보 창을 열고,
'충전' 버튼을 누른 뒤, 다음 렌더 화면에 충전창 내용(잔액 표시 + 충전 안내)이 실제로
나오는지 본다. DB는 _db_isolation.isolated_db()로만 만진다.
"""

from __future__ import annotations

import sys
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


def _member(handle: str) -> int:
    wdb.init_wallet_tables()
    mid, _new = wdb.get_or_create_member("kakao", handle)
    return int(mid)


def _open_my_info(mid: int) -> AppTest:
    """메인 화면 + 내정보 창이 열린 상태(앱 경로, native=1)."""
    at = AppTest.from_file(ENTRY, default_timeout=TIMEOUT_SEC)
    at.query_params["page"] = "main"
    at.query_params["gid"] = "chargeentry01"
    at.query_params["native"] = "1"
    at.session_state["member_id"] = mid
    at.session_state["_guest_id"] = "chargeentry01"
    at.session_state["my_info_dialog_open"] = True
    at.run()
    return at


def _keys(at: AppTest) -> list[str]:
    return [b.key for b in at.button]


def _body(at: AppTest) -> str:
    return "\n".join((m.value or "") for m in at.markdown)


def _infos(at: AppTest) -> str:
    return "\n".join((m.value or "") for m in at.info)


def test_C1_my_info_charge_button_opens_charge_dialog():
    with _db_isolation.isolated_db():
        import wallet_ui

        mid = _member("charge_entry")
        at = _open_my_info(mid)
        assert not at.exception, f"진입점 렌더 예외: {at.exception}"
        assert "wallet_charge_btn" in _keys(at), (
            f"내정보 창에 충전 버튼이 없다: {_keys(at)}"
        )

        # 내정보 창의 '충전' 클릭 — 다음 렌더에 충전창 내용이 나와야 한다.
        for button in at.button:
            if button.key == "wallet_charge_btn":
                at = button.click().run()
                break
        assert not at.exception, f"충전 클릭 후 예외: {at.exception}"

        opened = ("현재 잔액" in _body(at)) or (wallet_ui.CHARGE_PENDING_NOTICE in _infos(at))
        assert opened, (
            "충전 버튼을 눌러도 충전창이 뜨지 않는다 - "
            f"화면 요소: 버튼={_keys(at)} 안내={_infos(at)!r}"
        )


def _main() -> int:
    tests = [test_C1_my_info_charge_button_opens_charge_dialog]
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
