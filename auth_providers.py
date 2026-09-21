"""간편인증 provider 통합 (카카오 / PASS / 금융인증서)."""

from __future__ import annotations

import os
import time
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


def _origin_from_headers(headers) -> str | None:
    """요청 헤더에서 "이 서버가 지금 어느 주소로 서비스되고 있는지"(origin)를 만든다.

    2026-09-21(카카오 로그인 버튼이 눌러도 먹통): 예전엔 KAKAO_REDIRECT_URI가
    설정돼 있지 않으면 무조건 "http://localhost:8501"을 카카오에 알려줬다 — 로컬
    개발 서버에서는 그게 맞지만, 배포된 서버가 이 값을 그대로 쓰면 카카오는 로그인을
    마치고 "접속한 기기 자신의 localhost"로 돌려보내려 해서 어떤 폰에서도 돌아올 수
    없다(버튼을 눌러도 로그인이 끝나지 않음). 환경변수가 비어 있을 때는 요청이 실제로
    들어온 호스트를 그대로 쓴다 — 로컬 개발은 Host가 localhost라 기존과 동일하다."""
    try:
        get = getattr(headers, "get", None)
        if get is None:
            return None
        host = (get("Host") or get("host") or "").strip()
        if not host:
            return None
        proto = (
            get("X-Forwarded-Proto") or get("x-forwarded-proto") or ""
        ).split(",")[0].strip().lower()
        if proto not in ("http", "https"):
            proto = "http" if host.split(":")[0] in ("localhost", "127.0.0.1", "0.0.0.0") else "https"
        return f"{proto}://{host}"
    except Exception:
        return None


def _request_origin() -> str | None:
    try:
        return _origin_from_headers(st.context.headers)
    except Exception:
        return None


def _redirect_uri() -> str:
    configured = os.environ.get("KAKAO_REDIRECT_URI", "").strip()
    if configured:
        return configured
    return _request_origin() or "http://localhost:8501"


def _current_ua_hash() -> str | None:
    """2026-09-19: guest_id 링크공유 계정탈취 대응 — 요청의 User-Agent를 해시해
    guest_member_links.ua_hash와 대조하는 데 쓴다. 원문 UA를 그대로 저장하지 않고
    oauth_hash()와 동일하게 해시만 남긴다."""
    import hashlib

    try:
        ua = st.context.headers.get("User-Agent")
    except Exception:
        ua = None
    if not ua:
        return None
    return hashlib.sha256(ua.strip().encode("utf-8")).hexdigest()


@st.cache_data(ttl=30, show_spinner=False)
def _ua_check_enabled() -> bool:
    """30초 TTL 캐시 — admission_control._resolve_cap()과 동일한 패턴(모듈 최상위
    함수를 직접 캐싱 — 렌더마다 새 함수 객체를 만들어 감싸지 않는다). 이 장치
    자체가(설정 조회 실패 등으로) 페이지를 죽이면 안 되므로 예외 시 기본 꺼짐으로
    안전하게 대체한다.

    2026-09-19(긴급 롤백): 배포 직후 모바일(WebView)에서 로그인창 반복 노출 +
    QR스캔 등 전 기능 먹통 신고 — User-Agent가 로그인 시점과 이후 요청에서
    서버에 다르게(또는 비어있게) 잡혀 매번 "링크공유 의심"으로 오판, 정상
    사용자까지 재인증 루프에 걸린 것으로 추정. 운영자 대시보드 토글을 거치지
    않고 즉시 전체 반영되도록 기본값 자체를 꺼짐(False)으로 되돌렸다 — 관리자가
    저장한 값이 있으면(get_auth_require_ua_match) 그 값이 여전히 우선한다.
    UA 대조 로직 자체(guest_id 링크공유 대응)를 더 안정적으로 고친 뒤 다시
    기본 켜짐으로 되돌릴 것(원인: WebView 요청 간 UA 헤더 불안정 여부 확인 필요)."""
    try:
        from app_settings import get_auth_require_ua_match

        return get_auth_require_ua_match(default=False)
    except Exception:
        return False


