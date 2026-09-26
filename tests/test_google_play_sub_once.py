"""Google Play 인앱결제 구독 지급 — P0 검증 (2026-09-26).

무엇을 검증하는가: 이 함수가 없어서 google_play_pg import가 죽던 결함
(wallet_db.activate_paid_advanced_sub_once 미정의 → user_page.py 모듈 최상단
import 실패 → 기본 페이지 예외)의 수정이 실제로 성립하는지.

  W1  멱등성     같은 ref_id(purchaseToken)로 3회 지급 → 구독 행 1개, 만료일 불변
  W2  연장       다른 ref_id → 남은 만료일부터 이어서 연장(30일+90일), 행 2개
  W3  경계       만료된 과거 구독만 있을 때 → now 기준 연장(과거 만료일에 붙지 않음)
  W4  실패       없는 회원 → False, 마커·구독 0행(부분 기록 없음).
                 days<=0 / 빈 ref_id → ValueError(계약)
  W5  보존       지급이 적립금(wallets.balance)·wallet_ledger를 건드리지 않음
  W6  형태       기존 activate_paid_advanced_sub와 같은 모양이라 기존 판정
                 함수(has_active_subscription/get_subscription_expiry)가 그대로 인식
  W7  연계       gplay 마커가 Mock 결제 한도(count_recent_mock_charges)에 안 섞임
  W8  공존       무료 프로모 구독 위에 지급해도 무료 행을 덮어쓰지 않음
  W9  배선       google_play_pg._verify_and_credit_subscription 실제 호출(HTTP만 스텁):
                 basePlanId로 일수 결정 · 지급 후 acknowledge 1회 · 같은 토큰 재도착 멱등 ·
                 미지의 기본요금제/만료 구독은 지급 없이 실패
  W10 계약(정적) google_play_pg가 wallet_db에서 import하는 이름이 실제로 존재 + import 성공
  W11 조립       진입점(app.py) 렌더(토큰 없음) — 예외 없이 실행
  W12 조립       진입점에 토큰 + 로그인 연결 → 실제 지급 + 파라미터 1회 소비(무한 rerun 없음)
  W13 조립       진입점에 토큰만(로그인 없음) → 지급 없음(무부작용)

격리: 모든 DB 접근은 _db_isolation.isolated_db()의 임시 sqlite로만 간다(운영
Turso 접촉 0). Google API는 W9~W13에서 _api_get/_api_post를 스텁으로 바꿔치기하므로
네트워크 호출도 없다. pytest 없이 돌도록 표준 assert + __main__ 러너를 함께 둔다.

러너는 각 단계를 이름으로 찍고 실패한 단계만 FAIL/ERROR로 보고한다 — 나중에 오류가
나면 어느 단계에서 생긴 것인지 바로 확인하기 위해서다.
"""

from __future__ import annotations

import ast
import os
import sqlite3
import sys
from datetime import datetime, timedelta
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
FMT = "%Y-%m-%d %H:%M:%S.%f"

DAY_TOLERANCE_SEC = 180  # 날짜 계산 검증용 허용 오차(분 단위)


# ── 조회 헬퍼: 앱이 실제로 쓴 임시 DB를 직접 열어 확인한다 ────────────────────

