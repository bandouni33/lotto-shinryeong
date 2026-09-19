"""토스페이먼츠 결제창(Payment Window) SDK v1 연동 — 필수 플로우
(결제창 호출 → successUrl 콜백 → /v1/payments/confirm 승인 → 적립금 지급)만
다룬다. 비동기 웹훅(PAYMENT_STATUS_CHANGED 등)은 별도 서버리스 함수로 분리
예정(2026-09-19 사용자 결정 "서버리스 함수") — 여기엔 없다.

[중요 — 배포 전 실기기 확인 필수] 아래 JS(TossPayments(clientKey).requestPayment(...))
호출부는 토스 공식 문서·블로그 여러 곳을 대조해 작성했지만, 문서 사이트가
자동 수집을 막고 있어(docs.tosspayments.com 직접 접근 차단) 실제 대시보드가
보여주는 "내 연동 코드" 샘플과 토큰 단위까지 일치하는지 코드만으로는 100%
확증하지 못했다. TOSS_CLIENT_KEY/TOSS_SECRET_KEY를 실제 테스트 키로 채운 뒤
"Mock 결제" 대신 뜨는 이 버튼을 한 번 실제로 눌러 결제창이 정상적으로 뜨는지
반드시 확인할 것 — 만약 안 뜨면(예: 함수/파라미터명이 실제 SDK와 다름) 토스
개발자센터의 "내 연동 코드" 샘플 코드를 그대로 복붙해 이 파일의 JS 문자열만
교체하면 된다(서버 쪽 confirm 로직·DB 대조 로직은 SDK 버전과 무관하게 그대로
쓸 수 있다).

테스트 키 발급: https://developers.tosspayments.com/my/api-keys (가맹점마다
고유 발급 — 공용 테스트 키 없음, 공식 문서 확인). .env(로컬) 또는 Streamlit
Cloud secrets에 TOSS_CLIENT_KEY/TOSS_SECRET_KEY로 채워 넣을 것. 계약 확정 후
라이브 키로 바꿔 끼우면 코드 변경 없이 그대로 실결제로 전환된다.
"""

from __future__ import annotations

import base64
import json
import os

import requests
import streamlit as st
import streamlit.components.v1 as components

from wallet_db import (
    charge_points,
    create_toss_pending_order,
    get_or_create_toss_customer_key,
    get_toss_pending_order,
    mark_toss_order_status,
    pg_configured,
    toss_client_key,
    toss_secret_key,
    won_to_points,
)

TOSS_CONFIRM_URL = "https://api.tosspayments.com/v1/payments/confirm"
TOSS_SDK_SCRIPT_URL = "https://js.tosspayments.com/v1"

toss_configured = pg_configured


def _app_base_url() -> str:
    # 2026-09-19: 카카오 로그인이 이미 쓰고 있는 "앱 공개 URL" 설정을 그대로
    # 재사용한다(새 env 변수를 또 만들면 나중에 둘 중 하나만 바꿔서 어긋나는
    # 사고로 이어지기 쉬움 — auth_providers._redirect_uri()와 동일한 값).
    return os.environ.get("KAKAO_REDIRECT_URI", "http://localhost:8501").strip()


