"""조합 '확인 후 진행' 콜백의 불변식 — 2026-09-27 재현(scratch/repro_tester_blocks2.py)에서 파생.

신고: 일반(자동)조합·번개조합의 적립금 이용안내창에서 "확인 후 진행"을 눌러도
      창만 닫히고 조합시작 화면으로 돌아온다(반복해도 동일).

실제 진입점(app.py)으로 안내창을 띄운 상태를 만들어 확인 버튼까지 밟아 보고,
그때 실제로 나온 출력을 아래 불변식으로 고정한다. 앱 코드는 건드리지 않는다.

  G1. 자동조합 — 다음회차 조합 풀이 없으면 **포인트가 나가지 않고**(차감 0)
      사유 문구가 화면에 남는다(무음 return이 아니다).
  G2. 자동조합 — 잔액이 0이어도 차감은 0이고 화면에 사유가 남는다(음수 잔액 없음).
  G3. 번개조합 — 잔액이 부족하면 차감 0 + 부족/충전창이 뜬다(충전 수단이 노출된다).
  G4. [현재 동작 고정] 번개조합은 판매창·다음회차 풀 게이트가 없어 **확인 즉시**
      차감한다(자동조합에는 있는 게이트가 이 화면에만 없다). 조합 생성은 번호판
      iframe의 JS(poolCombos)가 하므로 그 뒤 실패는 화면 문구로 남지 않는다 —
      나중에 이 화면에 게이트를 넣으면 G4가 먼저 깨져 알려준다.

DB는 tests/_db_isolation.py의 isolated_db()로만 만진다(운영 Turso 접속 금지).
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

from streamlit.testing.v1 import AppTest

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _path in (str(ROOT), str(TESTS_DIR), str(ROOT / "tarot")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import _db_isolation  # noqa: E402
import auto_purchase_service as aps  # noqa: E402
import wallet_db as wdb  # noqa: E402
import wallet_ui  # noqa: E402

ENTRY = str(ROOT / "app.py")
TIMEOUT_SEC = 90
GAMES_DEFAULT = 5


def _safe(text: object) -> str:
    """콘솔(cp949)에서 못 찍는 문자 때문에 프로세스가 죽는 것을 막는다."""
    return str(text).encode("ascii", "replace").decode("ascii")


def _keys(at: AppTest) -> list[str]:
    return [b.key for b in at.button]


def _screen_text(at: AppTest) -> str:
    """화면에 실제로 찍힌 글자 전부 — 배너는 st.error/div(markdown)로 나간다."""
    parts: list[str] = []
    for attr in ("error", "warning", "info", "success"):
        for element in getattr(at, attr, []):
            value = getattr(element, "value", None)
            if value:
                parts.append(str(value))
    for element in at.markdown:
        value = getattr(element, "value", None)
        if value:
            parts.append(str(value))
    return "\n".join(parts)


def _member(handle: str, points: int) -> tuple[int, int]:
    wdb.init_wallet_tables()
    mid, _new = wdb.get_or_create_member("kakao", handle)
    mid = int(mid)
    balance = int(wdb.get_balance(mid) or 0)
    if points > balance:
        wdb.charge_points(mid, points - balance, f"gate:{mid}:{uuid.uuid4().hex[:8]}")
    return mid, int(wdb.get_balance(mid) or 0)


def _open_notice(kind: str, points: int, native: bool = True) -> tuple[AppTest, int, int]:
    """안내창이 떠 있는 상태의 화면과 (member_id, 시작잔액)을 돌려준다.

    native=False는 앱이 보낸 native=1이 유실된(=서버가 웹으로 판정한) 요청이다.
    """
    flag_key = "auto_show_points" if kind == "auto" else "open_thunder_dialog"
    page = "auto" if kind == "auto" else "thunder"
    gid = f"gate{kind}{points}{int(native)}"
    mid, balance = _member(f"gate_{kind}_{points}_{int(native)}", points)

    at = AppTest.from_file(ENTRY, default_timeout=TIMEOUT_SEC)
    at.query_params["page"] = page
    at.query_params["gid"] = gid
    if native:
        at.query_params["native"] = "1"
    at.session_state["member_id"] = mid
    at.session_state["_guest_id"] = gid
    at.session_state[flag_key] = True
    at.run()
    assert not at.exception, f"{kind} 화면 렌더 예외: {at.exception}"
    return at, mid, balance


def _confirm(at: AppTest, kind: str) -> AppTest:
    key = f"pn_confirm_{kind}"
    assert key in _keys(at), f"적립금 이용안내창의 확인 버튼이 없다: {_keys(at)}"
    for button in at.button:
        if button.key == key:
            at = button.click().run()
            break
    assert not at.exception, f"확인 후 진행에서 예외: {at.exception}"
    return at


def test_G1_auto_confirm_without_pool_takes_no_points_and_leaves_a_reason():
    """G1 — 자동조합: 다음회차 풀이 없으면 차감 0 + 사유 문구(무음 아님)."""
    with _db_isolation.isolated_db():
        at, mid, balance = _open_notice("auto", 200)
        at = _confirm(at, "auto")
        after = int(wdb.get_balance(mid) or 0)
        text = _screen_text(at)
        assert after == balance, f"풀이 없는데 포인트가 나갔다: {balance} -> {after}"
        assert aps.NEXT_DRAW_POOL_BANNER in text, (
            f"풀 부재 사유 문구가 화면에 없다(무음): {text[:400]!r}"
        )
        print(_safe(f"  (G1 차감={balance - after}P, 사유문구 확인)"))


def test_G2_auto_confirm_with_zero_balance_never_goes_negative():
    """G2 — 자동조합: 잔액 0이어도 차감 0(음수 잔액 금지)."""
    with _db_isolation.isolated_db():
        at, mid, balance = _open_notice("auto", 0)
        assert balance == 0, f"준비 실패: 잔액이 0이 아니다: {balance}"
        at = _confirm(at, "auto")
        after = int(wdb.get_balance(mid) or 0)
        assert after == 0, f"잔액이 변했다(음수/차감): {balance} -> {after}"
        assert _screen_text(at).strip(), "확인 후 화면에 아무 안내도 남지 않았다(무음)"
        print(_safe(f"  (G2 차감={balance - after}P, 안내문구 있음)"))


def test_G3_thunder_confirm_with_short_balance_opens_the_charge_dialog():
    """G3 — 번개조합: 잔액 부족이면 차감 0 + 부족/충전창(충전 수단 노출)."""
    with _db_isolation.isolated_db():
        at, mid, balance = _open_notice("thunder", 0)
        at = _confirm(at, "thunder")
        after = int(wdb.get_balance(mid) or 0)
        keys = _keys(at)
        assert after == balance == 0, f"부족한데 잔액이 변했다: {balance} -> {after}"
        assert "insufficient_balance_close" in keys, (
            f"부족/충전창이 뜨지 않았다(막다른 길): {keys}"
        )
        assert "test_charge_btn" in keys or "iap_buy_points_1000" in keys, (
            f"부족창에 충전 수단이 없다: {keys}"
        )
        print(_safe("  (G3 부족창 + 충전 수단 노출 확인)"))


def test_G4_thunder_confirm_deducts_immediately_without_any_gate():
    """G4 — [현재 동작 고정] 번개조합은 풀·판매창 게이트 없이 확인 즉시 차감한다.

    자동조합은 같은 자리에서 풀·판매창을 먼저 보고 사유를 남기지만(G1),
    번개조합에는 그 게이트가 없다 — 이 사실을 고정해 둔다. 이 화면에 게이트를
    넣는 수정을 하면 이 테스트가 먼저 실패해 알려준다.
    """
    with _db_isolation.isolated_db():
        at, mid, balance = _open_notice("thunder", 200)
        expected_cost = int(wdb.calc_thunder_cost(GAMES_DEFAULT))
        at = _confirm(at, "thunder")
        after = int(wdb.get_balance(mid) or 0)
        assert balance - after == expected_cost, (
            f"차감액이 게임 수 비용과 다르다: 기대 {expected_cost}P, 실제 {balance - after}P"
        )
        assert after >= 0, f"잔액이 음수가 됐다: {after}"
        print(_safe(f"  (G4 게이트 없이 {expected_cost}P 차감 확인 — 화면 문구는 없음)"))


def test_G5_insufficient_dialog_offers_a_charge_path_in_the_app():
    """G5 — 앱 판정(native=1)에서는 부족창에 실제 충전 수단이 있다 = 막다른 길이 아니다.

    조합시작에서 잔액이 모자란 테스터가 실제로 막히는 마지막 자리가 이 창이다.
    여기에 충전 버튼이 없으면 "충전도 조합도 못 한다"가 된다(그래서 불변식으로 고정).
    """
    with _db_isolation.isolated_db():
        at, mid, balance = _open_notice("thunder", 0, native=True)
        at = _confirm(at, "thunder")
        keys = _keys(at)
        text = _screen_text(at)
        assert "insufficient_balance_close" in keys, f"부족창이 뜨지 않았다: {keys}"
        assert "test_charge_btn" in keys or any(
            k.startswith("iap_buy_") for k in keys
        ), f"앱인데 부족창에 충전 수단이 없다(막다른 길): {keys}"
        assert wallet_ui.CHARGE_PENDING_NOTICE not in text, (
            f"앱인데 부족창이 '준비 중' 안내로 대체됐다: {text[:300]!r}"
        )
        assert int(wdb.get_balance(mid) or 0) == balance == 0, "부족한데 잔액이 변했다"
        print(_safe("  (G5 앱 판정: 부족창에 충전 수단 있음)"))


def test_G6_insufficient_dialog_is_a_dead_end_when_the_app_flag_is_lost():
    """G6 — 앱이 보낸 native=1이 유실되어 서버가 **웹**으로 판정하면,
    같은 부족창에 충전 수단이 하나도 없다(토스 미연동 + Mock 미허용).

    이것이 테스터 신고("충전창에 준비 중" + "조합 확인 후 진행해도 원점")가
    동시에 나타나는 구조다 — 조합 쪽 문제가 아니라 앱 판정 문제라는 증거로 고정한다.
    웹에도 결제 경로를 넣는 수정을 하면 이 테스트가 먼저 깨져 알려준다.
    """
    originals = (wallet_ui.pg_configured, wallet_ui.mock_charge_enabled)
    wallet_ui.pg_configured = lambda: False
    wallet_ui.mock_charge_enabled = lambda: False
    try:
        with _db_isolation.isolated_db():
            at, mid, balance = _open_notice("thunder", 0, native=False)
            at = _confirm(at, "thunder")
            keys = _keys(at)
            text = _screen_text(at)
            assert "insufficient_balance_close" in keys, f"부족창이 뜨지 않았다: {keys}"
            assert "test_charge_btn" not in keys, (
                f"웹 판정인데 테스터 충전 버튼이 떴다: {keys}"
            )
            assert not any(k.startswith("iap_buy_") for k in keys), (
                f"웹 판정인데 구글플레이 결제 버튼이 떴다: {keys}"
            )
            assert wallet_ui.CHARGE_PENDING_NOTICE in text, (
                f"웹 부족창에 사유 안내가 없다: {text[:300]!r}"
            )
            assert int(wdb.get_balance(mid) or 0) == balance == 0, "부족한데 잔액이 변했다"
            print(_safe("  (G6 웹 판정: 부족창에 충전 수단 없음 = 막다른 길 확인)"))
    finally:
        wallet_ui.pg_configured, wallet_ui.mock_charge_enabled = originals


def _open_gate_without_login(kind: str, page: str) -> AppTest:
    """창 열림 플래그만 있고 로그인 정보가 없는 상태의 화면을 실제 진입점으로 그린다.

    (로그인 없이 창이 열리는 경로가 있는지, 있다면 눌렀을 때 무엇이 남는지 보는 자리)
    """
    flag_key = f"open_{kind}_dialog"
    gid = f"silent{kind}"
    at = AppTest.from_file(ENTRY, default_timeout=TIMEOUT_SEC)
    at.query_params["page"] = page
    at.query_params["gid"] = gid
    at.query_params["native"] = "1"
    at.session_state["_guest_id"] = gid
    at.session_state[flag_key] = True
    if kind == "tarot":
        import tarot_page

        at.session_state["tarot_daily_date"] = tarot_page._today_str()
        at.session_state["tarot_daily_count"] = tarot_page.MAX_DAILY_DRAWS
    at.run()
    assert not at.exception, f"{kind} 렌더 예외: {at.exception}"
    return at


def test_G7_no_screen_ends_the_confirm_silently_without_login():
    """G7 — 로그인 정보가 없는 상태에서 '확인 후 진행'을 눌러도 **어떤 화면도 조용히 끝나지 않는다**.

    번개·안티액땜 두 화면 모두 current_member_id()가 None이면 사유 문구
    (login_gate.GATE_INLINE_HINT)를 남기고, 차감은 0이어야 한다 — "창만 닫히고 원점"
    으로 보이는 무음 경로를 만들면 이 테스트가 깨진다.

    타로(추가뽑기)는 넣지 않는다 — 실제 진입점에서는 페이지 전체 login_gate가 먼저
    막아 그 자리에 도달할 수 없고(실측: 도달해도 오류 문구를 소비하는
    _render_extra_draw_gate가 다시 그려지지 않는다), 같은 성질을
    tests/test_tarot_gate_flow.py의 T5가 전용 프로브로 이미 고정하고 있다.
    """
    from login_gate import GATE_INLINE_HINT

    checked = []
    for kind, page in (("thunder", "thunder"), ("hedge", "hedge")):
        with _db_isolation.isolated_db():
            at = _open_gate_without_login(kind, page)
            confirm = f"pn_confirm_{kind}"
            assert confirm in _keys(at), (
                f"{kind}: 안내창이 열려 있지 않아 확인 클릭 단계로 못 감: {_keys(at)}"
            )
            at = _confirm(at, kind)
            text = _screen_text(at)
            assert GATE_INLINE_HINT in text, (
                f"{kind}: 로그인 없이 확인을 눌렀는데 사유 문구가 없다(무음 종료): {text[-400:]!r}"
            )
            checked.append(kind)
    print(_safe(f"  (G7 무음 종료 없음 확인: {checked})"))


def _main() -> int:
    tests = [
        test_G1_auto_confirm_without_pool_takes_no_points_and_leaves_a_reason,
        test_G2_auto_confirm_with_zero_balance_never_goes_negative,
        test_G3_thunder_confirm_with_short_balance_opens_the_charge_dialog,
        test_G4_thunder_confirm_deducts_immediately_without_any_gate,
        test_G5_insufficient_dialog_offers_a_charge_path_in_the_app,
        test_G6_insufficient_dialog_is_a_dead_end_when_the_app_flag_is_lost,
        test_G7_no_screen_ends_the_confirm_silently_without_login,
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
