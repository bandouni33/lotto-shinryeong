"""지갑 UI — 로그인·적립금 안내 dialog."""

from __future__ import annotations

import html
import uuid

import streamlit as st
import streamlit.components.v1 as components

from auth_providers import (
    _dev_mock_enabled,
    current_member_id,
    get_kakao_authorize_url,
    kakao_configured,
    logout,
    mock_kakao_login,
)
from legal_notices import (
    AUTH_CONSENT_ITEMS,
    NOTICE_VERSION,
    PRICING,
    format_advanced_points_notice,
    format_auto_points_notice,
    format_hedge_points_notice,
    format_tarot_points_notice,
    format_thunder_points_notice,
    ADVANCED_FILTER_FIRST_SUB_FREE,
)
from wallet_db import (
    ADVANCED_3MONTH_COST,
    ADVANCED_3MONTH_DAYS,
    ADVANCED_MONTHLY_COST,
    CHARGE_WON_AMOUNTS,
    FREE_SUB_DAYS,
    SIGNUP_BONUS,
    activate_free_advanced_sub,
    activate_paid_advanced_sub,
    calc_auto_cost,
    calc_hedge_cost,
    calc_thunder_cost,
    charge_points,
    deduct_points,
    eligible_free_advanced_sub,
    get_balance,
    pg_configured,
    won_to_points,
)


def _dialog_decorator(title: str):
    if hasattr(st, "dialog"):
        return st.dialog(title)
    return st.experimental_dialog(title) if hasattr(st, "experimental_dialog") else _fallback_dialog(title)


def _fallback_dialog(title: str):
    def wrapper(func):
        def inner(*args, **kwargs):
            with st.container(border=True):
                st.subheader(title)
                return func(*args, **kwargs)
        return inner
    return wrapper


AUTH_BANNER_OPEN = "auth_banner_open"
AUTH_BANNER_REASON = "auth_banner_reason"
AUTH_RESUME_FLAG = "auth_resume_flag"
AUTH_RESUME_DATA = "auth_resume_data"
AUTH_BANNER_DISMISSED = "auth_banner_dismissed"
AUTH_BANNER_JUST_DISMISSED = "auth_banner_just_dismissed"
AUTH_BANNER_DISMISS_REDIRECT = "auth_banner_dismiss_redirect"


def open_auth_banner(
    *,
    reason: str = "",
    resume: str | None = None,
    resume_data: dict | None = None,
    dismiss_redirect: str | None = None,
) -> None:
    st.session_state[AUTH_BANNER_OPEN] = True
    st.session_state[AUTH_BANNER_REASON] = reason or "이 기능을 이용하려면 간편인증이 필요합니다."
    # 2026-09-12(사용자 지시): 타로·행운수처럼 페이지 전체가 로그인 없인 아무
    # 의미가 없는 화면에서는, ×로 닫아도 그 자리에 "로그인이 필요합니다"라는
    # 빈 화면만 남아 자동구매 등 다른(부분만 막힌) 화면과 경험이 달라 보였다
    # ("통일시켰다더니 왜 다르냐"는 지적). dismiss_redirect가 있으면 ×를
    # 눌렀을 때 배너만 닫는 게 아니라 그 페이지로 이동시킨다(보통 "main").
    if dismiss_redirect:
        st.session_state[AUTH_BANNER_DISMISS_REDIRECT] = dismiss_redirect
    else:
        st.session_state.pop(AUTH_BANNER_DISMISS_REDIRECT, None)
    # 2026-09-12(중대 버그 수정 — 사용자 지시로 원인 확인): resume을 "있을 때만
    # 덮어쓰기"로 해뒀더니, 예전에 다른 기능(예: 번개조합 "조합시작")에서 배너를
    # 열었다가 로그인 없이 [닫기]로 닫은 resume이 세션에 그대로 남아있었다. 그
    # 뒤 전혀 다른 기능(예: "저장내역", resume 없음)으로 배너를 다시 열어도 그
    # 묵은 resume이 안 지워졌고, 그 상태로 아무 경로로든(지금 하려는 일과
    # 무관하게) 로그인만 완료되면 render_auth_banner의 "로그인됨+resume 있음"
    # 체크가 그 묵은 resume을 실행해버렸다 — 조합 생성이 이미 진행 중인 화면
    # 위에 "적립금 이용 안내" 다이얼로그가 뜬금없이 다시 뜨고(사용자 신고),
    # 그 재실행이 만든 rerun이 번호판 iframe을 새로 만들어 생성이 1게임만
    # 나온 채 멈추는 것까지 같은 원인으로 보인다. 매번 이번 호출의 resume
    # 값으로 완전히 덮어써서(없으면 지움) 이전 호출의 잔재가 안 남게 한다.
    if resume:
        st.session_state[AUTH_RESUME_FLAG] = resume
    else:
        st.session_state.pop(AUTH_RESUME_FLAG, None)
    if resume_data:
        st.session_state[AUTH_RESUME_DATA] = resume_data
    else:
        st.session_state.pop(AUTH_RESUME_DATA, None)
    # 2026-09-11(사용자 지시): 배너는 항상 화면 최상단(render_wallet_bar 위치)에서
    # 그려지는데, 정작 이 배너를 여는 트리거(번개조합 "저장내역" 등)는 화면 아래쪽에
    # 있는 경우가 많다 — 유저가 방금 누른 위치에 그대로 머물러 있어서 배너가 뜬 걸
    # 못 보고 "안 눌힌다"고 오해하는 혼란으로 이어졌다. 배너를 여는 바로 이 순간
    # 1회, 다음 렌더에서 화면을 최상단으로 스크롤해 배너가 바로 보이게 한다.
    st.session_state["_auth_banner_scroll_pending"] = True


def close_auth_banner() -> None:
    # 2026-09-12: "닫기"(로그인 안 하고 취소)로 배너를 닫을 때도 resume 의도를
    # 함께 버린다 — 안 그러면 나중에 완전히 무관한 경로로 로그인했을 때 이
    # 묵은 resume이 갑자기 실행되는 사고로 이어진다(위 open_auth_banner 주석
    # 참고). 정상 로그인 성공 경로(_finish_auth_success)는 이미
    # _resume_after_auth()에서 먼저 pop해 소비하므로 여기서 또 지워도 안전하다.
    for key in (
        AUTH_BANNER_OPEN,
        AUTH_BANNER_REASON,
        AUTH_RESUME_FLAG,
        AUTH_RESUME_DATA,
        AUTH_BANNER_DISMISS_REDIRECT,
    ):
        st.session_state.pop(key, None)
    # 2026-09-12(사용자 신고 — × 눌러도 배너가 안 사라짐): 타로·행운수처럼
    # 페이지 전체를 매 렌더마다 무조건 login_gate()로 막는 화면에서는, ×로
    # 방금 닫아도 같은 rerun 흐름에서 그 페이지의 무조건 게이트가 바로 다시
    # login_gate()를 호출해 즉시 재오픈했다 — 유저 눈엔 "×가 안 먹힌다"로
    # 보였다. 이 1회성 플래그는 "방금 ×로 닫은 직후의 바로 다음 login_gate
    # 판정 1번"만 재오픈을 건너뛴다 — 그 이후 유저가 실제로 다른(혹은 같은)
    # 막힌 기능을 새로 클릭하면(2026-09-10 확정 규칙: "닫기 후 다른 막힌
    # 기능을 누르면 다시 뜬다") 정상적으로 다시 뜬다. 버튼 클릭으로만 도는
    # 8곳(조합시작·저장내역·내정보 등)은 이 rerun에서 애초에 login_gate가
    # 다시 불릴 일이 없으므로 영향받지 않는다.
    st.session_state[AUTH_BANNER_DISMISSED] = True


