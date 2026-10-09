# -*- coding: utf-8 -*-
"""구글 인앱결제 "결제 이후" 수명주기 검증 (2026-10-09 점검 B1·H1·H2·H3·H4·H5).

이전 테스트(test_google_play_sub_once)는 "첫 결제가 한 번만 지급되는가"만 봤다 — 그래서
갱신·해지·보류·환불·승인 실패처럼 시간이 지나야 생기는 일이 없어도 통과였다. 이 파일은
그 빈칸을 막는다(preflight --phase review 가 이 파일을 실행한다).

  L1  권한 규칙: 상태별(활성·유예·해지·보류·일시중지·만료·알수없음) 권한/재확인 시각
  L2  자동 갱신: 다시 확인하면 구글의 새 만료일로 늘어난다(첫 결제 1회만 지급하던 결함 B1)
  L3  해지 → 남은 기간까지 유지 / 만료 → 즉시 차단
  L4  결제 보류(계정 보류) → 차단, 복구되면 다시 권한
  L5  이월: 무료 프로모가 남아 있으면 그 기간을 구글 만료일 뒤에 붙인다(예전 동작 유지)
  L6  요금제 변경(linkedPurchaseToken) → 옛 구독 행 종료, 이월 승계
  L7  같은 토큰을 다른 회원이 보내면 거절(토큰 재사용 차단)
  L8  적립금 소비(consume) 실패 → 백그라운드 재시도로 완료 / 지급 중 끊김 → 재시도가 1회만 지급
  L9  적립금 환불(voided) → 잔액 한도 회수·멱등·못 회수한 몫 기록
  L10 구독 환불(voided) → 재확인으로 차단
  L11 회원 화면 확인은 백그라운드로, 10분에 한 번(렌더가 구글을 기다리지 않는다)
  L12 결제 대기(pending) → 지급 안 함, 대기 안내
  L13 진입점: 결제 요청 신호(iap_buy/iap_plan) 제거 · 실패 안내가 화면에 남는다
  L14 표시 가격: 꾸민 값·터무니없는 값은 무시, 정상 스토어 표기는 반영
  L15 서비스 계정 미설정(현재 운영) → 백그라운드·회원 확인 모두 아무 호출도 안 한다
  L16 로그에 결제 토큰 전체를 남기지 않는다
  L17 구글 구독이 끝나도 처음 남아 있던 기존 구독 기간(이월)은 지킨다(보류 재확인에도 안 밀림)
  L18 지급 전에 끊긴 결제가 환불돼도 다른 적립금을 빼앗지 않는다
  L19 요금제 변경으로 대체된 옛 토큰은 되살아나지 않는다

실행: venv312\\Scripts\\python.exe -X utf8 tests\\test_gplay_lifecycle.py
"""

from __future__ import annotations

