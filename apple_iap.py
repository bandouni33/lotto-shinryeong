"""App Store(애플) 인앱결제 서버 처리 — 검증·지급·구독 상태 추적·환불 회수 (2026-10-09).

[왜] iOS 1.0.2(빌드 11)가 "충전을 눌렀더니 '결제 연동 준비 중'만 뜬다"로 반려됐다(2.1(a) 앱 완성도).
애플 앱 안에서 디지털 재화(적립금·구독)는 애플 인앱결제로만 팔 수 있어 이 모듈을 만든다.

[흐름 — 구글(google_play_pg.py)과 같은 뼈대]
  1. 앱(streamlit-webview.tsx)이 StoreKit 으로 결제한 뒤 거래 ID 를 ?iap_apple_tx=<거래 ID> 로 실어 보낸다.
  2. 서버는 그 값을 믿지 않고 App Store Server API 로 **애플에 직접** 거래를 조회한다(TLS 로 애플에서
     받은 응답만 쓴다 — 앱이 보낸 서명 데이터를 따로 검증할 필요가 없다).
     운영 환경에서 못 찾으면 샌드박스(심사관·TestFlight 결제)에서 다시 찾는다(애플 권장 순서).
  3. 적립금: 거래당 한 번 지급(원장 ref = pg:gplay:apple:<거래 ID>, 멱등).
     구독: 원거래 ID 당 한 행 — 애플 만료일을 따라가며 권한을 준다(갱신·해지·결제 실패·환불 반영).
  4. 처리가 끝나면 앱에 "이 거래를 끝내라(finishTransaction)" 신호를 보낸다. 애플은 끝내지 않은 거래를
     앱을 켤 때마다 다시 보내므로, 앱이 꺼져 신호를 못 받아도 다음 실행 때 같은 경로로 이어진다.
     (구글과 달리 서버가 할 승인 단계가 없고, 미완료 거래를 3일 뒤 자동 환불하지도 않는다.)

[저장] wallet_db 의 gplay_purchases 표를 store='apple' 로 같이 쓴다(이월·탈퇴·출시 전 초기화가 그대로 동작).
       키: 'apple:<거래 ID>'(적립금) / 'apple:<원거래 ID>'(구독). 샌드박스 결제는 is_test=1.

[구독 상태] 서버(Streamlit)는 애플 서버 알림(POST)을 받을 수 없어, 확인할 때가 된 구독을 직접 조회한다
           (Get All Subscription Statuses). 환불은 애플 '알림 이력'(Get Notification History, REFUND)을
           한 시간마다 읽어 회수한다 — 알림 이력은 애플이 **보내려고 시도한** 알림만 남으므로 App Store
           Connect 에 서버 알림 주소(V2)를 등록해 둬야 한다(우리 서버가 받지 못해도 이력에는 남는다).

[키] App Store Connect → 사용자 및 액세스 → 통합 → 앱 내 구입 키(.p8). 값은 Cloud secrets 에만 둔다:
     APPLE_IAP_KEY_ID · APPLE_IAP_ISSUER_ID · APPLE_IAP_PRIVATE_KEY(.p8 파일 내용 전체).
     키가 없으면 이 모듈은 아무 호출도 하지 않는다(결제 확인 시 '준비되지 않음' 안내 + 기록).
"""

from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone

import requests

import products
from wallet_db import (
    activate_gplay_subscription,
    charge_points,
    get_gplay_purchase,
    gplay_ref,
    list_due_gplay_subscriptions,
    list_unfinished_gplay_purchases,
    mark_gplay_finished,
    mark_gplay_voided,
    reclaim_voided_gplay_points,
    record_gplay_points_purchase,
    update_gplay_subscription,
)

STORE = "apple"
KEY_PREFIX = "apple:"
# 번들 ID 의 기준점은 Apple 로그인 검증과 같은 값(auth_providers.APPLE_BUNDLE_ID, AGENTS §2 Q행)이다.
from auth_providers import APPLE_BUNDLE_ID as BUNDLE_ID  # noqa: E402
API_HOSTS = {
    "Production": "https://api.storekit.itunes.apple.com",
    "Sandbox": "https://api.storekit-sandbox.itunes.apple.com",
}
# 거래 ID 는 숫자 문자열이다 — 주소(경로)와 앱으로 보내는 스크립트에 그대로 들어가므로 형식을 먼저 막는다.
_TX_ID_RE = re.compile(r"^[0-9]{1,32}$")

