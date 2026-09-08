"""지갑 UI — 로그인·적립금 안내 dialog."""

from __future__ import annotations

import html
import uuid

import streamlit as st
import streamlit.components.v1 as components

from auth_providers import (
    _dev_mock_enabled,
    current_member_id,
    get_kakao_authorize_url,
    kakao_configured,
    logout,
    mock_kakao_login,
)
from legal_notices import (
    AUTH_CONSENT_ITEMS,
    AUTH_PROMPT_SUBTITLE,
    NOTICE_VERSION,
    format_advanced_points_notice,
    format_auto_points_notice,
    format_hedge_points_notice,
    format_tarot_points_notice,
    format_thunder_points_notice,
    ADVANCED_FILTER_FIRST_SUB_FREE,
)
from wallet_db import (
    ADVANCED_3MONTH_COST,
    ADVANCED_3MONTH_DAYS,
    ADVANCED_MONTHLY_COST,
    CHARGE_WON_AMOUNTS,
    FREE_SUB_DAYS,
    SIGNUP_BONUS,
    activate_free_advanced_sub,
    activate_paid_advanced_sub,
    calc_auto_cost,
    calc_hedge_cost,
    calc_thunder_cost,
    charge_points,
    deduct_points,
    eligible_free_advanced_sub,
    get_balance,
    pg_configured,
    won_to_points,
)


def _dialog_decorator(title: str):
    if hasattr(st, "dialog"):
        return st.dialog(title)
    return st.experimental_dialog(title) if hasattr(st, "experimental_dialog") else _fallback_dialog(title)


def _fallback_dialog(title: str):
    def wrapper(func):
        def inner(*args, **kwargs):
            with st.container(border=True):
                st.subheader(title)
                return func(*args, **kwargs)
        return inner
    return wrapper


AUTH_BANNER_OPEN = "auth_banner_open"
AUTH_BANNER_REASON = "auth_banner_reason"
AUTH_RESUME_FLAG = "auth_resume_flag"
AUTH_RESUME_DATA = "auth_resume_data"


def open_auth_banner(*, reason: str = "", resume: str | None = None, resume_data: dict | None = None) -> None:
    st.session_state[AUTH_BANNER_OPEN] = True
    st.session_state[AUTH_BANNER_REASON] = reason or "이 기능을 이용하려면 간편인증이 필요합니다."
    if resume:
        st.session_state[AUTH_RESUME_FLAG] = resume
    if resume_data:
        st.session_state[AUTH_RESUME_DATA] = resume_data


def close_auth_banner() -> None:
    for key in (AUTH_BANNER_OPEN, AUTH_BANNER_REASON):
        st.session_state.pop(key, None)


def _resume_after_auth() -> None:
    resume = st.session_state.pop(AUTH_RESUME_FLAG, None)
    data = st.session_state.pop(AUTH_RESUME_DATA, None) or {}
    if resume == "auto_show_points":
        st.session_state["auto_show_points"] = True
    elif resume == "open_thunder_dialog":
        st.session_state["open_thunder_dialog"] = True
        st.session_state["open_thunder_dialog_games"] = int(data.get("games", 5))
    elif resume == "open_hedge_dialog":
        # 2026-08-27: 조합시작 한 번에 개별리셋·전체리셋을 항상 함께 생성하도록
        # 바뀌면서 "모드" 선택 자체가 없어져 더 이상 넘길 값이 없다.
        st.session_state["open_hedge_dialog"] = True
        st.session_state["hedge_pending_lines"] = data.get("lines") or []
        st.session_state["hedge_pending_count"] = int(data.get("count", 5))
    elif resume == "open_tarot_dialog":
        st.session_state["open_tarot_dialog"] = True
    elif resume == "af_show_step1_points":
        st.session_state["af_show_step1_points"] = True
    elif resume == "af_show_step2_points":
        st.session_state["af_show_step2_points"] = True
    elif resume == "wallet_show_charge":
        st.session_state["wallet_show_charge"] = True
    elif resume == "my_info_dialog":
        st.session_state["my_info_dialog_open"] = True


def _finish_auth_success() -> None:
    _resume_after_auth()
    close_auth_banner()
    st.rerun()


