# -*- coding: utf-8 -*-
"""애플(App Store) 인앱결제 서버 처리 검증 — apple_iap.py (2026-10-09, iOS 1.0.2 반려 2.1(a) 대응).

구글 수명주기 테스트(test_gplay_lifecycle)와 같은 관점으로 "첫 결제 이후"까지 본다.
애플 서버 호출은 HTTP 경계(apple_iap._api) 하나만 바꿔치기한다. DB 는 isolated_db() 로만 만진다.

  A1  권한 규칙: 활성(자동갱신/해지)·유예·결제 재시도·만료·환불·알 수 없음
  A2  적립금: 애플에 확인한 뒤 1회만 지급(재전송 멱등) · store='apple' · 샌드박스는 is_test=1
  A3  적립금 거절: 다른 회원·환불된 거래·다른 앱·모르는 상품 → FATAL(끝내기), 애플 조회 실패 → RETRY(안 끝냄)
  A4  운영에서 못 찾으면 샌드박스에서 찾는다(심사관·TestFlight 결제)
  A5  구독: 원거래 하나 = 행 하나, 지급 기간은 애플 만료일(+자동갱신 여유) · 앱이 보낸 값은 안 쓴다
  A6  구독 갱신·결제 실패·복구·만료·재구독(같은 원거래)이 다시 확인으로 반영된다
  A7  구독 거절: 다른 회원(같은 Apple ID)·이미 만료된 구독 첫 등록
  A8  구글 점검은 애플 행을 건드리지 않고, 애플 점검은 구글 행을 건드리지 않는다(store 구분)
  A9  환불(알림 이력 REFUND): 적립금 잔액 한도 회수·멱등 / 구독은 다시 확인해 차단 / 다른 앱 알림 무시
  A10 끊긴 지급은 백그라운드가 1회만 마저 지급
  A11 진입점: 주소 신호 제거 · OK·FATAL 만 '끝내기' 대기열 · RETRY·키 없음·비로그인은 안 끝냄
  A12 끝내기 신호 스크립트에는 숫자 거래 ID 만 들어간다
  A13 인증 토큰(ES256 JWT): 헤더·클레임·서명 검증
  A14 키 미설정이면 백그라운드·회원 확인 모두 아무 호출도 안 한다
  A15 iOS 가격은 'ios:' 키로 따로 저장·표시(안드로이드 가격을 덮어쓰지 않는다)
  A16 앱(tsx)과 서버의 신호·상품 이름이 같다(교차 계약)

실행: venv312\\Scripts\\python.exe -X utf8 tests\\test_apple_iap.py
"""

from __future__ import annotations

import base64
import json
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
import apple_iap as ap  # noqa: E402
import products  # noqa: E402
import wallet_db as wdb  # noqa: E402

UTC = timezone.utc
TOL = 180
BUNDLE = ap.BUNDLE_ID


def _b64(obj) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()


def _jws(payload: dict) -> str:
    return f"{_b64({'alg': 'ES256'})}.{_b64(payload)}.sig"


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _tx(tid, product="points_1000", *, orig=None, env="Production", bundle=BUNDLE, days=None, revoked=False):
    data = {
        "transactionId": str(tid),
        "originalTransactionId": str(orig or tid),
        "bundleId": bundle,
        "productId": product,
        "environment": env,
        "type": "Consumable" if product in products.POINTS_PRODUCTS else "Auto-Renewable Subscription",
    }
    if days is not None:
        data["expiresDate"] = _ms(datetime.now(UTC) + timedelta(days=days))
    if revoked:
        data["revocationDate"] = _ms(datetime.now(UTC))
    return data


def _status(orig, status=1, *, product="premium_monthly", days=30.0, auto=True, grace_days=None, revoked=False):
    tx = _tx(f"{orig}9", product, orig=orig, days=days, revoked=revoked)
    renewal = {"autoRenewStatus": 1 if auto else 0, "originalTransactionId": str(orig)}
    if grace_days is not None:
        renewal["gracePeriodExpiresDate"] = _ms(datetime.now(UTC) + timedelta(days=grace_days))
    return {
        "data": [{
            "subscriptionGroupIdentifier": products.APPLE_SUBSCRIPTION_GROUP_ID,
            "lastTransactions": [{
                "originalTransactionId": str(orig),
                "status": status,
                "signedTransactionInfo": _jws(tx),
                "signedRenewalInfo": _jws(renewal),
            }],
        }]
    }


