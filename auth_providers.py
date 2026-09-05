"""간편인증 provider 통합 (카카오 / PASS / 금융인증서)."""

from __future__ import annotations

import os
import uuid
import urllib.parse

import requests
import streamlit as st

from legal_notices import NOTICE_VERSION
from wallet_db import SIGNUP_BONUS, grant_signup_bonus, init_wallet_tables, oauth_hash, record_consent

KAKAO_AUTH_URL = "https://kauth.kakao.com/oauth/authorize"
KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
KAKAO_USER_URL = "https://kapi.kakao.com/v2/user/me"


def _dev_mock_enabled() -> bool:
    return os.environ.get("LOTTO_DEV_MOCK_AUTH", "1").strip() not in ("0", "false", "False")


def kakao_configured() -> bool:
    return bool(os.environ.get("KAKAO_REST_API_KEY", "").strip())


def pass_configured() -> bool:
    return bool(os.environ.get("PASS_CLIENT_ID", "").strip())


def fincert_configured() -> bool:
    return bool(os.environ.get("FINCERT_CLIENT_ID", "").strip())


def _redirect_uri() -> str:
    return os.environ.get("KAKAO_REDIRECT_URI", "http://localhost:8501").strip()


def _encode_oauth_state(provider: str, return_page: str = "main", gid: str | None = None) -> str:
    page = (return_page or "main").strip() or "main"
    allowed = ("main", "thunder", "auto", "stats", "birthday", "advanced")
    if page not in allowed:
        page = "main"
    encoded = f"{provider}:{urllib.parse.quote(page, safe='')}"
    if gid:
        # 2026-09-05: 카카오 로그인이 앱 내장 웹뷰가 아니라 기기 기본 브라우저에서
        # 열리게 되면서(WebView OAuth 차단 대응) 콜백도 그 브라우저의 별도
        # Streamlit 세션에서 처리된다 — 그 세션엔 앱이 매 요청 실어 보내는
        # ?gid=...가 없어 get_or_create_guest_id()가 엉뚱한 새 guest_id를
        # 만들어버리고, 로그인이 그 새 guest_id에 연결돼 앱으로 돌아와도
        # 로그인 상태가 안 보이는 문제로 이어졌다. state에 원래 기기 gid를
        # 실어 보내 콜백 쪽에서 복원한다(handle_oauth_callback 참고).
        encoded += f":{urllib.parse.quote(gid, safe='')}"
    return encoded


def _decode_oauth_state(state: str | None) -> tuple[str, str, str | None]:
    raw = (state or "kakao").strip() or "kakao"
    parts = raw.split(":")
    provider = (parts[0] or "kakao").strip() or "kakao"
    page = "main"
    if len(parts) > 1 and parts[1]:
        page = urllib.parse.unquote(parts[1]).strip() or "main"
    gid = None
    if len(parts) > 2 and parts[2]:
        gid = urllib.parse.unquote(parts[2]).strip() or None
    return provider, page, gid


def get_kakao_authorize_url(return_page: str = "main") -> str:
    from user_scope import get_or_create_guest_id

    params = {
        "client_id": os.environ.get("KAKAO_REST_API_KEY", "").strip(),
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "state": _encode_oauth_state("kakao", return_page, get_or_create_guest_id()),
    }
    return f"{KAKAO_AUTH_URL}?{urllib.parse.urlencode(params)}"


def get_pass_authorize_url(return_page: str = "main") -> str | None:
    if not pass_configured():
        return None
    base = os.environ.get("PASS_AUTH_URL", "https://pass.example.com/oauth/authorize").strip()
    params = {
        "client_id": os.environ.get("PASS_CLIENT_ID", "").strip(),
        "redirect_uri": os.environ.get("PASS_REDIRECT_URI", _redirect_uri()).strip(),
        "response_type": "code",
        "state": _encode_oauth_state("pass", return_page),
    }
    return f"{base}?{urllib.parse.urlencode(params)}"


def get_fincert_authorize_url(return_page: str = "main") -> str | None:
    if not fincert_configured():
        return None
    base = os.environ.get("FINCERT_AUTH_URL", "https://fincert.example.com/oauth/authorize").strip()
    params = {
        "client_id": os.environ.get("FINCERT_CLIENT_ID", "").strip(),
        "redirect_uri": os.environ.get("FINCERT_REDIRECT_URI", _redirect_uri()).strip(),
        "response_type": "code",
        "state": _encode_oauth_state("fincert", return_page),
    }
    return f"{base}?{urllib.parse.urlencode(params)}"