def _log_cookie_reachability_once() -> None:
    """2026-09-19: A안(토큰 분리) 설계를 위한 계측 — 브라우저 쿠키가 실제로
    서버(st.context.cookies)에 도달하는지 세션당 1회만 기록한다. 렌더마다 DB에
    쓰면 안 되므로(Turso 처리량 병목, db_turso.py 참고) session_state로 가드."""
    if st.session_state.get("_cookie_reach_logged"):
        return
    st.session_state["_cookie_reach_logged"] = True
    try:
        from user_scope import GUEST_ID_COOKIE_KEY

        reachable = bool(st.context.cookies.get(GUEST_ID_COOKIE_KEY))
        import security_log

        security_log.log_event("cookie_reachable", "1" if reachable else "0")
    except Exception:
        pass


def _encode_oauth_state(provider: str, return_page: str = "main") -> str:
    page = (return_page or "main").strip() or "main"
    # 2026-09-11(사용자 지시): "hedge"(안티·액땜/전체·개별리셋)와 "tarot"가
    # 허용 목록에서 빠져 있었다 — user_page.py가 실제로 라우팅하는 8개 페이지
    # (main/thunder/auto/stats/birthday/advanced/tarot/hedge) 중 이 둘만
    # 빠져서, 안티·액땜·타로 화면에서 로그인하면 조용히 "main"으로 되돌려져
    # "저장내역 누르고 로그인했더니 메인으로 가버린다"는 신고로 이어졌다.
    allowed = ("main", "thunder", "auto", "stats", "birthday", "advanced", "tarot", "hedge")
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
    base = f"{provider}:{urllib.parse.quote(page, safe='')}:{urllib.parse.quote(guest_id, safe='')}"
    # 2026-09-19(사용자 지시): "로그인하고 나면 원래 하려던 동작이 자동 재개되지 않는다"
    # 문제 — 카카오/패스/금융인증서 로그인은 외부로 나갔다 돌아오는 "완전한 새 페이지
    # 로드"라 session_state가 통째로 비워지고, 그 안에만 있던 재개 의도(AUTH_RESUME_FLAG/
    # DATA)가 사라졌다. 이 왕복에서 살아남는 유일한 값이 state 파라미터라 여기에 함께
    # 실어 보낸다. 앞 3필드 형식은 그대로 두고 뒤에 2필드만 덧붙이므로(선택 필드),
    # 예전 state가 돌아와도 _decode_oauth_state가 안전하게 해석한다.
    resume_name, resume_data_raw = _encode_resume_state()
    if not resume_name:
        return base
    return f"{base}:{resume_name}:{resume_data_raw}"


# 재개 의도를 state에 실을 때 데이터가 너무 길어지면(인증사가 state 길이를 제한할 수
# 있음) 데이터만 생략하고 의도 이름은 살린다 — 기능은 재개되고 세부값만 기본값이 된다.
_RESUME_STATE_DATA_MAX = 700

# 네이티브 앱(카카오 SDK) 로그인은 state를 거치지 않는다 — 서버에 잠깐 남겨두는 값의
# 키 접두사와 유효시간(15분). 로그인 완료 시 1회 소비된다.
_PENDING_RESUME_PREFIX = "pending_resume:"
_PENDING_RESUME_TTL_SEC = 900


def _encode_resume_state() -> tuple[str, str]:
    """현재 세션의 재개 의도(AUTH_RESUME_FLAG/DATA)를 state에 실을 문자열 2개로 만든다."""
    import json

    try:
        from wallet_ui import AUTH_RESUME_DATA, AUTH_RESUME_FLAG
    except Exception:
        return "", ""
    resume = str(st.session_state.get(AUTH_RESUME_FLAG) or "").strip()
    if not resume:
        return "", ""
    data = st.session_state.get(AUTH_RESUME_DATA) or {}
    packed = ""
    try:
        packed = urllib.parse.quote(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")), safe=""
        )
    except Exception:
        packed = ""
    if len(packed) > _RESUME_STATE_DATA_MAX:
        packed = ""
    return urllib.parse.quote(resume, safe=""), packed


def _restore_resume_from_state(resume: str | None, data_raw: str | None) -> None:
    """콜백으로 돌아온 state의 재개 의도를 session_state로 되살린다(로그인 성공 시에만
    호출된다 — 실패 경로에서 되살리면 로그인 안 된 채 재개가 돌아버린다)."""
    import json

    name = str(resume or "").strip()
    if not name:
        return
    from wallet_ui import AUTH_RESUME_DATA, AUTH_RESUME_FLAG

    st.session_state[AUTH_RESUME_FLAG] = name
    data = {}
    if data_raw:
        try:
            parsed = json.loads(data_raw)
            if isinstance(parsed, dict):
                data = parsed
        except Exception:
            data = {}
    if data:
        st.session_state[AUTH_RESUME_DATA] = data