class FakeApple:
    """(method, path, env) → (status, data). transactions[env][tid] / statuses[env][orig]."""

    def __init__(self):
        self.transactions = {"Production": {}, "Sandbox": {}}
        self.statuses = {"Production": {}, "Sandbox": {}}
        self.history = {"Production": [], "Sandbox": []}
        self.calls: list[tuple[str, str, str]] = []
        self.fail_status = None

    def api(self, method, path, env, *, body=None):
        self.calls.append((method, path, env))
        if self.fail_status:
            return self.fail_status, "stub failure"
        if path.startswith("/inApps/v1/transactions/"):
            tid = path.rsplit("/", 1)[1]
            tx = self.transactions[env].get(tid)
            return (200, {"signedTransactionInfo": _jws(tx)}) if tx else (404, {"errorCode": 4040010})
        if path.startswith("/inApps/v1/subscriptions/"):
            orig = path.rsplit("/", 1)[1]
            st = self.statuses[env].get(orig)
            return (200, st) if st else (404, {"errorCode": 4040010})
        if path.startswith("/inApps/v1/notifications/history"):
            return 200, {"notificationHistory": list(self.history[env]), "hasMore": False}
        return 500, f"no stub {path}"


@contextmanager
def _apple(configured=True):
    fake = FakeApple()
    saved = (ap._api, ap.apple_iap_configured)
    ap._api = fake.api
    ap.apple_iap_configured = lambda: configured
    ap._MEMBER_CHECKED.clear()
    try:
        yield fake
    finally:
        ap._api, ap.apple_iap_configured = saved
        ap._MEMBER_CHECKED.clear()


def _member(handle: str, balance: int | None = None) -> int:
    wdb.init_wallet_tables()
    mid, _ = wdb.get_or_create_member("kakao", handle)
    if balance is not None:
        conn = sqlite3.connect(_db_isolation.current_path())
        conn.execute("INSERT OR IGNORE INTO wallets (member_id, balance) VALUES (?, 0)", (mid,))
        conn.execute("UPDATE wallets SET balance = ? WHERE member_id = ?", (balance, mid))
        conn.commit()
        conn.close()
    return int(mid)


def _q(sql, params=()):
    conn = sqlite3.connect(_db_isolation.current_path())
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows


def _sub_expiry(orig) -> datetime:
    row = _q("SELECT expires_at FROM subscriptions WHERE source_ref = ?", (wdb.gplay_ref(ap.apple_key(orig)),))[0]
    return wdb._parse_ts(row["expires_at"])


def _near(a, b, tol=TOL):
    return abs((a - b).total_seconds()) < tol


# ── A1 ──────────────────────────────────────────────────────────────────────

def _entry(st_resp):
    item = st_resp["data"][0]["lastTransactions"][0]
    return {"status": item["status"], "tx": ap._jws_payload(item["signedTransactionInfo"]),
            "renewal": ap._jws_payload(item["signedRenewalInfo"])}