def _testing_period_active() -> bool:
    """[출시 전 테스트 기간 한정] 실제 카카오 인증·PG 결제가 아직 연동되지 않은
    동안엔 True — 인증/적립금/구독 안내 배너를 전부 숨기고 조용히 통과시키는
    데 쓴다(사용자 요청: "테스트기간엔 인증,적립금,결제,충전 안내배너창 다
    숨기기"). kakao_configured()가 켜지는 순간(=실제 연동 완료) 이 우회는
    자동으로 꺼지고 원래의 배너/안내창 흐름으로 돌아간다.

    [숙제 — 정식 출시 시 결정 필요] 지금은 전부 숨겼지만, 실제로 포인트가
    깎이는 정식 서비스에서는 사용자가 "왜 깎였는지" 알 방법이 아예 없어지면
    안 된다. 매번 안내창을 띄우던 예전 방식은 번거로워 이탈을 유발했으니,
    예를 들어 "처음 한 번만 안내 + 이후엔 상단에 잔액과 이번 차감액을 작게
    표시" 같은 절충안을 검토할 것."""
    return _dev_mock_enabled() and not kakao_configured()


AUTH_BANNER_SEEN_ONCE = "auth_banner_seen_once"


def ensure_member_or_banner(*, resume: str, reason: str, resume_data: dict | None = None) -> bool:
    """로그인됐으면 True. 아니면 배너만 띄우고 False.

    테스트 기간엔 "카카오로 시작하기" 배너를 띄우는 대신 조용히 로그인시키고
    바로 진행한다 — _testing_period_active() 참고.

    2026-09-08 추가(사용자 지시): 구매·내정보·충전 등을 시도할 때마다 매번
    이 배너가 다시 뜨는 게 번거롭다는 신고 — 이 배너는 세션(앱을 닫기 전까지)당
    **한 번만** 띄우고, 그 뒤로는 다시 안 띄운다(로그인이 안 됐어도 조용히
    False만 반환). 로그인 여부와 무관하게 "이미 한 번 안내했다"는 사실 자체를
    기억하는 플래그라, 이후 세션 중간에 실제로 로그아웃(idle 등)이 다시
    발생해도 이 배너는 두 번째부터는 안 뜬다 — 이게 의도와 다르면 알려줄 것."""
    if current_member_id():
        return True
    if _testing_period_active():
        mock_kakao_login()
        return True
    if st.session_state.get(AUTH_BANNER_SEEN_ONCE):
        return False
    st.session_state[AUTH_BANNER_SEEN_ONCE] = True
    open_auth_banner(reason=reason, resume=resume, resume_data=resume_data)
    st.rerun()
    return False