def _remember_pending_resume(resume: str | None, data: dict | None) -> None:
    """네이티브 앱(카카오 SDK) 로그인 경로용 — state를 거치지 않으므로 이 기기(gid)가
    로그인 직전에 하려던 동작을 서버에 잠깐 남겨둔다. 실패해도 로그인 자체를 막지 않는다."""
    import json

    name = str(resume or "").strip()
    if not name:
        return
    from user_scope import get_or_create_guest_id

    try:
        from app_settings import init_settings_table, set_setting

        init_settings_table()
        set_setting(
            _PENDING_RESUME_PREFIX + get_or_create_guest_id(),
            json.dumps(
                {"resume": name, "data": data or {}, "ts": int(time.time())},
                ensure_ascii=False,
            ),
        )
    except Exception:
        pass


def _forget_pending_resume() -> None:
    """배너를 [닫기]로 취소했을 때 서버에 남긴 재개 의도도 버린다."""
    from user_scope import get_or_create_guest_id

    try:
        from app_settings import init_settings_table, set_setting

        init_settings_table()
        set_setting(_PENDING_RESUME_PREFIX + get_or_create_guest_id(), "")
    except Exception:
        pass


def _restore_pending_resume() -> bool:
    """로그인 완료 직전에 서버에 남겨둔 재개 의도를 1회 소비해 session_state로 옮긴다.
    모든 로그인 경로(카카오 리다이렉트·PASS·금융인증서·네이티브 SDK 토큰)가 이
    함수가 불리는 finalize_login()을 공통으로 지나가므로, 이 한 곳으로 전 기능에 적용된다."""
    import json

    from user_scope import get_or_create_guest_id

    key = _PENDING_RESUME_PREFIX + get_or_create_guest_id()
    try:
        from app_settings import get_setting, init_settings_table, set_setting

        init_settings_table()
        raw = get_setting(key, "")
    except Exception:
        return False
    if not raw:
        return False
    try:
        set_setting(key, "")  # 1회 소비 — 재로그인 때 같은 의도가 또 뜨지 않게
    except Exception:
        pass
    try:
        payload = json.loads(raw)
    except Exception:
        return False
    if not isinstance(payload, dict):
        return False
    ts = int(payload.get("ts") or 0)
    if ts and (time.time() - ts) > _PENDING_RESUME_TTL_SEC:
        return False
    name = str(payload.get("resume") or "").strip()
    if not name:
        return False
    from wallet_ui import AUTH_RESUME_DATA, AUTH_RESUME_FLAG

    st.session_state[AUTH_RESUME_FLAG] = name
    data = payload.get("data")
    if isinstance(data, dict) and data:
        st.session_state[AUTH_RESUME_DATA] = data
    return True


def _decode_oauth_state(
    state: str | None,
) -> tuple[str, str, str | None, str | None, str | None]:
    """state를 (provider, page, guest_id, resume, resume_data_raw)로 푼다.

    2026-09-19: 뒤 2필드(resume/resume_data)는 선택이다 — 이 필드를 안 싣고 나간
    예전 state(3필드)나 외부에서 임의로 넣은 state가 돌아와도 앞 3개는 그대로 해석된다."""
    raw = (state or "kakao").strip() or "kakao"
    parts = raw.split(":", 4)
    provider = (parts[0] or "kakao").strip() or "kakao" if parts else "kakao"
    page = urllib.parse.unquote(parts[1]).strip() if len(parts) > 1 and parts[1] else "main"
    guest_id = urllib.parse.unquote(parts[2]).strip() if len(parts) > 2 and parts[2] else None
    resume = urllib.parse.unquote(parts[3]).strip() if len(parts) > 3 and parts[3] else None
    data_raw = urllib.parse.unquote(parts[4]) if len(parts) > 4 and parts[4] else None
    return provider, (page or "main"), (guest_id or None), (resume or None), (data_raw or None)


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
    _link_guest_to_member_safe(get_or_create_guest_id(), member_id, _current_ua_hash())
    # 2026-09-19: 이 기기가 로그인 직전에 하려던 동작(재개 의도)을 되산다. 모든 로그인
    # 경로가 이 함수를 지나가므로 여기 한 곳으로 전 기능(자동구매·번개조합·QR·내정보 등)에
    # 적용되고, 세션 리셋을 거치는 네이티브 앱 경로까지 커버된다.
    _restore_pending_resume()
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
    _link_guest_to_member_safe(get_or_create_guest_id(), member_id, _current_ua_hash())
    msg = f"{SIGNUP_BONUS:,}P 지급 완료!" if bonus else "로그인 완료"
    st.session_state.wallet_toast = f"{provider.upper()} {msg}"
    return member_id, is_new, bonus