def test_A1_entitlement_rules():
    now = datetime.now(UTC)
    e = ap.apple_entitlement(_entry(_status("1", 1, days=10, auto=True)), now)
    assert _near(e["access_until"], now + timedelta(days=11)), "자동갱신 중엔 만료 + 1일"
    assert _near(e["next_check"], now + timedelta(days=1)), "하루 한 번은 다시 본다"
    assert e["base_plan_id"] == products.BASE_PLAN_MONTHLY
    e = ap.apple_entitlement(_entry(_status("1", 1, days=5, auto=False)), now)
    assert _near(e["access_until"], now + timedelta(days=5)), "해지(자동갱신 끔)해도 남은 기간은 유지"
    e = ap.apple_entitlement(_entry(_status("1", 4, days=-1, grace_days=3)), now)
    assert _near(e["access_until"], now + timedelta(days=3)), "결제 유예 기간까지 유지"
    e = ap.apple_entitlement(_entry(_status("1", 3, days=-1)), now)
    assert e["access_until"] is None and e["next_check"] is not None, "결제 재시도 중엔 차단하되 다시 본다"
    e = ap.apple_entitlement(_entry(_status("1", 2, days=-1)), now)
    assert e["access_until"] is None and e["next_check"] is None, "만료는 차단·그만 본다"
    e = ap.apple_entitlement(_entry(_status("1", 5, days=20)), now)
    assert e["access_until"] is None and e["revoked"], "환불(취소)은 즉시 차단"
    e = ap.apple_entitlement(_entry(_status("1", 1, days=20, revoked=True)), now)
    assert e["access_until"] is None and e["revoked"], "거래에 취소일이 있으면 활성 상태여도 차단"
    e = ap.apple_entitlement(_entry(_status("1", 9, days=20)), now)
    assert e["keep_access"] is True, "알 수 없는 상태면 권한을 건드리지 않는다"
    e = ap.apple_entitlement(_entry(_status("1", 1, product="premium_3months", days=80)), now)
    assert e["base_plan_id"] == products.BASE_PLAN_QUARTERLY


# ── A2~A4 적립금 ─────────────────────────────────────────────────────────────

def test_A2_points_credit_once():
    with _db_isolation.isolated_db(), _apple() as fake:
        mid = _member("ap_a2", balance=0)
        fake.transactions["Production"]["1001"] = _tx("1001", "points_3000")
        assert ap.verify_and_credit(mid, "1001") == (ap.OK, "ok")
        assert wdb.get_balance(mid) == 3000
        assert ap.verify_and_credit(mid, "1001")[0] == ap.OK, "재전송(앱 재실행)도 OK 로 끝내기"
        assert wdb.get_balance(mid) == 3000, "재전송에 두 번 지급됐다"
        row = wdb.get_gplay_purchase("apple:1001")
        assert row["store"] == "apple" and int(row["finished"]) == 1 and int(row["is_test"]) == 0
        assert _q("SELECT 1 FROM wallet_ledger WHERE ref_id = ?", ("pg:gplay:apple:1001",))


def test_A3_points_rejections():
    with _db_isolation.isolated_db(), _apple() as fake:
        a = _member("ap_a3a", balance=0)
        b = _member("ap_a3b", balance=0)
        fake.transactions["Production"]["2001"] = _tx("2001")
        assert ap.verify_and_credit(a, "2001")[0] == ap.OK
        code, msg = ap.verify_and_credit(b, "2001")
        assert code == ap.FATAL and "다른 계정" in msg and wdb.get_balance(b) == 0, "다른 회원이 같은 거래로 받았다"
        fake.transactions["Production"]["2002"] = _tx("2002", revoked=True)
        assert ap.verify_and_credit(a, "2002")[0] == ap.FATAL
        fake.transactions["Production"]["2003"] = _tx("2003", bundle="com.other.app")
        assert ap.verify_and_credit(a, "2003")[0] == ap.FATAL, "다른 앱의 거래를 받아들였다"
        fake.transactions["Production"]["2004"] = _tx("2004", "gems_100")
        assert ap.verify_and_credit(a, "2004")[0] == ap.FATAL
        assert ap.verify_and_credit(a, "../etc")[0] == ap.FATAL, "거래 ID 형식을 안 막았다"
        assert ap.verify_and_credit(a, "2999")[0] == ap.RETRY, "애플이 모르는 거래는 끝내지 말고 다음에 다시"
        fake.fail_status = 503
        fake.transactions["Production"]["2005"] = _tx("2005")
        assert ap.verify_and_credit(a, "2005")[0] == ap.RETRY
        assert wdb.get_balance(a) == 1000, "거절된 거래에서 지급됐다"