def login_member(provider: str, provider_user_id: str) -> tuple[int, bool, bool]:
    from wallet_db import get_or_create_member

    init_wallet_tables()
    member_id, is_new = get_or_create_member(provider, provider_user_id)
    bonus = grant_signup_bonus(member_id) if is_new else False
    return member_id, is_new, bonus


def finalize_login(provider: str, provider_user_id: str) -> tuple[int, bool, bool]:
    member_id, is_new, bonus = login_member(provider, provider_user_id)
    if is_new:
        record_consent(member_id, NOTICE_VERSION)
    st.session_state.member_id = member_id
    st.session_state.oauth_provider = provider
    st.session_state.oauth_hash_display = oauth_hash(provider, provider_user_id)[:8] + "…"
    from user_scope import bind_identity_on_login, get_or_create_guest_id

    bind_identity_on_login(member_id)
    _link_guest_to_member_safe(get_or_create_guest_id(), member_id)
    if bonus:
        st.session_state.wallet_toast = f"간편인증 완료! 적립금 {SIGNUP_BONUS:,}P가 지급되었습니다."
    else:
        st.session_state.wallet_toast = "로그인되었습니다."
    return member_id, is_new, bonus


def mock_provider_login(provider: str) -> tuple[int, bool, bool]:
    fake_id = f"dev_{provider}_{uuid.uuid4().hex[:10]}"
    member_id, is_new, bonus = login_member(provider, fake_id)
    if is_new:
        record_consent(member_id, NOTICE_VERSION)
    st.session_state.member_id = member_id
    st.session_state.oauth_provider = provider
    st.session_state.oauth_hash_display = oauth_hash(provider, fake_id)[:8] + "…"
    from user_scope import bind_identity_on_login, get_or_create_guest_id

    bind_identity_on_login(member_id)
    _link_guest_to_member_safe(get_or_create_guest_id(), member_id)
    msg = f"{SIGNUP_BONUS:,}P 지급 완료!" if bonus else "로그인 완료"
    st.session_state.wallet_toast = f"{provider.upper()} {msg}"
    return member_id, is_new, bonus


def _link_guest_to_member_safe(guest_id: str, member_id: int) -> None:
    """guest_id(기기 식별자)와 회원을 연결 — 세션이 끊겨도 자동 재로그인시키기 위함
    (restore_member_from_guest 참고). 연결 자체가 로그인 성공을 막아선 안 되니
    실패해도 조용히 넘어간다."""
    try:
        from wallet_db import link_guest_to_member

        link_guest_to_member(guest_id, member_id)
    except Exception:
        pass


def restore_member_from_guest() -> int | None:
    """세션이 끊겼다 재연결됐을 때(백그라운드 전환·네트워크 끊김 등) member_id가
    사라져 매번 간편인증 배너가 다시 뜨는 문제 — 이 기기(guest_id)가 이미 로그인한
    적 있는 회원과 연결돼 있으면 조용히 다시 로그인시킨다(인증 절차 없이)."""
    if st.session_state.get("member_id"):
        return None
    from user_scope import bind_identity_on_login, get_or_create_guest_id
    from wallet_db import get_member_for_guest, init_wallet_tables

    init_wallet_tables()
    guest_id = get_or_create_guest_id()
    member_id = get_member_for_guest(guest_id)
    if not member_id:
        return None
    bind_identity_on_login(member_id)
    return member_id


def mock_kakao_login() -> tuple[int, bool, bool]:
    return mock_provider_login("kakao")