def render_checkout_trigger(member_id: int, won_amount: int) -> None:
    """결제창을 새로 연다. 버튼 클릭 즉시 호출 — st.button()이 True인 분기에서만
    불러야 한다(호출될 때마다 새 orderId를 발급하므로)."""
    client_key = toss_client_key()
    if not client_key:
        st.error("TOSS_CLIENT_KEY가 설정되지 않았습니다. 관리자에게 문의해 주세요.")
        return

    points = won_to_points(won_amount)
    order_id = create_toss_pending_order(member_id, won_amount)
    customer_key = get_or_create_toss_customer_key(member_id)
    base_url = _app_base_url()
    order_name = f"로또신령 적립금 {points:,}P"

    payload = {
        "clientKey": client_key,
        "customerKey": customer_key,
        "amount": int(won_amount),
        "orderId": order_id,
        "orderName": order_name,
        "successUrl": f"{base_url}?toss_pay=success",
        "failUrl": f"{base_url}?toss_pay=fail",
    }
    payload_json = json.dumps(payload, ensure_ascii=False)

    # 2026-08-22 QR스캔, 2026-09-06 카카오 네이티브 로그인에서 이미 검증된
    # "iframe 안에서 최상위 문서에 직접 <script> 심기" 기법을 그대로 쓴다.
    # components.html은 항상 sandbox iframe 안에서 실행되는데, 이 iframe에는
    # allow-top-navigation이 없어 location 이동(=토스 결제창으로의 리다이렉트)이
    # 막힌다(wallet_ui.py의 _scroll_to_top_once 주석 참고, 실측 확인된 제약) —
    # 토스 SDK 스크립트 자체와 그 실행을 최상위 문서(window.top)에 심어야
    # requestPayment()의 페이지 이동이 정상적으로 동작한다.
    components.html(
        f"""
        <script>
        (function() {{
            try {{
                var top = window.top;
                var payload = {payload_json};
                function runTossCheckout() {{
                    try {{
                        var tp = top.TossPayments(payload.clientKey);
                        var payment = tp.payment({{ customerKey: payload.customerKey }});
                        // 우선 카드 결제만 지원(기존 Mock 결제와 동일 범위) — 나중에
                        // 결제수단을 늘리려면 method 값만 바꾸면 된다.
                        payment.requestPayment({{
                            method: "CARD",
                            amount: {{ currency: "KRW", value: payload.amount }},
                            orderId: payload.orderId,
                            orderName: payload.orderName,
                            successUrl: payload.successUrl,
                            failUrl: payload.failUrl
                        }}).catch(function(err) {{
                            console.error("[toss] requestPayment 실패", err);
                            try {{
                                top.location.href = payload.failUrl + "&code=CLIENT_ERROR&message=" +
                                    encodeURIComponent(err && err.message ? err.message : String(err));
                            }} catch (e2) {{}}
                        }});
                    }} catch (e) {{
                        console.error("[toss] SDK 호출 실패", e);
                        try {{
                            top.location.href = payload.failUrl + "&code=SDK_ERROR&message=" +
                                encodeURIComponent(e && e.message ? e.message : String(e));
                        }} catch (e2) {{}}
                    }}
                }}
                if (top.TossPayments) {{
                    runTossCheckout();
                }} else {{
                    var s = top.document.createElement('script');
                    s.src = "{TOSS_SDK_SCRIPT_URL}";
                    s.onload = runTossCheckout;
                    s.onerror = function() {{
                        console.error("[toss] SDK 스크립트 로드 실패");
                    }};
                    top.document.head.appendChild(s);
                }}
            }} catch (e) {{
                console.error("[toss] 결제창 트리거 예외", e);
            }}
        }})();
        </script>
        """,
        height=0,
    )
    st.info("결제창을 여는 중입니다… 화면이 바뀌지 않으면 팝업 차단 여부를 확인해 주세요.")


def _confirm_with_toss(payment_key: str, order_id: str, amount: int) -> tuple[bool, str]:
    """POST /v1/payments/confirm — Basic Auth는 'secretKey:' (콜론 뒤 빈 문자열)를
    base64 인코딩한 값을 쓴다(토스 공식 문서·다수 공식 예제 코드로 확인한 형식)."""
    secret_key = toss_secret_key()
    if not secret_key:
        return False, "TOSS_SECRET_KEY가 설정되지 않았습니다."
    auth = base64.b64encode(f"{secret_key}:".encode("utf-8")).decode("utf-8")
    try:
        resp = requests.post(
            TOSS_CONFIRM_URL,
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/json",
            },
            json={"paymentKey": payment_key, "orderId": order_id, "amount": int(amount)},
            timeout=15,
        )
    except requests.RequestException as e:
        return False, f"토스 서버 통신 실패: {e}"

    if resp.status_code == 200:
        return True, "ok"
    try:
        body = resp.json()
        msg = body.get("message") or body.get("code") or resp.text
    except Exception:
        msg = resp.text
    return False, f"승인 실패({resp.status_code}): {msg}"