# 앱 ↔ 서버 신호 이름 — streamlit-webview.tsx 와 한 쌍이다(테스트가 양쪽 이름을 대조한다).
TX_PARAM = "iap_apple_tx"          # 앱 → 서버: 결제(또는 복원)된 거래 ID
FINISH_PARAM = "iap_finish"        # 서버 → 앱(주소 폴백): 끝내도 되는 거래 ID
FINISH_MESSAGE_TYPE = "iapFinish"  # 서버 → 앱(postMessage)
RESTORE_MESSAGE_TYPE = "iapRestore"
RESTORE_PARAM = "iap_restore"
FINISH_SESSION_KEY = "apple_iap_finish_queue"

# 권한 판정 시간 규칙 — 구글과 같은 값(google_play_pg)으로 맞춘다.
RENEWAL_BUFFER = timedelta(days=1)       # 자동갱신 중이면 만료 뒤 하루는 갱신 반영을 기다린다
RECHECK_MAX = timedelta(hours=24)
RECHECK_OVERDUE = timedelta(hours=3)
RECHECK_SUSPENDED = timedelta(hours=6)
UNFINISHED_RETRY_WINDOW = timedelta(days=3)

# App Store Server API 의 구독 상태 값.
STATUS_ACTIVE = 1
STATUS_EXPIRED = 2
STATUS_BILLING_RETRY = 3
STATUS_GRACE = 4
STATUS_REVOKED = 5
_STATE_NAMES = {
    STATUS_ACTIVE: "APPLE_ACTIVE",
    STATUS_EXPIRED: "APPLE_EXPIRED",
    STATUS_BILLING_RETRY: "APPLE_BILLING_RETRY",
    STATUS_GRACE: "APPLE_GRACE",
    STATUS_REVOKED: "APPLE_REVOKED",
}

# 결과 구분 — 앱에 '거래 끝내기'를 보낼지 정한다.
OK = "ok"        # 처리 끝(이미 처리된 것 포함) → 끝내기
RETRY = "retry"  # 일시 실패(네트워크·키 없음·애플이 아직 모름) → 끝내지 않는다(다음 실행 때 애플이 다시 보낸다)
FATAL = "fatal"  # 다시 해도 안 됨(다른 계정·환불됨·모르는 상품) → 끝낸다(앱 켤 때마다 오류가 반복되지 않게)


# ── 키·인증 ─────────────────────────────────────────────────────────────────