def test_A4_sandbox_fallback_marks_test():
    with _db_isolation.isolated_db(), _apple() as fake:
        mid = _member("ap_a4", balance=0)
        fake.transactions["Sandbox"]["3001"] = _tx("3001", env="Sandbox")
        assert ap.verify_and_credit(mid, "3001")[0] == ap.OK
        envs = [c[2] for c in fake.calls if "/transactions/" in c[1]]
        assert envs == ["Production", "Sandbox"], f"운영 → 샌드박스 순서가 아니다: {envs}"
        assert int(wdb.get_gplay_purchase("apple:3001")["is_test"]) == 1, "샌드박스 결제를 테스트로 표시하지 않았다"


# ── A5~A7 구독 ───────────────────────────────────────────────────────────────

def _sub(fake, mid, orig, tid, *, status=None, env="Production", product="premium_monthly", **kw):
    fake.transactions[env][tid] = _tx(tid, product, orig=orig, env=env, days=30)
    fake.statuses[env][orig] = status or _status(orig, product=product, **kw)
    return ap.verify_and_credit(mid, tid)


def test_A5_subscription_grant_follows_apple_expiry():
    with _db_isolation.isolated_db(), _apple() as fake:
        mid = _member("ap_a5")
        assert _sub(fake, mid, "5000", "5001", days=30, auto=True)[0] == ap.OK
        assert wdb.has_active_subscription(mid)
        assert _near(_sub_expiry("5000"), datetime.now(UTC) + timedelta(days=31))
        row = wdb.get_gplay_purchase("apple:5000")
        assert row["store"] == "apple" and row["kind"] == "sub" and row["base_plan_id"] == products.BASE_PLAN_MONTHLY
        # 3개월 제품은 애플 응답의 제품 ID 로 기간이 정해진다.
        assert _sub(fake, mid, "5100", "5101", product="premium_3months", days=90)[0] == ap.OK
        assert wdb.get_gplay_purchase("apple:5100")["base_plan_id"] == products.BASE_PLAN_QUARTERLY


def test_A6_renew_fail_recover_expire_resubscribe():
    with _db_isolation.isolated_db(), _apple() as fake:
        mid = _member("ap_a6")
        assert _sub(fake, mid, "6000", "6001", days=30)[0] == ap.OK
        fake.statuses["Production"]["6000"] = _status("6000", 1, days=60)
        assert ap.refresh_subscription("apple:6000")
        assert _near(_sub_expiry("6000"), datetime.now(UTC) + timedelta(days=61)), "갱신이 반영되지 않았다"
        fake.statuses["Production"]["6000"] = _status("6000", 3, days=-0.1)
        ap.refresh_subscription("apple:6000")
        assert not wdb.has_active_subscription(mid), "결제 실패(재시도 중)인데 권한이 남았다"
        assert wdb.get_gplay_purchase("apple:6000")["next_check_at"], "결제 재시도 중엔 계속 다시 봐야 한다"
        fake.statuses["Production"]["6000"] = _status("6000", 1, days=30)
        ap.refresh_subscription("apple:6000")
        assert wdb.has_active_subscription(mid), "결제가 복구됐는데 권한이 안 돌아왔다"
        fake.statuses["Production"]["6000"] = _status("6000", 2, days=-1, auto=False)
        ap.refresh_subscription("apple:6000")
        assert not wdb.has_active_subscription(mid)
        assert wdb.get_gplay_purchase("apple:6000")["next_check_at"] is None
        # 같은 그룹에 다시 구독 → 애플은 같은 원거래 ID 를 쓴다 → 앱이 새 거래를 보내면 다시 권한.
        fake.transactions["Production"]["6005"] = _tx("6005", "premium_3months", orig="6000", days=90)
        fake.statuses["Production"]["6000"] = _status("6000", 1, product="premium_3months", days=90)
        assert ap.verify_and_credit(mid, "6005")[0] == ap.OK
        assert wdb.has_active_subscription(mid), "재구독이 반영되지 않았다"
        assert wdb.get_gplay_purchase("apple:6000")["base_plan_id"] == products.BASE_PLAN_QUARTERLY
        assert len(_q("SELECT 1 FROM gplay_purchases WHERE purchase_token LIKE 'apple:6%'")) == 1


