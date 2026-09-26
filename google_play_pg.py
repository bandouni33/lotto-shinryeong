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

import requests

from wallet_db import activate_paid_advanced_sub_once, charge_points

# 2026-09-26: 상품 ID·구독 기간의 기준점은 products.py다(여기서 숫자를 새로 쓰지 말 것).
# 이름을 그대로 다시 내보내므로 기존 import(POINTS_PRODUCTS 등)는 그대로 동작한다.
from products import POINTS_PRODUCTS, SUBSCRIPTION_BASE_PLAN_DAYS, SUBSCRIPTION_PRODUCT

PACKAGE_NAME = "com.bandouni.lottoshinryeong"
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


def _verify_and_credit_one_time(member_id: int, product_id: str, token: str) -> tuple[bool, str]:
    points = POINTS_PRODUCTS.get(product_id)
    if points is None:
        return False, f"알 수 없는 상품 ID: {product_id}"

    ok, data = _api_get(f"purchases/products/{product_id}/tokens/{token}")
    if not ok:
        return False, str(data)
    purchase_state = data.get("purchaseState")
    if purchase_state != 0:
        # 0=Purchased, 1=Canceled, 2=Pending — 결제가 아직 안 끝났거나 취소된 건.
        return False, f"구매 상태가 유효하지 않음(purchaseState={purchase_state})"

    ref_id = f"pg:gplay:{token}"
    credited = charge_points(member_id, points, ref_id)
    if not credited:
        # 지갑이 없는 등 지급 자체가 실패 — 여기서 소비 처리하지 않고 그대로 둔다.
        # 클라이언트(streamlit-webview.tsx)의 "미승인 구매 재전송" 안전장치가
        # 다음 접속 때 다시 보내므로 재시도 여지가 남는다.
        return False, "포인트 지급 실패(지갑 없음 등)"

    # 소모성 상품은 지급이 확실히 끝난 뒤에만 소비 처리한다 — 순서를 바꾸면
    # (소비를 먼저 하면) 지급 실패 시 이미 소비된 구매를 되살릴 방법이 없다.
    if data.get("consumptionState") != 1:
        consumed_ok, consumed_msg = _api_post(
            f"purchases/products/{product_id}/tokens/{token}:consume"
        )
        if not consumed_ok:
            # 지급은 이미 끝났으니 사용자 입장에선 성공 — 소비 실패는 로그만
            # 남기고 넘어간다(재시도 루프에 걸리게 하면 오히려 중복 시도만 늘어남).
            _log_gplay_issue(
                "gplay_consume_failed",
                f"member_id={member_id} product_id={product_id} token={token} msg={consumed_msg}",
            )
    return True, "ok"


def _verify_and_credit_subscription(member_id: int, token: str) -> tuple[bool, str]:
    ok, data = _api_get(f"purchases/subscriptionsv2/tokens/{token}")
    if not ok:
        return False, str(data)

    state = data.get("subscriptionState")
    if state not in ("SUBSCRIPTION_STATE_ACTIVE", "SUBSCRIPTION_STATE_IN_GRACE_PERIOD"):
        return False, f"구독 상태가 유효하지 않음(subscriptionState={state})"

    line_items = data.get("lineItems") or []
    if not line_items:
        return False, "구독 상세 정보가 비어 있음"
    base_plan_id = (line_items[0].get("offerDetails") or {}).get("basePlanId")
    days = SUBSCRIPTION_BASE_PLAN_DAYS.get(base_plan_id)
    if days is None:
        return False, f"알 수 없는 기본요금제: {base_plan_id}"

    ref_id = f"pg:gplay:{token}"
    activated = activate_paid_advanced_sub_once(member_id, days, ref_id)
    if not activated:
        return False, "구독 활성화 실패"

    if data.get("acknowledgementState") != 1:
        acked_ok, acked_msg = _api_post(
            f"purchases/subscriptions/{SUBSCRIPTION_PRODUCT}/tokens/{token}:acknowledge"
        )
        if not acked_ok:
            _log_gplay_issue(
                "gplay_acknowledge_failed",
                f"member_id={member_id} token={token} msg={acked_msg}",
            )
    return True, "ok"


def handle_google_play_purchase_return(member_id: int | None) -> bool:
    """user_page.py에서 restore_member_from_guest() 이후(=member_id 확정 이후)에
    호출한다 — toss_pg.handle_toss_payment_return()과 달리 이 구매는 사전에
    서버가 기록해둔 주문이 없어서(전부 클라이언트/Google 쪽에서 먼저 끝남),
    처리 시점의 "현재 로그인된 회원"이 반드시 필요하기 때문이다(그래서 호출
    위치가 toss와 다르다 — user_page.py 쪽 배선 참고).

    처리할 구매 정보가 있었으면 True(호출부가 st.rerun())."""
    import streamlit as st

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
        try:
            st.toast("로그인 확인 중입니다. 잠시 후 자동으로 다시 시도합니다.", icon="⚠️")
        except Exception:
            pass
        return True

    if not google_play_configured():
        _log_gplay_issue(
            "gplay_not_configured",
            f"member_id={member_id} product_id={product_id} token={token}",
        )
        try:
            st.toast("결제 확인 시스템이 아직 준비되지 않았습니다. 관리자에게 문의해 주세요.", icon="🚨")
        except Exception:
            pass
        return True

    if product_id in POINTS_PRODUCTS:
        ok, msg = _verify_and_credit_one_time(member_id, product_id, token)
    elif product_id == SUBSCRIPTION_PRODUCT:
        ok, msg = _verify_and_credit_subscription(member_id, token)
    else:
        ok, msg = False, f"알 수 없는 상품 ID: {product_id}"

    if ok:
        st.session_state.wallet_toast = "결제가 완료되었습니다."
    else:
        _log_gplay_issue(
            "gplay_verify_failed",
            f"member_id={member_id} product_id={product_id} token={token} msg={msg}",
        )
        try:
            st.toast(f"결제 확인에 실패했습니다: {msg}", icon="⚠️")
        except Exception:
            pass
    return True