def _secret(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    try:
        import streamlit as st

        return str(st.secrets.get(name, "") or "").strip()
    except Exception:
        return ""


def _key_config() -> dict | None:
    key_id = _secret("APPLE_IAP_KEY_ID")
    issuer = _secret("APPLE_IAP_ISSUER_ID")
    pem = _secret("APPLE_IAP_PRIVATE_KEY").replace("\\n", "\n")
    if not (key_id and issuer and "PRIVATE KEY" in pem):
        return None
    return {"key_id": key_id, "issuer": issuer, "pem": pem}


def apple_iap_configured() -> bool:
    return _key_config() is not None


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


_token_cache: dict = {"token": None, "exp": 0.0, "kid": None}
_token_lock = threading.Lock()


def _make_api_token(cfg: dict, now: float) -> str:
    """App Store Server API 인증 토큰(ES256 JWT, 20분). 애플 문서의 필수 항목만 넣는다."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

    header = {"alg": "ES256", "kid": cfg["key_id"], "typ": "JWT"}
    payload = {
        "iss": cfg["issuer"],
        "iat": int(now),
        "exp": int(now) + 1200,
        "aud": "appstoreconnect-v1",
        "bid": BUNDLE_ID,
    }
    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url(json.dumps(payload, separators=(",", ":")).encode())
    )
    key = serialization.load_pem_private_key(cfg["pem"].encode(), password=None)
    der = key.sign(signing_input.encode("ascii"), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    return signing_input + "." + _b64url(r.to_bytes(32, "big") + s.to_bytes(32, "big"))


def _api_token() -> str | None:
    cfg = _key_config()
    if not cfg:
        return None
    now = time.time()
    with _token_lock:
        if _token_cache["token"] and _token_cache["kid"] == cfg["key_id"] and now < _token_cache["exp"]:
            return _token_cache["token"]
        try:
            token = _make_api_token(cfg, now)
        except Exception:
            return None
        _token_cache.update(token=token, exp=now + 900, kid=cfg["key_id"])
        return token


def _api(method: str, path: str, env: str, *, body: dict | None = None) -> tuple[int, dict | str]:
    """(HTTP 상태, JSON 또는 오류 문자열). 상태 0 = 통신 실패·키 없음."""
    token = _api_token()
    if not token:
        return 0, "애플 결제 키가 설정되지 않았습니다."
    try:
        resp = requests.request(
            method,
            f"{API_HOSTS[env]}{path}",
            headers={"Authorization": f"Bearer {token}"},
            json=body,
            timeout=15,
        )
    except requests.RequestException as exc:
        return 0, f"애플 서버 통신 실패: {exc}"
    try:
        data = resp.json()
    except Exception:
        data = resp.text[:300]
    return resp.status_code, data


def _jws_payload(jws: str) -> dict:
    """애플이 TLS 로 직접 보내준 서명 데이터(JWS)의 내용. 서명 검증은 하지 않는다 — 앱이 아니라 애플
    API 응답에서만 꺼내 쓰기 때문이다(앱이 보낸 JWS 는 이 함수로 읽지 않는다)."""
    part = str(jws or "").split(".")
    if len(part) != 3:
        return {}
    raw = part[1] + "=" * (-len(part[1]) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(raw))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _log(event: str, detail: str) -> None:
    try:
        import security_log

        security_log.log_event(event, detail[:500])
    except Exception:
        pass


def _ms_to_dt(value) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def apple_key(identifier: str) -> str:
    return f"{KEY_PREFIX}{identifier}"


def valid_transaction_id(value) -> bool:
    return bool(_TX_ID_RE.match(str(value or "")))


# ── 애플 조회 ────────────────────────────────────────────────────────────────

def _fetch_transaction(transaction_id: str) -> tuple[bool, dict | str, str | None]:
    """(성공, 거래 내용 또는 오류, 환경). 운영 → 샌드박스 순으로 찾는다."""
    last_error = "거래를 찾지 못했습니다"
    for env in ("Production", "Sandbox"):
        status, data = _api("GET", f"/inApps/v1/transactions/{transaction_id}", env)
        if status == 200 and isinstance(data, dict):
            info = _jws_payload(data.get("signedTransactionInfo", ""))
            if not info:
                return False, "거래 내용을 읽지 못했습니다", env
            return True, info, env
        if status == 404:
            continue
        return False, f"조회 실패({status}): {data}", env
    return False, last_error, None


def _fetch_subscription_status(original_id: str, env: str) -> tuple[bool, dict | str]:
    """원거래 ID 의 최신 구독 상태 {status, tx, renewal}."""
    status, data = _api("GET", f"/inApps/v1/subscriptions/{original_id}", env)
    if status != 200 or not isinstance(data, dict):
        return False, f"구독 조회 실패({status}): {data}"
    for group in data.get("data") or []:
        for item in group.get("lastTransactions") or []:
            if str(item.get("originalTransactionId")) == str(original_id):
                return True, {
                    "status": item.get("status"),
                    "tx": _jws_payload(item.get("signedTransactionInfo", "")),
                    "renewal": _jws_payload(item.get("signedRenewalInfo", "")),
                }
    return False, "구독 상태에 이 거래가 없습니다"


# ── 권한 판정(구독) ──────────────────────────────────────────────────────────

def apple_entitlement(entry: dict, now: datetime | None = None) -> dict:
    """구독 상태 조회 결과 → 우리 권한 결정. 반환 키는 구글 판정(google_play_pg.subscription_entitlement)과
    같은 모양: state, base_plan_id, google_expiry(=애플 만료 시각), access_until(None=차단),
    next_check(None=그만 봄), keep_access(해석 불가 — 권한은 그대로 두고 나중에 다시 본다), revoked."""
    now = now or datetime.now(timezone.utc)
    status = entry.get("status")
    tx = entry.get("tx") or {}
    renewal = entry.get("renewal") or {}
    expiry = _ms_to_dt(tx.get("expiresDate"))
    revoked = status == STATUS_REVOKED or bool(tx.get("revocationDate"))
    result = {
        "state": _STATE_NAMES.get(status, f"APPLE_{status}"),
        "base_plan_id": products.APPLE_SUBSCRIPTION_PRODUCTS.get(str(tx.get("productId") or "")),
        "google_expiry": expiry,
        "access_until": None,
        "next_check": None,
        "keep_access": False,
        "revoked": revoked,
    }
    if revoked:
        result["state"] = _STATE_NAMES[STATUS_REVOKED]
        return result
    if status == STATUS_ACTIVE:
        if not expiry:
            result["keep_access"] = True
            result["next_check"] = now + RECHECK_OVERDUE
            return result
        auto_renew = int(renewal.get("autoRenewStatus") or 0) == 1
        result["access_until"] = expiry + RENEWAL_BUFFER if auto_renew else expiry
        next_check = expiry if expiry > now else now + RECHECK_OVERDUE
        result["next_check"] = min(next_check, now + RECHECK_MAX)
    elif status == STATUS_GRACE:
        # 결제 유예 기간 — 애플이 결제를 다시 시도하는 동안 권한을 유지한다(ASC 에서 켰을 때만 온다).
        until = _ms_to_dt(renewal.get("gracePeriodExpiresDate")) or expiry
        if until and until > now:
            result["access_until"] = until
            result["next_check"] = min(until, now + RECHECK_SUSPENDED)
        else:
            result["next_check"] = now + RECHECK_SUSPENDED
    elif status == STATUS_BILLING_RETRY:
        # 결제 실패 후 재시도 중 — 권한은 끊고, 결제가 되면 같은 원거래로 복구되니 계속 본다.
        result["next_check"] = now + RECHECK_SUSPENDED
    elif status == STATUS_EXPIRED:
        pass
    else:
        result["keep_access"] = True
        result["next_check"] = now + RECHECK_SUSPENDED
    return result


def _env_of(row: dict | None) -> str:
    return "Sandbox" if row and int(row.get("is_test") or 0) else "Production"


def _apply_entitlement(key: str, ent: dict) -> None:
    update_gplay_subscription(
        key,
        state=ent["state"],
        google_expiry=ent["google_expiry"],
        access_until=ent["access_until"],
        next_check=ent["next_check"],
        keep_access=ent["keep_access"],
        base_plan_id=ent["base_plan_id"],
    )


# ── 지급 ────────────────────────────────────────────────────────────────────

def _credit_points(member_id: int, info: dict, env: str) -> tuple[str, str]:
    transaction_id = str(info.get("transactionId") or "")
    product_id = str(info.get("productId") or "")
    points = products.POINTS_PRODUCTS.get(product_id)
    if not points or not valid_transaction_id(transaction_id):
        return FATAL, f"알 수 없는 상품: {product_id}"
    key = apple_key(transaction_id)
    existing = get_gplay_purchase(key)
    if existing:
        if int(existing["member_id"]) != int(member_id):
            return FATAL, "다른 계정에서 이미 처리된 결제입니다"
        if existing.get("voided_at"):
            return FATAL, "환불·취소된 결제입니다"
    if info.get("revocationDate"):
        return FATAL, "환불·취소된 결제입니다"
    # 지급 전에 먼저 기록 — 아래에서 끊겨도 백그라운드가 이어서 지급한다(원장 ref 로 멱등).
    record_gplay_points_purchase(
        member_id, key, product_id, points, is_test=(env == "Sandbox"), store=STORE
    )
    if not charge_points(member_id, points, gplay_ref(key)):
        return RETRY, "포인트 지급 실패(지갑 없음 등)"
    mark_gplay_finished(key)
    return OK, "ok"


def _credit_subscription(member_id: int, info: dict, env: str) -> tuple[str, str]:
    original_id = str(info.get("originalTransactionId") or "")
    if not valid_transaction_id(original_id):
        return FATAL, "원거래 ID 형식 오류"
    key = apple_key(original_id)
    existing = get_gplay_purchase(key)
    if existing and int(existing["member_id"]) != int(member_id):
        # 같은 Apple ID 의 구독을 다른 회원이 또 받지 못하게 한다(구글과 같은 규칙).
        return FATAL, "다른 계정에 연결된 구독입니다"

    ok, entry = _fetch_subscription_status(original_id, env)
    if not ok:
        return RETRY, str(entry)
    ent = apple_entitlement(entry)
    if existing:
        # 같은 원거래(갱신·요금제 변경·재구독·복원) — 상태만 최신으로 맞춘다.
        _apply_entitlement(key, ent)
        if not int(existing.get("finished") or 0):
            mark_gplay_finished(key)
        return OK, "ok"

    if ent["access_until"] is None and not ent["keep_access"]:
        return FATAL, f"구독이 유효하지 않습니다({ent['state']})"
    base_plan_id = ent["base_plan_id"]
    # 기간은 애플이 돌려준 제품 ID 로만 정한다(앱이 보낸 값은 쓰지 않는다).
    if base_plan_id not in products.SUBSCRIPTION_BASE_PLAN_DAYS:
        return FATAL, "알 수 없는 구독 상품"
    expiry = ent["google_expiry"]
    access_until = ent["access_until"]
    if expiry is None or access_until is None:
        expiry = datetime.now(timezone.utc) + timedelta(days=products.SUBSCRIPTION_BASE_PLAN_DAYS[base_plan_id])
        access_until = expiry
    activated = activate_gplay_subscription(
        member_id,
        key,
        base_plan_id,
        state=ent["state"],
        google_expiry=expiry,
        access_until=access_until,
        next_check=ent["next_check"],
        is_test=(env == "Sandbox"),
        store=STORE,
    )
    if not activated:
        return RETRY, "구독 활성화 실패"
    mark_gplay_finished(key)
    return OK, "ok"


def verify_and_credit(member_id: int, transaction_id: str) -> tuple[str, str]:
    """거래 하나를 애플에 확인하고 지급한다. 반환 (OK|RETRY|FATAL, 사유)."""
    if not valid_transaction_id(transaction_id):
        return FATAL, "거래 ID 형식 오류"
    ok, info, env = _fetch_transaction(transaction_id)
    if not ok:
        return RETRY, str(info)
    if info.get("bundleId") != BUNDLE_ID:
        return FATAL, f"다른 앱의 거래입니다({info.get('bundleId')})"
    product_id = str(info.get("productId") or "")
    if product_id in products.POINTS_PRODUCTS:
        return _credit_points(member_id, info, env or "Production")
    if product_id in products.APPLE_SUBSCRIPTION_PRODUCTS:
        return _credit_subscription(member_id, info, env or "Production")
    return FATAL, f"알 수 없는 상품: {product_id}"


# ── 구독 다시 확인 ───────────────────────────────────────────────────────────

def refresh_subscription(key: str) -> bool:
    """저장된 애플 구독 하나를 애플에 다시 물어 권한을 맞춘다."""
    row = get_gplay_purchase(key)
    if not row or row.get("kind") != "sub" or row.get("store") != STORE:
        return False
    original_id = key[len(KEY_PREFIX):]
    ok, entry = _fetch_subscription_status(original_id, _env_of(row))
    if not ok:
        update_gplay_subscription(
            key,
            state=str(row.get("state") or ""),
            google_expiry=None,
            access_until=None,
            next_check=(datetime.now(timezone.utc) + timedelta(hours=1)) if row.get("next_check_at") else None,
            keep_access=True,
        )
        _log("apple_refresh_failed", f"member_id={row['member_id']} key={key} msg={entry}")
        return False
    ent = apple_entitlement(entry)
    _apply_entitlement(key, ent)
    if ent["revoked"]:
        mark_gplay_voided(key)
    return True


MEMBER_RECHECK_SECONDS = 600
_MEMBER_CHECKED: dict[int, float] = {}
_MEMBER_CHECK_LOCK = threading.Lock()


def _db_identity() -> int:
    try:
        import db_turso

        return id(db_turso.connect)
    except Exception:
        return 0


def refresh_member_subscriptions_if_due(member_id: int | None) -> bool:
    """회원이 앱을 쓰는 순간, 확인할 때가 된 애플 구독을 백그라운드에서 다시 본다(화면은 기다리지 않는다)."""
    if not member_id or not apple_iap_configured():
        return False
    now_mono = time.monotonic()
    with _MEMBER_CHECK_LOCK:
        last = _MEMBER_CHECKED.get(int(member_id))
        if last is not None and now_mono - last < MEMBER_RECHECK_SECONDS:
            return False
        _MEMBER_CHECKED[int(member_id)] = now_mono
    db_identity = _db_identity()

    def _run() -> None:
        if _db_identity() != db_identity:
            return
        try:
            for row in list_due_gplay_subscriptions(
                datetime.now(timezone.utc), member_id=int(member_id), limit=5, store=STORE
            ):
                refresh_subscription(row["purchase_token"])
        except Exception as exc:
            _log("apple_member_refresh_error", f"member_id={member_id} err={exc!r}")

    try:
        threading.Thread(target=_run, name="ln-apple-member", daemon=True).start()
    except Exception:
        return False
    return True


# ── 백그라운드 점검(끊긴 지급 마무리·구독 재확인·환불 회수) ─────────────────────
MAINTENANCE_INTERVAL_SECONDS = 3600
MAINTENANCE_FIRST_DELAY_SECONDS = 300
REFUND_POLL_SETTING = "apple_refund_last_poll_ms_{env}"
_HISTORY_DAYS = {"Production": 180, "Sandbox": 30}
_maint_state = {
    "running": False,
    "last": time.monotonic() - MAINTENANCE_INTERVAL_SECONDS + MAINTENANCE_FIRST_DELAY_SECONDS,
}
_maint_lock = threading.Lock()


def _retry_unfinished(now: datetime) -> int:
    """기록은 됐는데 지급이 끊긴 적립금(애플 확인은 이미 끝난 건)을 마저 지급한다."""
    done = 0
    for row in list_unfinished_gplay_purchases(now - UNFINISHED_RETRY_WINDOW, store=STORE):
        key = row["purchase_token"]
        if row["kind"] == "points":
            if charge_points(int(row["member_id"]), int(row["points"]), gplay_ref(key)):
                mark_gplay_finished(key)
                done += 1
        elif row["kind"] == "sub":
            if refresh_subscription(key):
                mark_gplay_finished(key)
                done += 1
    return done


def _handle_refund_notification(signed_payload: str) -> bool:
    payload = _jws_payload(signed_payload)
    data = payload.get("data") or {}
    if data.get("bundleId") not in (None, BUNDLE_ID):
        return False
    tx = _jws_payload(data.get("signedTransactionInfo", ""))
    if tx.get("bundleId") != BUNDLE_ID:
        return False
    product_id = str(tx.get("productId") or "")
    if product_id in products.POINTS_PRODUCTS:
        key = apple_key(str(tx.get("transactionId") or ""))
        row = get_gplay_purchase(key)
        if not row or row.get("store") != STORE or row.get("voided_at"):
            return False
        taken, shortfall, already = reclaim_voided_gplay_points(int(row["member_id"]), key, int(row["points"]))
        if already:
            return False
        _log(
            "apple_refund_points",
            f"member_id={row['member_id']} product_id={product_id} key={key} reclaimed={taken} shortfall={shortfall}",
        )
        return True
    if product_id in products.APPLE_SUBSCRIPTION_PRODUCTS:
        key = apple_key(str(tx.get("originalTransactionId") or ""))
        row = get_gplay_purchase(key)
        if not row or row.get("store") != STORE:
            return False
        refresh_subscription(key)  # 환불된 기간은 애플 상태에 반영돼 권한이 끊긴다
        _log("apple_refund_subscription", f"member_id={row['member_id']} key={key} tx={tx.get('transactionId')}")
        return True
    return False


def _poll_refunds(now: datetime, env: str) -> int:
    import app_settings

    app_settings.init_settings_table()
    setting = REFUND_POLL_SETTING.format(env=env.lower())
    now_ms = int(now.timestamp() * 1000)
    oldest_ms = now_ms - (_HISTORY_DAYS[env] * 86400 - 600) * 1000
    try:
        last_ms = int(app_settings.get_setting(setting, "0") or 0)
    except (TypeError, ValueError):
        last_ms = 0
    start_ms = max(oldest_ms, last_ms - 3600 * 1000)  # 1시간 겹쳐 읽는다(처리는 멱등)
    handled = 0
    pagination = ""
    for _page in range(20):
        path = "/inApps/v1/notifications/history"
        if pagination:
            path += f"?paginationToken={requests.utils.quote(pagination, safe='')}"
        status, data = _api(
            "POST", path, env, body={"startDate": start_ms, "endDate": now_ms, "notificationType": "REFUND"}
        )
        if status != 200 or not isinstance(data, dict):
            _log("apple_refund_poll_failed", f"env={env} status={status} msg={data}")
            return handled  # 기준 시각을 옮기지 않는다 — 다음 점검이 같은 구간을 다시 읽는다
        for item in data.get("notificationHistory") or []:
            try:
                if _handle_refund_notification(item.get("signedPayload", "")):
                    handled += 1
            except Exception as exc:
                _log("apple_maint_error", f"refund item {exc!r}")
        pagination = data.get("paginationToken") or ""
        if not data.get("hasMore") or not pagination:
            break
    else:
        # 쪽 수 한도에 걸려 아직 남았다 — 기준 시각을 옮기지 않는다(다음 점검이 이어서 다시 읽는다, 처리는 멱등).
        return handled
    try:
        app_settings.set_setting(setting, str(now_ms))
    except Exception:
        pass
    return handled


def run_maintenance_once(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    summary = {"finished": 0, "refreshed": 0, "refunds": 0}
    if not apple_iap_configured():
        return summary
    try:
        summary["finished"] = _retry_unfinished(now)
    except Exception as exc:
        _log("apple_maint_error", f"retry {exc!r}")
    try:
        for row in list_due_gplay_subscriptions(now, limit=50, store=STORE):
            if refresh_subscription(row["purchase_token"]):
                summary["refreshed"] += 1
    except Exception as exc:
        _log("apple_maint_error", f"refresh {exc!r}")
    for env in ("Production", "Sandbox"):
        try:
            summary["refunds"] += _poll_refunds(now, env)
        except Exception as exc:
            _log("apple_maint_error", f"refund {env} {exc!r}")
    return summary


def maybe_run_maintenance_in_background() -> bool:
    """한 시간에 한 번 백그라운드로 점검을 시작하고 바로 돌아온다. 키가 없으면 아무것도 안 한다."""
    if not apple_iap_configured():
        return False
    now_mono = time.monotonic()
    with _maint_lock:
        if _maint_state["running"] or now_mono - _maint_state["last"] < MAINTENANCE_INTERVAL_SECONDS:
            return False
        _maint_state["running"] = True
        _maint_state["last"] = now_mono
    db_identity = _db_identity()

    def _run() -> None:
        try:
            if _db_identity() == db_identity:
                run_maintenance_once()
        except Exception:
            pass
        finally:
            with _maint_lock:
                _maint_state["running"] = False

    try:
        threading.Thread(target=_run, name="ln-apple-maint", daemon=True).start()
    except Exception:
        with _maint_lock:
            _maint_state["running"] = False
        return False
    return True


# ── 진입점(user_page) ────────────────────────────────────────────────────────

PURCHASE_FAIL_NOTICE = (
    "결제 확인에 실패했습니다. 결제가 정상이라면 앱을 다시 열 때 자동으로 다시 확인됩니다. "
    "문의: bandouni@naver.com"
)
NOT_CONFIGURED_NOTICE = "결제 확인 시스템을 준비 중입니다. 결제 내역은 보관되며 앱을 다시 열면 자동으로 확인됩니다."


def _queue_finish(st, transaction_id: str) -> None:
    queue = list(st.session_state.get(FINISH_SESSION_KEY) or [])
    if transaction_id not in queue:
        queue.append(transaction_id)
    st.session_state[FINISH_SESSION_KEY] = queue[-5:]


def handle_apple_purchase_return(member_id: int | None) -> bool:
    """앱이 보낸 거래 ID(?iap_apple_tx=)를 확인·지급한다. 처리할 값이 있었으면 True(호출부가 st.rerun()).

    user_page.py 에서 로그인 회원이 확정된 뒤 부른다(구글 handle_google_play_purchase_return 과 같은 자리)."""
    import streamlit as st

    for key in (FINISH_PARAM, RESTORE_PARAM):
        try:
            if key in st.query_params:
                del st.query_params[key]
        except Exception:
            pass

    transaction_id = st.query_params.get(TX_PARAM)
    if isinstance(transaction_id, (list, tuple)):
        transaction_id = transaction_id[0] if transaction_id else ""
    if not transaction_id:
        return False
    try:
        del st.query_params[TX_PARAM]
    except Exception:
        pass
    transaction_id = str(transaction_id).strip()

    if not member_id:
        # 로그인 복구 전 — 끝내지 않으면 애플이 다음 실행 때 다시 보내 준다.
        st.session_state.wallet_toast_error = "로그인 확인 중입니다. 로그인 후 결제가 자동으로 다시 확인됩니다."
        return True
    if not apple_iap_configured():
        _log("apple_not_configured", f"member_id={member_id} tx={transaction_id[:32]}")
        st.session_state.wallet_toast_error = NOT_CONFIGURED_NOTICE
        return True

    try:
        code, msg = verify_and_credit(int(member_id), transaction_id)
    except Exception as exc:  # DB·네트워크 예외로 화면 전체가 죽지 않게
        code, msg = RETRY, f"예외: {exc!r}"[:300]

    if code == OK:
        st.session_state.wallet_toast = "결제가 완료되었습니다."
    else:
        _log("apple_verify_failed", f"member_id={member_id} tx={transaction_id[:32]} code={code} msg={msg}")
        if "다른 계정" in msg:
            st.session_state.wallet_toast_error = (
                "이 Apple ID의 결제는 다른 로또신령 계정에 연결되어 있습니다. 문의: bandouni@naver.com"
            )
        else:
            st.session_state.wallet_toast_error = PURCHASE_FAIL_NOTICE
    if code in (OK, FATAL) and valid_transaction_id(transaction_id):
        _queue_finish(st, transaction_id)
    return True


def render_finish_signals() -> None:
    """처리가 끝난 거래를 앱에 알려 StoreKit 거래를 끝내게 한다(finishTransaction).

    카카오·결제 요청 신호(wallet_ui._fire_iap_purchase_trigger)와 같은 이중화 — 최상위 문서에 스크립트를
    심어 브릿지가 있으면 postMessage, 없으면 주소 파라미터(iap_finish)로 알린다. 거래 ID 는 숫자만 통과한다."""
    import streamlit as st
    import streamlit.components.v1 as components

    queue = [tx for tx in (st.session_state.get(FINISH_SESSION_KEY) or []) if valid_transaction_id(tx)]
    if not queue:
        return
    st.session_state[FINISH_SESSION_KEY] = []
    ids_js = json.dumps(queue)
    components.html(
        f"""<script>
        (function () {{
            var ids = {ids_js};
            var top = window.top;
            try {{
                var s = top.document.createElement('script');
                s.textContent =
                    "try{{var ids=" + JSON.stringify(ids) + ";" +
                    "var rnwv = window.ReactNativeWebView;" +
                    "if(rnwv && typeof rnwv.postMessage === 'function'){{" +
                    "ids.forEach(function(id){{rnwv.postMessage(JSON.stringify({{type:'{FINISH_MESSAGE_TYPE}',transactionId:id}}));}});" +
                    "}}else{{" +
                    "var u = new URL(window.location.href);" +
                    "u.searchParams.set('{FINISH_PARAM}', ids.join(','));" +
                    "window.location.href = u.toString();" +
                    "}}" +
                    "}}catch(e){{}}";
                top.document.head.appendChild(s);
                s.parentNode.removeChild(s);
            }} catch (e) {{}}
        }})();
        </script>""",
        height=0,
    )


def fire_restore_trigger() -> None:
    """'구매 복원' — 앱이 이 Apple ID 의 유효한 구독을 찾아 다시 보내게 한다(App Store 지침 3.1.1)."""
    import streamlit.components.v1 as components

    components.html(
        f"""<script>
        (function () {{
            var top = window.top;
            try {{
                var s = top.document.createElement('script');
                s.textContent =
                    "try{{var rnwv = window.ReactNativeWebView;" +
                    "if(rnwv && typeof rnwv.postMessage === 'function'){{" +
                    "rnwv.postMessage(JSON.stringify({{type:'{RESTORE_MESSAGE_TYPE}'}}));" +
                    "}}else{{" +
                    "var u = new URL(window.location.href);" +
                    "u.searchParams.set('{RESTORE_PARAM}', '1');" +
                    "window.location.href = u.toString();" +
                    "}}" +
                    "}}catch(e){{}}";
                top.document.head.appendChild(s);
                s.parentNode.removeChild(s);
            }} catch (e) {{}}
        }})();
        </script>""",
        height=0,
    )