def handle_toss_payment_return() -> bool:
    """user_page.py 최상단에서 handle_oauth_callback()과 같은 자리에 호출한다.
    처리할 콜백이 있었으면 True(호출부가 st.rerun())."""
    toss_pay = st.query_params.get("toss_pay")
    if not toss_pay:
        return False

    if toss_pay == "fail":
        order_id = st.query_params.get("orderId")
        message = st.query_params.get("message", "결제가 취소되었습니다.")
        if order_id:
            try:
                mark_toss_order_status(order_id, "failed")
            except Exception:
                pass
        for key in ("toss_pay", "orderId", "code", "message"):
            if key in st.query_params:
                del st.query_params[key]
        try:
            st.toast(f"결제가 완료되지 않았습니다: {message}", icon="⚠️")
        except Exception:
            pass
        return True

    # toss_pay == "success"
    payment_key = st.query_params.get("paymentKey")
    order_id = st.query_params.get("orderId")
    amount_raw = st.query_params.get("amount")
    for key in ("toss_pay", "paymentKey", "orderId", "amount"):
        if key in st.query_params:
            del st.query_params[key]

    if not payment_key or not order_id or not amount_raw:
        try:
            st.toast("결제 정보가 올바르지 않습니다.", icon="⚠️")
        except Exception:
            pass
        return True

    try:
        client_amount = int(amount_raw)
    except ValueError:
        try:
            st.toast("결제 금액 정보가 올바르지 않습니다.", icon="⚠️")
        except Exception:
            pass
        return True

    order = get_toss_pending_order(order_id)
    if not order:
        try:
            st.toast("주문 정보를 찾을 수 없습니다. 관리자에게 문의해 주세요.", icon="⚠️")
        except Exception:
            pass
        return True

    if order["status"] == "confirmed":
        # 이미 처리된 콜백(새로고침·중복 리다이렉트 등) — 조용히 통과.
        return True

    # 2026-09-19: 클라이언트(브라우저 주소창)가 들고 온 amount는 조작될 수
    # 있으므로, 결제창을 열기 전 서버가 미리 기록해둔 금액과 반드시 대조한다
    # (토스 공식 문서 권고 — "금액 위·변조 확인"). 다르면 confirm API 자체를
    # 호출하지 않고 즉시 거부한다.
    if client_amount != order["won_amount"]:
        mark_toss_order_status(order_id, "mismatch")
        try:
            import security_log

            security_log.log_event(
                "toss_amount_mismatch",
                f"order_id={order_id} expected={order['won_amount']} got={client_amount}",
            )
        except Exception:
            pass
        try:
            st.toast("결제 금액이 일치하지 않아 처리를 중단했습니다. 관리자에게 문의해 주세요.", icon="🚨")
        except Exception:
            pass
        return True

    ok, msg = _confirm_with_toss(payment_key, order_id, client_amount)
    if not ok:
        mark_toss_order_status(order_id, "failed")
        try:
            st.toast(f"결제 승인에 실패했습니다: {msg}", icon="⚠️")
        except Exception:
            pass
        return True

    ref_id = f"pg:toss:{order_id}"
    credited = charge_points(order["member_id"], order["points"], ref_id)
    mark_toss_order_status(order_id, "confirmed" if credited else "credit_failed")
    if credited:
        st.session_state.wallet_toast = f"{order['won_amount']:,}원 · {order['points']:,}P 충전 완료"
    else:
        try:
            st.toast("결제는 승인됐지만 적립금 지급에 실패했습니다. 관리자에게 문의해 주세요.", icon="🚨")
        except Exception:
            pass
    return True