def _exchange_kakao_code(code: str) -> tuple[str | None, str | None]:
    data = {
        "grant_type": "authorization_code",
        "client_id": os.environ.get("KAKAO_REST_API_KEY", "").strip(),
        "redirect_uri": _redirect_uri(),
        "code": code,
    }
    secret = os.environ.get("KAKAO_CLIENT_SECRET", "").strip()
    if secret:
        data["client_secret"] = secret
    try:
        resp = requests.post(KAKAO_TOKEN_URL, data=data, timeout=15)
    except requests.RequestException as exc:
        return None, f"카카오 토큰 요청 실패: {exc}"
    if resp.status_code != 200:
        detail = resp.text[:200] if resp.text else resp.reason
        return None, f"카카오 토큰 발급 오류 ({resp.status_code}): {detail}"
    token = resp.json().get("access_token")
    if not token:
        return None, "카카오 access_token이 없습니다."
    try:
        user_resp = requests.get(
            KAKAO_USER_URL,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
    except requests.RequestException as exc:
        return None, f"카카오 사용자 조회 실패: {exc}"
    if user_resp.status_code != 200:
        detail = user_resp.text[:200] if user_resp.text else user_resp.reason
        return None, f"카카오 사용자 조회 오류 ({user_resp.status_code}): {detail}"
    uid = str(user_resp.json().get("id", "")) or None
    if not uid:
        return None, "카카오 사용자 ID를 받지 못했습니다."
    return uid, None


def _exchange_pass_code(code: str) -> str | None:
    if not pass_configured():
        return None
    token_url = os.environ.get("PASS_TOKEN_URL", "").strip()
    if not token_url:
        return f"pass_{code[:16]}"
    return f"pass_{code[:16]}"


def _exchange_fincert_code(code: str) -> str | None:
    if not fincert_configured():
        return None
    return f"fincert_{code[:16]}"


def handle_oauth_callback() -> bool:
    init_wallet_tables()
    code = st.query_params.get("code")
    if not code:
        return False

    provider_key, return_page, gid = _decode_oauth_state(st.query_params.get("state"))
    if gid:
        # 콜백이 앱의 gid 없이 열린 세션(기기 기본 브라우저)이어도, state에
        # 실어 보낸 원래 기기 gid를 여기서 복원해야 finalize_login()이 부르는
        # get_or_create_guest_id()가 엉뚱한 새 guest_id를 만들지 않는다.
        from user_scope import GUEST_ID_QUERY_KEY

        st.query_params[GUEST_ID_QUERY_KEY] = gid
    provider_uid: str | None = None
    provider = "kakao"
    error: str | None = None

    if provider_key == "pass" and pass_configured():
        provider = "pass"
        provider_uid = _exchange_pass_code(code)
    elif provider_key == "fincert" and fincert_configured():
        provider = "fincert"
        provider_uid = _exchange_fincert_code(code)
    elif provider_key == "kakao" and kakao_configured():
        provider_uid, error = _exchange_kakao_code(code)
    else:
        st.error("간편인증 설정이 올바르지 않습니다. 관리자에게 문의해 주세요.")
        for key in ("code", "state", "error", "error_description"):
            if key in st.query_params:
                del st.query_params[key]
        return False

    if not provider_uid:
        st.error(error or "간편인증에 실패했습니다. 다시 시도해 주세요.")
        for key in ("code", "state", "error", "error_description"):
            if key in st.query_params:
                del st.query_params[key]
        return False

    finalize_login(provider, provider_uid)
    st.query_params["page"] = return_page
    for key in ("code", "state", "error", "error_description"):
        if key in st.query_params:
            del st.query_params[key]

    # 2026-09-05: 카카오 로그인이 기기 기본 브라우저에서 끝나면(native=1),
    # 자동으로 앱에 복귀시키는 걸 여러 방식으로 시도했지만(Custom Tab 감지,
    # <meta refresh> 등) 실기기(삼성)에서 전부 막혀 실패했다 — 자동 복귀는
    # 포기하고, 로그인은 여기서 정상 완료(위에서 이미 끝남 + 올바른 gid 연결)
    # 시킨 뒤 그냥 평소와 같은 로그인 완료 화면을 보여준다. 사용자가 직접
    # 앱으로 돌아오면(뒤로가기·앱 전환 후 새로고침 버튼) restore_member_
    # from_guest()가 이 gid 연결을 보고 조용히 로그인 상태를 이어준다.
    return True


def logout() -> None:
    from user_scope import clear_user_session, get_or_create_guest_id
    from wallet_db import unlink_guest_from_member

    # session_state만 비우면 다음 페이지 이동 때 restore_member_from_guest()가
    # guest_member_links를 보고 조용히 다시 로그인시켜버린다 — 그 연결 자체도
    # 끊어야 로그아웃이 실제로 유지된다.
    unlink_guest_from_member(get_or_create_guest_id())
    clear_user_session()


def current_member_id() -> int | None:
    mid = st.session_state.get("member_id")
    return int(mid) if mid else None