def _inject_auth_banner_css() -> None:
    st.markdown(
        """
<div class="lotto-auth-banner-marker" aria-hidden="true"></div>
<style>
div[data-testid="stVerticalBlock"]:has(> div > .lotto-auth-banner-marker),
div[data-testid="stVerticalBlock"]:has(.lotto-auth-banner-marker) {
    position: sticky !important;
    top: 0 !important;
    z-index: 100 !important;
    margin-bottom: 12px !important;
}
.lotto-auth-banner {
    background: linear-gradient(135deg, #1a2744 0%, #12182b 100%);
    border: 1px solid #3d5a80;
    border-radius: 14px;
    padding: 14px 16px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
}
.lotto-auth-banner .auth-banner-title {
    font-size: 15px;
    font-weight: 800;
    color: #e3f2fd;
    margin: 0 0 4px 0;
}
.lotto-auth-banner .auth-banner-sub {
    font-size: 12px;
    color: #90caf9;
    margin: 0 0 10px 0;
    line-height: 1.45;
}
.lotto-auth-banner .auth-banner-bonus {
    font-size: 12px;
    color: #ffb300;
    font-weight: 700;
    margin: 0 0 10px 0;
}
div[data-testid="stVerticalBlock"]:has(.auth-banner-consent-marker) {
    background: rgba(13, 21, 40, 0.5) !important;
    border: 1px solid #2a3a60 !important;
    border-radius: 10px !important;
    padding: 8px 10px 4px 10px !important;
    margin-bottom: 10px !important;
}
div[data-testid="stVerticalBlock"]:has(.auth-banner-consent-marker) label p,
.auth-banner-consent-item {
    color: #e8eef2 !important;
    font-size: 13.5px !important;
    line-height: 1.7 !important;
    margin: 6px 0 !important;
}
.st-key-auth_banner_kakao a,
.st-key-auth_banner_kakao button[kind="primary"] {
    background: linear-gradient(145deg, #fee500, #f5d900) !important;
    color: #191919 !important;
    border-color: #e6c200 !important;
    border-radius: 10px !important;
    min-height: 42px !important;
    font-weight: 700 !important;
}
.st-key-auth_banner_close button {
    background: transparent !important;
    color: #78909c !important;
    border: 1px solid #37474f !important;
    border-radius: 10px !important;
    min-height: 36px !important;
    font-size: 13px !important;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def _fire_kakao_native_login_trigger() -> None:
    """네이티브 앱(streamlit-webview.tsx)에게 카카오 네이티브 SDK 로그인을
    시작하라는 신호를 보낸다 — page_hedge.py의 QR스캔 트리거(_fire_qr_scan_
    trigger)와 완전히 같은 기법: components.html은 항상 iframe 안에서
    실행되는데, 안드로이드 웹뷰가 심어주는 window.ReactNativeWebView 브릿지는
    보안상 최상위 프레임에만 존재해서 iframe 안에서는 그 자리에 아예 없다
    (2026-08-22 실기기 확인, QR스캔에서 이미 검증된 우회법). iframe 안에서
    최상위 문서에 직접 <script> 엘리먼트를 심어 그 스크립트가 최상위 문서
    컨텍스트에서 실행되게 하면, 거기서 보는 window.ReactNativeWebView는
    진짜 그 프레임에 심어진 브릿지를 가리킨다.

    2026-09-06: 처음엔 postMessage 브릿지 하나에만 의존했는데, QR스캔에서
    이미 겪었던 것과 같은 기기(브릿지 객체 자체가 최상위 문서에 안 심어지는
    실기기)에서 로그인 버튼이 조용히 아무 반응도 안 하는 문제가 실측 확인됐다.
    QR스캔과 동일하게 "브릿지가 있으면 postMessage만, 없으면 URL 트리거로
    폴백"하는 판단을 최상위 문서 스크립트 안에서 직접 하도록 만든다 — 둘 다
    항상 실행하면(QR스캔에서 겪은 부작용, 위 _fire_qr_scan_trigger 독스트링
    참고) 브릿지가 성공했을 때도 URL 이동이 같이 걸려 화면이 깜빡이며
    되돌아오는 문제가 생길 수 있어 피한다."""
    components.html(
        """<script>
        (function () {
            var top = window.top;
            try {
                var s = top.document.createElement('script');
                s.textContent =
                    "try{" +
                    "var rnwv = window.ReactNativeWebView;" +
                    "if(rnwv && typeof rnwv.postMessage === 'function'){" +
                    "rnwv.postMessage(JSON.stringify({type:'kakaoNativeLogin'}));" +
                    "}else{" +
                    "var u = new URL(window.location.href);" +
                    "u.searchParams.set('kakao_native_trigger', '1');" +
                    "window.location.href = u.toString();" +
                    "}" +
                    "}catch(e){}";
                top.document.head.appendChild(s);
                s.parentNode.removeChild(s);
            } catch (e) {
                // 최상위 문서에 스크립트를 못 심을 정도로 예외적인 상황이면
                // 최소한 이 폴백만이라도 시도한다.
                try {
                    var u2 = new URL(top.location.href);
                    u2.searchParams.set('kakao_native_trigger', '1');
                    top.location.href = u2.toString();
                } catch (e2) {}
            }
        })();
        </script>""",
        height=0,
    )


def _render_auth_banner_form() -> None:
    reason = st.session_state.get(AUTH_BANNER_REASON, "")
    reason_html = html.escape(reason)
    st.markdown(
        f'<div class="lotto-auth-banner">'
        f'<p class="auth-banner-title">간편인증</p>'
        f'<p class="auth-banner-sub">{reason_html}</p>'
        f'<p class="auth-banner-bonus">최초 인증 시 적립금 {SIGNUP_BONUS:,}P 지급 · 현금 환불 불가</p>'
        f"</div>",
        unsafe_allow_html=True,
    )

    with st.container():
        st.markdown('<div class="auth-banner-consent-marker"></div>', unsafe_allow_html=True)
        # 체크박스로 하나씩 동의받던 걸 안내 문구로 바꿨다 — 지금은 테스트 기간이라
        # 사용자 요청대로 "카카오로 시작하기"를 바로 누를 수 있어야 한다. 항목
        # 자체는(적립금 지급/환불 불가 등 고지 목적) 계속 텍스트로 보여준다.
        for item in AUTH_CONSENT_ITEMS:
            st.markdown(f'<p class="auth-banner-consent-item">· {html.escape(item)}</p>', unsafe_allow_html=True)

    return_page = st.query_params.get("page", "main")

    if kakao_configured():
        # 2026-09-06: 네이티브 앱(?native=1)에서는 REST API+웹뷰 리다이렉트
        # 방식(카카오 공식 미지원 — devtalk.kakao.com 답변)을 버리고, 카카오
        # 네이티브 SDK를 직접 호출하는 버튼으로 바꾼다. 일반 웹 접속은
        # 기존 방식 그대로 둔다(영향 없음).
        is_native_app = st.query_params.get("native") == "1"
        with st.container(key="auth_banner_kakao"):
            if is_native_app:
                if st.button(
                    "카카오로 시작하기",
                    use_container_width=True,
                    type="primary",
                    key="auth_banner_kakao_native",
                ):
                    _fire_kakao_native_login_trigger()
            else:
                st.link_button(
                    "카카오로 시작하기",
                    get_kakao_authorize_url(return_page),
                    use_container_width=True,
                    type="primary",
                )
        st.caption("카카오 로그인 후 이 페이지로 돌아옵니다.")
    elif _dev_mock_enabled():
        with st.container(key="auth_banner_kakao"):
            if st.button(
                "카카오로 시작하기",
                use_container_width=True,
                type="primary",
                key="auth_banner_kakao_mock",
            ):
                mock_kakao_login()
                _finish_auth_success()
        st.caption("개발 모드 · Mock 간편인증")
    else:
        with st.container(key="auth_banner_kakao"):
            st.button(
                "카카오로 시작하기",
                use_container_width=True,
                disabled=True,
                key="auth_banner_kakao_unconfigured",
            )
        st.error(
            "카카오 로그인 연동이 아직 설정되지 않았습니다. "
            "`.env`에 `KAKAO_REST_API_KEY`를 넣거나, "
            "개발 중이면 `LOTTO_DEV_MOCK_AUTH=1`로 설정 후 서버를 재시작하세요."
        )

    with st.container(key="auth_banner_close"):
        if st.button("닫기", use_container_width=True, key="auth_banner_dismiss", type="secondary"):
            close_auth_banner()
            st.session_state.pop(AUTH_RESUME_FLAG, None)
            st.session_state.pop(AUTH_RESUME_DATA, None)
            st.rerun()

    st.caption("PASS·금융인증서는 사업자 연동 계약 후 순차 제공 예정입니다.")


def render_auth_banner() -> None:
    if current_member_id() and st.session_state.get(AUTH_RESUME_FLAG):
        _finish_auth_success()
        return
    if not st.session_state.get(AUTH_BANNER_OPEN):
        return
    if current_member_id():
        _finish_auth_success()
        return
    _inject_auth_banner_css()
    _render_auth_banner_form()


def auth_dialog() -> bool:
    """하위 호환 — 배너로 대체됨."""
    open_auth_banner(reason=AUTH_PROMPT_SUBTITLE)
    return False


def _render_charge_actions(member_id: int) -> None:
    """충전 버튼/안내 렌더링 — charge_dialog()와 insufficient_balance_dialog()가
    공유한다(2026-09-08 분리). 두 곳에 똑같은 로직을 복붙해두면 나중에 금액·문구를
    한쪽만 고치고 다른 쪽을 놓치는 사고로 이어지므로, 결제 관련 코드는 항상 여기
    한 곳만 고치면 두 다이얼로그 모두에 반영되게 한다."""
    if pg_configured():
        won_amount = st.radio(
            "충전 금액",
            CHARGE_WON_AMOUNTS,
            format_func=lambda w: f"{w:,}원 → {won_to_points(w):,}P",
            horizontal=True,
        )
        st.info("PG 결제창 연동은 계약 후 활성화됩니다. (카드정보는 서버에 저장하지 않습니다.)")
        st.link_button(
            "결제창 열기 (준비중)",
            "#",
            disabled=True,
            use_container_width=True,
        )
    elif _testing_period_active():
        # 2026-09-05: 이 버튼은 카카오 로그인이 아직 mock인 "출시 전 테스트
        # 기간"에만 보여야 한다 — 예전엔 pg_configured()만 봐서, 카카오
        # 로그인이 실제로 연동된 뒤에도(=실사용자가 진짜 로그인한 뒤에도)
        # PG만 아직이면 누구나 눌러서 무한 포인트를 받을 수 있었다(실제
        # 무료 악용 가능 상태 — 2026-09-05 발견).
        # 2026-09-08 임시 조치(사용자 지시): 테스트 기간이 길어지면서 테스터들
        # 적립금이 바닥나는 문제 — 정식 결제 전까지는 실제 돈이 오가지 않는
        # Mock 결제이므로, 금액 선택 라디오(4종) 없이 1만원→1,000P 한 가지만
        # 반복해서 누를 수 있게 단순화한다. CHARGE_WON_AMOUNTS(4종)는 PG 연동
        # 후 실 결제 화면(위 pg_configured() 분기)에서 그대로 쓰이므로 건드리지
        # 않았다 — 원인 확인되면(=테스트 종료·PG 연동 시) 이 분기 자체가 안
        # 타므로 별도 원복 작업 불필요.
        test_won_amount = 10000
        test_points = won_to_points(test_won_amount)
        st.caption(f"PG 미연동 · 테스트 기간 임시 고정 금액 — {test_won_amount:,}원 → {test_points:,}P")
        if st.button(
            f"Mock 결제 (테스트) — {test_points:,}P 충전",
            type="primary",
            use_container_width=True,
        ):
            ref = f"pg:mock:{member_id}:{uuid.uuid4().hex[:10]}"
            if charge_points(member_id, test_points, ref):
                st.session_state.wallet_toast = f"{test_won_amount:,}원 · {test_points:,}P 충전 완료"
                # insufficient_balance_dialog()에서 호출된 경우, 충전 성공 후에도
                # 이 플래그가 남아있으면 다음 렌더에서 "부족합니다" 창이 또 뜬다 —
                # charge_dialog()에서 호출된 경우엔 애초에 없는 키라 pop이 그냥
                # 무시된다(두 다이얼로그가 이 함수를 공유하므로 항상 같이 정리).
                st.session_state.pop(INSUFFICIENT_BALANCE_OPEN, None)
                st.rerun()
            st.error("충전에 실패했습니다.")
    else:
        st.info("결제 연동 준비 중입니다. 조금만 기다려주세요.")


@_dialog_decorator("적립금 충전")
def charge_dialog() -> None:
    member_id = current_member_id()
    if not member_id:
        return

    balance = get_balance(member_id)
    st.markdown(f"현재 잔액 **{balance:,}P**")
    _render_charge_actions(member_id)


INSUFFICIENT_BALANCE_OPEN = "insufficient_balance_open"
INSUFFICIENT_BALANCE_NEED = "insufficient_balance_need"


def open_insufficient_balance_dialog(need_points: int) -> None:
    """자동구매/번개조합/안티·액땜조합 세 화면 공통 — 구매 확정 시 적립금이
    부족하면 이 함수 하나로 "부족합니다 + 충전하시겠습니까?" 통합 창을 띄운다.

    2026-09-08(사용자 지시): 예전엔 각 화면이 "적립금이 부족합니다" 에러 문구만
    보여주고 끝나서, 사용자가 직접 내정보→충전으로 따로 이동해야 했다. 그 자리에서
    바로 충전까지 이어지도록 세 화면 모두 이 함수로 통일한다(한 화면만 고치면
    나머지가 방치되는 문제가 반복 지적됐음 — apply_fixes_to_all_three_purchase_screens
    메모 참고)."""
    st.session_state[INSUFFICIENT_BALANCE_OPEN] = True
    st.session_state[INSUFFICIENT_BALANCE_NEED] = int(need_points)


@_dialog_decorator("적립금 부족")
def insufficient_balance_dialog() -> None:
    member_id = current_member_id()
    if not member_id:
        st.session_state.pop(INSUFFICIENT_BALANCE_OPEN, None)
        return
    need = int(st.session_state.get(INSUFFICIENT_BALANCE_NEED, 0))
    balance = get_balance(member_id)
    st.error(f"❌ 적립금이 부족합니다. (필요 {need:,}P / 보유 {balance:,}P)")
    st.markdown("**충전하시겠습니까?**")
    _render_charge_actions(member_id)
    if st.button("닫기", use_container_width=True, key="insufficient_balance_close"):
        st.session_state.pop(INSUFFICIENT_BALANCE_OPEN, None)
        st.rerun()


POINTS_NOTICE_SEEN_ONCE = "points_notice_seen_once"


@_dialog_decorator("적립금 이용 안내")
def points_notice_dialog(
    service: str,
    *,
    game_count: int = 5,
    quantity: int = 5,
    on_close,
) -> None:
    """service: thunder/hedge/auto/tarot. on_close(confirmed: bool)를 누른 버튼에 맞춰
    호출한 뒤 st.rerun()한다 — 반환값을 호출부가 받아 처리하는 방식은 st.dialog
    안에서 실제로 동작하지 않아(버튼을 눌러도 다음 단계로 못 넘어가고 같은 화면이
    반복되는 문제로 실기기에서 확인됨) 콜백 방식으로 바꿨다.

    지금은 실제 카카오 인증·PG 결제가 연결되지 않은 테스트 기간이라, 적립금 부족
    등의 이유로 사용자를 막지 않는다 — 안내만 보여주고 취소/확인 어느 쪽을 눌러도
    기능은 그대로 이용할 수 있게 통과시킨다(on_close(True/False)는 실제 차감
    시도 여부를 호출부에 알려줄 뿐, 통과 여부를 막는 용도가 아니다).

    테스트 기간엔(_testing_period_active) 이 안내창 자체를 아예 안 띄우고
    바로 확인 처리한다 — 매번 조합 만들 때마다 안내창이 뜨는 게 번거롭다는
    사용자 요청. 정식 출시 시 어떻게 다시 노출할지는 _testing_period_active
    독스트링의 "숙제" 참고.

    2026-09-08 추가(사용자 지시): 실연동 후에도 구매할 때마다 이 확인창이
    매번 뜨는 게 번거롭다는 신고 — 세션(앱을 닫기 전까지)당 **한 번**
    보여준 뒤로는 다시 안 띄우고 바로 확인 처리한다(위 테스트 기간 분기와
    동일하게 on_close(True)). 단, 이후 실제로 적립금이 부족하면 그건 이
    안내창과 별개로 각 화면의 실패 안내(예: page_thunder.py의 "적립금이
    부족합니다")가 그대로 뜬다 — "확인하시겠습니까" 질문만 한 번으로
    줄이는 것이지, 부족 안내 자체를 없애는 게 아니다."""
    if _testing_period_active():
        on_close(True)
        st.rerun()
        return
    if st.session_state.get(POINTS_NOTICE_SEEN_ONCE):
        on_close(True)
        st.rerun()
        return
    st.session_state[POINTS_NOTICE_SEEN_ONCE] = True
    member_id = current_member_id()
    balance = get_balance(member_id) if member_id else 0

    if service == "thunder":
        st.markdown(format_thunder_points_notice(game_count, balance))
    elif service == "hedge":
        st.markdown(format_hedge_points_notice(quantity, balance))
    elif service == "auto":
        st.markdown(format_auto_points_notice(quantity, balance))
    elif service == "tarot":
        st.markdown(format_tarot_points_notice(balance))
    else:
        st.error("알 수 없는 서비스")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("취소", use_container_width=True, key=f"pn_cancel_{service}"):
            on_close(False)
            st.rerun()
    with c2:
        if st.button("확인 후 진행", type="primary", use_container_width=True, key=f"pn_confirm_{service}"):
            on_close(True)
            st.rerun()


@_dialog_decorator("고급필터 구독")
def advanced_subscription_dialog(*, on_close) -> None:
    """구독 활성화까지 여기서 끝내고 on_close()를 호출한 뒤 st.rerun()한다 — 반환값을
    호출부가 받아 처리하는 방식은 st.dialog 안에서 실제로 동작하지 않는다(위
    points_notice_dialog와 동일한 이유). 여기는 (타로·번개 등과 달리) 진짜 잠금이라
    "취소"를 눌러도 구독이 되지는 않는다 — 그냥 닫기만 한다.

    테스트 기간엔(_testing_period_active) 이 안내창도 안 띄우고, 유료 결제 없이
    바로 장기 구독을 활성화해서 고급필터를 막힘없이 쓸 수 있게 한다 — 정식
    출시 시 어떻게 다시 노출할지는 _testing_period_active 독스트링 참고."""
    if _testing_period_active():
        member_id = current_member_id()
        if member_id:
            activate_paid_advanced_sub(member_id, 3650)
        on_close()
        st.rerun()
        return
    member_id = current_member_id()
    if not member_id:
        on_close()
        st.rerun()
        return

    balance = get_balance(member_id)
    free_ok = ADVANCED_FILTER_FIRST_SUB_FREE and eligible_free_advanced_sub(member_id)

    if free_ok:
        st.markdown(format_advanced_points_notice(has_free_sub=True, balance=balance))
        plan = "free"
        cost = 0
    else:
        plan = st.radio(
            "구독 기간",
            ["monthly", "3month"],
            format_func=lambda p: f"1개월 · {ADVANCED_MONTHLY_COST:,}P" if p == "monthly" else f"3개월 · {ADVANCED_3MONTH_COST:,}P",
            horizontal=True,
        )
        st.markdown(format_advanced_points_notice(plan=plan, balance=balance))
        cost = ADVANCED_MONTHLY_COST if plan == "monthly" else ADVANCED_3MONTH_COST

    if cost > 0 and balance < cost:
        st.error(f"적립금이 부족합니다. (필요 {cost:,}P / 보유 {balance:,}P)")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("취소", use_container_width=True, key="adv_sub_cancel"):
            on_close()
            st.rerun()
    with c2:
        if st.button("구독하기", type="primary", use_container_width=True, key="adv_sub_confirm", disabled=cost > 0 and balance < cost):
            if plan == "free":
                ok = activate_free_advanced_sub(member_id)
            else:
                ref = f"advanced:{plan}:{member_id}:{uuid.uuid4().hex[:10]}"
                days = FREE_SUB_DAYS if plan == "monthly" else ADVANCED_3MONTH_DAYS
                ok = deduct_points(member_id, cost, f"advanced:{plan}", ref) and activate_paid_advanced_sub(
                    member_id, days
                )
            if not ok:
                st.error("구독 처리에 실패했습니다.")
            on_close()
            st.rerun()
    return None


def render_wallet_bar(*, show_my_info_trigger: bool = True) -> int | None:
    """로그인 시에만 상단 잔액 바. 미로그인 시 배너는 인증 필요 클릭 때만.

    show_my_info_trigger=False면 "내정보" 버튼/다이얼로그 자체를 아예 안 그린다 —
    메인 화면에만 필요하고 다른 상세페이지에서는 불필요하다는 요청."""
    from shared_ui_styles import wallet_bar_button_css
    from zero_phone_db import TEST_USER_ID, get_user, init_zero_phone_tables, login_test_user

    init_zero_phone_tables()

    if current_member_id() and st.session_state.get(AUTH_RESUME_FLAG):
        _finish_auth_success()

    toast = st.session_state.pop("wallet_toast", None)
    if toast:
        st.success(toast)

    render_auth_banner()

    zp_uid = st.session_state.get("zp_user_id")
    if zp_uid:
        zp_row = get_user(zp_uid)
        if zp_row:
            st.session_state.zp_point_balance = zp_row["point_balance"]
            st.session_state.zp_is_premium = zp_row["is_premium"]
        else:
            st.session_state.pop("zp_user_id", None)

    member_id = current_member_id() if not zp_uid else None

    if st.session_state.get("wallet_show_charge") and member_id:
        st.session_state.pop("wallet_show_charge", None)
        charge_dialog()

    if not member_id and not zp_uid:
        # 2026-09-02: 예전엔 여기서 "개발용 테스트 로그인" 버튼을 사용자에게 직접
        # 노출했는데, 애플 심사(가이드라인 2.2 베타 테스트)에서 "테스트/평가판
        # 버전처럼 보인다"고 반려됨 — ensure_member_or_banner()가 이미 쓰던
        # "테스트 기간엔 버튼 없이 조용히 로그인" 패턴으로 통일한다. 카카오
        # 연동이 완료되면(kakao_configured()) _testing_period_active()가
        # 자동으로 False가 되면서 이 우회 자체가 꺼진다.
        if _testing_period_active():
            user, is_new = login_test_user(TEST_USER_ID)
            st.session_state.zp_user_id = user["user_id"]
            st.session_state.zp_point_balance = user["point_balance"]
            st.session_state.zp_is_premium = user["is_premium"]
            if is_new:
                st.session_state.wallet_toast = "가입 완료! 5,000P 지급"
            st.rerun()
        # 2026-09-05: 정식 출시 — "앱을 처음 열 때부터 로그인을 강제하진 않지만,
        # 구매·구매내역·적립금내역(=내정보)을 보려고 하면 그 시점에 간편인증을
        # 요구하고, 한 번 인증하면 그 방문 동안은 다시 안 묻는다"는 요구사항.
        # 카카오 연동 전엔(_testing_period_active) 위에서 이미 조용히 로그인
        # 처리하니 여기 도달하지 않는다 — 아래는 실제 인증이 켜진 뒤에만 탄다.
        if show_my_info_trigger:
            st.markdown(wallet_bar_button_css(), unsafe_allow_html=True)
            with st.container(key="my_info_trigger_wrap"):
                if st.button("👤 내정보", key="my_info_trigger_btn", use_container_width=True):
                    # 2026-09-08 수정: 이 버튼은 ensure_member_or_banner()를 안 거치고
                    # open_auth_banner()를 직접 불러서, "세션당 한 번만" 가드가 적용
                    # 안 되고 있었다(사용자가 지적한 "내정보 볼 때마다 로그인창" 사례 —
                    # 구매 쪽 가드만 고치고 이 경로를 놓쳤던 것) — 같은 플래그를 공유해서
                    # 한 번만 뜨게 통일한다.
                    if not st.session_state.get(AUTH_BANNER_SEEN_ONCE):
                        st.session_state[AUTH_BANNER_SEEN_ONCE] = True
                        open_auth_banner(
                            reason="내정보(구매내역·적립금)를 보려면 간편인증이 필요합니다.",
                            resume="my_info_dialog",
                        )
                    st.rerun()
        return None

    # 예전엔 이 정보(적립금/ID/로그아웃)를 화면마다 상단에 항상 띄워뒀는데, 페이지를
    # 옮길 때마다 계속 보여서 거슬린다는 요청 — 메인 화면 우상단의 "내정보" 버튼을
    # 눌러야만 뜨는 창으로 옮긴다. 다른 상세페이지에서는 이 버튼 자체가 불필요하다는
    # 요청이라 show_my_info_trigger=False면 아예 안 그린다(그 페이지들 상단에 빈
    # 공간을 남기던 원인이기도 했다). 로그아웃도 요즘 앱들처럼 앱을 완전히 닫으면
    # 세션이 알아서 끊기니 상시 노출할 필요가 없다는 게 사용자 판단(자동 로그아웃
    # 로직 자체를 새로 만든 건 아니고, 기존 세션 유지 방식은 그대로 둠).
    if show_my_info_trigger:
        st.markdown(wallet_bar_button_css(), unsafe_allow_html=True)
        with st.container(key="my_info_trigger_wrap"):
            if st.button("👤 내정보", key="my_info_trigger_btn", use_container_width=True):
                st.session_state["my_info_dialog_open"] = True
                st.rerun()

    if st.session_state.get("my_info_dialog_open"):
        _my_info_dialog(zp_uid=zp_uid, member_id=member_id)

    return member_id


@_dialog_decorator("내정보")
def _my_info_dialog(*, zp_uid: str | None, member_id: int | None) -> None:
    if zp_uid:
        bal = int(st.session_state.get("zp_point_balance", 0))
        tag = zp_uid if len(zp_uid) <= 16 else zp_uid[:12] + "…"
        st.markdown(f"**현재 보유 적립금: {bal:,}점** · ID `{tag}`")
        if st.button("로그아웃", key="zp_logout_btn", use_container_width=True, type="secondary"):
            from user_scope import clear_user_session

            for key in ("zp_user_id", "zp_point_balance", "zp_is_premium"):
                st.session_state.pop(key, None)
            clear_user_session()
            st.session_state["my_info_dialog_open"] = False
            st.rerun()
    else:
        bal = get_balance(member_id)
        tag = st.session_state.get("oauth_hash_display", "ID")
        st.markdown(f"**적립금 {bal:,}P** · ID `{tag}` · v{NOTICE_VERSION}")
        bc1, bc2 = st.columns(2)
        with bc1:
            if st.button("충전", key="wallet_charge_btn", use_container_width=True, type="secondary"):
                # charge_dialog()를 여기서 바로 부르면 이미 열려있는 dialog 위에
                # 또 다른 dialog를 겹쳐 여는 셈이라, 기존 코드 다른 곳에서 쓰던
                # 방식(플래그를 세워두고 다음 렌더에서 별도로 열기) 그대로 따른다.
                st.session_state["my_info_dialog_open"] = False
                st.session_state["wallet_show_charge"] = True
                st.rerun()
        with bc2:
            if st.button("로그아웃", key="wallet_logout_btn", use_container_width=True, type="secondary"):
                logout()
                st.session_state["my_info_dialog_open"] = False
                st.rerun()

    if st.button("닫기", key="my_info_dialog_close_btn", use_container_width=True):
        st.session_state["my_info_dialog_open"] = False
        st.rerun()


def require_auth_or_prompt() -> int | None:
    mid = current_member_id()
    if mid:
        return mid
    open_auth_banner(reason="이 기능을 이용하려면 간편인증이 필요합니다.")
    return None


def deduct_after_result(
    member_id: int,
    service: str,
    ref_id: str,
    *,
    game_count: int = 5,
    quantity: int = 5,
) -> bool:
    """thunder/hedge/auto — 결과 생성 성공 후 차감. 고급필터는 구독형이라
    advanced_subscription_dialog()가 구독 시작 시점에 별도로 처리한다."""
    if service == "thunder":
        cost = calc_thunder_cost(game_count)
        reason = f"thunder:{game_count}games"
    elif service == "hedge":
        cost = calc_hedge_cost(quantity)
        reason = f"hedge:{quantity}combos"
    elif service == "auto":
        cost = calc_auto_cost(quantity)
        reason = f"auto:{quantity}qty"
    else:
        return False

    return deduct_points(member_id, cost, reason, ref_id)