def test_A7_subscription_rejections():
    with _db_isolation.isolated_db(), _apple() as fake:
        a = _member("ap_a7a")
        b = _member("ap_a7b")
        assert _sub(fake, a, "7000", "7001")[0] == ap.OK
        fake.transactions["Production"]["7002"] = _tx("7002", "premium_monthly", orig="7000", days=30)
        code, msg = ap.verify_and_credit(b, "7002")
        assert code == ap.FATAL and "다른 계정" in msg and not wdb.has_active_subscription(b)
        code, _ = _sub(fake, b, "7100", "7101", status=_status("7100", 2, days=-3, auto=False))
        assert code == ap.FATAL and not wdb.has_active_subscription(b), "만료된 구독을 새로 등록했다"


# ── A8 store 구분 ────────────────────────────────────────────────────────────

def test_A8_google_and_apple_jobs_are_separate():
    import google_play_pg as gp

    with _db_isolation.isolated_db(), _apple() as fake:
        mid = _member("ap_a8")
        assert _sub(fake, mid, "8000", "8001", days=0.001)[0] == ap.OK
        later = datetime.now(UTC) + timedelta(days=2)
        assert not wdb.list_due_gplay_subscriptions(later), "구글 점검 목록에 애플 구독이 섞였다"
        assert wdb.list_due_gplay_subscriptions(later, store="apple"), "애플 점검 목록에 없다"
        wdb.record_gplay_points_purchase(mid, "gtoken_a8", "points_1000", 1000)
        old = datetime.now(UTC) - timedelta(days=1)
        assert [r["purchase_token"] for r in wdb.list_unfinished_gplay_purchases(old)] == ["gtoken_a8"]
        assert wdb.list_unfinished_gplay_purchases(old, store="apple") == []
        assert not ap.refresh_subscription("gtoken_a8"), "애플 확인이 구글 행을 건드렸다"
        assert not gp.refresh_subscription("apple:8000"), "구글 확인이 애플 행을 구글에 물었다"


# ── A9 환불 ─────────────────────────────────────────────────────────────────

def _refund_notice(tx: dict) -> dict:
    return {"signedPayload": _jws({"notificationType": "REFUND",
                                   "data": {"bundleId": BUNDLE, "signedTransactionInfo": _jws(tx)}})}


def test_A9_refunds_from_notification_history():
    import app_settings

    with _db_isolation.isolated_db(), _apple() as fake:
        app_settings.init_settings_table()
        mid = _member("ap_a9", balance=0)
        fake.transactions["Production"]["9001"] = _tx("9001", "points_3000")
        assert ap.verify_and_credit(mid, "9001")[0] == ap.OK
        conn = sqlite3.connect(_db_isolation.current_path())
        conn.execute("UPDATE wallets SET balance = 1200 WHERE member_id = ?", (mid,))  # 1,800P 사용
        conn.commit()
        conn.close()
        assert _sub(fake, mid, "9100", "9101", days=30)[0] == ap.OK
        fake.statuses["Production"]["9100"] = _status("9100", 5, days=30)
        fake.history["Production"] = [
            _refund_notice(_tx("9001", "points_3000")),
            _refund_notice(_tx("9102", "premium_monthly", orig="9100")),
            _refund_notice(_tx("9999", "points_1000", bundle="com.other.app")),
        ]
        summary = ap.run_maintenance_once()
        assert summary["refunds"] == 2, summary
        assert wdb.get_balance(mid) == 0, "잔액 한도까지 회수하지 않았다"
        assert not wdb.has_active_subscription(mid), "환불된 구독이 남았다"
        assert wdb.get_gplay_purchase("apple:9100")["voided_at"]
        again = ap.run_maintenance_once()
        assert again["refunds"] == 1 and wdb.get_balance(mid) == 0, "겹쳐 읽은 구간에서 두 번 회수했다"
        assert app_settings.get_setting("apple_refund_last_poll_ms_production", "")


# ── A10 끊긴 지급 ────────────────────────────────────────────────────────────

