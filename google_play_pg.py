"""Google Play Developer API 연동 — 인앱결제(일회성 상품·구독) 서버 검증 + 승인/소비.

[흐름] LottoShinryeong/components/streamlit-webview.tsx가 expo-iap로 구매를 시작하고,
구매 성공 시 purchaseToken을 ?iap_purchase_token=...&iap_product_id=... 형태로 웹뷰
주소에 실어 이 서버로 보낸다(카카오 네이티브 로그인의 native_kakao_token과 완전히
같은 "URL에 1회성으로 실어 보내기" 패턴 — toss_pg.py와 달리 서버가 결제 전에 미리
기록해둔 주문이 없다는 점만 다르다).

서버는 그 토큰을 클라이언트가 "구매했다"고 주장하는 걸 그대로 믿지 않고, Google Play
Developer API로 직접 재검증한 뒤에만 적립금 지급/구독 활성화를 한다. 구매 승인
(consume/acknowledge)도 이 서버가 전담한다 — 구글 공식 권장 방식("신뢰할 수 있는
백엔드가 있으면 서버에서 처리하라")이며, 클라이언트(streamlit-webview.tsx)는
finishTransaction을 아예 호출하지 않는다.

[승인 기한 — 중요] 구글 정책상 미승인 구매는 3일 뒤 자동 환불된다. 이 서버가
검증만 하고 승인(consume/acknowledge)을 안 하면, 3일 뒤 사용자는 환불되는데
포인트/구독은 이미 지급된 채로 남는 사고가 날 수 있다 — 그래서 지급 성공 직후
반드시 같은 요청 안에서 소비/승인까지 마친다(순서: 검증 → 지급 → 소비/승인).

[키 관리] Google Cloud 서비스 계정(lotto-play-billing@lotto-analyzer-7cafd.iam.gserviceaccount.com,
2026-09-25 발급)의 JSON 키 "전체 내용"을 GOOGLE_PLAY_SERVICE_ACCOUNT_JSON 환경변수 또는
Streamlit secrets에 문자열로 그대로 붙여넣는다(TOSS_SECRET_KEY와 동일하게 파일이 아니라
값으로 관리 — Streamlit Cloud엔 파일을 따로 올릴 방법이 없다). 이 서비스 계정은 Play
Console "사용자 및 권한"에 "재무 데이터, 주문, 취소 설문조사 응답 보기" + "주문 및 정기
결제 관리" 권한으로 이미 초대돼 있다(2026-09-25). requirements.txt에 google-auth 추가 필요.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import requests

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

# 2026-09-26: 상품 ID·구독 기간의 기준점은 products.py다(여기서 숫자를 새로 쓰지 말 것).
# 이름을 그대로 다시 내보내므로 기존 import(POINTS_PRODUCTS 등)는 그대로 동작한다.
from products import ANDROID_PACKAGE_NAME, POINTS_PRODUCTS, SUBSCRIPTION_BASE_PLAN_DAYS, SUBSCRIPTION_PRODUCT

PACKAGE_NAME = ANDROID_PACKAGE_NAME  # 기준점 products.py
ANDROID_PUBLISHER_SCOPE = "https://www.googleapis.com/auth/androidpublisher"
API_BASE = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications"

# 2026-09-25: Play Console에 실제 등록한 상품 ID와 정확히 일치해야 한다(정의는 products.py).
# 일회성 소모성 상품 → 지급 포인트 (product ID 자체가 지급 포인트를 의미하는
# 이름이라 별도 환산 없이 그대로 값으로 씀 — points_1000=1,000P/10,000원 등).
#
# 기본요금제 → 연장 일수도 products.py에서 온다. 반드시 "구글이 검증 응답으로
# 돌려준 basePlanId"에서 구해야 한다(아래 _verify_and_credit_subscription 참고) —
# 클라이언트가 URL에 실어 보낸 basePlanId는 참고용일 뿐 신뢰하지 않는다. 안 그러면
# 저가 요금제(월간)를 결제해놓고 고가 요금제(분기)라고 우겨서 3배 구독기간을 받아가는
# 걸 서버가 막을 수 없다.


def _service_account_info() -> dict | None:
    """TOSS_CLIENT_KEY/TOSS_SECRET_KEY와 동일한 패턴(env → st.secrets 순)으로
    서비스 계정 JSON "전체 내용"을 읽어 파싱한다."""
    raw = os.environ.get("GOOGLE_PLAY_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        try:
            import streamlit as st

            raw = str(st.secrets.get("GOOGLE_PLAY_SERVICE_ACCOUNT_JSON", "") or "").strip()
        except Exception:
            raw = ""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def google_play_configured() -> bool:
    return _service_account_info() is not None


_cached_credentials = None  # google.oauth2.service_account.Credentials — 지연 생성, 프로세스 생존 동안 재사용


def _access_token() -> str | None:
    """Bearer 액세스 토큰을 반환한다. google-auth 라이브러리가 만료 여부를
    스스로 판단해 필요할 때만 갱신하므로(credentials.valid), 매 호출마다 새로
    토큰을 발급받지 않는다."""
    global _cached_credentials
    info = _service_account_info()
    if not info:
        return None
    try:
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account
    except ImportError:
        return None

    if _cached_credentials is None:
        try:
            _cached_credentials = service_account.Credentials.from_service_account_info(
                info, scopes=[ANDROID_PUBLISHER_SCOPE]
            )
        except (ValueError, KeyError):
            return None

    if not _cached_credentials.valid:
        try:
            _cached_credentials.refresh(Request())
        except Exception:
            return None
    return _cached_credentials.token


def _api_get(path: str) -> tuple[bool, dict | str]:
    token = _access_token()
    if not token:
        return False, "Google Play 서비스 계정이 설정되지 않았습니다."
    try:
        resp = requests.get(
            f"{API_BASE}/{PACKAGE_NAME}/{path}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
    except requests.RequestException as e:
        return False, f"Google Play 서버 통신 실패: {e}"
    if resp.status_code == 200:
        try:
            return True, resp.json()
        except Exception as e:
            return False, f"Google Play 응답 파싱 실패: {e}"
    try:
        body = resp.json()
        msg = body.get("error", {}).get("message", resp.text)
    except Exception:
        msg = resp.text
    return False, f"조회 실패({resp.status_code}): {msg}"


def _api_post(path: str) -> tuple[bool, str]:
    token = _access_token()
    if not token:
        return False, "Google Play 서비스 계정이 설정되지 않았습니다."
    try:
        resp = requests.post(
            f"{API_BASE}/{PACKAGE_NAME}/{path}",
            headers={"Authorization": f"Bearer {token}"},
            json={},
            timeout=15,
        )
    except requests.RequestException as e:
        return False, f"Google Play 서버 통신 실패: {e}"
    if resp.status_code == 200:
        return True, "ok"
    try:
        body = resp.json()
        msg = body.get("error", {}).get("message", resp.text)
    except Exception:
        msg = resp.text
    return False, f"실패({resp.status_code}): {msg}"


def _log_gplay_issue(event: str, detail: str) -> None:
    try:
        import security_log

        security_log.log_event(event, detail)
    except Exception:
        pass


def _short(token: str | None) -> str:
    """로그에는 결제 토큰 전체를 남기지 않는다(토큰은 구매 조회 키다) — 앞 12자 + 길이만."""
    token = str(token or "")
    return f"{token[:12]}…({len(token)})" if token else "-"


# ── 구독 권한 판정 규칙(2026-10-09 점검 B1) ──────────────────────────────────
# 근거: Android 개발자 문서 "Subscription lifecycle"(subscriptionsv2.get 이 기준).
#   ACTIVE·IN_GRACE_PERIOD → 권한 유지(유예 기간에는 구글이 expiryTime 을 늘려 준다)
#   CANCELED → expiryTime 까지 유지(해지해도 남은 기간은 쓴다)
#   ON_HOLD·PAUSED → 권한 차단(같은 토큰으로 복구될 수 있어 주기적으로 다시 본다)
#   EXPIRED(만료·환불 회수) → 차단
# 자동갱신 중(ACTIVE + autoRenewEnabled)이면 만료 시각에 갱신 결과가 늦게 반영될 수 있어
# (구글은 갱신 실패 시 최소 1일을 조용히 기다린다) RENEWAL_BUFFER 만큼 여유를 둔다.
RENEWAL_BUFFER = timedelta(days=1)
RECHECK_MAX = timedelta(hours=24)        # 유효한 구독도 하루 한 번은 다시 본다(환불·회수 대비)
RECHECK_OVERDUE = timedelta(hours=3)     # 만료 시각이 지났는데 아직 ACTIVE 일 때
RECHECK_SUSPENDED = timedelta(hours=6)   # 보류·일시중지 — 복구되면 다시 권한을 준다
UNFINISHED_RETRY_WINDOW = timedelta(days=3)  # 구글 자동 환불 기한
GRANTABLE_STATES = (
    "SUBSCRIPTION_STATE_ACTIVE",
    "SUBSCRIPTION_STATE_IN_GRACE_PERIOD",
    "SUBSCRIPTION_STATE_CANCELED",
)
ACKNOWLEDGED_VALUES = ("ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED", 1)


def _parse_google_time(value) -> datetime | None:
    """RFC3339('2026-10-09T03:04:05.123456789Z') → 시간대 있는 datetime. 못 읽으면 None."""
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    if "." in text:
        head, rest = text.split(".", 1)
        digits = ""
        while rest and rest[0].isdigit():
            digits += rest[0]
            rest = rest[1:]
        text = f"{head}.{(digits + '000000')[:6]}{rest}"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _subscription_line_item(data: dict) -> dict:
    items = data.get("lineItems") or []
    for item in items:
        if item.get("productId") == SUBSCRIPTION_PRODUCT:
            return item
    return items[0] if items else {}


def subscription_entitlement(data: dict, now: datetime | None = None) -> dict:
    """subscriptionsv2 응답 → 우리 권한 결정.

    반환 키: state, base_plan_id, google_expiry, access_until(None=차단), next_check(None=그만 봄),
    keep_access(해석 불가 — 권한은 그대로 두고 나중에 다시 본다), linked_token, acknowledged."""
    now = now or datetime.now(timezone.utc)
    state = str(data.get("subscriptionState") or "")
    item = _subscription_line_item(data)
    expiry = _parse_google_time(item.get("expiryTime"))
    auto_renew = bool((item.get("autoRenewingPlan") or {}).get("autoRenewEnabled"))
    result = {
        "state": state,
        "base_plan_id": (item.get("offerDetails") or {}).get("basePlanId"),
        "google_expiry": expiry,
        "access_until": None,
        "next_check": None,
        "keep_access": False,
        "linked_token": data.get("linkedPurchaseToken") or None,
        "acknowledged": data.get("acknowledgementState") in ACKNOWLEDGED_VALUES,
    }
    if state in ("SUBSCRIPTION_STATE_ACTIVE", "SUBSCRIPTION_STATE_IN_GRACE_PERIOD"):
        if not expiry:
            # 문서상 항상 있어야 하는 값 — 없으면 권한은 그대로 두고 곧 다시 본다.
            result["keep_access"] = True
            result["next_check"] = now + RECHECK_OVERDUE
            return result
        auto_buffer = state == "SUBSCRIPTION_STATE_ACTIVE" and auto_renew
        result["access_until"] = expiry + RENEWAL_BUFFER if auto_buffer else expiry
        next_check = expiry if expiry > now else now + RECHECK_OVERDUE
        result["next_check"] = min(next_check, now + RECHECK_MAX)
    elif state == "SUBSCRIPTION_STATE_CANCELED":
        if expiry and expiry > now:
            result["access_until"] = expiry
            result["next_check"] = min(expiry, now + RECHECK_MAX)
    elif state in ("SUBSCRIPTION_STATE_ON_HOLD", "SUBSCRIPTION_STATE_PAUSED"):
        result["next_check"] = now + RECHECK_SUSPENDED
    elif state in ("SUBSCRIPTION_STATE_EXPIRED", "SUBSCRIPTION_STATE_PENDING_PURCHASE_CANCELED"):
        pass
    else:
        # PENDING·UNSPECIFIED·알 수 없는 값 — 권한은 그대로 두고 나중에 다시 확인한다.
        result["keep_access"] = True
        result["next_check"] = now + RECHECK_SUSPENDED
    return result


# ── 소모성(적립금) 상품 ─────────────────────────────────────────────────────

def _finish_points_purchase(product_id: str, token: str, data: dict | None, member_id) -> bool:
    """소비(consume) — 지급이 끝난 뒤에만. 성공(또는 이미 소비됨)이면 완료 표시."""
    if data is not None and data.get("consumptionState") == 1:
        mark_gplay_finished(token)
        return True
    ok, msg = _api_post(f"purchases/products/{product_id}/tokens/{token}:consume")
    if ok:
        mark_gplay_finished(token)
        return True
    # 실패해도 사용자는 이미 지급받았다 — 완료 표시를 안 남겨 백그라운드가 3일 안에 다시 시도한다
    # (소비가 안 되면 구글이 3일 뒤 자동 환불하고, 그 환불은 아래 환불 처리로 회수된다).
    _log_gplay_issue(
        "gplay_consume_failed",
        f"member_id={member_id} product_id={product_id} token={_short(token)} msg={msg}",
    )
    return False


def _verify_and_credit_one_time(member_id: int, product_id: str, token: str) -> tuple[bool, str]:
    points = POINTS_PRODUCTS.get(product_id)
    if points is None:
        return False, f"알 수 없는 상품 ID: {product_id}"

    existing = get_gplay_purchase(token)
    if existing:
        if int(existing["member_id"]) != int(member_id):
            return False, "다른 계정에서 이미 처리된 결제입니다"
        if existing.get("voided_at"):
            return False, "환불·취소된 결제입니다"

    ok, data = _api_get(f"purchases/products/{product_id}/tokens/{token}")
    if not ok:
        return False, str(data)
    purchase_state = data.get("purchaseState")
    if purchase_state == 2:
        return False, "결제 승인 대기 중입니다(결제가 완료되면 자동으로 지급됩니다)"
    if purchase_state != 0:
        # 0=Purchased, 1=Canceled, 2=Pending
        return False, f"구매 상태가 유효하지 않음(purchaseState={purchase_state})"

    # 지급 전에 먼저 기록 — 아래 어디서 끊겨도 백그라운드 재시도가 이어서 처리한다.
    # purchaseType 0 = 라이선스 테스터의 테스트 결제(실제 청구 없음) — 출시 전 적립금 초기화가 구분한다.
    record_gplay_points_purchase(member_id, token, product_id, points, is_test=data.get("purchaseType") == 0)
    if not charge_points(member_id, points, gplay_ref(token)):
        return False, "포인트 지급 실패(지갑 없음 등)"
    # 소모성 상품은 지급이 확실히 끝난 뒤에만 소비 처리한다(순서를 바꾸면 되살릴 방법이 없다).
    _finish_points_purchase(product_id, token, data, member_id)
    return True, "ok"


# ── 정기결제(구독) ─────────────────────────────────────────────────────────

def _acknowledge_subscription(token: str, member_id) -> bool:
    ok, msg = _api_post(f"purchases/subscriptions/{SUBSCRIPTION_PRODUCT}/tokens/{token}:acknowledge")
    if ok:
        mark_gplay_finished(token)
        return True
    _log_gplay_issue("gplay_acknowledge_failed", f"member_id={member_id} token={_short(token)} msg={msg}")
    return False


def _apply_entitlement(token: str, ent: dict) -> None:
    update_gplay_subscription(
        token,
        state=ent["state"],
        google_expiry=ent["google_expiry"],
        access_until=ent["access_until"],
        next_check=ent["next_check"],
        keep_access=ent["keep_access"],
    )


def _verify_and_credit_subscription(member_id: int, token: str) -> tuple[bool, str]:
    existing = get_gplay_purchase(token)
    if existing and int(existing["member_id"]) != int(member_id):
        return False, "다른 계정에서 이미 처리된 구독입니다"

    ok, data = _api_get(f"purchases/subscriptionsv2/tokens/{token}")
    if not ok:
        return False, str(data)

    ent = subscription_entitlement(data)
    if existing:
        # 같은 토큰 재도착(재전송·새로고침) — 지급은 이미 끝났고 상태만 최신으로 맞춘다.
        # 요금제 변경으로 대체된 옛 토큰은 되살리지 않는다.
        if existing.get("state") == "REPLACED":
            return True, "ok"
        _apply_entitlement(token, ent)
        if not ent["acknowledged"]:
            _acknowledge_subscription(token, member_id)
        elif not int(existing.get("finished") or 0):
            mark_gplay_finished(token)
        return True, "ok"

    if ent["state"] == "SUBSCRIPTION_STATE_PENDING":
        return False, "결제 승인 대기 중입니다(결제가 완료되면 자동으로 적용됩니다)"
    if ent["state"] not in GRANTABLE_STATES or (ent["access_until"] is None and not ent["keep_access"]):
        return False, f"구독 상태가 유효하지 않음(subscriptionState={ent['state']})"
    if not data.get("lineItems"):
        return False, "구독 상세 정보가 비어 있음"
    base_plan_id = ent["base_plan_id"]
    # 기간 판정은 구글이 돌려준 basePlanId·expiryTime 만 믿는다(클라이언트 값은 쓰지 않는다).
    if base_plan_id not in SUBSCRIPTION_BASE_PLAN_DAYS:
        return False, f"알 수 없는 기본요금제: {base_plan_id}"
    google_expiry = ent["google_expiry"]
    access_until = ent["access_until"]
    if google_expiry is None or access_until is None:
        # 만료 시각이 없는 응답(문서상 없어야 함) — 요금제 기간으로 대신 계산하고 곧 다시 확인한다.
        google_expiry = datetime.now(timezone.utc) + timedelta(days=SUBSCRIPTION_BASE_PLAN_DAYS[base_plan_id])
        access_until = google_expiry

    activated = activate_gplay_subscription(
        member_id,
        token,
        base_plan_id,
        state=ent["state"],
        google_expiry=google_expiry,
        access_until=access_until,
        next_check=ent["next_check"],
        linked_token=ent["linked_token"],
        is_test="testPurchase" in data,  # 라이선스 테스터의 테스트 결제(실제 청구 없음)
    )
    if not activated:
        return False, "구독 활성화 실패"

    if not ent["acknowledged"]:
        _acknowledge_subscription(token, member_id)
    else:
        mark_gplay_finished(token)
    return True, "ok"


def refresh_subscription(token: str) -> bool:
    """저장된 구글 구독 하나를 구글에 다시 물어 권한을 맞춘다(갱신·해지·보류·환불 반영)."""
    row = get_gplay_purchase(token)
    if not row or row.get("kind") != "sub" or row.get("state") == "REPLACED":
        return False
    if (row.get("store") or "google") != "google":
        return False  # 2026-10-09: 같은 표의 애플 행(apple_iap)은 구글에 묻지 않는다
    ok, data = _api_get(f"purchases/subscriptionsv2/tokens/{token}")
    if not ok:
        # 조회 실패 — 권한은 그대로 두고 1시간 뒤 다시 본다(이미 확인을 끝낸 행은 다시 켜지 않는다).
        update_gplay_subscription(
            token,
            state=str(row.get("state") or ""),
            google_expiry=None,
            access_until=None,
            next_check=(datetime.now(timezone.utc) + timedelta(hours=1)) if row.get("next_check_at") else None,
            keep_access=True,
        )
        _log_gplay_issue("gplay_refresh_failed", f"member_id={row['member_id']} token={_short(token)} msg={data}")
        return False
    ent = subscription_entitlement(data)
    _apply_entitlement(token, ent)
    if not int(row.get("finished") or 0):
        if ent["acknowledged"]:
            mark_gplay_finished(token)
        elif ent["state"] in GRANTABLE_STATES:
            _acknowledge_subscription(token, row["member_id"])
    return True


# 화면 쪽 확인 — 회원이 앱을 쓰는 순간 만료가 지난 구독을 바로 다시 본다(백그라운드가 돌기 전이라도).
MEMBER_RECHECK_SECONDS = 600
_MEMBER_CHECKED: dict[int, float] = {}
_MEMBER_CHECK_LOCK = threading.Lock()


def _refresh_member_now(member_id: int) -> int:
    done = 0
    try:
        for row in list_due_gplay_subscriptions(datetime.now(timezone.utc), member_id=int(member_id), limit=5):
            if refresh_subscription(row["purchase_token"]):
                done += 1
    except Exception as exc:
        _log_gplay_issue("gplay_member_refresh_error", f"member_id={member_id} err={exc!r}"[:300])
    return done


def refresh_member_subscriptions_if_due(member_id: int | None) -> bool:
    """회원이 앱을 쓰는 순간 확인할 때가 된 구독을 백그라운드에서 다시 본다(화면은 기다리지 않는다 —
    구글 응답이 느려도 렌더가 막히지 않게). 자동갱신 중이면 만료 뒤 1일 여유가 있어 한 박자 늦어도
    권한이 끊기지 않는다. 시작했으면 True."""
    if not member_id or not google_play_configured():
        return False
    now_mono = time.monotonic()
    with _MEMBER_CHECK_LOCK:
        last = _MEMBER_CHECKED.get(int(member_id))
        if last is not None and now_mono - last < MEMBER_RECHECK_SECONDS:
            return False
        _MEMBER_CHECKED[int(member_id)] = now_mono
    db_identity = _db_identity()

    def _run() -> None:
        if _db_identity() == db_identity:
            _refresh_member_now(int(member_id))

    try:
        threading.Thread(target=_run, name="ln-gplay-member", daemon=True).start()
    except Exception:
        return False
    return True


# ── 백그라운드 점검(승인 재시도·구독 재확인·환불 회수) ─────────────────────────
MAINTENANCE_INTERVAL_SECONDS = 3600
# 프로세스가 뜨고 첫 점검까지 기다리는 시간 — 화면 첫 로딩과 겹치지 않게, 그리고 짧게 끝나는
# 테스트 프로세스가 백그라운드 점검을 띄우지 않게 한다(Cloud 는 잠들었다 깨면 새 프로세스).
MAINTENANCE_FIRST_DELAY_SECONDS = 300
VOIDED_POLL_SETTING = "gplay_voided_last_poll_ms"
_maint_state = {
    "running": False,
    "last": time.monotonic() - MAINTENANCE_INTERVAL_SECONDS + MAINTENANCE_FIRST_DELAY_SECONDS,
}
_maint_lock = threading.Lock()


def _retry_unfinished(now: datetime) -> int:
    done = 0
    for row in list_unfinished_gplay_purchases(now - UNFINISHED_RETRY_WINDOW):
        token = row["purchase_token"]
        if row["kind"] == "points":
            product_id = row["product_id"]
            ok, data = _api_get(f"purchases/products/{product_id}/tokens/{token}")
            if not ok or data.get("purchaseState") != 0:
                continue
            # 지급이 중간에 끊긴 건이면 여기서 마저 지급한다(ref 멱등 — 이미 지급됐으면 그대로).
            if not charge_points(int(row["member_id"]), int(row["points"]), gplay_ref(token)):
                continue
            if _finish_points_purchase(product_id, token, data, row["member_id"]):
                done += 1
        elif row["kind"] == "sub":
            if refresh_subscription(token):
                done += 1
    return done


def _poll_voided_purchases(now: datetime) -> int:
    """구글에서 환불·취소된 결제를 찾아 회수한다(적립금은 잔액 한도에서 회수, 구독은 재확인)."""
    import app_settings

    app_settings.init_settings_table()
    now_ms = int(now.timestamp() * 1000)
    oldest_ms = now_ms - (30 * 86400 - 600) * 1000  # API 한도: 30일 이내
    try:
        last_ms = int(app_settings.get_setting(VOIDED_POLL_SETTING, "0") or 0)
    except (TypeError, ValueError):
        last_ms = 0
    start_ms = max(oldest_ms, last_ms - 3600 * 1000)  # 1시간 겹쳐 읽어 경계 누락을 막는다(처리는 멱등)
    handled = 0
    page_token = ""
    for _page in range(10):
        path = f"purchases/voidedpurchases?type=1&startTime={start_ms}&endTime={now_ms}&maxResults=1000"
        if page_token:
            path += f"&token={page_token}"
        ok, data = _api_get(path)
        if not ok:
            _log_gplay_issue("gplay_voided_poll_failed", str(data)[:300])
            return handled  # 기준 시각을 옮기지 않는다 — 다음 점검이 같은 구간을 다시 읽는다
        for item in data.get("voidedPurchases") or []:
            token = item.get("purchaseToken")
            row = get_gplay_purchase(token) if token else None
            if not row:
                continue
            if row["kind"] == "points":
                if row.get("voided_at"):
                    continue
                taken, shortfall, already = reclaim_voided_gplay_points(
                    int(row["member_id"]), token, int(row["points"])
                )
                if not already:
                    handled += 1
                    _log_gplay_issue(
                        "gplay_voided_points",
                        f"member_id={row['member_id']} product_id={row['product_id']} token={_short(token)} "
                        f"reclaimed={taken} shortfall={shortfall} order={item.get('orderId')}",
                    )
            else:
                if row.get("voided_at"):
                    continue  # 겹쳐 읽은 구간에서 이미 처리한 건
                refresh_subscription(token)
                mark_gplay_voided(token)
                handled += 1
                _log_gplay_issue(
                    "gplay_voided_subscription",
                    f"member_id={row['member_id']} token={_short(token)} order={item.get('orderId')}",
                )
        page_token = (data.get("tokenPagination") or {}).get("nextPageToken") or ""
        if not page_token:
            break
    try:
        app_settings.set_setting(VOIDED_POLL_SETTING, str(now_ms))
    except Exception:
        pass
    return handled


def run_maintenance_once(now: datetime | None = None) -> dict:
    """한 번 점검 — 각 단계는 서로 독립(한 단계가 실패해도 나머지는 돈다)."""
    now = now or datetime.now(timezone.utc)
    summary = {"finished": 0, "refreshed": 0, "voided": 0}
    if not google_play_configured():
        return summary
    try:
        summary["finished"] = _retry_unfinished(now)
    except Exception as exc:
        _log_gplay_issue("gplay_maint_error", f"retry {exc!r}"[:300])
    try:
        for row in list_due_gplay_subscriptions(now, limit=50):
            if refresh_subscription(row["purchase_token"]):
                summary["refreshed"] += 1
    except Exception as exc:
        _log_gplay_issue("gplay_maint_error", f"refresh {exc!r}"[:300])
    try:
        summary["voided"] = _poll_voided_purchases(now)
    except Exception as exc:
        _log_gplay_issue("gplay_maint_error", f"voided {exc!r}"[:300])
    return summary


def _db_identity() -> int:
    try:
        import db_turso

        return id(db_turso.connect)
    except Exception:
        return 0


def maybe_run_maintenance_in_background() -> bool:
    """한 시간에 한 번 백그라운드로 점검을 시작하고 바로 돌아온다(화면은 기다리지 않는다).
    서비스 계정이 없으면(지금 운영 상태) 아무것도 하지 않는다."""
    if not google_play_configured():
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
            # 시작 시점과 다른 DB 연결로 바뀌었으면(테스트 격리 해제 등) 아무것도 하지 않는다.
            if _db_identity() == db_identity:
                run_maintenance_once()
        except Exception:
            pass
        finally:
            with _maint_lock:
                _maint_state["running"] = False

    try:
        threading.Thread(target=_run, name="ln-gplay-maint", daemon=True).start()
    except Exception:
        with _maint_lock:
            _maint_state["running"] = False
        return False
    return True


# ── 진입점 ────────────────────────────────────────────────────────────────

# 결제 확인 실패 안내 — 사용자에게는 기술 메시지 대신 이 문구를 보인다(원인은 보안 로그에 남는다).
PURCHASE_FAIL_NOTICE = (
    "결제 확인에 실패했습니다. 결제가 정상이라면 자동으로 다시 확인되며, "
    "처리되지 않은 결제는 Google Play가 3일 안에 자동 환불합니다. 문의: bandouni@naver.com"
)
PURCHASE_PENDING_NOTICE = "결제 승인 대기 중입니다. 결제가 완료되면 자동으로 지급됩니다."


def handle_google_play_purchase_return(member_id: int | None) -> bool:
    """user_page.py에서 restore_member_from_guest() 이후(=member_id 확정 이후)에
    호출한다 — toss_pg.handle_toss_payment_return()과 달리 이 구매는 사전에
    서버가 기록해둔 주문이 없어서(전부 클라이언트/Google 쪽에서 먼저 끝남),
    처리 시점의 "현재 로그인된 회원"이 반드시 필요하기 때문이다(그래서 호출
    위치가 toss와 다르다 — user_page.py 쪽 배선 참고).

    2026-10-09(점검 H4): 결제 요청 신호(iap_buy/iap_plan)가 주소에 남아 있으면 지운다 —
    남아 있으면 앱이 그 주소를 다시 열 때 결제창이 또 뜰 수 있다.

    처리할 구매 정보가 있었으면 True(호출부가 st.rerun())."""
    import streamlit as st

    for key in ("iap_buy", "iap_plan"):
        try:
            if key in st.query_params:
                del st.query_params[key]
        except Exception:
            pass

    token = st.query_params.get("iap_purchase_token")
    if not token:
        return False
    product_id = st.query_params.get("iap_product_id", "")
    for key in ("iap_purchase_token", "iap_product_id"):
        if key in st.query_params:
            del st.query_params[key]

    if not member_id:
        # 로그인 세션이 아직 복구되기 전 — 여기서 버리면 구매가 유실된다.
        # 소비/승인을 안 했으므로 클라이언트의 재전송 안전장치가 로그인 확인
        # 후 다시 시도한다(3일 안에만 재접속하면 안전).
        st.session_state.wallet_toast_error = "로그인 확인 중입니다. 로그인 후 결제가 자동으로 다시 확인됩니다."
        return True

    if not google_play_configured():
        _log_gplay_issue(
            "gplay_not_configured",
            f"member_id={member_id} product_id={product_id} token={_short(token)}",
        )
        st.session_state.wallet_toast_error = "결제 확인 시스템이 아직 준비되지 않았습니다. 관리자에게 문의해 주세요."
        return True

    try:
        if product_id in POINTS_PRODUCTS:
            ok, msg = _verify_and_credit_one_time(member_id, product_id, token)
        elif product_id == SUBSCRIPTION_PRODUCT:
            ok, msg = _verify_and_credit_subscription(member_id, token)
        else:
            ok, msg = False, f"알 수 없는 상품 ID: {product_id}"
    except Exception as exc:  # DB·네트워크 예외로 화면 전체가 죽지 않게
        ok, msg = False, f"예외: {exc!r}"[:300]

    if ok:
        st.session_state.wallet_toast = "결제가 완료되었습니다."
    else:
        _log_gplay_issue(
            "gplay_verify_failed",
            f"member_id={member_id} product_id={product_id} token={_short(token)} msg={msg}",
        )
        st.session_state.wallet_toast_error = (
            PURCHASE_PENDING_NOTICE if "승인 대기" in msg else PURCHASE_FAIL_NOTICE
        )
    return True
