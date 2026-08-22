"""동시접속자가 급증할 때 서버가 죽는 대신, 신규 유입만 안내화면으로 잠시
막아두는 경량 입장 제한 장치.

Cloudflare Waiting Room 같은 상용 가상대기실은 Enterprise 전용 계약이 필요해
지금 체급(테스터 16명 → 목표 500~1,000명)엔 안 맞아서, 같은 개념(폭증 시
서버가 죽는 대신 신규 유입만 잠깐 막기)을 앱 안에 직접 구현했다.

Streamlit 세션 매니저 등 내부 비공개 API에는 기대지 않고, 공식 API인
st.session_state / st.cache_resource만 써서 버전이 올라가도 안 깨지게 만들었다.
동시접속 수는 "최근 몇 초 안에 화면이 다시 그려진(=하트비트를 보낸) 세션 수"로
근사한다 — 페이지를 열어만 두고 조작을 안 하는 세션은 서버에 실제 부하를
주지 않으니, 이 방식이 "지금 서버가 실제로 처리 중인 부하"에 더 가까운 지표다.

이미 입장을 허용받은 세션은 그 뒤로 동시접속 수가 상한을 넘어도 절대 다시
막히지 않는다 — 결제/적립 처리 중이던 사용자가 갑자기 튕겨나가는 게 서버
다운보다 더 나쁜 경험이자 분쟁 소지이기 때문이다.
"""

from __future__ import annotations

import threading
import time
import uuid

import streamlit as st

# 2026-08-22: Streamlit의 웹소켓 기반 구조상 정식 부하 테스트 도구(Locust 등)를
# 붙이기 어려워 실측을 보류하고, 기존 증거로 보수적으로 확정한 값이다.
#   - 커뮤니티에 보고된, 비슷하게 소박한 사양의 Streamlit 단일 인스턴스가
#     동시접속 ~100명대에서 먹통된 사례가 유일한 정량적 기준선.
#   - 지금 실제 운영 중인 Streamlit Community Cloud는 앱당 RAM 1GB 보장(최대
#     3GB)이라는 소박한 사양인데도 현재 테스터 규모에서 문제없이 동작 중.
#   - 최종 호스팅 플랫폼이 아직 미정이라 더 강력한 사양을 가정할 근거가 없음.
#   - 캐싱 개선으로 요청당 부담은 줄었지만 정확한 배율은 실측 전이라 반영 안 함.
# 위 유일한 정량 기준선(~100명)보다 확실히(약 40%) 낮춰 60명으로 잡는다.
# 서버가 죽어서 결제/적립 분쟁이 생기는 것보다, 신규 유입을 조금 더 자주
# 막는 쪽이 안전하다는 판단. 운영자 대시보드에서 실제 트래픽을 보며 이 값을
# 코드 배포 없이 바로 조정할 수 있다 — 이 값은 그게 아직 저장된 적 없을
# 때만 쓰이는 최초 기본값이다.
DEFAULT_MAX_CONCURRENT_SESSIONS = 60

# 이 시간(초) 안에 하트비트가 없으면 이미 나간 세션으로 간주해 집계에서 제외.
_HEARTBEAT_TTL_SECONDS = 60

# 운영자가 저장한 상한값을 매 렌더마다 DB에서 새로 읽으면 그 조회 자체가
# 부담이 되니(입장 제한 장치가 오히려 병목이 되면 본말전도), 짧은 TTL로
# 캐싱해서 값이 바뀌어도 최대 이 시간 안에는 반영되게 한다.
_SETTING_CACHE_TTL_SECONDS = 30