def _connect_ro(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _count(db_path: str, table: str, member_id: int) -> int:
    conn = _connect_ro(db_path)
    try:
        row = conn.execute(
            f"SELECT COUNT(*) AS c FROM {table} WHERE member_id = ?", (member_id,)
        ).fetchone()
        return int(row["c"])
    finally:
        conn.close()


def _count_all(db_path: str, table: str) -> int:
    conn = _connect_ro(db_path)
    try:
        return int(conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"])
    finally:
        conn.close()


def _subs(db_path: str, member_id: int) -> list[sqlite3.Row]:
    conn = _connect_ro(db_path)
    try:
        return list(
            conn.execute(
                "SELECT product, starts_at, expires_at, is_free_promo FROM subscriptions "
                "WHERE member_id = ? ORDER BY id",
                (member_id,),
            ).fetchall()
        )
    finally:
        conn.close()


def _expiries(db_path: str, member_id: int) -> list[datetime]:
    return [wdb._parse_kst(r["expires_at"]) for r in _subs(db_path, member_id)]


def _seed_subscription(
    db_path: str, member_id: int, expires: datetime, *, is_free_promo: int = 0
) -> None:
    """사전 상태 만들기 전용 — 만료된/미래 구독이 이미 있는 상황을 재현한다."""
    conn = _connect_ro(db_path)
    try:
        conn.execute(
            "INSERT INTO subscriptions (member_id, product, starts_at, expires_at, is_free_promo) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                member_id,
                wdb.ADVANCED_PRODUCT,
                (expires - timedelta(days=30)).strftime(FMT),
                expires.strftime(FMT),
                is_free_promo,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _member(handle: str) -> int:
    mid, _new = wdb.get_or_create_member("kakao", handle)
    return int(mid)


def _expect_value_error(fn, label: str) -> None:
    try:
        fn()
    except ValueError:
        return
    raise AssertionError(f"{label}: ValueError가 나야 하는데 나지 않았다")


def _gplay():
    """google_play_pg를 지연 import — import 자체가 실패하면 그 테스트만
    ERROR로 보고되고 나머지 단계는 계속 돌아, 오류 단계를 특정할 수 있다."""
    import importlib

    return importlib.import_module("google_play_pg")


def _stub_google_apis(gplay, payload_factory, *, token: str):
    """_api_get/_api_post만 바꿔치기해 'HTTP 경계'만 스텁으로 만든다.
    반환: (state, restore) — state['post_paths']에 실제 요청 경로가 쌓인다."""
    state = {"acked": 0, "post_paths": []}

    def fake_get(path):
        expected = f"purchases/subscriptionsv2/tokens/{token}"
        assert path == expected, f"조회 경로가 다르다: {path} != {expected}"
        return True, payload_factory(state)

    def fake_post(path):
        state["post_paths"].append(path)
        if path.endswith(":acknowledge"):
            state["acked"] += 1
        return True, "ok"

    original = (gplay._api_get, gplay._api_post)
    gplay._api_get, gplay._api_post = fake_get, fake_post

    def restore():
        gplay._api_get, gplay._api_post = original

    return state, restore


def _subscription_payload(state, *, base_plan_id: str, sub_state: str = "SUBSCRIPTION_STATE_ACTIVE"):
    """실제 subscriptionsv2 응답 형태(문서 기준) — acknowledgementState는 승인
    호출 이후 1로 바뀌는 실제 동작을 흉내낸다."""
    return {
        "subscriptionState": sub_state,
        "acknowledgementState": 1 if state["acked"] else 0,
        "lineItems": [{"offerDetails": {"basePlanId": base_plan_id}}],
    }


def _entry_app(gid: str, **extra_params) -> AppTest:
    at = AppTest.from_file(ENTRY, default_timeout=TIMEOUT_SEC)
    at.query_params["page"] = "main"
    at.query_params["gid"] = gid
    for key, value in extra_params.items():
        at.query_params[key] = value
    at.run()
    return at


def _disable_ua_gate() -> None:
    """자동로그인 UA 대조를 꺼서, 테스트가 만든 guest 연결이 로그인으로 이어지게
    한다(app_settings 킬스위치 — 배포 없이 끌 수 있는 실제 스위치)."""
    try:
        import app_settings

        try:
            app_settings.set_auth_require_ua_match(False)
        except Exception:
            app_settings.init_settings_table()
            app_settings.set_auth_require_ua_match(False)
    except Exception:
        pass


# ── W1~W8: wallet_db.activate_paid_advanced_sub_once 계약 ────────────────────

def test_W1_same_ref_id_credits_exactly_once():
    with _db_isolation.isolated_db() as db_path:
        wdb.init_wallet_tables()
        mid = _member("gplay_w1")
        ref = "pg:gplay:token_W1"

        assert wdb.activate_paid_advanced_sub_once(mid, 30, ref) is True
        first = _expiries(db_path, mid)
        assert len(first) == 1, f"첫 지급인데 구독 행이 {len(first)}개다"

        for _ in range(2):  # 재전송·새로고침·재시도로 같은 토큰이 다시 온 상황
            assert wdb.activate_paid_advanced_sub_once(mid, 30, ref) is True

        assert len(_subs(db_path, mid)) == 1, "같은 ref_id로 구독이 두 번 생겼다"
        assert _expiries(db_path, mid) == first, "같은 ref_id인데 만료일이 밀렸다(중복 연장)"
        assert _count(db_path, "pg_charges", mid) == 1, "멱등 마커가 중복 기록됐다"


def test_W2_different_ref_id_extends_back_to_back():
    with _db_isolation.isolated_db() as db_path:
        wdb.init_wallet_tables()
        mid = _member("gplay_w2")
        before = datetime.now(wdb.KST)

        assert wdb.activate_paid_advanced_sub_once(mid, 30, "pg:gplay:token_W2a") is True
        assert wdb.activate_paid_advanced_sub_once(mid, 90, "pg:gplay:token_W2b") is True

        expiries = _expiries(db_path, mid)
        assert len(expiries) == 2, f"서로 다른 토큰인데 행이 {len(expiries)}개다"
        assert expiries[1] > expiries[0], "두 번째 지급이 이어서 연장되지 않았다"
        delta_first = (expiries[0] - before).total_seconds()
        delta_between = (expiries[1] - expiries[0]).total_seconds()
        assert abs(delta_first - 30 * 86400) < DAY_TOLERANCE_SEC, f"30일 연장이 아니다: {delta_first}초"
        assert abs(delta_between - 90 * 86400) < DAY_TOLERANCE_SEC, (
            f"이어서 90일 연장이 아니다: {delta_between}초"
        )


def test_W3_expired_past_subscription_extends_from_now():
    with _db_isolation.isolated_db() as db_path:
        wdb.init_wallet_tables()
        mid = _member("gplay_w3")
        past = datetime.now(wdb.KST) - timedelta(days=400)
        _seed_subscription(db_path, mid, past)
        before = datetime.now(wdb.KST)

        assert wdb.activate_paid_advanced_sub_once(mid, 30, "pg:gplay:token_W3") is True

        paid = [e for e in _expiries(db_path, mid) if e > before]
        assert len(paid) == 1, "만료된 과거 구독에 이어붙지 않고 새 구간으로 계산되어야 한다"
        delta = (paid[0] - before).total_seconds()
        assert abs(delta - 30 * 86400) < DAY_TOLERANCE_SEC, (
            f"과거 만료일 기준으로 계산됐다(지금 기준이어야 함): {delta}초"
        )


def test_W4_failure_paths_leave_no_partial_records():
    with _db_isolation.isolated_db() as db_path:
        wdb.init_wallet_tables()
        ghost = 999999  # members에 없는 회원

        assert wdb.activate_paid_advanced_sub_once(ghost, 30, "pg:gplay:token_W4") is False
        assert _count(db_path, "pg_charges", ghost) == 0, "실패했는데 마커가 남았다"
        assert _count(db_path, "subscriptions", ghost) == 0, "실패했는데 구독이 생겼다"
        assert _count_all(db_path, "pg_charges") == 0, "실패 경로가 마커를 남겼다"

        mid = _member("gplay_w4")
        _expect_value_error(lambda: wdb.activate_paid_advanced_sub_once(mid, 0, "ref:0"), "days=0")
        _expect_value_error(lambda: wdb.activate_paid_advanced_sub_once(mid, -1, "ref:-1"), "days=-1")
        _expect_value_error(lambda: wdb.activate_paid_advanced_sub_once(mid, 30, "   "), "빈 ref_id")
        assert _count(db_path, "pg_charges", mid) == 0, "잘못된 인자가 마커를 남겼다"


def test_W5_grant_does_not_touch_points():
    with _db_isolation.isolated_db() as db_path:
        wdb.init_wallet_tables()
        mid = _member("gplay_w5")
        wdb.grant_signup_bonus(mid)
        balance_before = wdb.get_balance(mid)
        ledger_before = _count(db_path, "wallet_ledger", mid)

        assert wdb.activate_paid_advanced_sub_once(mid, 30, "pg:gplay:token_W5") is True

        assert wdb.get_balance(mid) == balance_before, "구독 지급이 적립금을 건드렸다"
        assert _count(db_path, "wallet_ledger", mid) == ledger_before, (
            "구독 지급이 적립금 원장에 행을 남겼다"
        )


def test_W6_row_shape_matches_existing_subscription_contract():
    with _db_isolation.isolated_db() as db_path:
        wdb.init_wallet_tables()
        mid = _member("gplay_w6")
        assert not wdb.has_active_subscription(mid)

        assert wdb.activate_paid_advanced_sub_once(mid, 30, "pg:gplay:token_W6") is True

        rows = _subs(db_path, mid)
        assert len(rows) == 1
        assert rows[0]["product"] == wdb.ADVANCED_PRODUCT, "상품명이 기존 구독과 다르다"
        assert int(rows[0]["is_free_promo"]) == 0, "무료 프로모 행으로 기록됐다"
        assert wdb.has_active_subscription(mid), "기존 유효성 판정이 새 행을 인식하지 못한다"
        assert wdb.get_subscription_expiry(mid) == rows[0]["expires_at"], (
            "만료일 조회가 새 행과 다른 값을 준다"
        )
        assert wdb.eligible_free_advanced_sub(mid), "유료 지급이 무료 프로모 자격을 소진시켰다"


def test_W7_gplay_marker_does_not_count_as_mock_charge():
    with _db_isolation.isolated_db() as db_path:
        wdb.init_wallet_tables()
        mid = _member("gplay_w7")

        assert wdb.activate_paid_advanced_sub_once(mid, 30, "pg:gplay:token_W7") is True
        assert wdb.count_recent_mock_charges(mid) == 0, (
            "구글 결제 마커가 Mock 충전 한도에 섞였다"
        )

        # 기존 충전 경로는 그대로 동작해야 한다(연계 회귀 확인).
        assert wdb.charge_points(mid, 10000, "pg:mock:w7:1") is True
        assert wdb.count_recent_mock_charges(mid) == 1
        assert wdb.charge_points(mid, 10000, "pg:gplay:token_W7") is True, (
            "같은 ref_id 충전이 예외 없이 처리돼야 한다(멱등)"
        )
        assert wdb.get_balance(mid) == 10000, "같은 ref_id가 두 번 충전됐다"


def test_W8_free_promo_row_is_preserved():
    with _db_isolation.isolated_db() as db_path:
        wdb.init_wallet_tables()
        mid = _member("gplay_w8")
        assert wdb.activate_free_advanced_sub(mid) is True
        free_expiry = _expiries(db_path, mid)[0]

        assert wdb.activate_paid_advanced_sub_once(mid, 30, "pg:gplay:token_W8") is True

        rows = _subs(db_path, mid)
        assert len(rows) == 2, "무료 구독 행이 사라졌다"
        assert any(int(r["is_free_promo"]) == 1 for r in rows), "무료 프로모 표시가 사라졌다"
        paid = [e for e in _expiries(db_path, mid) if e > free_expiry]
        assert len(paid) == 1, "무료 만료일부터 이어서 연장되지 않았다"
        assert abs((paid[0] - free_expiry).total_seconds() - 30 * 86400) < DAY_TOLERANCE_SEC


# ── W9~W10: 서버 배선·import 계약 ───────────────────────────────────────────

def test_W9_verification_wiring_credits_and_acknowledges_once():
    gplay = _gplay()
    with _db_isolation.isolated_db() as db_path:
        wdb.init_wallet_tables()
        mid = _member("gplay_w9")
        token = "token_W9"
        before = datetime.now(wdb.KST)

        state, restore = _stub_google_apis(
            gplay, lambda s: _subscription_payload(s, base_plan_id="premium-monthly"), token=token
        )
        try:
            ok, msg = gplay._verify_and_credit_subscription(mid, token)
            assert ok, f"월간 구독 검증이 실패했다: {msg}"
            ok2, msg2 = gplay._verify_and_credit_subscription(mid, token)
            assert ok2, f"같은 토큰 재검증이 실패했다: {msg2}"

            # 미지의 기본요금제 — 클라이언트가 뭘 보내든 구글 응답의 basePlanId만 신뢰한다.
            token_bad = "token_W9_unknown"
            _, restore_bad = _stub_google_apis(
                gplay, lambda s: _subscription_payload(s, base_plan_id="premium-yearly"), token=token_bad
            )
            try:
                ok_bad, _msg_bad = gplay._verify_and_credit_subscription(mid, token_bad)
                assert ok_bad is False, "모르는 기본요금제인데 지급됐다"
            finally:
                restore_bad()

            # 만료된 구독 — 지급 대상이 아니다.
            token_expired = "token_W9_expired"
            _, restore_exp = _stub_google_apis(
                gplay,
                lambda s: _subscription_payload(
                    s, base_plan_id="premium-monthly", sub_state="SUBSCRIPTION_STATE_EXPIRED"
                ),
                token=token_expired,
            )
            try:
                ok_exp, _msg_exp = gplay._verify_and_credit_subscription(mid, token_expired)
                assert ok_exp is False, "만료된 구독인데 지급됐다"
            finally:
                restore_exp()
        finally:
            restore()

        rows = _subs(db_path, mid)
        assert len(rows) == 1, f"지급은 한 번인데 구독 행이 {len(rows)}개다"
        delta = (_expiries(db_path, mid)[0] - before).total_seconds()
        assert abs(delta - 30 * 86400) < DAY_TOLERANCE_SEC, "월간 요금제가 30일로 계산되지 않았다"
        assert state["post_paths"] == [
            f"purchases/subscriptions/{gplay.SUBSCRIPTION_PRODUCT}/tokens/{token}:acknowledge"
        ], f"승인 호출이 정확히 1회가 아니다: {state['post_paths']}"
        assert _count(db_path, "pg_charges", mid) == 1, "멱등 마커가 정확히 1개가 아니다"

        # 분기 요금제는 90일 — basePlanId → 일수 매핑이 살아있는지.
        token_q = "token_W9_quarterly"
        state_q, restore_q = _stub_google_apis(
            gplay, lambda s: _subscription_payload(s, base_plan_id="premium-quarterly"), token=token_q
        )
        try:
            ok_q, msg_q = gplay._verify_and_credit_subscription(mid, token_q)
            assert ok_q, f"분기 구독 검증이 실패했다: {msg_q}"
        finally:
            restore_q()
        paid_expiries = [e for e in _expiries(db_path, mid) if e > before + timedelta(days=29)]
        assert abs((max(_expiries(db_path, mid)) - before).total_seconds() - 120 * 86400) < DAY_TOLERANCE_SEC, (
            "분기(90일)가 기존 30일 위에 이어서 붙지 않았다"
        )
        assert paid_expiries, "지급된 구독 구간이 없다"


def test_W10_wallet_db_import_contract_holds():
    """google_play_pg가 wallet_db에서 가져오는 이름이 전부 실제로 존재해야 한다
    (이 계약이 깨져서 기본 페이지가 죽던 것이 이번 P0였다)."""
    tree = ast.parse((ROOT / "google_play_pg.py").read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "wallet_db":
            imported.extend(alias.name for alias in node.names)
    assert imported, "google_play_pg.py에 wallet_db import가 없다"
    missing = [name for name in imported if not hasattr(wdb, name)]
    assert not missing, f"wallet_db에 없는 이름을 import하고 있다: {missing}"

    # 실제 import가 성공하는지(정적 검사가 놓치는 실행 시점 오류까지).
    module = _gplay()
    assert hasattr(module, "handle_google_play_purchase_return")
    assert module.SUBSCRIPTION_BASE_PLAN_DAYS == {"premium-monthly": 30, "premium-quarterly": 90}
    assert module.POINTS_PRODUCTS == {"points_1000": 1000, "points_3000": 3000}


# ── W11~W13: 조립 검증 — 사용자가 만나는 진입점으로 실행 ─────────────────────

def test_W11_entry_renders_without_purchase_params():
    with _db_isolation.isolated_db():
        at = _entry_app("gplay_no_token")
        assert not at.exception, f"진입점 실행 중 예외: {at.exception}"


def test_W12_entry_credits_when_token_and_login_present():
    gplay = _gplay()
    gid = "gplay_entry_login"
    token = "token_W12"
    with _db_isolation.isolated_db() as db_path:
        wdb.init_wallet_tables()
        _disable_ua_gate()
        mid = _member("gplay_w12")
        wdb.link_guest_to_member(gid, mid, None)

        state, restore = _stub_google_apis(
            gplay, lambda s: _subscription_payload(s, base_plan_id="premium-monthly"), token=token
        )
        try:
            at = _entry_app(gid, iap_purchase_token=token, iap_product_id="premium")
        finally:
            restore()

        assert not at.exception, f"진입점 실행 중 예외: {at.exception}"
        assert _count(db_path, "pg_charges", mid) == 1, "진입점을 통과했는데 지급 마커가 없다"
        assert len(_subs(db_path, mid)) == 1, "진입점을 통과했는데 구독이 생기지 않았다"
        assert state["post_paths"], "진입점을 통과했는데 승인(acknowledge) 호출이 없다"

        # 조립 검증의 핵심 — 사용자가 실제로 보는 출력에 결제 완료 안내가 떴는가
        # (DB만 맞고 화면에 아무것도 안 뜨는 경우를 잡는다). 안내는
        # wallet_ui.py:1174가 st.success로 띄운다(마크다운이 아니다) — 어느 쪽으로
        # 그려지든 잡히도록 함께 본다.
        rendered = [m.value or "" for m in at.markdown]
        toast_texts = [getattr(t, "value", "") or "" for t in getattr(at, "toast", [])]
        successes = [getattr(s, "value", "") or "" for s in at.success]
        notices = rendered + toast_texts + successes
        paid_text = "결제가 완료되었습니다"
        assert rendered, "진입점이 아무 마크다운도 그리지 않았다(빈 화면)"
        assert any(paid_text in txt for txt in notices) or (
            at.session_state.get("wallet_toast") == paid_text
        ), (
            "결제 완료 안내가 화면 어디에도 없다 "
            f"(성공박스 {len(successes)}건 / 토스트 {len(toast_texts)}건 / 마크다운 {len(rendered)}건)"
        )
        assert at.query_params.get("iap_purchase_token") in (None, []), (
            "토큰 파라미터가 소비되지 않아 재처리(무한 rerun) 위험이 있다"
        )


def test_W13_entry_without_login_does_not_credit():
    gid = "gplay_entry_nologin"
    token = "token_W13"
    with _db_isolation.isolated_db() as db_path:
        wdb.init_wallet_tables()
        _disable_ua_gate()

        at = _entry_app(gid, iap_purchase_token=token, iap_product_id="premium")

        assert not at.exception, f"진입점 실행 중 예외: {at.exception}"
        assert _count_all(db_path, "pg_charges") == 0, "로그인 없이 지급됐다"
        assert _count_all(db_path, "subscriptions") == 0, "로그인 없이 구독이 생겼다"
        assert at.query_params.get("iap_purchase_token") in (None, []), (
            "미로그인 상태의 토큰이 남아 있다(재시도 경로 확인 필요)"
        )


def _main() -> int:
    tests = [
        test_W1_same_ref_id_credits_exactly_once,
        test_W2_different_ref_id_extends_back_to_back,
        test_W3_expired_past_subscription_extends_from_now,
        test_W4_failure_paths_leave_no_partial_records,
        test_W5_grant_does_not_touch_points,
        test_W6_row_shape_matches_existing_subscription_contract,
        test_W7_gplay_marker_does_not_count_as_mock_charge,
        test_W8_free_promo_row_is_preserved,
        test_W9_verification_wiring_credits_and_acknowledges_once,
        test_W10_wallet_db_import_contract_holds,
        test_W11_entry_renders_without_purchase_params,
        test_W12_entry_credits_when_token_and_login_present,
        test_W13_entry_without_login_does_not_credit,
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