def test_A10_interrupted_credit_is_finished_once():
    with _db_isolation.isolated_db(), _apple():
        mid = _member("ap_a10", balance=0)
        wdb.record_gplay_points_purchase(mid, "apple:10001", "points_1000", 1000, store="apple")
        ap.run_maintenance_once()
        ap.run_maintenance_once()
        assert wdb.get_balance(mid) == 1000
        assert int(wdb.get_gplay_purchase("apple:10001")["finished"]) == 1


# ── A11~A12 진입점 ───────────────────────────────────────────────────────────

_ENTRY = """
import streamlit as st, apple_iap
member = st.session_state.get('member')
st.session_state['ret'] = apple_iap.handle_apple_purchase_return(member)
st.session_state['queue'] = list(st.session_state.get(apple_iap.FINISH_SESSION_KEY) or [])
st.session_state['params'] = dict(st.query_params)
"""


def _run_entry(member, tx, **extra):
    at = AppTest.from_string(_ENTRY, default_timeout=60)
    if member is not None:
        at.session_state["member"] = member
    at.query_params["iap_apple_tx"] = tx
    for k, v in extra.items():
        at.query_params[k] = v
    at.run()
    assert not at.exception, at.exception
    return at


def test_A11_entry_queues_finish_only_when_done():
    with _db_isolation.isolated_db(), _apple() as fake:
        mid = _member("ap_a11", balance=0)
        fake.transactions["Production"]["11001"] = _tx("11001")
        at = _run_entry(mid, "11001", iap_finish="5", iap_restore="1")
        assert at.session_state["ret"] is True
        assert at.session_state["queue"] == ["11001"], "지급 성공인데 끝내기 대기열에 없다"
        params = at.session_state["params"]
        for key in ("iap_apple_tx", "iap_finish", "iap_restore"):
            assert key not in params, f"{key} 가 주소에 남았다"
        assert at.session_state["wallet_toast"] == "결제가 완료되었습니다."
        other = _member("ap_a11b", balance=0)
        at = _run_entry(other, "11001")
        assert at.session_state["queue"] == ["11001"], "다른 계정(FATAL)도 끝내야 앱 실행마다 반복되지 않는다"
        assert "다른 로또신령 계정" in at.session_state["wallet_toast_error"]
        at = _run_entry(mid, "11999")  # 애플이 모름 → RETRY
        assert at.session_state["queue"] == [], "일시 실패인데 거래를 끝냈다(지급 기회를 잃는다)"
        at = _run_entry(None, "11001")
        assert at.session_state["queue"] == [] and "로그인" in at.session_state["wallet_toast_error"]
    with _db_isolation.isolated_db(), _apple(configured=False) as fake:
        mid = _member("ap_a11c", balance=0)
        at = _run_entry(mid, "11001")
        assert at.session_state["queue"] == [] and not fake.calls, "키가 없는데 애플을 불렀거나 거래를 끝냈다"


def test_A12_finish_signal_only_digits():
    script = """
import streamlit as st, apple_iap
st.session_state[apple_iap.FINISH_SESSION_KEY] = ['123', "1');alert(1);//", '456']
apple_iap.render_finish_signals()
st.session_state['left'] = st.session_state[apple_iap.FINISH_SESSION_KEY]
"""
    captured = {}
    import streamlit.components.v1 as components

    saved = components.html
    components.html = lambda body, **kw: captured.setdefault("body", body)
    try:
        at = AppTest.from_string(script, default_timeout=60)
        at.run()
    finally:
        components.html = saved
    assert not at.exception, at.exception
    body = captured.get("body", "")
    assert '["123", "456"]' in body and "alert" not in body, body[:300]
    assert "iapFinish" in body and "iap_finish" in body
    assert at.session_state["left"] == []


# ── A13 인증 토큰 ────────────────────────────────────────────────────────────

