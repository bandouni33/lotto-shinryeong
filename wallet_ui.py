"""지갑 UI — 로그인·적립금 안내 dialog."""

from __future__ import annotations

import html
import uuid

import streamlit as st

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
    format_thunder_points_notice,
    ADVANCED_FILTER_FIRST_SUB_FREE,
)
from wallet_db import (
    CHARGE_AMOUNTS,
    activate_free_advanced_sub,
    calc_auto_cost,
    calc_thunder_cost,
    charge_points,
    deduct_points,
    eligible_free_advanced_sub,
    get_balance,
    has_active_subscription,
    pg_configured,
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
    elif resume == "af_show_step1_points":
        st.session_state["af_show_step1_points"] = True
    elif resume == "af_show_step2_points":
        st.session_state["af_show_step2_points"] = True
    elif resume == "wallet_show_charge":
        st.session_state["wallet_show_charge"] = True


def _finish_auth_success() -> None:
    _resume_after_auth()
    close_auth_banner()
    st.rerun()


def ensure_member_or_banner(*, resume: str, reason: str, resume_data: dict | None = None) -> bool:
    """로그인됐으면 True. 아니면 배너만 띄우고 False."""
    if current_member_id():
        return True
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
div[data-testid="stVerticalBlock"]:has(.auth-banner-consent-marker) label p {
    color: #cfd8dc !important;
    font-size: 11.5px !important;
    line-height: 1.4 !important;
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


def _render_auth_banner_form() -> None:
    reason = st.session_state.get(AUTH_BANNER_REASON, "")
    reason_html = html.escape(reason)
    st.markdown(
        f'<div class="lotto-auth-banner">'
        f'<p class="auth-banner-title">간편인증</p>'
        f'<p class="auth-banner-sub">{reason_html}</p>'
        f'<p class="auth-banner-bonus">최초 인증 시 적립금 5,000P 지급 · 현금 환불 불가</p>'
        f"</div>",
        unsafe_allow_html=True,
    )

    with st.container():
        st.markdown('<div class="auth-banner-consent-marker"></div>', unsafe_allow_html=True)
        checks = [st.checkbox(item, key=f"auth_banner_consent_{i}") for i, item in enumerate(AUTH_CONSENT_ITEMS)]
    all_agreed = all(checks)

    return_page = st.query_params.get("page", "main")

    if all_agreed:
        if kakao_configured():
            with st.container(key="auth_banner_kakao"):
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
    else:
        with st.container(key="auth_banner_kakao"):
            st.button(
                "카카오로 시작하기",
                use_container_width=True,
                disabled=True,
                key="auth_banner_kakao_locked",
            )
        st.caption("필수 동의를 모두 체크한 뒤 카카오로 시작할 수 있습니다.")

    with st.container(key="auth_banner_close"):
        if st.button("닫기", use_container_width=True, key="auth_banner_dismiss", type="secondary"):
            close_auth_banner()
            st.session_state.pop(AUTH_RESUME_FLAG, None)
            st.session_state.pop(AUTH_RESUME_DATA, None)
            st.rerun()

    if all_agreed:
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


@_dialog_decorator("적립금 충전")
def charge_dialog() -> None:
    member_id = current_member_id()
    if not member_id:
        return

    balance = get_balance(member_id)
    st.markdown(f"현재 잔액 **{balance:,}P**")
    amount = st.radio(
        "충전 금액",
        CHARGE_AMOUNTS,
        format_func=lambda x: f"{x:,}P",
        horizontal=True,
    )

    if pg_configured():
        st.info("PG 결제창 연동은 계약 후 활성화됩니다. (카드정보는 서버에 저장하지 않습니다.)")
        st.link_button(
            "결제창 열기 (준비중)",
            "#",
            disabled=True,
            use_container_width=True,
        )
    else:
        st.caption("PG 미연동 · 테스트는 Mock 결제를 이용하세요.")
        if st.button("Mock 결제 (테스트)", type="primary", use_container_width=True):
            ref = f"pg:mock:{member_id}:{uuid.uuid4().hex[:10]}"
            if charge_points(member_id, int(amount), ref):
                st.session_state.wallet_toast = f"{int(amount):,}P 충전 완료"
                st.rerun()
            st.error("충전에 실패했습니다.")


@_dialog_decorator("적립금 이용 안내")
def points_notice_dialog(
    service: str,
    *,
    game_count: int = 5,
    quantity: int = 5,
) -> str | None:
    """Returns 'confirm' | 'cancel' | None (closed)."""
    member_id = current_member_id()
    balance = get_balance(member_id) if member_id else 0

    if not member_id:
        return "cancel"

    if service == "thunder":
        st.markdown(format_thunder_points_notice(game_count, balance))
        cost = calc_thunder_cost(game_count)
    elif service == "auto":
        st.markdown(format_auto_points_notice(quantity, balance))
        cost = calc_auto_cost(quantity)
    elif service == "advanced":
        free_ok = ADVANCED_FILTER_FIRST_SUB_FREE and eligible_free_advanced_sub(member_id)
        active = has_active_subscription(member_id)
        st.markdown(format_advanced_points_notice(has_free_sub=free_ok and not active, balance=balance))
        cost = 0 if (free_ok or active) else 15000
    else:
        st.error("알 수 없는 서비스")
        return "cancel"

    if cost > 0 and balance < cost:
        st.error(f"적립금이 부족합니다. (필요 {cost:,}P / 보유 {balance:,}P)")
        return "cancel"

    c1, c2 = st.columns(2)
    with c1:
        if st.button("취소", use_container_width=True):
            return "cancel"
    with c2:
        if st.button("확인 후 진행", type="primary", use_container_width=True):
            return "confirm"
    return None


def render_wallet_bar() -> int | None:
    """로그인 시에만 상단 잔액 바. 미로그인 시 배너는 인증 필요 클릭 때만."""
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
        if _dev_mock_enabled():
            with st.expander("개발용 테스트 로그인", expanded=False):
                if st.button(
                    f"테스트 로그인 (ID: {TEST_USER_ID})",
                    key="zp_test_login_btn",
                    use_container_width=True,
                ):
                    user, is_new = login_test_user(TEST_USER_ID)
                    st.session_state.zp_user_id = user["user_id"]
                    st.session_state.zp_point_balance = user["point_balance"]
                    st.session_state.zp_is_premium = user["is_premium"]
                    if is_new:
                        st.session_state.wallet_toast = "테스트 가입 완료! 5,000점 지급"
                    st.rerun()
        return None

    st.markdown(wallet_bar_button_css(), unsafe_allow_html=True)
    col_a, col_b = st.columns([1.2, 1])
    with col_a:
        if zp_uid:
            bal = int(st.session_state.get("zp_point_balance", 0))
            tag = zp_uid if len(zp_uid) <= 16 else zp_uid[:12] + "…"
            st.markdown(f"**현재 보유 적립금: {bal:,}점** · ID `{tag}`")
        else:
            bal = get_balance(member_id)
            tag = st.session_state.get("oauth_hash_display", "ID")
            st.markdown(f"**적립금 {bal:,}P** · ID `{tag}` · v{NOTICE_VERSION}")
    with col_b:
        if zp_uid:
            if st.button("로그아웃", key="zp_logout_btn", use_container_width=True, type="secondary"):
                from user_scope import clear_user_session

                for key in ("zp_user_id", "zp_point_balance", "zp_is_premium"):
                    st.session_state.pop(key, None)
                clear_user_session()
                st.rerun()
        else:
            bc1, bc2 = st.columns(2)
            with bc1:
                if st.button("충전", key="wallet_charge_btn", use_container_width=True, type="secondary"):
                    charge_dialog()
            with bc2:
                if st.button("로그아웃", key="wallet_logout_btn", use_container_width=True, type="secondary"):
                    logout()
                    st.rerun()
    return member_id


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
    if service == "advanced":
        if has_active_subscription(member_id):
            return True
        if ADVANCED_FILTER_FIRST_SUB_FREE and eligible_free_advanced_sub(member_id):
            return activate_free_advanced_sub(member_id)
        cost = 15000
        reason = "advanced:monthly"
        return deduct_points(member_id, cost, reason, ref_id)

    if service == "thunder":
        cost = calc_thunder_cost(game_count)
        reason = f"thunder:{game_count}games"
    elif service == "auto":
        cost = calc_auto_cost(quantity)
        reason = f"auto:{quantity}qty"
    else:
        return False

    return deduct_points(member_id, cost, reason, ref_id)
