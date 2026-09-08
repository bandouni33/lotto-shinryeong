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


# ────────────────────────────────────────────────
# 비로그인 게스트 식별자 (자동구매 내역, 타로 일일 제한 등 여러 페이지가 공유)
# ────────────────────────────────────────────────

GUEST_ID_COOKIE_KEY = "lotto_guest_id"
GUEST_ID_QUERY_KEY = "gid"


def get_or_create_guest_id() -> str:
    """비로그인(테스트 기간) 사용자를 앱을 껐다 켜도 같은 사람으로 알아보기 위한 식별자.

    네이티브 앱은 기기에 AsyncStorage로 영속시켜둔 id를 URL 쿼리 파라미터
    (?gid=...)로 매 요청마다 실어 보내므로 그걸 최우선으로 쓴다 — 안드로이드
    웹뷰는 화면 전환마다 새로 생성돼 쿠키 저장(document.cookie)이 디스크에
    flush되기 전에 유실되는 경우가 있었지만, 쿼리 파라미터는 그 문제가 없다.
    브라우저로 직접 접속하는 경우(쿼리 파라미터 없음)에는 기존 쿠키 방식으로
    폴백한다.
    """
    query_gid = st.query_params.get(GUEST_ID_QUERY_KEY)
    if query_gid:
        st.session_state["_guest_id"] = query_gid
        st.session_state["_guest_id_confirmed"] = True
        _log_guest_id_branch("query", query_gid)
        return query_gid
    if st.session_state.get("_guest_id"):
        _log_guest_id_branch("session_state", st.session_state["_guest_id"])
        return st.session_state["_guest_id"]
    cookie_val = st.context.cookies.get(GUEST_ID_COOKIE_KEY)
    if cookie_val:
        st.session_state["_guest_id"] = cookie_val
        st.session_state["_guest_id_confirmed"] = True
        _log_guest_id_branch("cookie", cookie_val)
        return cookie_val
    import uuid

    new_id = uuid.uuid4().hex
    st.session_state["_guest_id"] = new_id
    st.session_state["_guest_id_confirmed"] = False
    _log_guest_id_branch("NEW_MINTED", new_id)
    return new_id


def _log_guest_id_branch(branch: str, guest_id: str) -> None:
    """2026-09-08 임시 진단 코드 — guest_id가 화면 이동마다 계속 새로 발급되는
    문제의 원인을 찾기 위해, 매 호출마다 어느 분기를 탔는지(query/session_state
    /cookie/NEW_MINTED)와 그때 받은 native 파라미터·page 값을 안 보이게(화면
    노출 없이 DB로만) 기록한다. 원인 확인되면 바로 제거할 것 — 화면에는
    아무것도 안 보인다."""
    try:
        from wallet_db import _connect, _now_iso

        conn = _connect()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS _diag_guest_id_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                branch TEXT NOT NULL,
                guest_id TEXT NOT NULL,
                page TEXT,
                native TEXT,
                query_gid_raw TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO _diag_guest_id_log (branch, guest_id, page, native, query_gid_raw, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                branch,
                guest_id,
                st.query_params.get("page"),
                st.query_params.get("native"),
                st.query_params.get(GUEST_ID_QUERY_KEY),
                _now_iso(),
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def guest_id_cookie_sync_html(guest_id: str) -> str:
    """브라우저 폴백 경로에서만 의미 있는 쿠키 동기화 스크립트(components.html로 렌더)."""
    return f"""
    <script>
    (function() {{
        const doc = window.parent.document;
        doc.cookie = {GUEST_ID_COOKIE_KEY!r} + '=' + {guest_id!r} + '; max-age=31536000; path=/';
    }})();
    </script>
    """