@st.cache_data(ttl=_SETTING_CACHE_TTL_SECONDS, show_spinner=False)
def _resolve_cap() -> int:
    # 이 입장 제한 장치는 "서버가 죽는 걸 막기 위한 안전장치"인데, 그 장치
    # 자체가(예: DB 일시 장애, 배포 환경 차이로 인한 import 실패 등) 앱
    # 전체를 죽여버리면 본말전도다(2026-08-23 실제로 이렇게 앱이 통째로
    # 다운된 사고가 있었음) — 무슨 일이 있어도 기본값으로 조용히 대체한다.
    try:
        from app_settings import get_max_concurrent_sessions

        return get_max_concurrent_sessions(default=DEFAULT_MAX_CONCURRENT_SESSIONS)
    except Exception:
        return DEFAULT_MAX_CONCURRENT_SESSIONS

_SESSION_ID_KEY = "_admission_sid"
_ADMITTED_KEY = "_admission_ok"


@st.cache_resource(show_spinner=False)
def _active_sessions_store():
    """{세션ID: 마지막 하트비트 시각} — 프로세스 전체가 공유하는 저장소."""
    return {}, threading.Lock()


def _heartbeat_and_count(session_id: str) -> int:
    """이 세션이 지금 활동 중임을 기록하고, 최근 활동 중인 전체 세션 수를 반환."""
    store, lock = _active_sessions_store()
    now = time.time()
    with lock:
        store[session_id] = now
        stale_ids = [sid for sid, ts in store.items() if now - ts > _HEARTBEAT_TTL_SECONDS]
        for sid in stale_ids:
            del store[sid]
        return len(store)


def _render_overload_screen() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stAppViewContainer"] .block-container { padding-top: 8vh !important; }
        .admission-overload-wrap {
            max-width: 420px;
            margin: 0 auto;
            text-align: center;
            padding: 32px 24px;
            border-radius: 16px;
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(212,175,55,0.35);
        }
        .admission-overload-emoji { font-size: 44px; margin-bottom: 12px; }
        .admission-overload-title {
            font-size: 19px; font-weight: 700; color: #f5e6b8; margin-bottom: 10px;
        }
        .admission-overload-desc {
            font-size: 14px; line-height: 1.6; color: #d8d8d8;
        }
        </style>
        <div class="admission-overload-wrap">
            <div class="admission-overload-emoji">🙏</div>
            <div class="admission-overload-title">이용자 폭증으로 잠시 대기 중입니다</div>
            <div class="admission-overload-desc">
                지금 많은 분들이 함께 접속해 있어요.<br>
                잠시 후 새로고침하면 다시 이용하실 수 있습니다.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def check_admission(cap: int | None = None) -> None:
    """무거운 페이지 로직(pg.run() 등) 실행 직전에 호출한다.

    이미 입장을 허용받은 세션은 하트비트만 남기고 그대로 통과시키고,
    아직 입장 전인 신규 세션만 동시접속 수가 cap을 넘을 때 안내화면을
    띄우고 st.stop()으로 이후 로직 실행을 막는다.

    cap을 안 넘기면 운영자 대시보드에서 저장한 값(없으면 기본값)을 쓴다.
    """
    if cap is None:
        cap = _resolve_cap()

    if _SESSION_ID_KEY not in st.session_state:
        st.session_state[_SESSION_ID_KEY] = str(uuid.uuid4())
    session_id = st.session_state[_SESSION_ID_KEY]

    active_count = _heartbeat_and_count(session_id)

    if st.session_state.get(_ADMITTED_KEY, False):
        return

    if active_count > cap:
        _render_overload_screen()
        st.stop()

    st.session_state[_ADMITTED_KEY] = True


def get_live_status() -> tuple[int, int]:
    """(현재 활동 중인 세션 수, 적용 중인 상한값) — 운영자 대시보드 표시용.
    하트비트를 새로 남기지 않고(=이 조회 자체가 세션으로 집계되지 않게) 만료된
    것만 정리한 뒤 현재 값을 그대로 읽는다."""
    store, lock = _active_sessions_store()
    now = time.time()
    with lock:
        stale_ids = [sid for sid, ts in store.items() if now - ts > _HEARTBEAT_TTL_SECONDS]
        for sid in stale_ids:
            del store[sid]
        count = len(store)
    return count, _resolve_cap()