def _link_guest_to_member_safe(guest_id: str, member_id: int, ua_hash: str | None = None) -> None:
    """guest_id(기기 식별자)와 회원을 연결 — 세션이 끊겨도 자동 재로그인시키기 위함
    (restore_member_from_guest 참고). 연결 자체가 로그인 성공을 막아선 안 되니
    실패해도 조용히 넘어간다."""
    try:
        from wallet_db import link_guest_to_member

        link_guest_to_member(guest_id, member_id, ua_hash)
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
        get_member_and_ua_for_guest,
        guest_idle_seconds,
        init_wallet_tables,
        touch_guest_last_seen,
    )

    init_wallet_tables()
    guest_id = get_or_create_guest_id()
    _log_cookie_reachability_once()

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
        member_id, stored_ua_hash = get_member_and_ua_for_guest(guest_id)
    except Exception:
        # 이 조회가 실패하면 이미 연결된 회원인지 알 수 없다 — 로그인
        # 배너가 한 번 더 뜨는 게 최악의 경우이고(로그인 상태를 잃지는
        # 않음), 예외를 그대로 흘려서 페이지 자체가 죽는 것보단 안전하다.
        return None
    if not member_id:
        return None

    # 2026-09-20(진단 모드, 구름님 지시 — 아래 _ua_check_enabled() 차단 로직은
    # 전혀 건드리지 않는다): 지금 기본값이 꺼짐(2026-09-19 긴급 롤백)이라
    # 아래 차단 분기 자체가 안 타면서 UA 불일치 데이터가 전혀 안 쌓이고 있다.
    # 다시 켜기 전에 실제로 저장된 UA 해시와 지금 요청의 UA 해시가 얼마나/
    # 어떤 패턴으로 다른지 먼저 데이터로 확인하기 위해, 차단 여부와 완전히
    # 무관하게(항상) 불일치만 별도 이벤트명으로 기록한다. 완전히 새 변수명·
    # 이벤트명만 쓰고 기존 로직 변수는 하나도 참조하지 않으며, 이 블록이
    # 죽어도 로그인 자체에는 영향이 없도록 예외를 전부 삼킨다.
    try:
        _diag_ua_hash_now = _current_ua_hash()
        if stored_ua_hash and _diag_ua_hash_now and stored_ua_hash != _diag_ua_hash_now:
            import security_log

            security_log.log_event(
                "guest_ua_diag_mismatch",
                f"member_id={member_id} guest={str(guest_id)[:8]}… enforced={_ua_check_enabled()}",
            )
    except Exception:
        pass

    # 2026-09-19: guest_id 링크공유 계정탈취 대응(1단계) — guest_id는
    # internal_nav_href()를 통해 모든 내부이동 링크에 실려 노출되므로, 그 값
    # 하나만으로 인증 없이 로그인시키던 기존 동작은 링크 공유·주소창 복사로
    # 계정이 그대로 넘어가는 구멍이었다(아스트라 자문 확인). UA 해시를 함께
    # 대조해, 링크만 가진 다른 기기에서는 자동로그인을 막고 재인증 배너로
    # 유도한다. app_settings.get_auth_require_ua_match()로 코드 배포 없이
    # 즉시 끌 수 있는 킬스위치를 둔다.
    if _ua_check_enabled():
        current_ua_hash = _current_ua_hash()
        if not stored_ua_hash or not current_ua_hash or stored_ua_hash != current_ua_hash:
            # stored_ua_hash가 없는 경우(2026-09-19 이전 연결, 마이그레이션
            # 대상)는 침입이 아니라 "아직 새 방식으로 재인증 안 한 기존 사용자"이므로
            # 보안 알림으로 기록하지 않는다 — 실제 값이 서로 달라 불일치한 경우만
            # (링크 공유로 다른 기기가 시도했을 가능성) 침입 의심 기록에 남긴다.
            if stored_ua_hash and current_ua_hash and stored_ua_hash != current_ua_hash:
                try:
                    import security_log

                    security_log.log_event(
                        "guest_autologin_ua_mismatch",
                        f"member_id={member_id} guest={str(guest_id)[:8]}…",
                    )
                except Exception:
                    pass
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

    (
        provider_key,
        return_page,
        saved_guest_id,
        resume_from_state,
        resume_data_from_state,
    ) = _decode_oauth_state(st.query_params.get("state"))
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
        for key in ("code", "state", "error", "error_description"):
            if key in st.query_params:
                del st.query_params[key]
        # 카카오 인가코드(code)는 1회용이라, 이 콜백이 두 번 실행되면
        # (Streamlit 리런·뒤로가기·새로고침 등으로 흔함) 두 번째는 카카오가
        # KOE320("authorization code not found")로 거절한다. 예전엔 그 raw JSON
        # 응답을 화면 최상단에 빨간 st.error로 그대로 노출해서, 실제로는 첫
        # 콜백에서 로그인이 됐는데도 사용자에겐 "카카오 토큰 발급 오류 (400):
        # {...}"가 계속 보였다(사용자 신고 2026-09-10). 이미 로그인돼 있으면
        # 조용히 넘어가고, 아니면 원본 대신 짧은 토스트만 띄운다.
        if current_member_id():
            return False
        try:
            st.toast("로그인이 완료되지 않았어요. 다시 시도해 주세요.", icon="⚠️")
        except Exception:
            pass
        return False

    finalize_login(provider, provider_uid)
    # 2026-09-19: state에 실려 돌아온 재개 의도를 여기서(로그인 성공 시에만) 되산다 —
    # session_state는 이 콜백 요청에서 세로 비어 있기 때문.
    _restore_resume_from_state(resume_from_state, resume_data_from_state)
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


