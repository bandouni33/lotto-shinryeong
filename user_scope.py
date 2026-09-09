"""사용자별 데이터 스코프 — 생일·필터·세션·파일 경로 공통 식별."""

from __future__ import annotations

import re
import urllib.parse
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


def internal_nav_href(page: str, **extra_params: str) -> str:
    """페이지 안의 `<a href="?page=...">` 내부이동 링크를 만들 때 항상 이 함수를 써야
    한다 — 2026-09-09 발견: 이 링크들이 gid를 안 실어보내서, 네이티브 앱(쿼리파라미터로
    guest_id 영속)과 달리 일반 브라우저 접속자는 화면을 옮길 때마다(자동구매↔번개조합
    등 real <a href> 네비게이션은 브라우저 완전 새로고침이라 st.session_state가 통째로
    사라진다) 쿠키 폴백에 기대야 했는데, 실측 결과 Streamlit Community Cloud의 중첩
    iframe 구조에서는 그 쿠키가 서버에 안정적으로 전달되지 않아 매번 새 guest_id가
    발급됐다 — 이게 "타로 무료뽑기 무한사용", "카카오 로그인 배너 반복", "저장내역이
    사라짐"의 공통 원인이었다(전부 guest_id가 안 이어지는 데서 비롯됨). 네이티브 앱과
    동일하게 모든 내부이동 링크에 현재 guest_id를 쿼리파라미터로 실어보내면, 브라우저
    접속자도 get_or_create_guest_id()의 최우선 분기(query)를 그대로 타게 돼 안정된다.
    """
    query = urllib.parse.urlencode({"page": page, GUEST_ID_QUERY_KEY: get_or_create_guest_id(), **extra_params})
    return f"?{query}"


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


LOCAL_STORAGE_GID_KEY = "lotto_guest_id_ls"


def local_storage_gid_recovery_html() -> str:
    """2026-09-09 추가 — 모바일 브라우저에서 Streamlit 웹소켓이 끊겼다 재연결되면
    (알려진 Streamlit 플랫폼 이슈: streamlit/streamlit#8901 등, 화면 잠금·네트워크
    전환 등으로 흔히 발생) 세션이 통째로 새로 만들어지면서 주소창의 ?gid=가 유실된
    채로 첫 스크립트가 실행되는 경우가 실측 로그로 확인됐다(약 15~40초 간격으로
    반복). 쿠키는 이 환경에서 서버가 안정적으로 못 읽는 것을 이미 확인했으므로,
    브라우저 localStorage에 별도로 게스트ID를 저장해두고 — 주소창에 gid가 없는
    채로 페이지가 뜨면 파이썬 로직이 뭘 하기 전에 즉시 localStorage 값을 붙여
    새로고침한다. 모든 페이지 렌더 맨 앞에서 항상 이 스크립트 하나만 심으면 되고,
    현재 guest_id를 파이썬에서 넘겨줄 필요 없이 URL 자체에서 읽어 판단한다.

    2026-09-09 수정: 처음 버전은 이 iframe(components.html) 안에서 곧바로
    top.location.replace(...)를 불렀는데, 실기기/브라우저 콘솔에서 "Unsafe
    attempt to initiate navigation ... sandboxed, but the flag of
    'allow-top-navigation' ... is not set" 에러로 조용히 막히는 걸 확인했다
    (Streamlit의 components.html iframe sandbox엔 allow-top-navigation이 없어
    최상위 창 네비게이션 자체가 금지됨). page_hedge.py의 QR스캔 트리거가 이미
    쓰던 우회법과 동일하게, 최상위 문서에 <script> 엘리먼트를 직접 심어 그
    스크립트가(iframe이 아니라) 최상위 문서 컨텍스트에서 실행되게 한다 —
    localStorage 읽기/쓰기 자체는 sandbox 제약이 없어 원래도 잘 됐지만,
    실제 새로고침(location.replace)만 이 방식으로 바꿔야 한다."""
    return f"""
    <script>
    (function() {{
        try {{
            var topDoc = window.top.document;
            var s = topDoc.createElement('script');
            s.textContent =
                "(function(){{" +
                "try{{" +
                "var url = new URL(location.href);" +
                "var urlGid = url.searchParams.get({GUEST_ID_QUERY_KEY!r});" +
                "var midOauth = !!url.searchParams.get('code');" +
                "var stored = null;" +
                "try{{ stored = localStorage.getItem({LOCAL_STORAGE_GID_KEY!r}); }}catch(e){{}}" +
                "if(urlGid){{" +
                "try{{ localStorage.setItem({LOCAL_STORAGE_GID_KEY!r}, urlGid); }}catch(e){{}}" +
                "}} else if(stored && !midOauth){{" +
                "url.searchParams.set({GUEST_ID_QUERY_KEY!r}, stored);" +
                "location.replace(url.pathname + url.search);" +
                "}}" +
                "}}catch(e){{}}" +
                "}})();";
            topDoc.head.appendChild(s);
            s.parentNode.removeChild(s);
        }} catch (e) {{}}
    }})();
    </script>
    """
