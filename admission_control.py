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

# 부하 테스트로 실측하기 전까지의 잠정 안전값. 커뮤니티에 보고된 Streamlit
# 단일 인스턴스 동시접속 한계(~100명대에서 먹통)보다 여유 있게 낮춰서, 실측
# 전까지는 "서버가 죽느니 조금 더 자주 막히는 쪽"으로 보수적으로 잡는다.
# 실제 배포 플랫폼이 정해지고 부하 테스트를 마치면 이 값을 그 결과로 교체한다.
MAX_CONCURRENT_SESSIONS = 70

# 이 시간(초) 안에 하트비트가 없으면 이미 나간 세션으로 간주해 집계에서 제외.
_HEARTBEAT_TTL_SECONDS = 60

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


def check_admission(cap: int = MAX_CONCURRENT_SESSIONS) -> None:
    """무거운 페이지 로직(pg.run() 등) 실행 직전에 호출한다.

    이미 입장을 허용받은 세션은 하트비트만 남기고 그대로 통과시키고,
    아직 입장 전인 신규 세션만 동시접속 수가 cap을 넘을 때 안내화면을
    띄우고 st.stop()으로 이후 로직 실행을 막는다.
    """
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
