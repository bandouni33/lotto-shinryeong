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


def _encode_oauth_state(provider: str, return_page: str = "main") -> str:
    page = (return_page or "main").strip() or "main"
    allowed = ("main", "thunder", "auto", "stats", "birthday", "advanced")
    if page not in allowed:
        page = "main"
    # 2026-09-09 수정: 카카오 로그인 버튼을 누른 시점의 guest_id를 state에 실어서
    # 콜백 때 복원한다 — 예전엔 안 실었는데, 카카오의 redirect_uri는 고정 URL이라
    # 우리 쪽 ?gid= 파라미터를 못 실어보내고, 그러면 로그인 완료 직후 이 콜백
    # 요청 자체가 "gid 없는 새 요청"이 돼서 방금까지 쓰던 guest_id와 다른 새
    # guest_id가 발급되고, 로그인이 그 새 guest_id에만 연결돼버렸다. 그 뒤
    # 사용자가 원래 쓰던(주소창에 남아있던) guest_id로 다시 이동하면 로그인
    # 연결이 없는 것처럼 보여 "구매할 때마다 재인증창이 뜬다"는 신고로 이어짐 —
    # state에 담아 콜백에서 그대로 복원해 이 단절을 없앤다.
    from user_scope import get_or_create_guest_id

    guest_id = get_or_create_guest_id()
    return f"{provider}:{urllib.parse.quote(page, safe='')}:{urllib.parse.quote(guest_id, safe='')}"