import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from streamlit.testing.v1 import AppTest

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _path in (str(ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import _db_isolation  # noqa: E402
import google_play_pg as gp  # noqa: E402
import wallet_db as wdb  # noqa: E402

UTC = timezone.utc
TOL = 180  # 초


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _sub_payload(state="SUBSCRIPTION_STATE_ACTIVE", *, days=30.0, auto=True, plan="premium-monthly",
                 acked=True, linked=None, expiry=None):
    exp = expiry or (datetime.now(UTC) + timedelta(days=days))
    data = {
        "subscriptionState": state,
        "acknowledgementState": "ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED" if acked else "ACKNOWLEDGEMENT_STATE_PENDING",
        "lineItems": [{
            "productId": "premium",
            "expiryTime": _iso(exp),
            "autoRenewingPlan": {"autoRenewEnabled": auto},
            "offerDetails": {"basePlanId": plan},
        }],
    }
    if linked:
        data["linkedPurchaseToken"] = linked
    return data


class FakeGoogle:
    """HTTP 경계(_api_get/_api_post)만 바꿔치기한다. responses[path 앞부분] = (ok, data)."""

    def __init__(self):
        self.responses: dict[str, tuple[bool, object]] = {}
        self.gets: list[str] = []
        self.posts: list[str] = []
        self.post_ok = True

    def get(self, path):
        self.gets.append(path)
        for prefix, value in self.responses.items():
            if path.startswith(prefix):
                return value
        return False, f"no stub for {path}"

    def post(self, path):
        self.posts.append(path)
        return (True, "ok") if self.post_ok else (False, "stub failure")


@contextmanager
def _google(configured=True):
    fake = FakeGoogle()
    saved = (gp._api_get, gp._api_post, gp.google_play_configured)
    gp._api_get, gp._api_post = fake.get, fake.post
    gp.google_play_configured = lambda: configured
    gp._MEMBER_CHECKED.clear()
    try:
        yield fake
    finally:
        gp._api_get, gp._api_post, gp.google_play_configured = saved
        gp._MEMBER_CHECKED.clear()


def _member(handle: str) -> int:
    wdb.init_wallet_tables()
    mid, _ = wdb.get_or_create_member("kakao", handle)
    return int(mid)


def _wallet(mid: int, balance: int = 0) -> None:
    conn = sqlite3.connect(_db_isolation.current_path())
    conn.execute("INSERT OR IGNORE INTO wallets (member_id, balance) VALUES (?, 0)", (mid,))
    conn.execute("UPDATE wallets SET balance = ? WHERE member_id = ?", (balance, mid))
    conn.commit()
    conn.close()


def _q(sql, params=()):
    conn = sqlite3.connect(_db_isolation.current_path())
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows


def _sub_expiry(token: str) -> datetime:
    row = _q("SELECT expires_at FROM subscriptions WHERE source_ref = ?", (wdb.gplay_ref(token),))[0]
    return wdb._parse_ts(row["expires_at"])


def _near(a: datetime, b: datetime, tol=TOL) -> bool:
    return abs((a - b).total_seconds()) < tol


def _sub_path(token):
    return f"purchases/subscriptionsv2/tokens/{token}"


def _grant(fake, mid, token, payload):
    fake.responses[_sub_path(token)] = (True, payload)
    ok, msg = gp._verify_and_credit_subscription(mid, token)
    assert ok, msg


# ── L1 ────────────────────────────────────────────────────────────────────

def test_L1_entitlement_rules():
    now = datetime.now(UTC)
    e = gp.subscription_entitlement(_sub_payload(days=10, auto=True), now)
    assert _near(e["access_until"], now + timedelta(days=11)), "자동갱신 중엔 만료 + 1일 여유"
    assert _near(e["next_check"], now + timedelta(days=1)), "유효 구독도 하루 한 번은 다시 본다"
    e = gp.subscription_entitlement(_sub_payload(days=0.5, auto=True), now)
    assert _near(e["next_check"], now + timedelta(days=0.5)), "만료 시각에 다시 본다"
    e = gp.subscription_entitlement(_sub_payload("SUBSCRIPTION_STATE_IN_GRACE_PERIOD", days=3), now)
    assert _near(e["access_until"], now + timedelta(days=3)), "유예 기간은 구글 만료일까지(구글이 늘려 줌)"
    e = gp.subscription_entitlement(_sub_payload("SUBSCRIPTION_STATE_CANCELED", days=5, auto=False), now)
    assert _near(e["access_until"], now + timedelta(days=5)), "해지해도 남은 기간은 유지"
    e = gp.subscription_entitlement(_sub_payload("SUBSCRIPTION_STATE_CANCELED", days=-1, auto=False), now)
    assert e["access_until"] is None and e["next_check"] is None
    for st in ("SUBSCRIPTION_STATE_ON_HOLD", "SUBSCRIPTION_STATE_PAUSED"):
        e = gp.subscription_entitlement(_sub_payload(st, days=-1), now)
        assert e["access_until"] is None and e["next_check"] is not None, f"{st}: 차단하되 복구를 위해 다시 본다"
    e = gp.subscription_entitlement(_sub_payload("SUBSCRIPTION_STATE_EXPIRED", days=-1), now)
    assert e["access_until"] is None and e["next_check"] is None
    e = gp.subscription_entitlement(_sub_payload("SUBSCRIPTION_STATE_UNSPECIFIED"), now)
    assert e["keep_access"] is True, "알 수 없는 상태면 권한을 건드리지 않는다"
    e = gp.subscription_entitlement({"subscriptionState": "SUBSCRIPTION_STATE_ACTIVE",
                                     "lineItems": [{"productId": "premium"}]}, now)
    assert e["keep_access"] is True, "만료 시각이 없으면 권한을 건드리지 않는다"
    assert gp._parse_google_time("2026-10-09T03:04:05.123456789Z") == datetime(
        2026, 10, 9, 3, 4, 5, 123456, tzinfo=UTC), "나노초 표기도 읽는다"


# ── L2~L7 구독 ─────────────────────────────────────────────────────────────

def test_L2_renewal_extends():
    with _db_isolation.isolated_db(), _google() as fake:
        mid = _member("lc_l2")
        _grant(fake, mid, "tok_l2", _sub_payload(days=30, auto=True))
        first = _sub_expiry("tok_l2")
        assert _near(first, datetime.now(UTC) + timedelta(days=31))
        fake.responses[_sub_path("tok_l2")] = (True, _sub_payload(days=60, auto=True))
        assert gp.refresh_subscription("tok_l2")
        assert _near(_sub_expiry("tok_l2"), datetime.now(UTC) + timedelta(days=61)), "갱신이 반영되지 않았다(B1)"
        assert wdb.has_active_subscription(mid)


def test_L3_cancel_then_expire():
    with _db_isolation.isolated_db(), _google() as fake:
        mid = _member("lc_l3")
        _grant(fake, mid, "tok_l3", _sub_payload(days=30, auto=True))
        fake.responses[_sub_path("tok_l3")] = (True, _sub_payload("SUBSCRIPTION_STATE_CANCELED", days=12, auto=False))
        gp.refresh_subscription("tok_l3")
        assert _near(_sub_expiry("tok_l3"), datetime.now(UTC) + timedelta(days=12)), "해지 후 남은 기간이 아니다"
        assert wdb.has_active_subscription(mid)
        fake.responses[_sub_path("tok_l3")] = (True, _sub_payload("SUBSCRIPTION_STATE_EXPIRED", days=-1, auto=False))
        gp.refresh_subscription("tok_l3")
        assert not wdb.has_active_subscription(mid), "만료됐는데 권한이 남았다"
        row = wdb.get_gplay_purchase("tok_l3")
        assert row["next_check_at"] is None, "만료된 구독을 계속 확인한다"


def test_L4_hold_then_recover():
    with _db_isolation.isolated_db(), _google() as fake:
        mid = _member("lc_l4")
        _grant(fake, mid, "tok_l4", _sub_payload(days=30))
        fake.responses[_sub_path("tok_l4")] = (True, _sub_payload("SUBSCRIPTION_STATE_ON_HOLD", days=-1))
        gp.refresh_subscription("tok_l4")
        assert not wdb.has_active_subscription(mid), "결제 보류인데 권한이 남았다"
        assert wdb.get_gplay_purchase("tok_l4")["next_check_at"], "보류는 복구를 위해 다시 봐야 한다"
        fake.responses[_sub_path("tok_l4")] = (True, _sub_payload(days=30))
        gp.refresh_subscription("tok_l4")
        assert wdb.has_active_subscription(mid), "복구됐는데 권한이 돌아오지 않았다"


def test_L5_carry_keeps_free_promo_days():
    with _db_isolation.isolated_db(), _google() as fake:
        mid = _member("lc_l5")
        assert wdb.activate_free_advanced_sub(mid)  # 30일 무료
        _grant(fake, mid, "tok_l5", _sub_payload(days=30, auto=False))
        assert _near(_sub_expiry("tok_l5"), datetime.now(UTC) + timedelta(days=60)), "무료 남은 기간이 이어지지 않았다"
        fake.responses[_sub_path("tok_l5")] = (True, _sub_payload("SUBSCRIPTION_STATE_ON_HOLD", days=-1))
        gp.refresh_subscription("tok_l5")
        assert wdb.has_active_subscription(mid), "보류여도 무료 프로모 기간은 남아야 한다"


def test_L6_plan_change_supersedes_old_token():
    with _db_isolation.isolated_db(), _google() as fake:
        mid = _member("lc_l6")
        _grant(fake, mid, "tok_l6a", _sub_payload(days=30, auto=False))
        _grant(fake, mid, "tok_l6b", _sub_payload(days=90, auto=False, plan="premium-quarterly", linked="tok_l6a"))
        assert _sub_expiry("tok_l6a") <= datetime.now(UTC) + timedelta(seconds=5), "옛 요금제 구독 행이 남았다"
        assert _near(_sub_expiry("tok_l6b"), datetime.now(UTC) + timedelta(days=90))
        assert wdb.get_gplay_purchase("tok_l6a")["next_check_at"] is None


def test_L7_token_reuse_by_other_member_refused():
    with _db_isolation.isolated_db(), _google() as fake:
        a, b = _member("lc_l7a"), _member("lc_l7b")
        _grant(fake, a, "tok_l7", _sub_payload(days=30))
        ok, _ = gp._verify_and_credit_subscription(b, "tok_l7")
        assert not ok and not wdb.has_active_subscription(b), "남의 구독 토큰으로 권한을 받았다"
        _wallet(a, 0)
        _wallet(b, 0)
        fake.responses["purchases/products/points_1000/tokens/ptok_l7"] = (
            True, {"purchaseState": 0, "consumptionState": 0})
        assert gp._verify_and_credit_one_time(a, "points_1000", "ptok_l7")[0]
        ok, _ = gp._verify_and_credit_one_time(b, "points_1000", "ptok_l7")
        assert not ok and wdb.get_balance(b) == 0, "남의 적립금 토큰으로 지급받았다"


# ── L8~L10 적립금·환불 ─────────────────────────────────────────────────────

def test_L8_consume_retry_and_interrupted_credit():
    with _db_isolation.isolated_db(), _google() as fake:
        mid = _member("lc_l8")
        _wallet(mid, 0)
        path = "purchases/products/points_1000/tokens/ptok_l8"
        fake.responses[path] = (True, {"purchaseState": 0, "consumptionState": 0})
        fake.post_ok = False
        ok, _ = gp._verify_and_credit_one_time(mid, "points_1000", "ptok_l8")
        assert ok and wdb.get_balance(mid) == 1000
        assert int(wdb.get_gplay_purchase("ptok_l8")["finished"]) == 0, "소비 실패인데 완료로 표시됐다"
        fake.post_ok = True
        gp._retry_unfinished(datetime.now(UTC))
        assert int(wdb.get_gplay_purchase("ptok_l8")["finished"]) == 1, "재시도가 소비를 마치지 못했다(H1)"
        assert wdb.get_balance(mid) == 1000, "재시도가 중복 지급했다"

        # 지급 직전에 끊긴 상황: 기록만 있고 지급 전
        wdb.record_gplay_points_purchase(mid, "ptok_l8b", "points_3000", 3000)
        fake.responses["purchases/products/points_3000/tokens/ptok_l8b"] = (
            True, {"purchaseState": 0, "consumptionState": 0})
        gp._retry_unfinished(datetime.now(UTC))
        gp._retry_unfinished(datetime.now(UTC))
        assert wdb.get_balance(mid) == 4000, "끊긴 지급이 정확히 한 번 이어지지 않았다"


def test_L9_voided_points_reclaimed_within_balance():
    with _db_isolation.isolated_db(), _google() as fake:
        import security_log

        security_log.init_security_tables()
        mid = _member("lc_l9")
        _wallet(mid, 0)
        fake.responses["purchases/products/points_3000/tokens/ptok_l9"] = (
            True, {"purchaseState": 0, "consumptionState": 0})
        assert gp._verify_and_credit_one_time(mid, "points_3000", "ptok_l9")[0]
        assert wdb.deduct_points(mid, 1000, "use", "use:l9")  # 일부 사용
        fake.responses["purchases/voidedpurchases"] = (True, {"voidedPurchases": [
            {"purchaseToken": "ptok_l9", "orderId": "GPA.1"}, {"purchaseToken": "unknown", "orderId": "GPA.2"}]})
        assert gp._poll_voided_purchases(datetime.now(UTC)) == 1
        assert wdb.get_balance(mid) == 0, "환불됐는데 적립금이 남았다(H2)"
        gp._poll_voided_purchases(datetime.now(UTC))
        assert wdb.get_balance(mid) == 0
        ledger = _q("SELECT delta FROM wallet_ledger WHERE reason = 'pg_void'")
        assert ledger == [{"delta": -2000}], f"회수는 잔액 한도에서 1회: {ledger}"
        events = _q("SELECT detail FROM security_events WHERE event_type = 'gplay_voided_points'")
        assert events and "shortfall=1000" in events[0]["detail"], "못 회수한 몫이 기록되지 않았다"


def test_L10_voided_subscription_cut():
    with _db_isolation.isolated_db(), _google() as fake:
        mid = _member("lc_l10")
        _grant(fake, mid, "tok_l10", _sub_payload(days=30))
        fake.responses["purchases/voidedpurchases"] = (True, {"voidedPurchases": [
            {"purchaseToken": "tok_l10", "orderId": "GPA.3"}]})
        fake.responses[_sub_path("tok_l10")] = (True, _sub_payload("SUBSCRIPTION_STATE_EXPIRED", days=-1))
        gp._poll_voided_purchases(datetime.now(UTC))
        assert not wdb.has_active_subscription(mid), "환불된 구독 권한이 남았다"


# ── L11~L12 ───────────────────────────────────────────────────────────────

def test_L11_member_refresh_is_throttled_and_off_render():
    with _db_isolation.isolated_db(), _google() as fake:
        mid = _member("lc_l11")
        _grant(fake, mid, "tok_l11", _sub_payload(days=30))
        before = len(fake.gets)
        assert gp._refresh_member_now(mid) == 0 and len(fake.gets) == before, "확인할 때가 안 됐는데 구글을 불렀다"
        conn = sqlite3.connect(_db_isolation.current_path())
        conn.execute("UPDATE gplay_purchases SET next_check_at = '2000-01-01 00:00:00.000000'")
        conn.commit()
        conn.close()
        assert gp._refresh_member_now(mid) == 1 and len(fake.gets) == before + 1, "확인할 때가 된 구독을 다시 보지 않았다"
        # 화면 쪽 진입은 백그라운드로 시작만 하고(렌더가 구글을 기다리지 않음), 10분 안에는 다시 시작하지 않는다.
        started = []
        saved = gp.threading.Thread

        class _NoThread:
            def __init__(self, *a, **k):
                started.append(k.get("name"))

            def start(self):
                pass

        gp.threading.Thread = _NoThread
        try:
            assert gp.refresh_member_subscriptions_if_due(mid) is True
            assert gp.refresh_member_subscriptions_if_due(mid) is False, "10분 안에 또 시작했다"
        finally:
            gp.threading.Thread = saved
        assert started == ["ln-gplay-member"]


def test_L17_carry_survives_google_expiry():
    """리뷰 지적(10-09): 구글 구독이 끝날 때 처음 남아 있던 기존 구독 기간(이월)까지 잘리면 안 된다."""
    with _db_isolation.isolated_db(), _google() as fake:
        mid = _member("lc_l17")
        assert wdb.activate_paid_advanced_sub(mid, 20)  # 포인트로 산 20일
        _grant(fake, mid, "tok_l17", _sub_payload(days=30, auto=False))
        # 포인트 구독 행이 이미 끝난 상황(구글 결제 기간 도중)으로 만든다.
        conn = sqlite3.connect(_db_isolation.current_path())
        conn.execute("UPDATE subscriptions SET expires_at = '2000-01-01 00:00:00.000000' WHERE source_ref IS NULL")
        conn.commit()
        conn.close()
        expired_at = datetime.now(UTC) - timedelta(minutes=1)
        fake.responses[_sub_path("tok_l17")] = (
            True, _sub_payload("SUBSCRIPTION_STATE_EXPIRED", auto=False, expiry=expired_at))
        gp.refresh_subscription("tok_l17")
        assert _near(_sub_expiry("tok_l17"), expired_at + timedelta(days=20)), "이월 20일이 사라졌다"
        assert wdb.has_active_subscription(mid)
        # 보류 상태로 여러 번 다시 봐도 날짜가 밀리지 않는다.
        fake.responses[_sub_path("tok_l17")] = (
            True, _sub_payload("SUBSCRIPTION_STATE_ON_HOLD", auto=True, expiry=expired_at))
        gp.refresh_subscription("tok_l17")
        gp.refresh_subscription("tok_l17")
        assert _near(_sub_expiry("tok_l17"), expired_at + timedelta(days=20)), "보류 재확인마다 날짜가 밀린다"


def test_L18_void_of_uncredited_purchase_takes_nothing():
    """리뷰 지적(10-09): 지급 전에 끊긴 결제를 구글이 자동 환불해도 다른 적립금을 빼앗지 않는다."""
    with _db_isolation.isolated_db(), _google() as fake:
        mid = _member("lc_l18")
        _wallet(mid, 500)
        wdb.record_gplay_points_purchase(mid, "ptok_l18", "points_1000", 1000)  # 기록만, 지급 전
        fake.responses["purchases/voidedpurchases"] = (True, {"voidedPurchases": [
            {"purchaseToken": "ptok_l18", "orderId": "GPA.18"}]})
        gp._poll_voided_purchases(datetime.now(UTC))
        assert wdb.get_balance(mid) == 500, "지급된 적 없는 결제 환불로 적립금이 빠졌다"
        assert wdb.get_gplay_purchase("ptok_l18")["voided_at"], "환불 표시가 남지 않아 재시도가 지급할 수 있다"
        gp._retry_unfinished(datetime.now(UTC))
        assert wdb.get_balance(mid) == 500, "환불된 결제를 재시도가 지급했다"


def test_L19_replaced_token_not_revived():
    with _db_isolation.isolated_db(), _google() as fake:
        mid = _member("lc_l19")
        _grant(fake, mid, "tok_l19a", _sub_payload(days=30, auto=False))
        _grant(fake, mid, "tok_l19b", _sub_payload(days=90, auto=False, plan="premium-quarterly", linked="tok_l19a"))
        fake.responses[_sub_path("tok_l19a")] = (True, _sub_payload(days=30, auto=False))
        assert gp._verify_and_credit_subscription(mid, "tok_l19a")[0]
        assert gp.refresh_subscription("tok_l19a") is False
        assert _sub_expiry("tok_l19a") <= datetime.now(UTC) + timedelta(seconds=5), "대체된 옛 토큰이 되살아났다"
        assert wdb.get_gplay_purchase("tok_l19a")["next_check_at"] is None


def test_L12_pending_not_credited():
    with _db_isolation.isolated_db(), _google() as fake:
        mid = _member("lc_l12")
        _wallet(mid, 0)
        fake.responses["purchases/products/points_1000/tokens/ptok_l12"] = (True, {"purchaseState": 2})
        ok, msg = gp._verify_and_credit_one_time(mid, "points_1000", "ptok_l12")
        assert not ok and "대기" in msg and wdb.get_balance(mid) == 0
        assert wdb.get_gplay_purchase("ptok_l12") is None
        fake.responses[_sub_path("tok_l12")] = (True, _sub_payload("SUBSCRIPTION_STATE_PENDING"))
        ok, msg = gp._verify_and_credit_subscription(mid, "tok_l12")
        assert not ok and "대기" in msg and not wdb.has_active_subscription(mid)


# ── L13 진입점 ─────────────────────────────────────────────────────────────

def _entry(gid, **params):
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90)
    at.query_params["page"] = "main"
    at.query_params["gid"] = gid
    for k, v in params.items():
        at.query_params[k] = v
    at.run()
    return at


def test_L13_entry_strips_buy_signal_and_shows_failure():
    import app_settings

    with _db_isolation.isolated_db(), _google() as fake:
        app_settings.init_settings_table()
        app_settings.set_auth_require_ua_match(False)
        mid = _member("lc_l13")
        wdb.link_guest_to_member("lc_gid_13", mid, None)
        fake.responses["purchases/products/points_1000/tokens/bad"] = (False, "조회 실패(400)")
        at = _entry("lc_gid_13", iap_buy="points_1000", iap_plan="premium-monthly",
                    iap_purchase_token="bad", iap_product_id="points_1000")
        assert not at.exception, at.exception
        for key in ("iap_buy", "iap_plan", "iap_purchase_token"):
            assert at.query_params.get(key) in (None, []), f"{key} 가 주소에 남았다(H4)"
        errors = [e.value for e in at.error]
        assert any("결제 확인에 실패" in (v or "") for v in errors), f"실패 안내가 화면에 없다: {errors}"
        assert not any("조회 실패(400)" in (v or "") for v in errors), "기술 메시지가 사용자에게 보인다"


# ── L14~L16 ───────────────────────────────────────────────────────────────

def test_L14_store_price_validation():
    import wallet_ui

    ok = wallet_ui._plausible_store_price
    assert ok("points_1000", "₩10,000") and ok("points_1000", "9,900원") and ok("premium-monthly", "₩12,000")
    assert not ok("points_1000", "₩100"), "터무니없이 싼 가격을 받아들였다"
    assert not ok("points_1000", "₩1,000,000"), "터무니없이 비싼 가격을 받아들였다"
    assert not ok("points_1000", "<b>무료</b>"), "꾸민 문자열을 받아들였다"
    assert not ok("points_1000", "1" * 30)
    with _db_isolation.isolated_db():
        import app_settings

        app_settings.init_settings_table()
        app_settings.set_store_prices({"points_1000": "공짜!!", "points_3000": "₩29,000"})
        exec_at = AppTest.from_string(
            "import streamlit as st, wallet_ui\nst.session_state['p'] = wallet_ui.iap_prices()", default_timeout=60)
        exec_at.query_params["iap_price_points_3000"] = "₩999,999"
        exec_at.run()
        prices = exec_at.session_state["p"]
        assert prices["points_1000"] == "10,000원", f"저장된 꾸민 가격이 쓰였다: {prices}"
        assert prices["points_3000"] == "₩29,000", f"정상 저장 가격이 무시됐다: {prices}"


def test_L15_not_configured_is_noop():
    with _db_isolation.isolated_db(), _google(configured=False) as fake:
        mid = _member("lc_l15")
        gp.refresh_member_subscriptions_if_due(mid)
        assert gp.run_maintenance_once() == {"finished": 0, "refreshed": 0, "voided": 0}
        assert gp.maybe_run_maintenance_in_background() is False
        assert fake.gets == [] and fake.posts == [], "설정 안 된 상태에서 구글을 불렀다"


def test_L16_token_not_logged_in_full():
    long_token = "x" * 120
    assert long_token not in gp._short(long_token) and len(gp._short(long_token)) < 30
    src = (ROOT / "google_play_pg.py").read_text(encoding="utf-8")
    assert "token={token}" not in src, "로그에 토큰 전체를 남기는 줄이 있다"


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_L")]


def _main() -> int:
    failed = 0
    for t in sorted(TESTS, key=lambda f: int(f.__name__.split("_")[1][1:])):
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
