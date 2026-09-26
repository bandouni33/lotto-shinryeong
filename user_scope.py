"""사용자별 데이터 스코프 — 생일·필터·세션·파일 경로 공통 식별."""

from __future__ import annotations

import re
import urllib.parse
import streamlit as st

import dialog_registry

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
        "thunder_purchase_error",
        "tarot_purchase_error",
        "thunder_pending_ref",
        "auto_purchase_error",
        "auto_purchase_notice",
        "my_info_dialog_open",
        # 2026-09-27(계정 삭제): 탈퇴 확인 체크박스 — 로그아웃 뒤에도 True로 남으면
        # 다음 로그인에서 확인 없이 [탈퇴 실행]이 눌린다(되돌릴 수 없는 작업이라
        # 매번 다시 확인하게 한다). 다이얼로그 플래그 자체는 dialog_registry에서 파생된다.
        "delete_account_agree",
    }
)

# 2026-09-26: 다이얼로그 재개 플래그(+재개 데이터 키)는 dialog_registry가 기준점이다 —
# 새 창을 추가하면 이 손목록을 고치지 않아도 로그아웃 시 함께 정리된다(묵은 플래그가
# 남아 다음 로그인에 엉뚱한 창이 열리는 사고 방지).
_LOGOUT_EXACT_KEYS = _LOGOUT_EXACT_KEYS | dialog_registry.logout_keys()

_LOGOUT_PREFIXES = (
    "editing_",
    "elabel_",
    "emmdd_",
    "label_",
    "mmdd_",
    "auto_purchase_history_",
    "auto_purchase_seq_",
    "hedge_",
    "tarot_",
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

    2026-09-19(아스트라 진단 — "반전/겹침"의 실제 정체): 위와 똑같은 이유로 gid만
    챙기고 native=1은 안 실어보내고 있었다 — constants/streamlit.ts의 getStreamlitPageUrl()은
    앱이 웹뷰를 최초로 띄울 때만 native=1을 붙이는데, 이 함수로 만든 내부이동 링크(예:
    번개조합→행운수관리)는 실제 <a href> 전체 새로고침이라 그 최초 주소값이 안 이어지고
    사라진다. wallet_ui.py의 로그인 배너는 이 native 파라미터 하나로 "앱 전용 버튼"과
    "일반 웹 링크(항상 새 탭으로 열림 — Streamlit 자체 사양)"를 가른다 — native가 없으면
    앱 안에서도 웹 분기로 떨어져, 로그인 안내창이 앱 웹뷰가 아니라 기기 기본 브라우저에서
    열려버린 것이 "반전/두 개 화면"으로 보인 정체였다(웹뷰에 새 창을 앱 안에 가두는
    처리가 없어 그대로 외부로 샌다). gid와 동일하게, 지금 요청에 native=1이 있으면
    그대로 다음 내부이동 링크에도 이어서 실어보낸다.
    """
    params: dict[str, str] = {"page": page, GUEST_ID_QUERY_KEY: get_or_create_guest_id()}
    native = st.query_params.get("native")
    if native:
        params["native"] = native
    params.update(extra_params)
    query = urllib.parse.urlencode(params)
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
        return query_gid
    if st.session_state.get("_guest_id"):
        return st.session_state["_guest_id"]
    cookie_val = st.context.cookies.get(GUEST_ID_COOKIE_KEY)
    if cookie_val:
        st.session_state["_guest_id"] = cookie_val
        st.session_state["_guest_id_confirmed"] = True
        return cookie_val
    import uuid

    new_id = uuid.uuid4().hex
    st.session_state["_guest_id"] = new_id
    st.session_state["_guest_id_confirmed"] = False
    return new_id


def history_guest_ids() -> list[str]:
    """구매/저장 내역을 조회할 때 써야 하는 guest_id 목록 — 현재 guest_id + (로그인
    상태면) 이 회원에 묶인 적 있는 모든 guest_id. 2026-09-10: guest_id churn으로
    내역이 여러 id에 흩어져도 로그인 상태면 전부 합쳐 보여주기 위함. 현재 id를
    맨 앞에 두고 중복 제거."""
    current = get_or_create_guest_id()
    ids = [current]
    mid = current_member_id()
    if mid:
        try:
            from wallet_db import get_guest_ids_for_member

            # 최근 연결된 것부터 최대 15개까지만 — 구매/저장 내역은 어차피 최근
            # 2회차만 보관되므로(cleanup_old_*), 그보다 오래된 guest_id를 조회해봐야
            # 데이터가 없다. 회원당 guest_id가 수십 개까지 쌓일 수 있어(churn)
            # 상한 없이 다 조회하면 렌더마다 수십 번 DB 조회가 발생한다.
            for gid in get_guest_ids_for_member(mid)[:15]:
                if gid and gid not in ids:
                    ids.append(gid)
        except Exception:
            pass
    return ids


# 2026-09-08에 붙였던 임시 진단 코드(_log_guest_id_branch — guest_id 분기별
# DB 로깅)는 2026-09-15 원인 규명 완료 후 제거했다. get_or_create_guest_id()가
# 호출될 때마다(메인화면 메뉴 링크 6개 렌더 등 렌더 1회에 여러 번) 원격 Turso에
# CREATE TABLE + INSERT 왕복이 걸려, 메인 페이지 로드 시 19~22회의 불필요한
# 원격 DB 왕복이 쌓이는 게 느려짐의 주 원인 중 하나로 확인됐다. wallet_db.py의
# init_wallet_tables()가 이미 겪은 것과 같은 종류의 문제(멱등 CREATE TABLE도
# 매 렌더 반복 호출되면 원격 왕복이 쌓인다)인데, 이 진단 코드만 그 가드
# 패턴(_WALLET_TABLES_READY류)을 안 따르고 있었다.


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