def _resume_after_auth() -> None:
    resume = st.session_state.pop(AUTH_RESUME_FLAG, None)
    data = st.session_state.pop(AUTH_RESUME_DATA, None) or {}
    if resume == "auto_show_points":
        st.session_state["auto_show_points"] = True
    elif resume == "open_thunder_dialog":
        st.session_state["open_thunder_dialog"] = True
        st.session_state["open_thunder_dialog_games"] = int(data.get("games", 5))
    elif resume == "open_hedge_dialog":
        # 2026-08-27: 조합시작 한 번에 개별리셋·전체리셋을 항상 함께 생성하도록
        # 바뀌면서 "모드" 선택 자체가 없어져 더 이상 넘길 값이 없다.
        st.session_state["open_hedge_dialog"] = True
        st.session_state["hedge_pending_lines"] = data.get("lines") or []
        st.session_state["hedge_pending_count"] = int(data.get("count", 5))
    elif resume == "open_tarot_dialog":
        st.session_state["open_tarot_dialog"] = True
    elif resume == "af_show_step1_points":
        st.session_state["af_show_step1_points"] = True
    elif resume == "af_show_step2_points":
        st.session_state["af_show_step2_points"] = True
    elif resume == "wallet_show_charge":
        st.session_state["wallet_show_charge"] = True
    elif resume == "my_info_dialog":
        st.session_state["my_info_dialog_open"] = True


def _finish_auth_success() -> None:
    _resume_after_auth()
    close_auth_banner()
    st.rerun()


def _testing_period_active() -> bool:
    """[출시 전 테스트 기간 한정] 실제 카카오 인증·PG 결제가 아직 연동되지 않은
    동안엔 True — 인증/적립금/구독 안내 배너를 전부 숨기고 조용히 통과시키는
    데 쓴다(사용자 요청: "테스트기간엔 인증,적립금,결제,충전 안내배너창 다
    숨기기"). kakao_configured()가 켜지는 순간(=실제 연동 완료) 이 우회는
    자동으로 꺼지고 원래의 배너/안내창 흐름으로 돌아간다.

    [숙제 — 정식 출시 시 결정 필요] 지금은 전부 숨겼지만, 실제로 포인트가
    깎이는 정식 서비스에서는 사용자가 "왜 깎였는지" 알 방법이 아예 없어지면
    안 된다. 매번 안내창을 띄우던 예전 방식은 번거로워 이탈을 유발했으니,
    예를 들어 "처음 한 번만 안내 + 이후엔 상단에 잔액과 이번 차감액을 작게
    표시" 같은 절충안을 검토할 것."""
    return _dev_mock_enabled() and not kakao_configured()


def login_gate(
    *,
    resume: str | None = None,
    resume_data: dict | None = None,
    dismiss_redirect: str | None = None,
) -> bool:
    """로그인이 필요한 기능의 **단일 게이트**. 로그인됐으면 True(기능 진행).
    아니면 통합 안내창(login_gate.py 문구)을 띄우고 False.

    노출 규칙(2026-09-10 사용자 확정): 로그인 안 한 채로 막힌 기능을 누르면
    **매번** 이 안내창을 띄운다("상태 1"). 안내창이 이미 떠 있는 동안은 다시
    안 띄운다(AUTH_BANNER_OPEN 가드) — login_gate는 버튼 클릭뿐 아니라 저장내역
    패널 렌더 중에도 불리므로, 이 가드가 없으면 st.rerun() 무한 루프가 된다.
    사용자가 "닫기"로 안내창을 닫은 뒤 다른 막힌 기능을 누르면 다시 뜬다.

    2026-09-12 추가: 타로·행운수처럼 페이지 전체를 매 렌더마다 무조건
    login_gate()로 막는 화면에서는, AUTH_BANNER_OPEN 가드만으로는 ×로 닫은
    바로 다음 rerun에서 그 페이지가 다시 login_gate()를 호출해 즉시
    재오픈해버리는 문제가 있었다(사용자 신고: "×눌러도 안 사라짐"). 방금
    ×로 닫은 직후의 판정만 AUTH_BANNER_JUST_DISMISSED로 건너뛴다 — 이
    플래그는 render_wallet_bar()가 매 rerun 시작 시 AUTH_BANNER_DISMISSED
    (닫기 버튼이 세팅하는 1회성 이벤트)로부터 매번 새로 계산해 정확히
    "닫은 직후의 그 다음 rerun 1번" 동안만 True다 — 그 이후의 진짜 새
    클릭(버튼을 다시 누르는 것)은 전혀 다른 rerun이라 자동으로 False로
    돌아와 있으므로, 위 2026-09-10 규칙("다른 막힌 기능을 누르면 다시
    뜬다")이 그대로 유지된다.

    테스트 기간엔(_testing_period_active) 안내창 대신 조용히 로그인시키고 진행."""
    if current_member_id():
        return True
    if _testing_period_active():
        mock_kakao_login()
        return True
    if st.session_state.get(AUTH_BANNER_OPEN):
        return False
    if st.session_state.get(AUTH_BANNER_JUST_DISMISSED):
        return False
    open_auth_banner(resume=resume, resume_data=resume_data, dismiss_redirect=dismiss_redirect)
    st.rerun()
    return False


def ensure_member_or_banner(*, resume: str | None = None, reason: str = "", resume_data: dict | None = None) -> bool:
    """하위 호환용 껍데기 — login_gate로 위임. reason은 더 이상 표시하지 않는다
    (문구가 login_gate.py로 통일됨)."""
    return login_gate(resume=resume, resume_data=resume_data)