def test_A13_api_token_is_valid_es256():
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    token = ap._make_api_token({"key_id": "KID123", "issuer": "ISS-1", "pem": pem}, 1_700_000_000)
    h, p, s = token.split(".")
    header = ap._jws_payload(f"x.{h}.y")
    claims = ap._jws_payload(token)
    assert header == {"alg": "ES256", "kid": "KID123", "typ": "JWT"}, header
    assert claims["aud"] == "appstoreconnect-v1" and claims["bid"] == BUNDLE and claims["iss"] == "ISS-1"
    assert claims["exp"] - claims["iat"] <= 3600
    raw = base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
    assert len(raw) == 64, "ES256 서명은 r||s 64바이트"
    sig = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
    key.public_key().verify(sig, f"{h}.{p}".encode(), ec.ECDSA(hashes.SHA256()))


# ── A14 키 없음 ──────────────────────────────────────────────────────────────

def test_A14_not_configured_is_noop():
    with _db_isolation.isolated_db(), _apple(configured=False) as fake:
        assert ap.maybe_run_maintenance_in_background() is False
        assert ap.refresh_member_subscriptions_if_due(1) is False
        assert ap.run_maintenance_once() == {"finished": 0, "refreshed": 0, "refunds": 0}
        assert fake.calls == []


# ── A15 iOS 가격 ─────────────────────────────────────────────────────────────

def test_A15_ios_prices_are_kept_apart():
    import app_settings

    script = "import streamlit as st, wallet_ui\nst.session_state['p'] = wallet_ui.iap_prices()"
    with _db_isolation.isolated_db():
        app_settings.init_settings_table()
        app_settings.set_store_prices({"points_1000": "₩10,000"})
        at = AppTest.from_string(script, default_timeout=60)
        for k, v in {"native": "1", "native_platform": "ios", "iap": "1",
                     "iap_price_points_1000": "₩9,900", "iap_price_premium_monthly": "₩11,000"}.items():
            at.query_params[k] = v
        at.run()
        p = at.session_state["p"]
        assert p["points_1000"] == "₩9,900" and p["premium-monthly"] == "₩11,000", p
        assert p["points_3000"] == products.IAP_PRICE_FALLBACK_IOS["points_3000"], "iOS 기본값이 아니다"
        saved = app_settings.get_store_prices()
        assert saved["points_1000"] == "₩10,000", "iOS 가격이 안드로이드 가격을 덮어썼다"
        assert saved["ios:points_1000"] == "₩9,900"
        android = AppTest.from_string(script, default_timeout=60)
        android.query_params["native"] = "1"
        android.run()
        assert android.session_state["p"]["points_1000"] == "₩10,000"
        ios_again = AppTest.from_string(script, default_timeout=60)
        ios_again.query_params["native"] = "1"
        ios_again.query_params["native_platform"] = "ios"
        ios_again.run()
        assert ios_again.session_state["p"]["points_1000"] == "₩9,900", "저장된 iOS 가격을 안 쓴다"


# ── A16 교차 계약 ────────────────────────────────────────────────────────────

def test_A16_app_and_server_names_match():
    tsx = (ROOT / "LottoShinryeong" / "components" / "streamlit-webview.tsx").read_text(encoding="utf-8")
    for apple_id, plan in products.APPLE_SUBSCRIPTION_PRODUCTS.items():
        assert f"{apple_id}: '{plan}'" in tsx, f"앱의 애플 구독 매핑에 {apple_id} → {plan} 이 없다"
    for name in (ap.TX_PARAM, ap.FINISH_PARAM, ap.RESTORE_PARAM):
        assert f"'{name}'" in tsx, f"앱이 {name} 를 모른다"
    for msg in (ap.FINISH_MESSAGE_TYPE, ap.RESTORE_MESSAGE_TYPE):
        assert f"'{msg}'" in tsx, f"앱이 {msg} 메시지를 처리하지 않는다"
    assert "const IAP_CAPABILITY_PARAMS: Record<string, string> = { iap: '1' };" in tsx, "iOS 도 iap=1 을 보내야 한다"
    assert "finishTransaction(" in tsx and "isAppStoreUrl(request.url)" in tsx
    for pid in products.POINTS_PRODUCTS:
        assert pid in products.IAP_PRICE_FALLBACK_IOS


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_A")]


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