def toss_review_login(input_id: str, input_pw: str) -> tuple[int, bool, bool] | None:
    """토스페이먼츠 카드사 심사용 ID/PW 로그인 (2026-09-19 추가).

    토스 심사 메일에서 "소셜 로그인(카카오/구글 등) 테스트 계정은 사용 불가"라고
    명시해서, 심사팀이 직접 로그인해볼 수 있는 ID/PW 경로를 별도로 추가했다.
    고정된 provider_user_id("toss_review_fixed_account_001")를 써서 매번 같은
    테스트 전용 계정으로 로그인되며, 실제 카카오/PASS/금융인증 로그인 회원과는
    provider가 달라 완전히 분리된다(oauth_hash가 provider까지 포함해 해시하므로
    다른 계정으로 섞일 수 없음).

    2026-09-20(fail-closed, 구름님 지시): 하드코딩된 기본 자격증명(ID "toss" /
    PW "3333")을 완전히 제거했다 — 이 저장소가 Public이라 그 기본값이 사실상
    공개돼 있었고, 진입 URL(user_page.py의 ?page=toss_test_login)도 공개돼
    있어 사람이면 누구나 로그인할 수 있는 상태였다. 이제 TOSS_REVIEW_TEST_ID/
    TOSS_REVIEW_TEST_PW 두 환경변수가 모두 비어있지 않게 설정돼 있을 때만
    이 경로가 동작하고, 하나라도 없으면 입력값과 무관하게 무조건 거부한다.
    심사 기간엔 이 두 값을 Streamlit Cloud secrets에 넣어 그대로 쓰고, 심사가
    끝나면 그 두 값만 지우면 이 경로가 자동으로 닫힌다(코드 변경 불필요).
    """
    expected_id = os.environ.get("TOSS_REVIEW_TEST_ID", "").strip()
    expected_pw = os.environ.get("TOSS_REVIEW_TEST_PW", "").strip()
    if not expected_id or not expected_pw:
        return None
    if (input_id or "").strip() != expected_id or (input_pw or "").strip() != expected_pw:
        return None
    return finalize_login("toss_review", "toss_review_fixed_account_001")