def _inject_auth_banner_css() -> None:
    st.markdown(
        """
<div class="lotto-auth-banner-marker" aria-hidden="true"></div>
<style>
div[data-testid="stVerticalBlock"]:has(> div > .lotto-auth-banner-marker),
div[data-testid="stVerticalBlock"]:has(.lotto-auth-banner-marker) {
    position: sticky !important;
    top: 0 !important;
    z-index: 100 !important;
    margin-bottom: 12px !important;
}
/* 2026-09-12(사용자 지시 — 재수정): :has(.auth-banner-consent-marker)로
   잡으면 이 마커를 포함하는 조상 stVerticalBlock 전부(맨 위 sticky 전체폭
   래퍼까지)에 카드 배경·테두리·max-width가 다 걸려서, 폭이 다른 배경 두
   겹이 겹쳐 보이는("구구절절"스러운) 문제가 실측 확인됨. 조상 전체가 아니라
   이 카드 자신에게만 스타일이 걸리도록 st.container(key=...) 고유 클래스로
   정확히 한 겹만 지정한다. */
/* 2026-09-12(사용자 신고 — 3번째 줄이 카카오 버튼에 가려짐, 타로에서 특히
   심함): 닫기(×)를 이 박스 "안"의 첫 자식으로 넣었더니, position:absolute라
   화면엔 안 보여도 여전히 flex 자식 1개로 카운트돼 Streamlit 기본
   gap(16px)이 다음 형제(첫 줄) 앞에 그대로 붙었다 — 실측: 텍스트 시작점이
   padding-top보다 20px 더 아래였고, 그만큼 박스 바닥을 넘어 3번째 줄이
   버튼과 겹쳤다(직접 그 자식 노드를 DOM에서 제거해 실측 확인, gap만 0으로
   죽이면 이번엔 Streamlit 기본 음수 마진과 충돌해 줄끼리 겹침). 근본적으로
   닫기(×)를 카드 자신의 flex 자식으로 두지 않도록 바깥 래퍼로 뺀다 —
   래퍼가 position:relative만 담당하고, 카드는 원래처럼 텍스트 3줄만 자식으로
   가진다. */
.st-key-auth_banner_wrap {
    position: relative !important;
    max-width: 325px !important; /* 2026-09-12(사용자 지시): 3줄이 각각 한 줄로
       보이도록 실측(가장 긴 줄 실제 필요폭 약 294px + 좌우 패딩 20px + 여유)
       기준으로 확보 */
    margin: 10px auto 0 auto !important;
}
.st-key-auth_banner_box {
    background: rgba(13, 21, 40, 0.6) !important;
    border: 1px solid #2a3a60 !important;
    border-radius: 10px !important;
    padding: 10px 10px 22px 10px !important; /* 2026-09-12: 이 컨테이너의
       auto-height 계산이 실제 텍스트 줄 높이보다 10px가량 작게 잡히는
       Streamlit 내부 레이아웃 특성이 실측 확인됨(원인 불문, 여러 겹의
       Streamlit 내부 wrapper 중 하나가 줄임) — 근본 셀렉터를 계속 뒤지는
       대신, 바닥 패딩을 넉넉히 키워 그 어긋남을 확실히 흡수한다. */
    margin: 0 0 6px 0 !important;
}
.auth-banner-consent-item {
    white-space: nowrap !important;
    color: #e8eef2 !important;
    font-size: 13px !important;
    line-height: 1.45 !important;
    margin: 3px 0 !important;
}
/* 닫기(×)는 st.columns가 아니라 절대위치로 앵커한다 — 모바일 폭(대략
   640px 미만)에서는 Streamlit 컬럼이 세로로 쌓이는 기본 반응형 동작 때문에,
   이 배너의 실제 사용 환경(좁은 웹뷰)에서 columns([11,1])로 만들면 ×가
   우측 상단이 아니라 자기 줄 가운데에 나타나는 문제가 실측 확인됨.
   2026-09-12(사용자 지시 — 재수정): 카드 안쪽에 자리를 차지하고 앉아있지
   않도록, 카드 테두리 바깥쪽 모서리에 살짝 걸치는 작은 원형 배지로 뺀다
   (다른 사이트의 통상적인 모달 닫기 배지 위치 참고). 위치 기준은 이제
   .st-key-auth_banner_wrap(카드 바깥 래퍼)이다. */
.st-key-auth_banner_close_x {
    position: absolute !important;
    top: -14px !important;
    right: -12px !important;
    width: auto !important;
    z-index: 5 !important;
}
.st-key-auth_banner_close_x button {
    background: #2a3a60 !important;
    color: #c7d3e0 !important;
    border: 1px solid #45597e !important;
    border-radius: 50% !important;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.35) !important;
    padding: 0 !important;
    min-height: 22px !important;
    height: 22px !important;
    width: 22px !important;
    font-size: 11px !important;
    line-height: 1 !important;
}
.st-key-auth_banner_kakao {
    max-width: 325px !important;
    margin: 0 auto !important;
}
.st-key-auth_banner_kakao a,
.st-key-auth_banner_kakao button[kind="primary"] {
    background: linear-gradient(145deg, #fee500, #f5d900) !important;
    color: #191919 !important;
    border-color: #e6c200 !important;
    border-radius: 10px !important;
    min-height: 42px !important;
    font-weight: 700 !important;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def _force_kakao_link_same_tab() -> None:
    """st.link_button은 Streamlit 자체 사양상 항상 새 탭(target="_blank")으로
    열리고, 이 옵션을 끌 파라미터가 없다(공식 문서: "a new tab will be opened
    ... This will create a new session for the user"). 문제는 카카오 로그인이
    그 새 탭 안에서 끝나버리면, 원래 있던 탭의 세션은 로그인 사실을 전혀
    모른 채 그대로 남아있다는 것 — 유저가 로그인 후 원래 탭으로 돌아오면
    배너가 그대로 떠 있어 "카카오로 시작하기를 눌러도 기존 로그인창이 또
    보인다"는 신고로 이어졌다(2026-09-12, 실제 배포본에서 재현 확인).
    렌더된 <a> 태그의 target 속성만 제거해 같은 탭에서 이동하게 만든다 —
    페이지 복귀(return_page)를 위해 state에 인코딩해두는 다른 로직은 전혀
    건드리지 않는다.

    2026-09-12: 처음엔 querySelectorAll을 한 번만 실행했는데, 이 iframe
    스크립트가 실제 <a> 태그보다 먼저 실행돼(components.html이 st.link_button
    보다 빨리 마운트되는 타이밍 경쟁) target이 그대로 남는 경우가 실측
    확인됐다 — MutationObserver로 해당 링크가 나타날 때까지 기다렸다가
    지운다."""
    components.html(
        """<script>
        (function() {
            try {
                var doc = window.top.document;
                function strip() {
                    var links = doc.querySelectorAll('.st-key-auth_banner_kakao a[target]');
                    if (links.length) {
                        links.forEach(function(a) { a.removeAttribute('target'); });
                        return true;
                    }
                    return false;
                }
                if (strip()) return;
                var obs = new MutationObserver(function() { if (strip()) obs.disconnect(); });
                obs.observe(doc.body, {childList: true, subtree: true});
                setTimeout(function() { obs.disconnect(); }, 5000);
            } catch (e) {}
        })();
        </script>""",
        height=0,
    )


def _fire_kakao_native_login_trigger() -> None:
    """네이티브 앱(streamlit-webview.tsx)에게 카카오 네이티브 SDK 로그인을
    시작하라는 신호를 보낸다 — page_hedge.py의 QR스캔 트리거(_fire_qr_scan_
    trigger)와 완전히 같은 기법: components.html은 항상 iframe 안에서
    실행되는데, 안드로이드 웹뷰가 심어주는 window.ReactNativeWebView 브릿지는
    보안상 최상위 프레임에만 존재해서 iframe 안에서는 그 자리에 아예 없다
    (2026-08-22 실기기 확인, QR스캔에서 이미 검증된 우회법). iframe 안에서
    최상위 문서에 직접 <script> 엘리먼트를 심어 그 스크립트가 최상위 문서
    컨텍스트에서 실행되게 하면, 거기서 보는 window.ReactNativeWebView는
    진짜 그 프레임에 심어진 브릿지를 가리킨다.

    2026-09-06: 처음엔 postMessage 브릿지 하나에만 의존했는데, QR스캔에서
    이미 겪었던 것과 같은 기기(브릿지 객체 자체가 최상위 문서에 안 심어지는
    실기기)에서 로그인 버튼이 조용히 아무 반응도 안 하는 문제가 실측 확인됐다.
    QR스캔과 동일하게 "브릿지가 있으면 postMessage만, 없으면 URL 트리거로
    폴백"하는 판단을 최상위 문서 스크립트 안에서 직접 하도록 만든다 — 둘 다
    항상 실행하면(QR스캔에서 겪은 부작용, 위 _fire_qr_scan_trigger 독스트링
    참고) 브릿지가 성공했을 때도 URL 이동이 같이 걸려 화면이 깜빡이며
    되돌아오는 문제가 생길 수 있어 피한다."""
    components.html(
        """<script>
        (function () {
            var top = window.top;
            try {
                var s = top.document.createElement('script');
                s.textContent =
                    "try{" +
                    "var rnwv = window.ReactNativeWebView;" +
                    "if(rnwv && typeof rnwv.postMessage === 'function'){" +
                    "rnwv.postMessage(JSON.stringify({type:'kakaoNativeLogin'}));" +
                    "}else{" +
                    "var u = new URL(window.location.href);" +
                    "u.searchParams.set('kakao_native_trigger', '1');" +
                    "window.location.href = u.toString();" +
                    "}" +
                    "}catch(e){}";
                top.document.head.appendChild(s);
                s.parentNode.removeChild(s);
            } catch (e) {
                // 최상위 문서에 스크립트를 못 심을 정도로 예외적인 상황이면
                // 최소한 이 폴백만이라도 시도한다.
                try {
                    var u2 = new URL(top.location.href);
                    u2.searchParams.set('kakao_native_trigger', '1');
                    top.location.href = u2.toString();
                } catch (e2) {}
            }
        })();
        </script>""",
        height=0,
    )


def _render_auth_banner_form() -> None:
    # 2026-09-12(사용자 지시 — "초간단하게 가로·세로 대폭 줄이기"): 제목 문구,
    # "카카오 로그인 후 이 화면으로 돌아옵니다" 안내, PASS·금융인증서 안내를
    # 전부 없애고 약관 3줄 + 카카오 버튼만 남긴다. 닫을 방법이 아예 없으면
    # 로그인 안 한 유저에게 이 배너가 모든 화면 상단에 계속 고정 노출되므로,
    # 우측 상단에 아주 작은 닫기(×) 하나만 남겨둔다.
    from login_gate import GATE_BUTTON, GATE_LINES

    dismissed_clicked = False
    with st.container(key="auth_banner_wrap"):
        with st.container(key="auth_banner_close_x"):
            if st.button("✕", key="auth_banner_close_x_btn"):
                dismissed_clicked = True
        with st.container(key="auth_banner_box"):
            for item in GATE_LINES:
                st.markdown(f'<p class="auth-banner-consent-item">· {html.escape(item)}</p>', unsafe_allow_html=True)

    if dismissed_clicked:
        # 2026-09-12(사용자 신고 — × 잔재): st.rerun()을 중첩된 st.container(...)
        # with 블록 "안"에서 호출하면(이전 코드), 그 예외가 여러 겹의 with
        # 블록을 한꺼번에 빠져나가면서 프런트엔드가 이 특정 중첩 컨테이너의
        # "닫힘"을 제대로 못 받아, 다음 렌더에서 배경 없는 흰 박스 안에 ×만
        # 남는 고아 DOM으로 남았다(실제 배포본에서 재현 확인 — 안드로이드
        # 웹뷰만의 문제가 아니라 일반 데스크톱 브라우저에서도 동일 재현).
        # 클릭 여부만 안에서 기록해두고, rerun은 모든 with 블록을 정상적으로
        # 빠져나온 뒤 여기서 호출한다.
        #
        # 2026-09-12(사용자 지시 — 타로 등 전체 게이트 화면 대응): close_auth_
        # banner()가 지우기 전에 dismiss_redirect를 먼저 읽어둔다 — 타로·
        # 행운수처럼 페이지 전체가 로그인 없인 빈 화면뿐인 곳은, ×를 눌렀을 때
        # 그 자리에 "로그인이 필요합니다"만 남기지 않고 메인으로 돌려보낸다
        # (자동구매처럼 부분만 막힌 화면은 dismiss_redirect가 없어 그 자리에
        # 그대로 남는다 — 동작 차이 없음).
        redirect_page = st.session_state.get(AUTH_BANNER_DISMISS_REDIRECT)
        close_auth_banner()
        st.session_state.pop(AUTH_RESUME_FLAG, None)
        st.session_state.pop(AUTH_RESUME_DATA, None)
        if redirect_page:
            st.query_params["page"] = redirect_page
        st.rerun()

    return_page = st.query_params.get("page", "main")

    if kakao_configured():
        # 2026-09-06: 네이티브 앱(?native=1)에서는 REST API+웹뷰 리다이렉트
        # 방식(카카오 공식 미지원 — devtalk.kakao.com 답변)을 버리고, 카카오
        # 네이티브 SDK를 직접 호출하는 버튼으로 바꾼다. 일반 웹 접속은
        # 기존 방식 그대로 둔다(영향 없음).
        is_native_app = st.query_params.get("native") == "1"
        with st.container(key="auth_banner_kakao"):
            if is_native_app:
                if st.button(
                    GATE_BUTTON,
                    use_container_width=True,
                    type="primary",
                    key="auth_banner_kakao_native",
                ):
                    _fire_kakao_native_login_trigger()
            else:
                st.link_button(
                    GATE_BUTTON,
                    get_kakao_authorize_url(return_page),
                    use_container_width=True,
                    type="primary",
                )
                _force_kakao_link_same_tab()
    elif _dev_mock_enabled():
        with st.container(key="auth_banner_kakao"):
            if st.button(
                GATE_BUTTON,
                use_container_width=True,
                type="primary",
                key="auth_banner_kakao_mock",
            ):
                mock_kakao_login()
                _finish_auth_success()
        st.caption("개발 모드 · Mock 간편인증")
    else:
        with st.container(key="auth_banner_kakao"):
            st.button(
                GATE_BUTTON,
                use_container_width=True,
                disabled=True,
                key="auth_banner_kakao_unconfigured",
            )
        st.error(
            "카카오 로그인 연동이 아직 설정되지 않았습니다. "
            "`.env`에 `KAKAO_REST_API_KEY`를 넣거나, "
            "개발 중이면 `LOTTO_DEV_MOCK_AUTH=1`로 설정 후 서버를 재시작하세요."
        )


def _scroll_to_top_once() -> None:
    """화면을 최상단으로 1회 스크롤한다 — 화면 아래쪽에서 누른 버튼이 최상단
    배너를 열 때, 유저가 스크롤하지 않아도 바로 보이게 한다(사용자 지시
    2026-09-11). components.html iframe sandbox엔 allow-top-navigation이 없어
    location 이동은 막히지만 scrollTo는 막히지 않는다 — 그래도 기존에 검증된
    "최상위 문서에 스크립트 심기" 방식을 그대로 재사용해 일관되게 둔다."""
    components.html(
        """
        <script>
        (function() {
            try {
                var s = window.top.document.createElement('script');
                s.textContent = "try{window.scrollTo({top:0,behavior:'smooth'});}catch(e){window.scrollTo(0,0);}";
                window.top.document.head.appendChild(s);
                s.parentNode.removeChild(s);
            } catch (e) {
                try { window.parent.scrollTo(0, 0); } catch (e2) {}
            }
        })();
        </script>
        """,
        height=0,
    )


def _cleanup_stale_auth_banner_dom() -> None:
    """×로 닫은 직후의 다음 렌더 딱 1번만 호출 — st.container(key=...) 중첩
    구조 특성상 프런트엔드가 이전 렌더의 배너 DOM(× 아이콘만 남거나, 약관
    3줄 박스만 남는 두 형태 모두 실측 재현됨 — dc73a91에서 X 아이콘 잔재는
    한 번 고쳤지만, 그 뒤 "닫기(×)를 카드 바깥 래퍼로 뺀" 재구성이 같은
    클래스의 문제를 다른 모양으로 재현시켰다)를 못 지우고 고아로 남기는
    경우가 있어, 남아있으면 JS로 강제 제거한다. AUTH_BANNER_JUST_DISMISSED로
    "닫은 직후 1번"에만 실행되게 가드해서, 이후 모든 렌더마다 불필요한
    iframe이 반복 주입되지 않게 한다."""
    components.html(
        """
        <script>
        (function() {
            try {
                var doc = window.top.document;
                doc.querySelectorAll('.st-key-auth_banner_wrap').forEach(function(el) {
                    el.remove();
                });
            } catch (e) {}
        })();
        </script>
        """,
        height=0,
    )


def render_auth_banner() -> None:
    if current_member_id() and st.session_state.get(AUTH_RESUME_FLAG):
        _finish_auth_success()
        return
    if not st.session_state.get(AUTH_BANNER_OPEN):
        if st.session_state.get(AUTH_BANNER_JUST_DISMISSED):
            _cleanup_stale_auth_banner_dom()
        return
    if current_member_id():
        _finish_auth_success()
        return
    if st.session_state.pop("_auth_banner_scroll_pending", False):
        _scroll_to_top_once()
    _inject_auth_banner_css()
    _render_auth_banner_form()


def _render_charge_actions(member_id: int) -> None:
    """충전 버튼/안내 렌더링 — charge_dialog()와 insufficient_balance_dialog()가
    공유한다(2026-09-08 분리). 두 곳에 똑같은 로직을 복붙해두면 나중에 금액·문구를
    한쪽만 고치고 다른 쪽을 놓치는 사고로 이어지므로, 결제 관련 코드는 항상 여기
    한 곳만 고치면 두 다이얼로그 모두에 반영되게 한다."""
    if pg_configured():
        won_amount = st.radio(
            "충전 금액",
            CHARGE_WON_AMOUNTS,
            format_func=lambda w: f"{w:,}원 → {won_to_points(w):,}P",
            horizontal=True,
        )
        st.info("PG 결제창 연동은 계약 후 활성화됩니다. (카드정보는 서버에 저장하지 않습니다.)")
        st.link_button(
            "결제창 열기 (준비중)",
            "#",
            disabled=True,
            use_container_width=True,
        )
    elif not pg_configured():
        # 2026-09-05: 이 버튼은 원래 "카카오 로그인이 아직 mock인 테스트 기간"
        # (_testing_period_active())에만 보이게 막아뒀었다 — 실제 카카오 로그인이
        # 연동된 뒤에도 PG만 아직이면 아무나 눌러서 무한 포인트를 받을 수 있었기
        # 때문(실제 무료 악용 가능 상태 — 2026-09-05 발견).
        # 2026-09-08 재조정(사용자 지시): 그런데 그 뒤 실제 카카오 로그인이
        # 연동되면서 _testing_period_active()가 항상 False가 돼버려, 이미
        # 실로그인한 테스터들이 PG 연동 전까지 충전할 방법이 아예 없어지는
        # 사고로 이어졌다(자동구매/번개조합/안티액땜 전부 "결제 연동 준비
        # 중입니다"만 뜨고 막힘). 지금은 소수 테스터만 접근 가능한 단계라는
        # 사용자 확인 하에, 조건을 "PG 미연동이면(로그인 방식 무관)"으로
        # 완화한다 — 위에서 우려했던 "실로그인 후 무한 악용" 리스크가 다시
        # 열리는 셈이지만, 테스터 외 일반 사용자에게 노출되기 전까지만 쓰는
        # 한시적 조치다. PG 연동되는 순간(pg_configured()=True) 이 분기
        # 자체가 안 타므로 자동으로 다시 잠긴다 — 별도 원복 작업 불필요.
        # 다만 테스터 아닌 일반 방문자도 카카오 로그인이 가능해지는 시점이
        # 오면 이 조건은 반드시 다시 좁혀야 한다(사용자에게 고지함).
        test_won_amount = 10000
        test_points = won_to_points(test_won_amount)
        st.caption(f"PG 미연동 · 테스트 기간 임시 고정 금액 — {test_won_amount:,}원 → {test_points:,}P")
        if st.button(
            f"Mock 결제 (테스트) — {test_points:,}P 충전",
            type="primary",
            use_container_width=True,
        ):
            ref = f"pg:mock:{member_id}:{uuid.uuid4().hex[:10]}"
            if charge_points(member_id, test_points, ref):
                st.session_state.wallet_toast = f"{test_won_amount:,}원 · {test_points:,}P 충전 완료"
                # insufficient_balance_dialog()에서 호출된 경우, 충전 성공 후에도
                # 이 플래그가 남아있으면 다음 렌더에서 "부족합니다" 창이 또 뜬다 —
                # charge_dialog()에서 호출된 경우엔 애초에 없는 키라 pop이 그냥
                # 무시된다(두 다이얼로그가 이 함수를 공유하므로 항상 같이 정리).
                st.session_state.pop(INSUFFICIENT_BALANCE_OPEN, None)
                st.rerun()
            st.error("충전에 실패했습니다.")
    else:
        st.info("결제 연동 준비 중입니다. 조금만 기다려주세요.")


@_dialog_decorator("적립금 충전")
def charge_dialog() -> None:
    member_id = current_member_id()
    if not member_id:
        return

    balance = get_balance(member_id)
    st.markdown(f"현재 잔액 **{balance:,}P**")
    _render_charge_actions(member_id)


INSUFFICIENT_BALANCE_OPEN = "insufficient_balance_open"
INSUFFICIENT_BALANCE_NEED = "insufficient_balance_need"


def open_insufficient_balance_dialog(need_points: int) -> None:
    """자동구매/번개조합/안티·액땜조합 세 화면 공통 — 구매 확정 시 적립금이
    부족하면 이 함수 하나로 "부족합니다 + 충전하시겠습니까?" 통합 창을 띄운다.

    2026-09-08(사용자 지시): 예전엔 각 화면이 "적립금이 부족합니다" 에러 문구만
    보여주고 끝나서, 사용자가 직접 내정보→충전으로 따로 이동해야 했다. 그 자리에서
    바로 충전까지 이어지도록 세 화면 모두 이 함수로 통일한다(한 화면만 고치면
    나머지가 방치되는 문제가 반복 지적됐음 — apply_fixes_to_all_three_purchase_screens
    메모 참고)."""
    st.session_state[INSUFFICIENT_BALANCE_OPEN] = True
    st.session_state[INSUFFICIENT_BALANCE_NEED] = int(need_points)


@_dialog_decorator("적립금 부족")
def insufficient_balance_dialog() -> None:
    member_id = current_member_id()
    if not member_id:
        st.session_state.pop(INSUFFICIENT_BALANCE_OPEN, None)
        return
    need = int(st.session_state.get(INSUFFICIENT_BALANCE_NEED, 0))
    balance = get_balance(member_id)
    st.error(f"❌ 적립금이 부족합니다. (필요 {need:,}P / 보유 {balance:,}P)")
    st.markdown("**충전하시겠습니까?**")
    _render_charge_actions(member_id)
    if st.button("닫기", use_container_width=True, key="insufficient_balance_close"):
        st.session_state.pop(INSUFFICIENT_BALANCE_OPEN, None)
        st.rerun()


POINTS_NOTICE_SEEN_ONCE = "points_notice_seen_once"

# 조합시작/구매확정 → points_notice_dialog를 여는 트리거 플래그들. dialog가 X로
# 닫히거나(버튼 클릭 없이) 하면 이 플래그가 남아 다음 렌더에서 다시 뜨는데,
# 예전엔 그 재-렌더가 SEEN_ONCE 자동통과 분기를 타면서 사용자가 취소했는데도
# 적립금이 차감되는 사고로 이어졌다(2026-09-10 사용자 지적 — 분쟁 리스크).
# on_dismiss에서 이 플래그를 모두 지워 "X로 닫음 = 취소"가 되게 한다.
_PN_TRIGGER_FLAGS = ("open_thunder_dialog", "open_hedge_dialog", "auto_show_points")


def _points_notice_on_dismiss() -> None:
    for _k in _PN_TRIGGER_FLAGS:
        st.session_state.pop(_k, None)


def _points_notice_dialog_decorator(title: str):
    if hasattr(st, "dialog"):
        try:
            return st.dialog(title, on_dismiss=_points_notice_on_dismiss)
        except TypeError:
            return st.dialog(title)
    return _dialog_decorator(title)


@_points_notice_dialog_decorator("적립금 이용 안내")
def points_notice_dialog(
    service: str,
    *,
    game_count: int = 5,
    quantity: int = 5,
    on_close,
) -> None:
    """service: thunder/hedge/auto/tarot. on_close(confirmed: bool)를 누른 버튼에 맞춰
    호출한 뒤 st.rerun()한다 — 반환값을 호출부가 받아 처리하는 방식은 st.dialog
    안에서 실제로 동작하지 않아(버튼을 눌러도 다음 단계로 못 넘어가고 같은 화면이
    반복되는 문제로 실기기에서 확인됨) 콜백 방식으로 바꿨다.

    지금은 실제 카카오 인증·PG 결제가 연결되지 않은 테스트 기간이라, 적립금 부족
    등의 이유로 사용자를 막지 않는다 — 안내만 보여주고 취소/확인 어느 쪽을 눌러도
    기능은 그대로 이용할 수 있게 통과시킨다(on_close(True/False)는 실제 차감
    시도 여부를 호출부에 알려줄 뿐, 통과 여부를 막는 용도가 아니다).

    테스트 기간엔(_testing_period_active) 이 안내창 자체를 아예 안 띄우고
    바로 확인 처리한다 — 매번 조합 만들 때마다 안내창이 뜨는 게 번거롭다는
    사용자 요청. 정식 출시 시 어떻게 다시 노출할지는 _testing_period_active
    독스트링의 "숙제" 참고.

    2026-09-08: "매번 뜨는 게 번거롭다"는 요청으로 세션당 1회만 전체 안내를
    보여주고 이후엔 자동 통과(on_close(True))시켰었는데, 2026-09-10에 사용자가
    "그러면 조합시작/구매확정을 실수로 눌러도(또는 이 창을 X로 닫아도) 바로
    적립금이 차감돼 분쟁 소지가 크다"고 지적 — 자동 통과를 없앤다. 적립금이
    실제로 차감되는 확정은 **매번 명시적인 '확인' 클릭**을 거쳐야 한다. 대신
    두 번째부터는 긴 고지문 대신 한 줄짜리 간단 확인만 보여줘 번거로움을
    줄인다. X로 닫으면(on_dismiss) 취소로 처리돼 차감되지 않는다."""
    member_id = current_member_id()
    balance = get_balance(member_id) if member_id else 0
    first_time = not st.session_state.get(POINTS_NOTICE_SEEN_ONCE)
    st.session_state[POINTS_NOTICE_SEEN_ONCE] = True

    if first_time:
        if service == "thunder":
            st.markdown(format_thunder_points_notice(game_count, balance))
        elif service == "hedge":
            st.markdown(format_hedge_points_notice(quantity, balance))
        elif service == "auto":
            st.markdown(format_auto_points_notice(quantity, balance))
        elif service == "tarot":
            st.markdown(format_tarot_points_notice(balance))
        else:
            st.error("알 수 없는 서비스")
    else:
        # 두 번째부터: 한 줄 간단 확인
        _svc_label = {
            "thunder": f"번개조합 {game_count}게임",
            "hedge": f"안티·액땜조합 {quantity}개",
            "auto": f"자동구매 {quantity}개",
            "tarot": "타로 추가뽑기",
        }.get(service, "구매")
        _amt = {
            "thunder": calc_thunder_cost(game_count),
            "hedge": calc_hedge_cost(quantity),
            "auto": calc_auto_cost(quantity),
            "tarot": PRICING["tarot_extra_draw"],
        }.get(service, 0)
        st.markdown(
            f"**{_svc_label}** — 확인 시 **{_amt:,}P** 차감됩니다."
            f"\n\n현재 잔액: **{balance:,}P**"
        )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("취소", use_container_width=True, key=f"pn_cancel_{service}"):
            on_close(False)
            st.rerun()
    with c2:
        if st.button("확인 후 진행", type="primary", use_container_width=True, key=f"pn_confirm_{service}"):
            on_close(True)
            st.rerun()


@_dialog_decorator("고급필터 구독")
def advanced_subscription_dialog(*, on_close) -> None:
    """구독 활성화까지 여기서 끝내고 on_close()를 호출한 뒤 st.rerun()한다 — 반환값을
    호출부가 받아 처리하는 방식은 st.dialog 안에서 실제로 동작하지 않는다(위
    points_notice_dialog와 동일한 이유). 여기는 (타로·번개 등과 달리) 진짜 잠금이라
    "취소"를 눌러도 구독이 되지는 않는다 — 그냥 닫기만 한다.

    테스트 기간엔(_testing_period_active) 이 안내창도 안 띄우고, 유료 결제 없이
    바로 장기 구독을 활성화해서 고급필터를 막힘없이 쓸 수 있게 한다 — 정식
    출시 시 어떻게 다시 노출할지는 _testing_period_active 독스트링 참고."""
    if _testing_period_active():
        member_id = current_member_id()
        if member_id:
            activate_paid_advanced_sub(member_id, 3650)
        on_close()
        st.rerun()
        return
    member_id = current_member_id()
    if not member_id:
        on_close()
        st.rerun()
        return

    balance = get_balance(member_id)
    free_ok = ADVANCED_FILTER_FIRST_SUB_FREE and eligible_free_advanced_sub(member_id)

    if free_ok:
        st.markdown(format_advanced_points_notice(has_free_sub=True, balance=balance))
        plan = "free"
        cost = 0
    else:
        plan = st.radio(
            "구독 기간",
            ["monthly", "3month"],
            format_func=lambda p: f"1개월 · {ADVANCED_MONTHLY_COST:,}P" if p == "monthly" else f"3개월 · {ADVANCED_3MONTH_COST:,}P",
            horizontal=True,
        )
        st.markdown(format_advanced_points_notice(plan=plan, balance=balance))
        cost = ADVANCED_MONTHLY_COST if plan == "monthly" else ADVANCED_3MONTH_COST

    if cost > 0 and balance < cost:
        st.error(f"적립금이 부족합니다. (필요 {cost:,}P / 보유 {balance:,}P)")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("취소", use_container_width=True, key="adv_sub_cancel"):
            on_close()
            st.rerun()
    with c2:
        if st.button("구독하기", type="primary", use_container_width=True, key="adv_sub_confirm", disabled=cost > 0 and balance < cost):
            if plan == "free":
                ok = activate_free_advanced_sub(member_id)
            else:
                ref = f"advanced:{plan}:{member_id}:{uuid.uuid4().hex[:10]}"
                days = FREE_SUB_DAYS if plan == "monthly" else ADVANCED_3MONTH_DAYS
                # 2026-09-10(사용자 지시): 차감은 성공했는데 구독 활성화가 실패/예외로
                # 끊기면 적립금만 빠지고 구독이 안 걸린 상태가 된다 — 이 경우 즉시 환불.
                if not deduct_points(member_id, cost, f"advanced:{plan}", ref):
                    ok = False
                else:
                    try:
                        ok = activate_paid_advanced_sub(member_id, days)
                    except Exception:
                        ok = False
                    if not ok:
                        from wallet_db import refund_points

                        refund_points(member_id, cost, f"advanced:refund:{plan}", f"{ref}:refund")
            if not ok:
                st.error("구독 처리에 실패했습니다. 적립금이 차감됐다면 곧 자동 환불됩니다.")
            on_close()
            st.rerun()
    return None


def render_generation_complete_notice(kind: str) -> None:
    """조합생성/구매/뽑기 완료 안내 — 자동구매·번개조합·안티액땜·타로 4화면
    공용(2026-09-11 사용자 지시: "버튼 밑에 완료 안내멘트, 4군데 통일화").
    각 화면은 조합생성(또는 뽑기)이 실제로 끝난 시점에 이 함수를 그 화면의
    조합시작 버튼 바로 밑에서 호출하면 된다. 문구는 legal_notices.py의
    GENERATION_COMPLETE_NOTICES 한 곳에서만 관리 — 바꿀 때마다 4화면 전부
    찾아다니며 고치지 않게 한다."""
    from legal_notices import GENERATION_COMPLETE_NOTICES

    st.success(GENERATION_COMPLETE_NOTICES.get(kind, "✅ 완료되었습니다."))


def inject_app_haptic() -> None:
    """앱 전역 햅틱 — 최상위 문서에서 버튼/링크/셀렉트 등 상호작용 요소 클릭 시
    짧게 진동. render_wallet_bar가 모든 페이지에서 부르므로 한 곳에서 전체 커버.
    (2026-09-10: 예전엔 메인 6버튼·번개조합 일부에만 개별로 붙어 있어서 내정보·
    조합시작·저장내역·QR스캔·카카오 로그인·닫기·타로 버튼 등에 진동이 빠져
    있었다. 이벤트 위임 한 개로 통일.) page_thunder의 숫자판 iframe 안 클릭은
    별도 문서라 여기서 못 잡으므로 거기 자체 safeVibrate는 그대로 둔다."""
    components.html(
        """
        <script>
        (function() {
            var doc = window.parent.document;
            if (doc.__appHapticBound) return;
            doc.__appHapticBound = true;
            function vib() {
                try { if (navigator.vibrate) navigator.vibrate(28); } catch (e) {}
            }
            var SEL = 'button, a[href], summary, [role="button"], label[data-baseweb], '
                    + 'div[data-testid="stButton"], div[data-testid="stFormSubmitButton"], '
                    + 'div[data-baseweb="select"]';
            doc.addEventListener('click', function(e) {
                var t = e.target;
                if (t && t.closest && t.closest(SEL)) vib();
            }, true);
        })();
        </script>
        """,
        height=0,
    )


@st.cache_data(ttl=3, show_spinner=False)
def _cached_zp_user(zp_uid: str) -> dict | None:
    """render_wallet_bar()의 zp_uid(카카오 미연동 테스트 기간 임시 로그인) 잔액
    조회 전용 캐시. render_wallet_bar는 페이지 종류·상호작용과 무관하게 매
    rerun마다 정확히 한 번 불리는데, 예전엔 여기서 zero_phone_db.get_user()를
    캐시 없이 매번 원격 DB에 왕복해 화면을 옮기거나 버튼 하나 누를 때마다도
    쓸데없이 조회가 반복됐다. 실제 적립금 차감/환불은 이 zp_uid 경로가 아니라
    member_id 기반 wallet_db 쪽에서만 일어나므로(current_member_id() 필요),
    여기 잔액은 분쟁 위험이 있는 구매 확정 값이 아니라 화면 표시용 — 3초
    TTL로 짧게 캐싱해도 안전하다."""
    from zero_phone_db import get_user

    return get_user(zp_uid)


def render_wallet_bar(*, show_my_info_trigger: bool = True) -> int | None:
    """로그인 시에만 상단 잔액 바. 미로그인 시 배너는 인증 필요 클릭 때만.

    show_my_info_trigger=False면 "내정보" 버튼/다이얼로그 자체를 아예 안 그린다 —
    메인 화면에만 필요하고 다른 상세페이지에서는 불필요하다는 요청."""
    from shared_ui_styles import wallet_bar_button_css
    from zero_phone_db import TEST_USER_ID, init_zero_phone_tables, login_test_user

    # 2026-09-12: AUTH_BANNER_DISMISSED(× 클릭이 세팅하는 1회성 이벤트)를 매
    # rerun 시작 시 여기서 한 번만 소비해 AUTH_BANNER_JUST_DISMISSED로 옮겨
    # 둔다 — render_wallet_bar()는 페이지 종류와 무관하게 매 rerun마다 정확히
    # 한 번, 가장 먼저 실행되므로, 이렇게 하면 "닫은 직후의 그 다음 rerun
    # 1번" 동안만 True였다가 그 다음 rerun에서 자동으로 False로 재계산된다
    # (login_gate 독스트링 참고 — 이 화면 안쪽 여러 곳에서 몇 번을 읽든 값이
    # 안 바뀌어야, 방금 dismissed 이벤트와 무관한 진짜 새 클릭까지 실수로
    # 삼켜버리지 않는다).
    st.session_state[AUTH_BANNER_JUST_DISMISSED] = st.session_state.pop(AUTH_BANNER_DISMISSED, False)

    inject_app_haptic()
    init_zero_phone_tables()

    if current_member_id() and st.session_state.get(AUTH_RESUME_FLAG):
        _finish_auth_success()

    toast = st.session_state.pop("wallet_toast", None)
    if toast:
        st.success(toast)

    render_auth_banner()

    zp_uid = st.session_state.get("zp_user_id")
    if zp_uid:
        zp_row = _cached_zp_user(zp_uid)
        if zp_row:
            st.session_state.zp_point_balance = zp_row["point_balance"]
            st.session_state.zp_is_premium = zp_row["is_premium"]
        else:
            st.session_state.pop("zp_user_id", None)

    member_id = current_member_id() if not zp_uid else None

    if st.session_state.get("wallet_show_charge") and member_id:
        st.session_state.pop("wallet_show_charge", None)
        charge_dialog()

    if not member_id and not zp_uid:
        # 2026-09-02: 예전엔 여기서 "개발용 테스트 로그인" 버튼을 사용자에게 직접
        # 노출했는데, 애플 심사(가이드라인 2.2 베타 테스트)에서 "테스트/평가판
        # 버전처럼 보인다"고 반려됨 — ensure_member_or_banner()가 이미 쓰던
        # "테스트 기간엔 버튼 없이 조용히 로그인" 패턴으로 통일한다. 카카오
        # 연동이 완료되면(kakao_configured()) _testing_period_active()가
        # 자동으로 False가 되면서 이 우회 자체가 꺼진다.
        if _testing_period_active():
            user, is_new = login_test_user(TEST_USER_ID)
            st.session_state.zp_user_id = user["user_id"]
            st.session_state.zp_point_balance = user["point_balance"]
            st.session_state.zp_is_premium = user["is_premium"]
            if is_new:
                st.session_state.wallet_toast = "가입 완료! 5,000P 지급"
            st.rerun()
        # 2026-09-05: 정식 출시 — "앱을 처음 열 때부터 로그인을 강제하진 않지만,
        # 구매·구매내역·적립금내역(=내정보)을 보려고 하면 그 시점에 간편인증을
        # 요구하고, 한 번 인증하면 그 방문 동안은 다시 안 묻는다"는 요구사항.
        # 카카오 연동 전엔(_testing_period_active) 위에서 이미 조용히 로그인
        # 처리하니 여기 도달하지 않는다 — 아래는 실제 인증이 켜진 뒤에만 탄다.
        if show_my_info_trigger:
            st.markdown(wallet_bar_button_css(), unsafe_allow_html=True)
            with st.container(key="my_info_trigger_wrap"):
                if st.button("👤 내정보", key="my_info_trigger_btn", use_container_width=True):
                    # 2026-09-10: 다른 막힌 기능과 동일하게 login_gate 경로로 통일 —
                    # 로그인 안 했으면 통합 안내창을 매번 띄운다(AUTH_BANNER_OPEN
                    # 가드로 이미 떠 있으면 중복 안 함).
                    if not st.session_state.get(AUTH_BANNER_OPEN):
                        open_auth_banner(resume="my_info_dialog")
                    st.rerun()
        return None

    # 예전엔 이 정보(적립금/ID/로그아웃)를 화면마다 상단에 항상 띄워뒀는데, 페이지를
    # 옮길 때마다 계속 보여서 거슬린다는 요청 — 메인 화면 우상단의 "내정보" 버튼을
    # 눌러야만 뜨는 창으로 옮긴다. 다른 상세페이지에서는 이 버튼 자체가 불필요하다는
    # 요청이라 show_my_info_trigger=False면 아예 안 그린다(그 페이지들 상단에 빈
    # 공간을 남기던 원인이기도 했다). 로그아웃도 요즘 앱들처럼 앱을 완전히 닫으면
    # 세션이 알아서 끊기니 상시 노출할 필요가 없다는 게 사용자 판단(자동 로그아웃
    # 로직 자체를 새로 만든 건 아니고, 기존 세션 유지 방식은 그대로 둠).
    if show_my_info_trigger:
        st.markdown(wallet_bar_button_css(), unsafe_allow_html=True)
        with st.container(key="my_info_trigger_wrap"):
            if st.button("👤 내정보", key="my_info_trigger_btn", use_container_width=True):
                st.session_state["my_info_dialog_open"] = True
                st.rerun()

    if st.session_state.get("my_info_dialog_open"):
        _my_info_dialog(zp_uid=zp_uid, member_id=member_id)

    return member_id


@_dialog_decorator("내정보")
def _my_info_dialog(*, zp_uid: str | None, member_id: int | None) -> None:
    if zp_uid:
        bal = int(st.session_state.get("zp_point_balance", 0))
        tag = zp_uid if len(zp_uid) <= 16 else zp_uid[:12] + "…"
        st.markdown(f"**현재 보유 적립금: {bal:,}점** · ID `{tag}`")
        if st.button("로그아웃", key="zp_logout_btn", use_container_width=True, type="secondary"):
            from user_scope import clear_user_session

            for key in ("zp_user_id", "zp_point_balance", "zp_is_premium"):
                st.session_state.pop(key, None)
            clear_user_session()
            st.session_state["my_info_dialog_open"] = False
            st.rerun()
    else:
        bal = get_balance(member_id)
        tag = st.session_state.get("oauth_hash_display", "ID")
        st.markdown(f"**적립금 {bal:,}P** · ID `{tag}` · v{NOTICE_VERSION}")
        bc1, bc2 = st.columns(2)
        with bc1:
            if st.button("충전", key="wallet_charge_btn", use_container_width=True, type="secondary"):
                # charge_dialog()를 여기서 바로 부르면 이미 열려있는 dialog 위에
                # 또 다른 dialog를 겹쳐 여는 셈이라, 기존 코드 다른 곳에서 쓰던
                # 방식(플래그를 세워두고 다음 렌더에서 별도로 열기) 그대로 따른다.
                st.session_state["my_info_dialog_open"] = False
                st.session_state["wallet_show_charge"] = True
                st.rerun()
        with bc2:
            if st.button("로그아웃", key="wallet_logout_btn", use_container_width=True, type="secondary"):
                logout()
                st.session_state["my_info_dialog_open"] = False
                st.rerun()

    if st.button("닫기", key="my_info_dialog_close_btn", use_container_width=True):
        st.session_state["my_info_dialog_open"] = False
        st.rerun()


def deduct_after_result(
    member_id: int,
    service: str,
    ref_id: str,
    *,
    game_count: int = 5,
    quantity: int = 5,
) -> bool:
    """thunder/hedge/auto — 조합시작(구매확정) 시 차감. hedge/auto는 조합 생성·
    배정을 확인한 뒤 이 함수를 부르고, thunder는 차감 후 번호 저장이 끝내
    안 되면 wallet_db.sweep_stale_thunder_pending가 자동 환불한다. 고급필터는
    구독형이라 advanced_subscription_dialog()가 구독 시작 시점에 별도 처리."""
    if service == "thunder":
        cost = calc_thunder_cost(game_count)
        reason = f"thunder:{game_count}games"
    elif service == "hedge":
        cost = calc_hedge_cost(quantity)
        reason = f"hedge:{quantity}combos"
    elif service == "auto":
        cost = calc_auto_cost(quantity)
        reason = f"auto:{quantity}qty"
    else:
        return False

    return deduct_points(member_id, cost, reason, ref_id)
