"""간편인증 provider 통합 (카카오 / PASS / 금융인증서)."""

from __future__ import annotations

import os
import uuid
import urllib.parse

import requests
import streamlit as st

from legal_notices import NOTICE_VERSION
from wallet_db import grant_signup_bonus, init_wallet_tables, oauth_hash, record_consent

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


def _encode_oauth_state(provider: str, return_page: str = "main") -> str:
    page = (return_page or "main").strip() or "main"
    allowed = ("main", "thunder", "auto", "stats", "birthday", "advanced")
    if page not in allowed:
        page = "main"
    return f"{provider}:{urllib.parse.quote(page, safe='')}"


def _decode_oauth_state(state: str | None) -> tuple[str, str]:
    raw = (state or "kakao").strip() or "kakao"
    if ":" in raw:
        provider, page = raw.split(":", 1)
        provider = (provider or "kakao").strip() or "kakao"
        page = urllib.parse.unquote(page).strip() or "main"
        return provider, page
    return raw, "main"


def get_kakao_authorize_url(return_page: str = "main") -> str:
    params = {
        "client_id": os.environ.get("KAKAO_REST_API_KEY", "").strip(),
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "state": _encode_oauth_state("kakao", return_page),
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
    if bonus:
        st.session_state.wallet_toast = "간편인증 완료! 적립금 5,000P가 지급되었습니다."
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
    msg = "5,000P 지급 완료!" if bonus else "로그인 완료"
    st.session_state.wallet_toast = f"{provider.upper()} {msg}"
    return member_id, is_new, bonus


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

    provider_key, return_page = _decode_oauth_state(st.query_params.get("state"))
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
    return True


def logout() -> None:
    for key in (
        "member_id",
        "oauth_provider",
        "oauth_hash_display",
        "wallet_toast",
    ):
        st.session_state.pop(key, None)


def current_member_id() -> int | None:
    mid = st.session_state.get("member_id")
    return int(mid) if mid else None