def _decode_oauth_state(state: str | None) -> tuple[str, str, str | None]:
    raw = (state or "kakao").strip() or "kakao"
    parts = raw.split(":", 2)
    provider = (parts[0] or "kakao").strip() or "kakao" if parts else "kakao"
    page = urllib.parse.unquote(parts[1]).strip() if len(parts) > 1 and parts[1] else "main"
    guest_id = urllib.parse.unquote(parts[2]).strip() if len(parts) > 2 and parts[2] else None
    return provider, (page or "main"), (guest_id or None)


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
    적 있는 회원과 연결돼 있으면 조용히 다시 로그인시킨다(인증 절차 없이).

    2026-09-06: "앱을 3분 이상 백그라운드에 뒀다가 돌아오면 자동 로그아웃"을
    앱(클라이언트) 쪽에서 직접 감지하려던 시도(메모리 기록 → AsyncStorage
    기록 → 하트비트 → 웹뷰 캐시버스팅)가 실기기에서 네 번 연속 실패했다.
    뒤로가기 종료 시 AppState 이벤트 신뢰성, 안드로이드 프로세스 종료
    타이밍, 웹뷰 캐싱 등 클라이언트 쪽에 통제 못 하는 변수가 너무 많았기
    때문으로 보인다. 앱이 백그라운드에 있는 동안은 이 앱이 서버로 요청
    자체를 전혀 안 보낸다는 사실은 변하지 않으므로, "서버가 이 기기의
    요청을 마지막으로 받은 시각"만 기록해두면 클라이언트의 협조 없이도
    똑같은 정보를 훨씬 안정적으로 얻을 수 있다 — 이 함수는 이미 로그인된
    세션에서도(page.py가 매 렌더마다 호출하므로) 매번 idle 시간을 확인해서,
    3분 넘게 아무 요청도 없었다면 강제 로그아웃시킨다."""
    from user_scope import bind_identity_on_login, get_or_create_guest_id
    from wallet_db import (
        get_member_for_guest,
        guest_idle_seconds,
        init_wallet_tables,
        touch_guest_last_seen,
    )

    init_wallet_tables()
    guest_id = get_or_create_guest_id()

    # 2026-09-07: 서버 idle 로그아웃 정상 동작 확인 완료(2026-09-07 실기기
    # 백그라운드→재접속 테스트로 검증) — 검증 과정에서 원인 추적용으로 넣었던
    # 임시 진단 코드(예외를 last_seen_at에 기록)는 확인 완료 후 제거함.
    #
    # 2026-09-08 수정: 이 함수는 이미 로그인된 세션에서도 매 렌더(=구매
    # 버튼 클릭 등 모든 상호작용)마다 호출되는데, db_turso.py의 _guarded()는
    # Turso가 응답 없을 때 일부러 TimeoutError를 던지도록 설계돼 있고
    # (호출부가 잡아서 폴백하라는 의도 — db_turso.py 주석 참고), libsql_client
    # 자체도 간헐적으로 KeyError('result')를 던지는 게 이 세션에서만도 여러 번
    # 실측됐다. 여기서 이 예외를 안 잡고 있어서, Turso가 잠깐 느려지거나
    # 흔들릴 때마다 "구매할 때마다 로그인창이 뜬다"는 신고로 이어졌을 가능성이
    # 높다(idle 판정이 실패하면서 로그인 상태를 못 이어받음). 일시적 조회
    # 실패는 강제 로그아웃과는 전혀 다른 사안이므로 — 실패하면 그냥 이번
    # 렌더는 판정을 건너뛰고 기존 세션 상태를 그대로 둔다(안전한 쪽으로
    # fail-open; 진짜 3분 이상 idle이면 다음 정상 조회 때 어차피 잡힌다).
    try:
        idle_seconds = guest_idle_seconds(guest_id)
    except Exception:
        idle_seconds = None

    if idle_seconds is not None and idle_seconds >= 180:
        logout()
        return None

    if st.session_state.get("member_id"):
        try:
            touch_guest_last_seen(guest_id)
        except Exception:
            pass
        return None

    try:
        member_id = get_member_for_guest(guest_id)
    except Exception:
        # 이 조회가 실패하면 이미 연결된 회원인지 알 수 없다 — 로그인
        # 배너가 한 번 더 뜨는 게 최악의 경우이고(로그인 상태를 잃지는
        # 않음), 예외를 그대로 흘려서 페이지 자체가 죽는 것보단 안전하다.
        return None
    if not member_id:
        return None
    bind_identity_on_login(member_id)
    try:
        touch_guest_last_seen(guest_id)
    except Exception:
        pass
    return member_id


def mock_kakao_login() -> tuple[int, bool, bool]:
    return mock_provider_login("kakao")


def _fetch_kakao_uid_with_token(access_token: str) -> tuple[str | None, str | None]:
    """카카오 access_token으로 사용자 정보를 직접 조회 — REST API 코드교환
    (_exchange_kakao_code)과 네이티브 SDK 토큰(finalize_login_with_native_token)
    양쪽에서 공유하는 마지막 단계. 클라이언트가 보낸 토큰을 그대로 믿지 않고
    카카오 서버에 직접 물어봐서 확인하므로, 위조된 토큰/ID로는 통과할 수 없다."""
    try:
        user_resp = requests.get(
            KAKAO_USER_URL,
            headers={"Authorization": f"Bearer {access_token}"},
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
    return _fetch_kakao_uid_with_token(token)


def finalize_login_with_native_token(access_token: str) -> tuple[int, bool, bool] | None:
    """네이티브 앱(@react-native-seoul/kakao-login)이 카카오톡 앱/Custom Tab을
    통해 이미 발급받은 access_token으로 로그인을 완료한다. REST API 코드교환
    (kauth.kakao.com 리다이렉트) 자체를 안 거치므로 웹뷰 관련 문제가 애초에
    발생할 수 없다 — 앱이 보낸 토큰은 신뢰하지 않고 카카오 서버에 직접
    검증한다(_fetch_kakao_uid_with_token)."""
    uid, error = _fetch_kakao_uid_with_token(access_token)
    if not uid:
        return None
    return finalize_login("kakao", uid)


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
    from user_scope import GUEST_ID_QUERY_KEY

    init_wallet_tables()
    code = st.query_params.get("code")
    if not code:
        return False

    provider_key, return_page, saved_guest_id = _decode_oauth_state(st.query_params.get("state"))
    if saved_guest_id:
        # 카카오 redirect_uri가 고정 URL이라 이 콜백 요청 자체엔 원래 쓰던 gid가
        # 안 실려 있다 — state에서 복원해 session_state에 먼저 심어둔다. 이 다음에
        # 실행되는 get_or_create_guest_id() 호출들(_link_guest_to_member_safe 등)이
        # 전부 이 값을 그대로 쓰게 되어, 로그인 전 guest_id와 로그인이 연결되는
        # guest_id가 어긋나지 않는다.
        st.session_state["_guest_id"] = saved_guest_id
        st.session_state["_guest_id_confirmed"] = True
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
    if saved_guest_id:
        # 세션 안에서만이 아니라 주소창(다음 새로고침/공유 등)에도 원래 gid가
        # 그대로 남아있어야, 로그인 직후 첫 화면부터 계속 같은 guest_id로
        # 이어진다.
        st.query_params[GUEST_ID_QUERY_KEY] = saved_guest_id
    for key in ("code", "state", "error", "error_description"):
        if key in st.query_params:
            del st.query_params[key]
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
