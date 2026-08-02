"""사용자별 데이터 스코프 — 생일·필터·세션·파일 경로 공통 식별."""

from __future__ import annotations

import re
import streamlit as st

GUEST_SCOPE = "guest_local"

# 로그아웃 시 제거할 session_state 키 (접두/정확 일치)
_LOGOUT_EXACT_KEYS = frozenset(
    {
        "member_id",
        "oauth_provider",
        "oauth_hash_display",
        "wallet_toast",
        "user_id",
        "user_email",
        "_user_scope_bound",
        "_premium_settings_hydrated",
        "_advanced_filter_hydrated",
        "saved_settings",
        "settings_saved",
        "af_advanced_filter_df",
        "af_mobile_notice_dismissed",
        "auto_purchase_history",
        "auto_purchase_seq",
        "auto_history_blink",
        "auto_show_points",
        "auto_pattern_toast",
        "thunder_approved",
        "open_thunder_dialog",
        "open_thunder_dialog_games",
        "thunder_auto_run",
        "thunder_reveal_version",
        "zp_user_id",
        "zp_point_balance",
        "zp_is_premium",
        "auth_banner_open",
        "auth_banner_reason",
        "auth_resume_flag",
        "auth_resume_data",
        "wallet_show_charge",
    }
)

_LOGOUT_PREFIXES = (
    "editing_",
    "elabel_",
    "emmdd_",
    "label_",
    "mmdd_",
    "auto_purchase_history_",
    "auto_purchase_seq_",
)


def current_member_id() -> int | None:
    mid = st.session_state.get("member_id")
    if mid is None:
        return None
    try:
        return int(mid)
    except (TypeError, ValueError):
        return None


def birthday_scope_for(member_id: int | None) -> str:
    return f"m_{member_id}" if member_id else GUEST_SCOPE


def data_dir_key_for(member_id: int | None) -> str:
    return f"member_{member_id}" if member_id else GUEST_SCOPE


def session_key_for(prefix: str, member_id: int | None) -> str:
    return f"{prefix}_{birthday_scope_for(member_id)}"


def current_birthday_scope() -> str:
    """SQLite userBirthdays.user_id 스코프."""
    return birthday_scope_for(current_member_id())


def current_data_dir_key() -> str:
    """data/users/{key}/ 디스크 스코프."""
    return data_dir_key_for(current_member_id())


def _sanitize_dir_key(key: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_@.-]", "_", str(key).strip())
    return cleaned or GUEST_SCOPE


def data_dir_name(scope_key: str | None = None) -> str:
    return _sanitize_dir_key(scope_key or current_data_dir_key())


def session_key(prefix: str) -> str:
    """세션 저장 키를 사용자 스코프별로 분리."""
    return f"{prefix}_{current_birthday_scope()}"


def bind_identity_on_login(member_id: int) -> None:
    """OAuth 로그인 직후 — 파일/DB 스코프를 회원 ID에 연결."""
    mid = int(member_id)
    st.session_state.member_id = mid
    st.session_state.user_id = f"m_{mid}"
    st.session_state.user_email = f"member_{mid}@app.local"
    st.session_state._user_scope_bound = mid
    _reset_hydration_flags()


def init_guest_scope() -> None:
    """비로그인 사용자 — guest 전용 스코프 고정."""
    if current_member_id():
        mid = current_member_id()
        if st.session_state.get("_user_scope_bound") != mid:
            bind_identity_on_login(mid)
        return
    st.session_state.user_id = GUEST_SCOPE
    st.session_state.user_email = GUEST_SCOPE
    st.session_state.pop("_user_scope_bound", None)


def clear_user_session() -> None:
    """로그아웃·계정 전환 시 사용자 잔여 session_state 제거."""
    to_delete: list[str] = []
    for key in st.session_state.keys():
        if key in _LOGOUT_EXACT_KEYS:
            to_delete.append(key)
            continue
        if any(key.startswith(p) for p in _LOGOUT_PREFIXES):
            to_delete.append(key)
    for key in to_delete:
        st.session_state.pop(key, None)
    init_guest_scope()


def _reset_hydration_flags() -> None:
    for key in (
        "_premium_settings_hydrated",
        "_advanced_filter_hydrated",
        "saved_settings",
        "settings_saved",
        "af_advanced_filter_df",
    ):
        st.session_state.pop(key, None)


def thunder_reveal_storage_suffix() -> str:
    """iframe localStorage 키 접미사 (브라우저 프로필 내 사용자 구분)."""
    return current_birthday_scope()
