import streamlit as st
import streamlit.components.v1 as components
from birthday_db import get_user_birthdays
from lucky_numbers import calculate_all_lucky_numbers
from lotto_stats import get_number_weights, get_resolved_pattern_rules, get_thunder_filter_config
import json
import uuid

from auth_kakao import current_member_id
from user_scope import (
    current_birthday_scope,
    get_or_create_guest_id,
    guest_id_cookie_sync_html,
    init_guest_scope,
    internal_nav_href,
)
from wallet_ui import (
    deduct_after_result,
    insufficient_balance_dialog,
    open_insufficient_balance_dialog,
    points_notice_dialog,
    INSUFFICIENT_BALANCE_OPEN,
)
from wallet_db import (
    calc_thunder_cost,
    record_thunder_pending,
    settle_thunder_pending,
    sweep_stale_thunder_pending,
)

# ── 번개조합 선택 색상 단일 정의 (삭제수/고정수/행운수) ──
# 이 3가지 색상은 반드시 여기서만 정의합니다. 다른 파일·CSS 블록에 중복 정의하지 마세요.
# 레이아웃·진동·통계 등 다른 작업을 할 때도 이 값을 임의로 변경하지 마세요.
THUNDER_COLOR_DELETE = "#64748B"   # 삭제수: 회색
THUNDER_COLOR_FIXED = "#FF9800"    # 고정수: 오렌지
THUNDER_COLOR_LUCKY = "#F0ABFC"    # 행운수: 연핑크

def render():
    init_guest_scope()
    # 게스트 식별자를 쿠키로도 남겨둔다(자동구매/타로 페이지엔 이미 있던 동기화인데
    # 번개조합엔 빠져 있었다) — 네이티브 앱은 ?gid= 쿼리파라미터로 항상 정확한 값을
    # 실어주지만, 모바일 브라우저로 직접 접속하는 경우엔 이게 없으면 "홈"으로 갔다가
    # 다시 들어올 때 게스트 식별자가 매번 새로 생성돼 저장내역이 안 보이던 원인이었다.
    if not st.session_state.get("_guest_id_confirmed"):
        components.html(guest_id_cookie_sync_html(get_or_create_guest_id()), height=0)
    # ─── 데이터 로드 및 행운수 계산 ───
    # "관리자 행운수"(admin_lucky) 기능은 완전히 제거했다 — 실제로는 메인 화면
    # 캐릭터 이미지 주변 장식용 숫자 볼(user_page.py의 lucky_display)과 동일한,
    # admin이 매주 감으로 손수 입력하던 리스트가 조합 생성에까지 몰래 섞여 들어가고
    # 있었다(과거 데이터 근거 전혀 없음) — 조합에는 절대 반영되면 안 된다는 요청.
    # 2026-09-10(사용자 지시): 조합시작 시 차감했지만 번호 생성·저장이 끝내
    # 안 된 미정산 건을 자동 환불한다(안티·액땜/자동구매와 같은 "실패 시 환불"
    # 정책 통일). 10분 지나도 저장 안 됐으면 환불. 정상 저장되면 th_save
    # 처리부에서 먼저 정산 처리돼 여기 안 걸린다.
    _sweep_mid = current_member_id()
    if _sweep_mid:
        _refunded = sweep_stale_thunder_pending(_sweep_mid)
        if _refunded:
            st.session_state["thunder_refund_toast"] = _refunded

    user_id = current_birthday_scope()
    birthdays = get_user_birthdays(user_id)

    if birthdays:
        mmdd_list = [b["mmdd"] for b in birthdays]
        family_lucky = calculate_all_lucky_numbers(mmdd_list)
    else:
        family_lucky = []

    js_lucky_array = str(family_lucky)
    # 번호별 과거(1회~최신회차) 출현 가중치 — 그동안 완전 무작위이던 나머지 자리
    # 채우기를 이 가중치 기반 추첨으로 바꾼다(과거 데이터 근거 요구사항). 회차가
    # 쌓일수록 get_number_weights()가 다시 계산되어 패턴도 같이 갱신된다.
    js_number_weights = json.dumps(get_number_weights())
    js_filter_config = json.dumps(get_thunder_filter_config())
    # 2026-09-05: 1241회차부터 — 1차+2차+4차 필터를 통과한 조합 풀(고정,
    # 삭제/소비되지 않는 참고용 샘플)에서 사용자가 지금 고른 고정수/삭제수
    # 조건에 맞는 게 있으면 그걸 우선 쓰고, 없는 자리만 기존 방식(가중치
    # 추첨+자연분포 필터)으로 채운다.
    try:
        from auto_purchase_service import _next_draw_round
        from marketing_db import get_random_pool_combos

        js_pool_combos = json.dumps(get_random_pool_combos(_next_draw_round()))
    except Exception:
        js_pool_combos = "[]"
    # 관리자가 대시보드(기준값패턴 업로드)에서 엑셀로 올린 과거데이터 근거 규칙
    # 전체 — 하드코딩했던 8개 유형지표는 이 업로드 시스템으로 완전히 교체됐다
    # (2026-08-21, 사용자 확인: 기존 8개 지표는 업로드 파일에 다 반영돼 있음).
    # 재업로드 전까지는 이 패턴이 계속 기준값으로 쓰인다.
    js_pattern_rules = json.dumps(
        [
            {"targets": sorted(r["targets"]), "min": r["min"], "max": r["max"]}
            for r in get_resolved_pattern_rules()
        ]
    )
    has_birthdays = bool(birthdays)

    # 결과저장 — 실제 클릭이 최상위 문서의 진짜 <a>에서 일어나야 브라우저가 이동을
    # 허용한다(components.html iframe은 sandbox에 allow-top-navigation 권한이 아예
    # 없어서 스크립트로 대신 눌러주는 건 불가능 — 실기기 콘솔에서 직접 확인된 제약).
    # href는 아래 동기화 스크립트가 iframe의 window.currentResults를 same-origin으로
    # 읽어와 미리 채워둔다.
    #
    # (진단 기록) "결과저장을 눌러도 저장이 안 되고 화면만 멈춘다"는 신고의 실제
    # 원인은 이 동기화 스크립트에 있었다 — "한 번만 setInterval 걸기" 플래그를
    # 최상위 document(재생성돼도 안 사라짐)에 저장해서, 결제 확인 후 rerun으로 이
    # 폴링 iframe이 통째로 다시 만들어지면 "이미 걸려있네" 하고 새 인터벌을 안
    # 걸어버렸다. 그 사이 이전 iframe(과 그 인터벌)은 이미 사라진 상태라, 조합이
    # 다 생성된 후에도 href가 계속 빈 상태(?page=thunder)로 멈춰 있었던 것 — 그래서
    # 클릭해도 아무것도 저장되지 않은 채 그냥 재로딩만 됐다. 아래에서는 이 폴링
    # iframe이 새로 만들어질 때마다 매번 자기 인터벌을 새로 건다.
    if st.query_params.get("th_save"):
        raw = st.query_params.get("th_save") or ""
        if "th_save" in st.query_params:
            del st.query_params["th_save"]
        combos = []
        for group in raw.split(","):
            parts = group.split("-")
            if len(parts) != 6:
                continue
            try:
                combos.append(tuple(int(n) for n in parts))
            except ValueError:
                continue
        if combos:
            from auto_purchase_service import _next_draw_round
            from marketing_db import init_marketing_tables, save_guest_generated_combos

            init_marketing_tables()
            save_guest_generated_combos(
                get_or_create_guest_id(), "thunder", _next_draw_round(), combos
            )
            # 번호가 실제로 저장됐으니, 조합시작 때 잡아둔 미정산 차감을 정산
            # 완료로 표시한다(자동 환불 대상에서 제외). 세션에 ref가 남아 있으면
            # 그걸로, 재연결 등으로 유실됐으면 이 회원의 가장 오래된 미정산 건을 정산.
            _settle_mid = current_member_id()
            if _settle_mid:
                settle_thunder_pending(
                    _settle_mid, st.session_state.pop("thunder_pending_ref", None)
                )
            st.session_state["thunder_history_blink"] = True
            # 저장 후 페이지가 맨 위로 리로드되는데, 저장내역은 화면 맨 아래(스크롤
            # 필요)에 있어서 저장이 됐는지 안 됐는지 알기 어렵다는 신고가 있었다 —
            # 스크롤 없이 바로 보이는 위치(제목 바로 아래)에 저장 완료 안내를 띄운다.
            st.session_state["thunder_save_toast"] = True
            # 2026-09-10(사용자 지시): 조합 생성·저장이 끝났으니 고정수·삭제수·
            # 행운수 선택을 자동으로 비운다 — 다음 iframe 렌더에서 localStorage를
            # 지우도록 플래그를 남긴다(지난 선택이 남은 걸 모르고 또 생성하는 것 방지).
            st.session_state["thunder_clear_selections"] = True
        # 생성·저장이 끝났으니 "생성 중" 상태 해제 — 조합시작 버튼/게임수 선택을
        # 다시 활성화한다(아래 참고).
        st.session_state.pop("thunder_approved", None)
        st.rerun()

    if st.session_state.get("open_thunder_dialog"):
        g = int(st.session_state.get("open_thunder_dialog_games", 5))

        def _thunder_dialog_close(confirmed: bool, g: int = g) -> None:
            st.session_state["open_thunder_dialog"] = False
            if not confirmed:
                return
            # 2026-09-08 수정: "테스트 기간이라 차감 성공 여부와 무관하게 진행"
            # 하던 leftover 로직이 카카오 실연동 후에도 그대로 남아있어서,
            # 적립금이 부족해도 조합 생성이 그냥 진행되는 버그가 있었다(실측
            # 확인: member 105 잔액 0인 상태). 차감이 실제로 성공했을 때만
            # 진행시킨다.
            from sales_window import SALES_WINDOW_BANNER, is_sales_window_open

            if not is_sales_window_open():
                # 다이얼로그가 열려있는 사이 판매시간대 경계를 넘는 경우 대비
                # (자동구매와 동일하게 확정 시점에도 한 번 더 확인).
                st.session_state["thunder_purchase_error"] = SALES_WINDOW_BANNER
                return
            mid = current_member_id()
            if not mid:
                st.session_state["thunder_purchase_error"] = "로그인이 필요합니다."
                return
            ref = f"thunder:{mid}:{uuid.uuid4().hex[:10]}"
            if not deduct_after_result(mid, "thunder", ref, game_count=g):
                # 2026-09-08(사용자 지시): "부족합니다" 문구만 띄우고 끝내지 않고,
                # 그 자리에서 바로 충전할 수 있는 통합 창을 띄운다(자동구매·
                # 안티·액땜조합과 동일 — wallet_ui.open_insufficient_balance_dialog).
                open_insufficient_balance_dialog(calc_thunder_cost(g))
                return
            # 2026-09-10: 차감은 됐지만 번호는 아직 브라우저에서 생성 전 —
            # '미정산'으로 기록해 두고, 번호가 저장되면(th_save) 정산, 10분 내
            # 저장 안 되면(생성 실패·이탈) 다음 진입 때 자동 환불한다.
            record_thunder_pending(mid, ref, calc_thunder_cost(g), g)
            st.session_state["thunder_pending_ref"] = ref
            st.session_state["thunder_approved"] = True
            st.session_state["thunder_auto_run"] = g

        points_notice_dialog("thunder", game_count=g, on_close=_thunder_dialog_close)

    th_auto_run = st.session_state.pop("thunder_auto_run", None)
    # thunder_approved는 "방금 확정 → 자동 생성 도는 중" 표시로만 쓴다. 이번 렌더가
    # 그 자동 생성 사이클(th_auto_run 있음)이 아니면, 남아 있는 approved는 이미
    # 끝난(또는 중간에 끊긴) 생성의 잔재이므로 지운다 — 안 지우면 생성 실패 시
    # 조합시작 버튼이 계속 비활성으로 묶여 다시 시작을 못 한다.
    if not th_auto_run:
        st.session_state.pop("thunder_approved", None)
    thunder_generating = bool(st.session_state.get("thunder_approved"))
    th_approved_js = "true" if thunder_generating else "false"
    th_auto_run_js = str(th_auto_run) if th_auto_run else "null"
    reveal_version_js = str(st.session_state.get("thunder_reveal_version", 1))
    # 조합 저장 직후 1회: iframe이 localStorage의 고정수·삭제수·행운수 선택을 비운다.
    clear_selections_js = "true" if st.session_state.pop("thunder_clear_selections", False) else "false"
    # 연출 타입 순환 저장 키는 member_id(로그인 스코프) 대신 guest_id를 쓴다 — 개발용
    # Mock 카카오 로그인은 누를 때마다 매번 새 member_id를 발급하고(uuid4), 모바일에서는
    # Streamlit 세션 재연결(백그라운드 전환·네트워크 끊김 등)로 재로그인이 잦은데, 그때마다
    # 순환 저장 키가 바뀌어서 매번 1번 타입으로 리셋되는 게 "한 타입만 계속 보임" 신고의
    # 원인이었다. guest_id는 기기에 영속되도록 이미 설계돼 있어 이 문제가 없다.
    reveal_scope_js = get_or_create_guest_id().replace("\\", "\\\\").replace("'", "\\'")

    # ─── 커스텀 CSS ───
    st.markdown("""
        <style>
        /* 안드로이드 웹뷰 강제 다크모드 대응 — 예전엔 최상위 문서에 이 처리를
           components.html(JS)로만 걸어놨는데, 그건 별도 iframe이 새로 만들어지고
           로드·실행되는 시간만큼 늦게 적용된다. "결과저장" 버튼은 진짜 페이지
           새로고침(navigate)을 거치는데, 그 새로고침 순간 강제 다크모드가 먼저
           반영되고 나서야 이 CSS/JS가 뒤따라와 화면이 잠깐 반전됐다가 정상으로
           돌아오는 "이상한 화면" 신고로 이어졌다. 이 <style> 태그는 iframe을
           안 거치고 최상위 문서 자체에 바로 얹히는 일반 CSS라 좀 더 일찍 적용된다.
           (참고: 이것만으로 깜빡임이 완전히 없어진다는 보장은 없다 — 강제 다크모드가
           최초 페인트 시점에 한 번만 판단하는 기기라면 그 찰나는 여전히 남을 수 있다.) */
        :root { color-scheme: light !important; }
        /* 이 페이지 바깥(최상위 문서)엔 어두운 배경이 안 걸려있어서, 번호판 등
           대부분의 어두운 느낌은 사실 components.html 번호판 iframe 내부 자체
           배경(body{background-color:#0F172A} — 그 iframe 문서 안에서만 적용됨)
           이었다. 그 iframe이 아직 안 뜬 최상위 문서 맨 위쪽은 Streamlit 기본
           밝은 배경이 그대로 보여 "빈 공간"처럼 느껴졌다(생일/행운수 페이지와
           동일한 원인). 최상위 문서 자체에도 같은 색을 걸어 통일한다. */
        .stApp { background-color: #12182b; }
        html, body, #root, .stApp, [data-testid="stAppViewContainer"],
        [data-testid="stAppViewContainer"] > section.main {
            overflow-x: hidden !important;
        }
        /* .block-container는 기본적으로 위쪽 96px를 Streamlit 자체 헤더(메뉴바)
           자리로 비워둔다 — 그 헤더는 아래에서 숨기는데 비운 공간은 안 없어져서
           실제로 진짜 빈 공간이 생겼다(자동구매 페이지는 이미 이 처리가 있었음).
           실측 확인 후 자동구매와 동일하게 맞춘다. */
        .block-container { padding-top: 10px !important; }
        header[data-testid="stHeader"], section[data-testid="stSidebar"] {
            display: none !important;
        }
        /* PC 녹화용: 480px 이상 뷰포트에서만 폭 제한 (모바일 <480px 미적용) */
        @media (min-width: 480px) {
            .block-container {
                max-width: 480px !important;
                margin-left: auto !important;
                margin-right: auto !important;
                padding-left: 12px !important;
                padding-right: 12px !important;
            }
            div[data-testid="stHtml"] iframe,
            div[data-testid="stHtmlIFrame"] iframe {
                max-width: 480px !important;
                margin-left: auto !important;
                margin-right: auto !important;
                display: block !important;
            }
        }
        .main-title {
            font-size: 32px;
            font-weight: 800;
            color: #FFB800;
            text-align: center;
            margin-bottom: 20px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        div[data-testid="stVerticalBlock"] > div:has(div.main-title) {
            padding: 0;
        }
        div[data-testid="stButton"] > button {
            background: linear-gradient(180deg, #ffffff 0%, #e2e8f0 100%) !important;
            border: none !important;
            border-radius: 12px !important;
            color: #0F172A !important;
            font-weight: 800 !important;
            transition: transform 0.12s ease, box-shadow 0.12s ease !important;
            box-shadow:
                0 4px 0 #94a3b8,
                0 6px 14px rgba(0, 0, 0, 0.28),
                inset 0 1px 0 rgba(255, 255, 255, 0.55) !important;
        }
        div[data-testid="stButton"] > button:hover {
            box-shadow:
                0 5px 0 #94a3b8,
                0 9px 18px rgba(0, 0, 0, 0.34),
                inset 0 1px 0 rgba(255, 255, 255, 0.6) !important;
        }
        div[data-testid="stButton"] > button:active {
            transform: scale(0.97) !important;
            box-shadow:
                0 2px 0 #94a3b8,
                0 4px 8px rgba(0, 0, 0, 0.22),
                inset 0 1px 0 rgba(255, 255, 255, 0.45) !important;
        }
        /* 모바일 좁은 화면에서 st.columns()가 기본적으로 세로로 쌓이는 문제 — 이
           페이지 전역에서 가로 배치를 강제한다(홈/생일행운수관리 버튼 2개, 게임수
           선택+조합시작 버튼 2개 모두 한 줄 유지 목적. 공간이 좁은 모바일에서
           불필요하게 세로로 쌓이면 스크롤이 길어진다). */
        div[data-testid="stHorizontalBlock"] {
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: nowrap !important;
        }
        div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
            flex: 1 1 0 !important;
            width: auto !important;
            min-width: 0 !important;
        }
        /* 상단 네비 2버튼만: 글자 한 단계 + iframe 레이어 위로 */
        div[data-testid="stHorizontalBlock"]:has(.st-key-th_nav_home_6n36s5) {
            position: relative !important;
            z-index: 50 !important;
            isolation: isolate !important;
        }
        .st-key-th_nav_home_6n36s5,
        .st-key-th_nav_bday_6n36s5 {
            position: relative !important;
            z-index: 51 !important;
        }
        .st-key-th_nav_home_6n36s5 div[data-testid="stButton"] > button,
        .st-key-th_nav_bday_6n36s5 div[data-testid="stButton"] > button {
            font-size: 16px !important;
            font-weight: 900 !important;
            line-height: 1.35 !important;
            position: relative !important;
            z-index: 52 !important;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
            text-rendering: optimizeLegibility;
            transform: translateZ(0);
        }
        .st-key-th_nav_home_6n36s5 div[data-testid="stButton"] > button p,
        .st-key-th_nav_bday_6n36s5 div[data-testid="stButton"] > button p {
            font-weight: 900 !important;
        }
        /* 저장내역 카드 CSS(.auto-purchase-banner 등)는 combo_history_ui.history_css()가
           렌더링 시점에 별도로 주입한다 — 다른 페이지와 공유하는 정의라 여기서 중복
           정의하지 않는다. */
        /* 결과저장 — components.html iframe 안에서는 브라우저 sandbox 정책상 최상위
           문서를 이동시킬 수 없어서(allow-top-navigation 권한이 없음), 진짜 <a> 링크를
           iframe 밖(진짜 Streamlit 영역)에 두고 iframe은 그 href만 갱신한다. */
        .th-save-real-btn {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 100%;
            box-sizing: border-box;
            height: 46px;
            margin: -6px 0 18px;
            border-radius: 12px;
            background: linear-gradient(180deg, #65a30d 0%, #3F6212 55%, #365314 100%);
            color: #FFFFFF !important;
            font-family: 'Noto Sans KR', sans-serif;
            font-weight: 900;
            font-size: 15px;
            text-decoration: none !important;
            box-shadow:
                0 4px 0 #1a2e05,
                0 7px 14px rgba(63, 98, 18, 0.4),
                inset 0 1px 0 rgba(255, 255, 255, 0.2);
        }
        .th-save-real-btn:active { transform: scale(0.97); }
        /* 2026-08-29: "조합시작"에서 적립금이 이미 차감된 뒤, 번호 생성 자체는
           iframe 안 JS가 담당해서(서버는 결과저장 클릭 전까진 실제 번호를 모름)
           생성=저장을 한 몸으로 묶는 게 구조적으로 불가능하다 — 라고 결론 냈었으나,
           2026-09-09에 사용자 재지시로 자동저장 방식을 다시 검토. 예전엔 "결과저장을
           스크립트로 대신 눌러주는 것"이 iframe sandbox 제약(allow-top-navigation
           권한 없음)으로 실기기에서 불가능하다고 확인돼 있었는데, 같은 날 localStorage
           게스트ID 복구 기능을 만들며 그 sandbox를 우회하는 방법(최상위 문서에
           <script> 엘리먼트를 직접 심어 그 스크립트가 iframe이 아니라 최상위 문서
           컨텍스트에서 실행되게 하는 방식, QR스캔 트리거가 이미 쓰던 것과 동일 계열)을
           확인해서, 이제는 결과가 다 나오면 사람이 누르지 않아도 자동으로 저장된다
           (아래 스크립트의 doc.createElement('script') 주입 부분 참고). 수동 버튼은
           "혹시 자동저장이 실패하면" 대비 안전망으로 작게 남겨둔다.
           색상은 이 파일에서 이미 안내 용도로 쓰던 #fbbf24(luckyWarn)와 통일. */
        .th-save-warn {
            margin: 4px 0 10px;
            padding: 10px 12px;
            background: rgba(251, 191, 36, 0.12);
            border: 1px solid rgba(251, 191, 36, 0.45);
            border-radius: 10px;
            color: #fbbf24;
            font-size: 12px;
            font-weight: 700;
            line-height: 1.5;
            text-align: center;
        }
        /* 조합시작 — 결제 확인창(points_notice_dialog)을 거쳐야 해서, 이 버튼도
           iframe 밖 진짜 Streamlit 버튼으로 둔다(같은 이유, 위 주석 참고). */
        .th-generate-label {
            font-size: 13px;
            font-weight: 800;
            color: #1E293B;
            margin: 4px 0 6px;
        }
        .st-key-th_generate_btn div[data-testid="stButton"] > button {
            background: linear-gradient(180deg, #22d3ee 0%, #06B6D4 55%, #0891b2 100%) !important;
            color: #FFFFFF !important;
            box-shadow:
                0 4px 0 #0e7490,
                0 7px 14px rgba(6, 182, 212, 0.4),
                inset 0 1px 0 rgba(255, 255, 255, 0.3) !important;
        }
        </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="main-title">⚡ 번\u200b\u200b개조합</div>', unsafe_allow_html=True)

    if st.session_state.pop("thunder_save_toast", False):
        st.success("✅ 결과가 저장됐어요! 아래로 스크롤하면 저장내역에서 확인할 수 있어요.")

    _refund_toast = st.session_state.pop("thunder_refund_toast", None)
    if _refund_toast:
        st.info(
            f"💸 이전에 조합시작 후 번호가 저장되지 않은 건이 있어 **{_refund_toast:,}P**를 자동 환불했어요."
        )

    thunder_purchase_error = st.session_state.pop("thunder_purchase_error", None)
    if thunder_purchase_error:
        st.error(f"❌ {thunder_purchase_error}")

    if st.session_state.get(INSUFFICIENT_BALANCE_OPEN):
        insufficient_balance_dialog()

    # 2026-08-28: 네이티브 앱 툴바가 이미 자체 "← 메인" 버튼을 갖고 있어서(showBack,
    # streamlit-webview.tsx) 화면 안 "메인으로" 버튼은 지웠다(옆 "생일/행운수 관리"는
    # 이제 혼자 전체 폭을 씀) — 다만 브라우저로 직접 열었을 땐 메인으로 갈 방법이
    # 없어지므로, 자리를 거의 안 차지하는 작은 로고 링크를 대신 둔다.
    from shared_ui_styles import brand_home_link_css, brand_home_link_html

    st.markdown(brand_home_link_css() + brand_home_link_html(), unsafe_allow_html=True)

    if st.button("📝 생일/행운수 관리", key="th_nav_bday_6n36s5", use_container_width=True):
        st.query_params.clear()
        st.query_params["page"] = "birthday"
        st.rerun()

    # 예전엔 여기서 postMessage + window.parent.location.href로 iframe 밖(최상위 문서)을
    # 내비게이션 시키려 했는데, Streamlit의 components.html iframe은 sandbox에
    # allow-top-navigation(-by-user-activation) 권한이 아예 없어서 실제 사용자 클릭에서
    # 바로 호출돼도 브라우저가 SecurityError로 무조건 막는다(실기기 콘솔에서 직접 확인).
    # 그래서 "결과저장"은 실제 최상위 문서에 진짜 <a> 링크를 두고 iframe은 그 href만
    # 갱신하는 방식(아래 결과저장 동기화 스크립트)으로, "조합시작" 포인트 차감은 iframe
    # 밖의 진짜 Streamlit 버튼(points_notice_dialog의 "확인 후 진행") 클릭 시점으로
    # 처리한다.

    st.markdown('<div class="th-generate-label">게임 수를 고른 뒤 조합시작을 누르세요</div>', unsafe_allow_html=True)
    gcol1, gcol2 = st.columns([1, 1.6])
    with gcol1:
        selected_game_count = st.selectbox(
            "게임 수",
            [5, 10, 15, 20],
            index=0,
            key="th_game_count_select",
            label_visibility="collapsed",
            # 생성 중에는 못 바꾸게 — 스크롤하다 실수로 건드리면 st.rerun()이
            # 걸려 iframe이 재생성되고 생성 중이던 조합이 통째로 사라진다.
            disabled=thunder_generating,
        )
    with gcol2:
        if st.button(
            "⚡ 생성 중…" if thunder_generating else "⚡ 조합시작",
            type="primary",
            use_container_width=True,
            key="th_generate_btn",
            # 생성 중 재클릭 방지 — 스크롤하다 실수로 눌러 확정창이 다시 뜨고
            # 생성이 멈추는 문제(사용자 신고 2026-09-10)를 막는다.
            disabled=thunder_generating,
        ):
            from wallet_ui import ensure_member_or_banner
            from sales_window import SALES_WINDOW_BANNER, is_sales_window_open

            # 2026-09-09(사용자 지시): 자동구매와 동일한 방식으로 판매시간대 제한
            # 확정 적용 — 세 화면이 각자 따로 관리하면 시간대가 바뀔 때 하나를
            # 빠뜨리는 사고로 이어지므로 sales_window.py 공용 모듈을 그대로 쓴다.
            if not is_sales_window_open():
                st.session_state["thunder_purchase_error"] = SALES_WINDOW_BANNER
            elif ensure_member_or_banner(
                resume="open_thunder_dialog",
                reason="번개조합 생성을 위해 간편인증이 필요합니다.",
                resume_data={"games": selected_game_count},
            ):
                st.session_state["open_thunder_dialog"] = True
                st.session_state["open_thunder_dialog_games"] = selected_game_count
                st.rerun()

    components.html("""
    <script>
    (function() {
        function safeVibrate() {
            if (typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function') {
                try { navigator.vibrate(70); } catch (e) {}
            }
        }
        const doc = window.parent.document;
        doc.querySelectorAll('div[data-testid="stButton"] button').forEach(function(btn) {
            if (btn.dataset.thVibrateBound) return;
            const label = (btn.innerText || '').trim();
            if (label.indexOf('홈') !== -1 || label.indexOf('생일/행운수 관리') !== -1) {
                btn.dataset.thVibrateBound = '1';
                btn.addEventListener('click', safeVibrate, { passive: true });
            }
        });
    })();
    </script>
    """, height=0)

    # ─── 메인 UI HTML (Grid & Logic) ───
    thunder_ui_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="color-scheme" content="light">
        <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700;900&display=swap" rel="stylesheet">
        <style>
            /* 안드로이드 웹뷰의 "강제 다크모드"가 색을 정의하지 않은 걸로 판단해 흰색
               번호 버튼 등을 임의로 어둡게 반전시키는 문제 — color-scheme을 명시해서
               이 페이지는 항상 라이트 배색이라고 웹뷰에 알려준다. */
            :root {{ color-scheme: light; }}
            * {{ font-family: 'Noto Sans KR', sans-serif; box-sizing: border-box; }}
            :root {{
                --th-delete: {THUNDER_COLOR_DELETE};
                --th-fixed: {THUNDER_COLOR_FIXED};
                --th-lucky: {THUNDER_COLOR_LUCKY};
                --th-mode-btn-h: 35px;
            }}
            /* 레이아웃 전체 10% 축소 — transform:scale은 텍스트가 별도 레이어로 래스터라이즈되며
               번져 보이는 문제가 있어서(위에서 겪은 문제와 동일 원인), 대신 zoom을 쓴다. zoom은
               실제 레이아웃 재계산을 거쳐 텍스트를 새 크기로 다시 그리므로 번짐이 없다. */
            body {{ background-color: #0F172A; color: #F8FAFC; margin: 0 auto; padding: 10px; overflow-x: hidden; width: 100%; max-width: 480px; zoom: 0.9; }}

            /* PC: 부모 창 너비 기준 (iframe 내부 media query는 iframe 폭만 보므로 JS로 pc-layout 부여) */
            html.pc-layout .number-grid {{
                grid-template-columns: repeat(7, 42px);
                justify-content: center;
                width: fit-content;
                max-width: 100%;
                margin-left: auto;
                margin-right: auto;
                min-height: 372px;
            }}
            html.pc-layout .num-cell {{
                width: 42px;
                height: 42px;
                aspect-ratio: unset;
                font-size: 13px;
            }}
            html.pc-layout .tab-container,
            html.pc-layout .result-area {{
                max-width: 360px;
                margin-left: auto;
                margin-right: auto;
            }}

            .lucky-warn-slot {{
                min-height: 22px;
                margin-bottom: 8px;
            }}
            #luckyWarn {{
                color: #fbbf24;
                text-align: center;
                margin: 0;
                font-size: 13px;
                line-height: 22px;
            }}

            .nav-container {{ display: flex; gap: 10px; margin-bottom: 20px; }}
            .nav-btn {{
                flex: 1; padding: 12px; border-radius: 12px; border: none;
                cursor: pointer; font-weight: bold; font-size: 14px;
                display: flex; align-items: center; justify-content: center; gap: 8px;
                transition: all 0.2s; background: white; color: #1E293B;
            }}
            .nav-btn:hover {{ transform: translateY(-2px ); box-shadow: 0 4px 12px rgba(0,0,0,0.3); }}

            .tab-container {{
                display: flex; background: linear-gradient(180deg, #243044 0%, #1E293B 100%);
                padding: 5px; border-radius: 12px; margin-bottom: 15px; gap: 5px;
                box-shadow:
                    0 6px 0 #0b1220,
                    0 10px 20px rgba(0, 0, 0, 0.35),
                    inset 0 1px 0 rgba(255, 255, 255, 0.08);
                transition: box-shadow 0.12s ease;
                position: relative;
                z-index: 8;
                isolation: isolate;
            }}
            .tab {{
                flex: 1;
                box-sizing: border-box;
                height: var(--th-mode-btn-h);
                min-height: var(--th-mode-btn-h);
                max-height: var(--th-mode-btn-h);
                padding: 0 10px;
                display: flex;
                align-items: center;
                justify-content: center;
                text-align: center;
                border-radius: 12px;
                border: none;
                cursor: pointer;
                font-family: 'Noto Sans KR', sans-serif;
                font-weight: 900;
                font-size: 15px;
                line-height: 1.25;
                transition: transform 0.12s ease, box-shadow 0.12s ease, background 0.12s ease;
                box-shadow:
                    0 4px 0 rgba(0, 0, 0, 0.35),
                    0 7px 14px rgba(0, 0, 0, 0.28),
                    inset 0 1px 0 rgba(255, 255, 255, 0.25);
                position: relative;
                z-index: 9;
                isolation: isolate;
                -webkit-font-smoothing: antialiased;
                -moz-osx-font-smoothing: grayscale;
                text-rendering: optimizeLegibility;
                opacity: 1;
            }}
            .tab.active {{
                background: linear-gradient(180deg, #c084fc 0%, #A855F7 55%, #9333ea 100%);
                color: #FFFFFF;
                text-shadow: none;
                box-shadow:
                    0 4px 0 #6b21a8,
                    0 7px 14px rgba(168, 85, 247, 0.45),
                    inset 0 1px 0 rgba(255, 255, 255, 0.3);
            }}
            .tab:not(.active) {{
                color: #FFFFFF;
                background: linear-gradient(180deg, #334155 0%, #1e293b 100%);
                text-shadow: none;
            }}
            .tab:not(.active):hover {{
                box-shadow:
                    0 5px 0 rgba(0, 0, 0, 0.38),
                    0 9px 18px rgba(0, 0, 0, 0.32),
                    inset 0 1px 0 rgba(255, 255, 255, 0.3);
            }}
            .tab:active {{ transform: scale(0.97); }}

            .number-grid {{
                display: grid; grid-template-columns: repeat(7, 1fr); gap: 8px;
                background: linear-gradient(180deg, #243044 0%, #1E293B 100%);
                padding: 15px; border-radius: 16px; margin-bottom: 20px;
                box-shadow:
                    0 6px 0 #0b1220,
                    0 10px 20px rgba(0, 0, 0, 0.35),
                    inset 0 1px 0 rgba(255, 255, 255, 0.08);
            }}
            .num-cell {{
                aspect-ratio: 1; display: flex; align-items: center; justify-content: center;
                background: linear-gradient(180deg, #ffffff 0%, #e2e8f0 100%);
                color: #0F172A; border-radius: 8px; font-weight: 900;
                cursor: pointer; font-size: 14px; border: 2px solid transparent;
                transition: transform 0.12s ease, box-shadow 0.12s ease, background 0.12s ease, color 0.12s ease;
                box-shadow:
                    0 3px 0 #94a3b8,
                    0 5px 10px rgba(0, 0, 0, 0.22),
                    inset 0 1px 0 rgba(255, 255, 255, 0.55);
            }}
            .num-cell:hover {{
                box-shadow:
                    0 4px 0 #94a3b8,
                    0 7px 14px rgba(0, 0, 0, 0.28),
                    inset 0 1px 0 rgba(255, 255, 255, 0.6);
            }}
            .num-cell:active {{ transform: scale(0.97); }}
            /* 선택 색상: :root 변수만 사용 (Python 상수 THUNDER_COLOR_* 와 동기화) */
            .num-cell.selected-delete {{
                background: var(--th-delete);
                color: #FFFFFF; border-color: var(--th-delete);
                text-shadow: 0 1px 2px rgba(0, 0, 0, 0.35);
                box-shadow:
                    0 3px 0 #334155,
                    0 5px 10px rgba(0, 0, 0, 0.28),
                    inset 0 1px 0 rgba(255, 255, 255, 0.2);
            }}
            .num-cell.selected-fixed {{
                background: var(--th-fixed);
                color: #FFFFFF; border-color: var(--th-fixed);
                text-shadow: 0 1px 2px rgba(0, 0, 0, 0.35);
                box-shadow:
                    0 3px 0 #c2410c,
                    0 5px 10px rgba(255, 152, 0, 0.35),
                    inset 0 1px 0 rgba(255, 255, 255, 0.25);
            }}
            .num-cell.selected-lucky {{
                background: var(--th-lucky);
                color: #831843; border-color: var(--th-lucky);
                text-shadow: 0 1px 1px rgba(255, 255, 255, 0.45);
                box-shadow:
                    0 3px 0 #c026d3,
                    0 5px 10px rgba(240, 171, 252, 0.45),
                    inset 0 1px 0 rgba(255, 255, 255, 0.35);
            }}
            
            .result-area {{ margin-top: 20px; display: flex; flex-direction: column; gap: 10px; }}
            .result-row {{
                background: linear-gradient(145deg, #0A0A0F 0%, #050508 55%, #0D0D1A 100%);
                padding: 15px; border-radius: 12px;
                border: 1px solid #1A1A2E;
                display: flex; justify-content: center; gap: 8px;
                box-shadow:
                    0 4px 0 #000000,
                    0 7px 16px rgba(0, 0, 0, 0.55),
                    inset 0 1px 0 rgba(255, 255, 255, 0.04);
            }}
            .result-row.reveal {{
                opacity: 0;
                will-change: transform, opacity;
                animation: resultRowReveal 1s cubic-bezier(0.34, 1.45, 0.64, 1) forwards;
            }}
            /* 버전1: 슬라이드 업 + 볼 글로우 */
            /* 메인화면(user_page) 로또볼 3D 스타일 재사용 */
            .ball {{
                width: 35px; height: 35px; border-radius: 50%; display: flex;
                align-items: center; justify-content: center; color: white;
                font-weight: 900; font-size: 15px;
                text-shadow: 1px 1px 2px rgba(0,0,0,0.8);
                box-shadow:
                    2px 3px 5px rgba(0,0,0,0.5),
                    inset -3px -3px 5px rgba(0,0,0,0.4),
                    inset 2px 2px 4px rgba(255,255,255,0.6);
            }}
            .result-row.reveal .ball {{
                will-change: box-shadow, filter;
                animation: ballGlowReveal 1.1s ease-out forwards;
            }}
            .result-row.reveal .ball:nth-child(1) {{ animation-delay: 0.04s; }}
            .result-row.reveal .ball:nth-child(2) {{ animation-delay: 0.08s; }}
            .result-row.reveal .ball:nth-child(3) {{ animation-delay: 0.12s; }}
            .result-row.reveal .ball:nth-child(4) {{ animation-delay: 0.16s; }}
            .result-row.reveal .ball:nth-child(5) {{ animation-delay: 0.20s; }}
            .result-row.reveal .ball:nth-child(6) {{ animation-delay: 0.24s; }}

            /* 버전2·3 전용 (버전1 reveal CSS와 완전 분리 — JS Web Animations 구동) */
            .mystic-v2-row, .mystic-v3-row {{
                position: relative;
                overflow: visible;
            }}
            .mystic-v2-track, .mystic-v3-track {{
                display: flex;
                justify-content: center;
                gap: 8px;
                position: relative;
                z-index: 2;
            }}
            .mystic-v2-aura {{
                position: absolute;
                inset: 0;
                border-radius: 12px;
                background: linear-gradient(180deg, rgba(2, 6, 23, 0.9) 0%, rgba(6, 182, 212, 0.35) 45%, rgba(168, 85, 247, 0.65) 100%);
                z-index: 0;
                pointer-events: none;
                transform-origin: bottom center;
            }}
            .mystic-v2-spark {{
                position: absolute;
                width: 6px;
                height: 6px;
                border-radius: 50%;
                background: #e0f2fe;
                box-shadow: 0 0 10px 3px rgba(34, 211, 238, 0.9);
                pointer-events: none;
                z-index: 1;
            }}
            .mystic-v3-rift {{
                position: absolute;
                inset: -6px;
                border-radius: 16px;
                background: radial-gradient(ellipse at center, rgba(168, 85, 247, 0.55) 0%, rgba(15, 23, 42, 0) 72%);
                z-index: 0;
                pointer-events: none;
            }}
            .mystic-v3-row .ball {{
                will-change: transform, opacity, filter;
            }}

            @keyframes resultRowReveal {{
                0% {{
                    opacity: 0;
                    transform: translateY(42px);
                }}
                45% {{
                    opacity: 0.75;
                    transform: translateY(-7px);
                }}
                62% {{
                    opacity: 1;
                    transform: translateY(4px);
                }}
                78% {{
                    transform: translateY(-3px);
                }}
                90% {{
                    transform: translateY(1px);
                }}
                100% {{
                    opacity: 1;
                    transform: translateY(0);
                }}
            }}
            @keyframes ballGlowReveal {{
                0% {{
                    filter: brightness(0.65);
                    box-shadow: 0 0 0 rgba(255, 255, 255, 0);
                }}
                28% {{
                    filter: brightness(1.2);
                    box-shadow:
                        0 0 14px 5px rgba(255, 255, 255, 0.75),
                        0 0 26px 10px rgba(168, 85, 247, 0.42);
                }}
                55% {{
                    filter: brightness(1.08);
                    box-shadow:
                        0 0 18px 7px rgba(255, 255, 255, 0.9),
                        0 0 32px 12px rgba(192, 132, 252, 0.55);
                }}
                78% {{
                    filter: brightness(1.02);
                    box-shadow:
                        0 0 10px 3px rgba(255, 255, 255, 0.45),
                        0 0 18px 6px rgba(168, 85, 247, 0.22);
                }}
                100% {{
                    filter: brightness(1);
                    box-shadow:
                        2px 3px 5px rgba(0,0,0,0.5),
                        inset -3px -3px 5px rgba(0,0,0,0.4),
                        inset 2px 2px 4px rgba(255,255,255,0.6);
                }}
            }}
        </style>
    </head>
    <body>
        <div class="tab-container">
            <div id="tab-delete" class="tab active" onclick="setMode('delete')">삭\u200b제수</div>
            <div id="tab-fixed" class="tab" onclick="setMode('fixed')">고\u200b정수</div>
            <div id="tab-lucky" class="tab" onclick="setMode('lucky')">행\u200b운수</div>
        </div>

        <div class="lucky-warn-slot">
            <p id="luckyWarn" style="display:none;">생일/행운수 관리에서 먼저 등록하세요.</p>
        </div>

        <div class="number-grid" id="numberGrid"></div>


        <div class="result-area" id="resultArea"></div>

        <script>
            // ── 1) 초기 상태: 삭제수 탭, 모든 선택 비움, DB 행운수는 보관만 ──
            let thunderApproved = {th_approved_js};
            const autoRunCount = {th_auto_run_js};
            let selectedGameCount = autoRunCount || 5;

            let selectedDelete = new Set();
            let selectedFixed = new Set();
            let luckyNumbers = new Set();
            const registeredFamilyLucky = {js_lucky_array};
            const numberWeights = {js_number_weights};
            let poolCombos = {js_pool_combos};
            const thunderFilter = {js_filter_config};
            const patternRules = {js_pattern_rules};
            const hasBirthdays = {'true' if has_birthdays else 'false'};
            let luckyLoaded = false;

            // ── 고정수/삭제수/행운수 선택을 localStorage에 보존 ──
            // 2026-09-10(중대 버그 수정): 이 선택값들은 components.html iframe의
            // JS 메모리(let Set)에만 있었다. 그런데 "조합시작"을 누르면
            //   ① 로그인 게이트 → st.rerun() (iframe 파기·재생성)
            //   ② 적립금 확정창 "확인 후 진행" → st.rerun() (또 파기·재생성)
            // 두 번의 재생성을 거친 뒤 autoRunCount로 자동 생성이 도는데, 그때
            // iframe은 selectedFixed/selectedDelete가 빈 Set인 새 인스턴스라
            // 사용자가 고른 고정수·삭제수가 전부 무시된 채 조합이 생성됐다
            // ("고정수·삭제수 적용해도 엉터리"의 실제 원인). reveal 사이클처럼
            // localStorage에 넣어 iframe이 다시 만들어져도 복원되게 한다.
            const THUNDER_SEL_STORE = 'thunder_selections_v1';
            function persistSelections() {{
                try {{
                    localStorage.setItem(THUNDER_SEL_STORE, JSON.stringify({{
                        fixed: Array.from(selectedFixed),
                        deleted: Array.from(selectedDelete),
                        lucky: Array.from(luckyNumbers),
                    }}));
                }} catch (e) {{}}
            }}
            (function restoreSelections() {{
                // 조합 저장 직후 1회: 선택을 자동으로 비운다(사용자 지시 2026-09-10).
                if ({clear_selections_js}) {{
                    try {{ localStorage.removeItem(THUNDER_SEL_STORE); }} catch (e) {{}}
                    return;
                }}
                try {{
                    const raw = localStorage.getItem(THUNDER_SEL_STORE);
                    if (!raw) return;
                    const s = JSON.parse(raw);
                    if (Array.isArray(s.fixed)) selectedFixed = new Set(s.fixed.slice(0, 5));
                    if (Array.isArray(s.deleted)) selectedDelete = new Set(s.deleted);
                    if (Array.isArray(s.lucky) && s.lucky.length) {{
                        luckyNumbers = new Set(s.lucky);
                        luckyLoaded = true;
                    }}
                    // 같은 번호가 두 곳에 들어가는 모순 방지(삭제수 우선 제거)
                    selectedDelete.forEach(n => {{ selectedFixed.delete(n); luckyNumbers.delete(n); }});
                    selectedFixed.forEach(n => luckyNumbers.delete(n));
                }} catch (e) {{}}
            }})();
            // 최상위 문서(iframe 밖)의 결과저장 동기화 스크립트가 same-origin으로 읽어가야
            // 하므로, let이 아니라 window의 프로퍼티로 선언한다(let은 이 iframe의 window에도
            // 안 붙어서 외부에서 읽을 수 없다).
            window.currentResults = [];
            // 게임이 2초 간격으로 하나씩 순차 추가되므로, 목표 게임 수를 같이 노출해서
            // 자동저장 스크립트가 "다 채워졌는지" 판단할 수 있게 한다.
            window.expectedGameCount = selectedGameCount;
            const activeRevealVersion = {reveal_version_js};
            const REVEAL_STORE = 'thunder_reveal_cycle_{reveal_scope_js}';
            let runRevealVersion = activeRevealVersion;
            let genRunId = 0;
            let isGenerating = false;
            let activeGenTimers = [];
            let activeGenIntervals = [];

            function clearActiveGeneration() {{
                activeGenTimers.forEach((id) => clearTimeout(id));
                activeGenTimers = [];
                activeGenIntervals.forEach((id) => clearInterval(id));
                activeGenIntervals = [];
            }}

            function setStartButtonEnabled(enabled) {{
                const startBtn = document.querySelector('.btn-start');
                if (startBtn) startBtn.disabled = !enabled;
            }}

            try {{
                if (!localStorage.getItem(REVEAL_STORE)) {{
                    localStorage.setItem(REVEAL_STORE, String(activeRevealVersion));
                }}
            }} catch (e) {{}}

            function consumeRevealVersion() {{
                let v = 1;
                try {{
                    v = parseInt(localStorage.getItem(REVEAL_STORE) || String(activeRevealVersion), 10);
                }} catch (e) {{}}
                if (isNaN(v) || v < 1 || v > 3) v = 1;
                const current = v;
                const next = (v % 3) + 1;
                try {{ localStorage.setItem(REVEAL_STORE, String(next)); }} catch (e) {{}}
                return current;
            }}

            function safeVibrate() {{
                if (typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function') {{
                    try {{ navigator.vibrate(70); }} catch (e) {{}}
                }}
            }}

            function showLuckyWarn(show) {{
                const el = document.getElementById('luckyWarn');
                if (el) el.style.display = show ? 'block' : 'none';
            }}

            function applyPcLayout() {{
                let parentW = window.innerWidth;
                try {{
                    parentW = window.parent.innerWidth || parentW;
                }} catch (e) {{}}
                if (parentW >= 480) {{
                    document.documentElement.classList.add('pc-layout');
                }} else {{
                    document.documentElement.classList.remove('pc-layout');
                }}
            }}
            applyPcLayout();
            window.addEventListener('resize', applyPcLayout);

            // ── 2) initGrid: 최초 로드 포함 항상 기본 흰색, 핑크는 luckyLoaded 이후만 ──
            function initGrid() {{
                const grid = document.getElementById('numberGrid');
                grid.innerHTML = '';
                for (let i = 1; i <= 45; i++) {{
                    const cell = document.createElement('div');
                    cell.className = 'num-cell';
                    if (selectedDelete.has(i)) {{
                        cell.classList.add('selected-delete');
                    }}
                    if (selectedFixed.has(i)) {{
                        cell.classList.add('selected-fixed');
                    }}
                    if (luckyLoaded && luckyNumbers.has(i)) {{
                        cell.classList.add('selected-lucky');
                    }}
                    cell.innerText = i;
                    cell.onclick = () => toggleNumber(i);
                    grid.appendChild(cell);
                }}
            }}

            // ── 3) setMode: 행운수 탭 클릭 시에만 DB 데이터 로드 후 핑크 렌더링 ──
            function setMode(mode) {{
                safeVibrate();
                currentMode = mode;
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.getElementById('tab-' + mode).classList.add('active');

                if (mode === 'lucky') {{
                    if (!luckyLoaded) {{
                        luckyLoaded = true;
                        if (hasBirthdays && registeredFamilyLucky.length > 0) {{
                            luckyNumbers = new Set(registeredFamilyLucky);
                            showLuckyWarn(false);
                        }} else {{
                            luckyNumbers = new Set();
                            showLuckyWarn(true);
                        }}
                        persistSelections();
                    }}
                }} else {{
                    showLuckyWarn(false);
                }}

                initGrid();
            }}

            function toggleNumber(num) {{
                safeVibrate();
                if (currentMode === 'delete') {{
                    if (selectedDelete.has(num)) {{
                        selectedDelete.delete(num);
                    }} else {{
                        selectedDelete.add(num);
                        selectedFixed.delete(num);
                        luckyNumbers.delete(num);
                    }}
                }} else if (currentMode === 'fixed') {{
                    if (selectedFixed.has(num)) {{
                        selectedFixed.delete(num);
                    }} else {{
                        if (selectedFixed.size >= 5) return;
                        selectedFixed.add(num);
                        selectedDelete.delete(num);
                        luckyNumbers.delete(num);
                    }}
                }} else if (currentMode === 'lucky') {{
                    if (!luckyLoaded) return;
                    if (luckyNumbers.has(num)) {{
                        luckyNumbers.delete(num);
                    }} else {{
                        luckyNumbers.add(num);
                        selectedDelete.delete(num);
                        selectedFixed.delete(num);
                    }}
                }}
                persistSelections();
                initGrid();
            }}

            function pickLuckyCount() {{
                const r = Math.random();
                if (r < 0.30) return 0;
                if (r < 0.65) return 1;
                if (r < 0.90) return 2;
                return 3;
            }}

            // 나머지 빈 자리를 채울 때 완전 무작위 대신, 1회~최신회차 실제 당첨
            // 데이터의 번호별 출현 횟수(numberWeights)를 가중치로 비복원 추출한다
            // — "과거 데이터를 근거로 그 패턴 유형 우선순위로 조합이 생성돼야
            // 한다"는 요구사항. (예전엔 여기서 "관리자 행운수"라는 admin이 매주
            // 손으로 감으로 입력하던, 과거 데이터와 무관한 리스트를 섞어 넣고
            // 있었다 — 완전히 제거했다.)
            function weightedPickWithoutReplacement(count, sourcePool) {{
                const candidates = sourcePool.slice();
                const picked = [];
                for (let p = 0; p < count && candidates.length > 0; p++) {{
                    const weights = candidates.map(n => numberWeights[n] || 1);
                    const total = weights.reduce((a, b) => a + b, 0);
                    let r = Math.random() * total;
                    let cum = 0;
                    let chosenIdx = candidates.length - 1;
                    for (let i = 0; i < candidates.length; i++) {{
                        cum += weights[i];
                        if (r <= cum) {{
                            chosenIdx = i;
                            break;
                        }}
                    }}
                    picked.push(candidates[chosenIdx]);
                    candidates.splice(chosenIdx, 1);
                }}
                return picked;
            }}

            function longestConsecutiveRun(nums) {{
                if (nums.length === 0) return 0;
                const sorted = [...nums].sort((a, b) => a - b);
                let best = 1;
                let cur = 1;
                for (let i = 1; i < sorted.length; i++) {{
                    if (sorted[i] === sorted[i - 1] + 1) {{
                        cur += 1;
                        best = Math.max(best, cur);
                    }} else {{
                        cur = 1;
                    }}
                }}
                return best;
            }}

            function maxDecadeCount(nums) {{
                const bands = [
                    [1, 9], [10, 19], [20, 29], [30, 39], [40, 45]
                ];
                let best = 0;
                for (const [lo, hi] of bands) {{
                    const c = nums.filter(n => n >= lo && n <= hi).length;
                    best = Math.max(best, c);
                }}
                return best;
            }}

            function maxLastDigitCount(nums) {{
                const counts = {{}};
                nums.forEach(n => {{
                    const d = n % 10;
                    counts[d] = (counts[d] || 0) + 1;
                }});
                return Math.max(0, ...Object.values(counts));
            }}

            function violatesNaturalFilter(nums) {{
                const t = thunderFilter.thresholds;
                if (longestConsecutiveRun(nums) >= t.max_consecutive_run) return true;
                if (maxDecadeCount(nums) >= t.max_decade_count) return true;
                if (maxLastDigitCount(nums) >= t.max_last_digit_count) return true;
                return false;
            }}

            function fillRandomSlots(fixedArr, availablePool) {{
                let game = fixedArr.slice();
                const gameSet = new Set(game);
                const pool = availablePool.filter(n => !selectedFixed.has(n));

                let luckyCandidates = pool.filter(n => luckyNumbers.has(n));
                let targetLucky = pickLuckyCount();
                targetLucky = Math.min(targetLucky, luckyCandidates.length, 6 - game.length);
                luckyCandidates.sort(() => Math.random() - 0.5);
                const pickedLucky = luckyCandidates.slice(0, targetLucky);
                game = game.concat(pickedLucky);
                pickedLucky.forEach(n => gameSet.add(n));

                const remainingPool = pool.filter(n => !gameSet.has(n));
                const pickedRest = weightedPickWithoutReplacement(6 - game.length, remainingPool);
                game = game.concat(pickedRest);
                return game;
            }}

            // 관리자가 대시보드(기준값패턴 업로드)에서 올린 규칙(patternRules) 전부를
            // 대상으로, 후보 조합과 각 규칙 targets의 교집합 개수가 min~max 범위인
            // 규칙이 몇 개인지 채점한다. 하드코딩했던 8개 유형지표(홀짝·저고·끝수저고
            // ·연속쌍·AC·총합·소자배·10단위)는 이 업로드 시스템으로 완전히 교체됐다
            // (2026-08-21, 사용자 확인 — 기존 8개 지표는 업로드 파일에 다 반영돼 있음).
            // 만점을 못 채워도 가장 많이 만족한 후보를 fallback으로 쓸 수 있도록
            // matched 개수를 같이 반환한다.
            function scoreComboPattern(nums) {{
                if (patternRules.length === 0) {{
                    return {{ allPass: true, matched: 0 }};
                }}
                const comboSet = new Set(nums);
                let matched = 0;
                for (const rule of patternRules) {{
                    let overlap = 0;
                    for (const t of rule.targets) {{
                        if (comboSet.has(t)) overlap += 1;
                    }}
                    if (overlap >= rule.min && overlap <= rule.max) matched += 1;
                }}
                return {{ allPass: matched === patternRules.length, matched }};
            }}

            // 2026-09-05: 1241회차부터 — 저장된 필터 통과 조합 풀에서 지금
            // 고른 고정수(전부 포함)/삭제수(전혀 포함 안 함) 조건에 맞는 걸
            // 찾아 우선 쓴다. 같은 배치(한 번의 "조합 생성") 안에서만 중복
            // 사용을 막기 위해 찾으면 poolCombos에서 빼지만, DB에서 지우진
            // 않는다(다른 사용자에겐 계속 후보로 남음 — "삭제수에 영향 안받는").
            function tryPoolMatch() {{
                const fixedArr = Array.from(selectedFixed);
                for (let i = 0; i < poolCombos.length; i++) {{
                    const combo = poolCombos[i];
                    const comboSet = new Set(combo);
                    const hasAllFixed = fixedArr.every(n => comboSet.has(n));
                    const hasNoDeleted = combo.every(n => !selectedDelete.has(n));
                    if (hasAllFixed && hasNoDeleted) {{
                        poolCombos.splice(i, 1);
                        return combo.slice().sort((a, b) => a - b);
                    }}
                }}
                return null;
            }}

            function buildOneGame(availablePool) {{
                const fixedArr = Array.from(selectedFixed);
                const fixedExempt = violatesNaturalFilter(fixedArr);
                // 자연수 필터 하나만 볼 때의 기존 재시도 한도(100)에, 8가지 유형지표까지
                // 함께 만족하는 조합을 찾을 여유를 더 준다 — 반복 1회 비용이 미미해서
                // (45개 중 6개 뽑기 수준) 늘려도 체감 속도 차이는 없다.
                const maxRetries = Math.max(thunderFilter.thresholds.max_retries, 400);
                let game = fixedArr.slice();
                let attempts = 0;
                let gaveUp = false;
                let bestGame = null;
                let bestScore = -1;

                if (fixedArr.length >= 6) {{
                    return {{ game: fixedArr.slice().sort((a, b) => a - b), attempts: 0, gaveUp: false }};
                }}

                do {{
                    game = fillRandomSlots(fixedArr, availablePool);
                    attempts += 1;
                    if (fixedExempt) break;
                    if (violatesNaturalFilter(game)) continue;
                    const {{ allPass, matched }} = scoreComboPattern(game);
                    if (matched > bestScore) {{
                        bestScore = matched;
                        bestGame = game.slice();
                    }}
                    if (allPass) break;
                }} while (attempts < maxRetries);

                if (!fixedExempt && attempts >= maxRetries) {{
                    // 자연수 필터 + 8가지 유형지표를 전부 만족하는 조합을 못 찾았으면
                    // 시도한 것 중 유형지표를 가장 많이 만족한 후보로 대체한다(0개로
                    // 포기하지 않음).
                    const finalOk = !violatesNaturalFilter(game) && scoreComboPattern(game).allPass;
                    if (!finalOk && bestGame) {{
                        game = bestGame;
                    }}
                    gaveUp = violatesNaturalFilter(game);
                }}

                game.sort((a, b) => a - b);
                return {{ game, attempts, gaveUp }};
            }}

            // 2026-09-10(사용자 신고): 게임이 하나씩 나올 때마다 그 행으로
            // 스크롤을 따라가서, 사용자가 생성 화면을 보려고 위로 올리면 다음
            // 게임이 나오는 순간 다시 아래로 홱 끌어내려 "생성 화면에 머무를 수
            // 없다"는 문제가 있었다. 첫 게임이 나올 때 한 번만 결과 영역으로
            // 스크롤하고, 그 뒤로는 사용자 스크롤을 건드리지 않는다.
            function scrollToResultsIfFirst() {{
                const area = document.getElementById('resultArea');
                if (area && area.children.length <= 1) scrollResultsIntoView(area);
            }}

            function scrollResultsIntoView(anchorEl) {{
                const target = anchorEl || document.getElementById('resultArea');
                if (!target) return;

                requestAnimationFrame(() => {{
                    target.scrollIntoView({{ behavior: 'smooth', block: 'start', inline: 'nearest' }});
                    try {{
                        const frame = window.frameElement;
                        const parentWin = window.parent;
                        if (frame && parentWin) {{
                            const targetRect = target.getBoundingClientRect();
                            const frameRect = frame.getBoundingClientRect();
                            const topInParent = frameRect.top + targetRect.top;
                            parentWin.scrollTo({{
                                top: Math.max(0, parentWin.scrollY + topInParent - 12),
                                behavior: 'smooth',
                            }});
                        }}
                    }} catch (e) {{}}
                }});
            }}

            function generateCombination() {{
                if (isGenerating) return;

                safeVibrate();
                clearActiveGeneration();
                genRunId += 1;
                const thisRun = genRunId;
                isGenerating = true;
                setStartButtonEnabled(false);

                runRevealVersion = consumeRevealVersion();

                const count = parseInt(selectedGameCount, 10);
                if (isNaN(count) || count < 1) {{
                    isGenerating = false;
                    setStartButtonEnabled(true);
                    return;
                }}
                showLuckyWarn(false);

                const available = [];
                for (let i = 1; i <= 45; i++) {{
                    if (!selectedDelete.has(i)) available.push(i);
                }}

                currentResults = [];
                const resultArea = document.getElementById('resultArea');
                resultArea.innerHTML = '';
                scrollResultsIntoView(resultArea);

                for (let g = 0; g < count; g++) {{
                    const tid = setTimeout(() => {{
                        if (thisRun !== genRunId) return;
                        const poolMatch = tryPoolMatch();
                        const game = poolMatch || buildOneGame(available).game;
                        currentResults.push(game);
                        renderGame(game);
                    }}, g * 2000);
                    activeGenTimers.push(tid);
                }}
                const completeId = setTimeout(() => {{
                    if (thisRun !== genRunId) return;
                    isGenerating = false;
                    setStartButtonEnabled(true);
                    window.parent.postMessage({{ type: 'thunder_complete', count: count }}, '*');
                }}, count * 2000 + 600);
                activeGenTimers.push(completeId);
            }}

            /* 메인화면 user_page get_ball_style() / orbit-ball radial-gradient 재사용 */
            function getBallBackground(n) {{
                if (n <= 10) return 'radial-gradient(circle at 35% 35%, #ffeb3b, #f9a825, #f57f17)';
                if (n <= 20) return 'radial-gradient(circle at 35% 35%, #4fc3f7, #1976d2, #0d47a1)';
                if (n <= 30) return 'radial-gradient(circle at 35% 35%, #ef5350, #e53935, #b71c1c)';
                if (n <= 40) return 'radial-gradient(circle at 35% 35%, #bdbdbd, #757575, #424242)';
                return 'radial-gradient(circle at 35% 35%, #81c784, #388e3c, #1b5e20)';
            }}

            function createBallEl(n) {{
                const ball = document.createElement('div');
                ball.className = 'ball';
                ball.style.background = getBallBackground(n);
                ball.innerText = n;
                return ball;
            }}

            /* 버전2: 심해 오라 — 볼이 어둠 속에서 1.6배까지 튀어오르며 계시 (v1과 무관) */
            function renderGameV2(nums) {{
                const row = document.createElement('div');
                row.className = 'result-row mystic-v2-row';

                const aura = document.createElement('div');
                aura.className = 'mystic-v2-aura';
                row.appendChild(aura);

                const track = document.createElement('div');
                track.className = 'mystic-v2-track';
                row.appendChild(track);

                const balls = nums.map(n => {{
                    const b = createBallEl(n);
                    b.style.opacity = '0';
                    b.style.visibility = 'hidden';
                    track.appendChild(b);
                    return b;
                }});

                document.getElementById('resultArea').appendChild(row);
                scrollToResultsIfFirst();

                aura.animate([
                    {{ opacity: 0, transform: 'scaleY(0)' }},
                    {{ opacity: 1, transform: 'scaleY(1)', offset: 0.25 }},
                    {{ opacity: 0.85, transform: 'scaleY(0.55)', offset: 0.75 }},
                    {{ opacity: 0, transform: 'scaleY(0)' }}
                ], {{ duration: 3000, easing: 'ease-in-out', fill: 'forwards' }});

                balls.forEach((ball, i) => {{
                    const tid = setTimeout(() => {{
                        const spark = document.createElement('div');
                        spark.className = 'mystic-v2-spark';
                        spark.style.left = (18 + i * 14) + '%';
                        spark.style.bottom = '6px';
                        row.appendChild(spark);
                        spark.animate([
                            {{ opacity: 0, transform: 'translateY(0) scale(0)' }},
                            {{ opacity: 1, transform: 'translateY(-30px) scale(2)', offset: 0.4 }},
                            {{ opacity: 0, transform: 'translateY(-70px) scale(0)' }}
                        ], {{ duration: 1200, fill: 'forwards' }});
                        setTimeout(() => spark.remove(), 1300);

                        ball.style.visibility = 'visible';
                        ball.animate([
                            {{ opacity: 0, transform: 'translateY(180px) scale(0) rotate(270deg)', filter: 'blur(18px) brightness(0.05)' }},
                            {{ opacity: 0.7, transform: 'translateY(-50px) scale(1.65) rotate(-20deg)', filter: 'blur(0) brightness(2.2) drop-shadow(0 0 28px #22d3ee) drop-shadow(0 0 48px #a855f7)', offset: 0.42 }},
                            {{ opacity: 1, transform: 'translateY(22px) scale(0.82) rotate(10deg)', filter: 'brightness(1.15)', offset: 0.72 }},
                            {{ opacity: 1, transform: 'translateY(0) scale(1) rotate(0deg)', filter: 'none' }}
                        ], {{ duration: 2600, easing: 'cubic-bezier(0.1, 1.45, 0.22, 1)', fill: 'forwards' }});
                    }}, i * 320);
                    activeGenTimers.push(tid);
                }});
            }}

            /* 버전3: 균열 너머 영혼 — 5.5초간 사라졌다 나타났다 후 수렴 (v1과 무관) */
            function renderGameV3(nums) {{
                const row = document.createElement('div');
                row.className = 'result-row mystic-v3-row';

                const rift = document.createElement('div');
                rift.className = 'mystic-v3-rift';
                row.appendChild(rift);

                const track = document.createElement('div');
                track.className = 'mystic-v3-track';
                row.appendChild(track);

                const balls = nums.map(n => {{
                    const b = createBallEl(n);
                    b.style.opacity = '0';
                    track.appendChild(b);
                    return b;
                }});

                document.getElementById('resultArea').appendChild(row);
                scrollToResultsIfFirst();

                rift.animate([
                    {{ opacity: 0, transform: 'scale(0.7) rotate(0deg)' }},
                    {{ opacity: 0.95, transform: 'scale(1.08) rotate(6deg)', offset: 0.35 }},
                    {{ opacity: 0.5, transform: 'scale(1.15) rotate(-8deg)', offset: 0.7 }},
                    {{ opacity: 0, transform: 'scale(1.3) rotate(0deg)' }}
                ], {{ duration: 5500, fill: 'forwards' }});

                const started = performance.now();
                const duration = 5500;
                const baseShadow = '0 4px 0 #000000, 0 7px 16px rgba(0, 0, 0, 0.55), inset 0 1px 0 rgba(255, 255, 255, 0.04)';

                const flickerTimer = setInterval(() => {{
                    const progress = (performance.now() - started) / duration;
                    if (progress >= 1) {{
                        clearInterval(flickerTimer);
                        balls.forEach(b => {{
                            b.style.opacity = '1';
                            b.style.transform = 'translate(0px, 0px) scale(1)';
                            b.style.filter = 'none';
                        }});
                        row.style.boxShadow = baseShadow;
                        row.style.transform = 'scale(1)';
                        return;
                    }}

                    const chaos = 1 - progress * progress;
                    balls.forEach(b => {{
                        if (Math.random() > chaos * 0.85 + 0.08) {{
                            b.style.opacity = String(0.15 + Math.random() * 0.85);
                            b.style.transform = 'translate('
                                + Math.round((Math.random() - 0.5) * 56) + 'px,'
                                + Math.round((Math.random() - 0.5) * 44) + 'px) scale('
                                + (0.35 + Math.random() * 1.35).toFixed(2) + ')';
                            b.style.filter = 'hue-rotate(' + Math.round(Math.random() * 300)
                                + 'deg) brightness(' + (0.4 + Math.random() * 1.6).toFixed(2) + ')';
                        }} else {{
                            b.style.opacity = '0';
                            b.style.transform = 'translate('
                                + Math.round((Math.random() - 0.5) * 80) + 'px,'
                                + Math.round((Math.random() - 0.5) * 60) + 'px) scale(0.15)';
                        }}
                    }});

                    if (Math.random() > 0.45) {{
                        row.style.boxShadow = '0 0 ' + Math.round(18 + Math.random() * 36)
                            + 'px ' + Math.round(6 + Math.random() * 10)
                            + 'px rgba(168, 85, 247, ' + (0.45 + Math.random() * 0.55).toFixed(2) + ')';
                        row.style.transform = 'scale(' + (0.97 + Math.random() * 0.06).toFixed(3) + ')';
                    }} else {{
                        row.style.boxShadow = baseShadow;
                        row.style.transform = 'scale(1)';
                    }}
                }}, 100);
                activeGenIntervals.push(flickerTimer);
            }}

            function renderGame(nums) {{
                const ver = runRevealVersion;
                if (ver === 2 || ver === '2') {{
                    renderGameV2(nums);
                    return;
                }}
                if (ver === 3 || ver === '3') {{
                    renderGameV3(nums);
                    return;
                }}

                const row = document.createElement('div');
                row.className = 'result-row reveal';
                nums.forEach(n => {{
                    const ball = document.createElement('div');
                    ball.className = 'ball';
                    ball.style.background = getBallBackground(n);
                    ball.innerText = n;
                    row.appendChild(ball);
                }});
                document.getElementById('resultArea').appendChild(row);
                scrollToResultsIfFirst();
            }}

            window.addEventListener('message', function(e) {{
                if (e.data.type === 'nav') {{
                    // Streamlit reruns on query param change
                }}
            }});

            // ── 4) 최초 렌더: setMode 호출 없이 빈 격자만 그림 ──
            initGrid();
            if (autoRunCount) {{
                selectedGameCount = autoRunCount;
                thunderApproved = true;
                setTimeout(() => {{
                    if (!isGenerating) generateCombination();
                }}, 400);
            }}
        </script>
    </body>
    </html>
    """

    # components.html iframe은 이 Streamlit 버전에서 "streamlit:setFrameHeight"
    # postMessage로 높이를 동적으로 알려줘도 반영되지 않지만(실측 확인 — 아무
    # 반응 없음), Streamlit 프론트엔드 자체가 iframe 콘텐츠 실제 크기를 감시해서
    # "커지는 방향"으로는 알아서 자동 확장해준다(실측 확인). 그래서 결과 생성 직후
    # 게임 수만큼 미리 크게 잡아뒀었는데(500 + count*84), 그러면 시작부터 화면이
    # 실제 콘텐츠보다 훨씬 크게 확보돼서 결과가 하나씩 나타날 때마다 실행되는
    # scrollResultsIntoView가 그 빈 공간까지 과도하게 스크롤해버려 정작 방금 나온
    # 결과가 화면 위로 밀려나 안 보이는 문제가 있었다(신고 확인) — 항상 짧게
    # 잡아두고 자동 확장에 맡긴다.
    thunder_iframe_height = 500

    with st.container(key="th_main_iframe_wrap_6n36s5"):
        components.html(thunder_ui_html, height=thunder_iframe_height, scrolling=True)

    st.markdown(
        '<div class="th-save-warn">✅ 조합이 결정되면 잠시 후 자동으로 저장됩니다.'
        ' 혹시 자동저장이 안 되면 아래 링크를 눌러 직접 저장해주세요.</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<a id="th_save_real_link" class="th-save-real-btn" style="opacity:0.55;font-size:13px;height:36px;'
        f'background:linear-gradient(180deg,#475569 0%,#334155 55%,#1e293b 100%);'
        f'box-shadow:0 3px 0 #0f172a,0 5px 10px rgba(0,0,0,0.3);"'
        f' href="{internal_nav_href("thunder")}">저장 안 되면 여기를 눌러주세요</a>',
        unsafe_allow_html=True,
    )
    components.html(
        """
        <script>
        (function() {
            const doc = window.parent.document;
            function sync() {
                const wrap = doc.querySelector('.st-key-th_main_iframe_wrap_6n36s5');
                const link = doc.getElementById('th_save_real_link');
                if (!wrap || !link) return;
                const ifr = wrap.querySelector('iframe');
                if (!ifr) return;
                let results, expected;
                try {
                    results = ifr.contentWindow.currentResults;
                    expected = ifr.contentWindow.expectedGameCount;
                } catch (e) { return; }
                // 게임이 하나씩 순차로(2초 간격) currentResults에 쌓이는 도중에 href를
                // 갱신해 버리면 일부만 저장되므로, 목표 게임 수(expectedGameCount)만큼
                // 다 찼을 때만 갱신한다.
                if (!results || !expected || results.length < expected) return;
                const saveParam = results.map(function(g) { return g.join('-'); }).join(',');
                const u = new URL(doc.location.href);
                u.searchParams.set('page', 'thunder');
                u.searchParams.set('th_save', saveParam);
                link.setAttribute('href', u.pathname + u.search);

                // 2026-09-09(사용자 지시): "결과저장" 버튼을 사람이 누르길 기다리지
                // 않고 결과가 다 나오면 자동으로 저장한다. link는 이 폴링 iframe이
                // 아니라 최상위 문서(doc)에 속한 진짜 엘리먼트라, 이 iframe의
                // sandbox 제약과 무관하게 최상위 문서에 <script>를 심어 그 스크립트가
                // 최상위 문서 컨텍스트에서 직접 location을 옮기게 한다(QR스캔
                // 트리거와 동일 계열의 우회법 — 위 CSS 주석 참고).
                // 폴링 iframe은 Streamlit이 rerun될 때마다 새로 만들어져 지역
                // 변수로는 "이미 트리거했는지" 기억이 안 되므로, 최상위 문서에
                // 계속 남아있는 link 엘리먼트 자체에 표시(dataset)해 중복 저장을
                // 막는다 — 우연히 두 번 트리거돼도 같은 조합이 저장내역에 두 번
                // 찍히는 사고를 방지.
                if (link.dataset.autoSaveArmed === saveParam) return;
                link.dataset.autoSaveArmed = saveParam;
                setTimeout(function() {
                    try {
                        const s = doc.createElement('script');
                        s.textContent =
                            "(function(){" +
                            "try{" +
                            "var u=new URL(location.href);" +
                            "u.searchParams.set('page','thunder');" +
                            "u.searchParams.set('th_save'," + JSON.stringify(saveParam) + ");" +
                            "location.href=u.pathname+u.search;" +
                            "}catch(e){}" +
                            "})();";
                        doc.head.appendChild(s);
                        s.parentNode.removeChild(s);
                    } catch (e) {}
                }, 2500);
            }
            // 이 작은 폴링 iframe은 Streamlit이 rerun될 때마다 통째로 새로 만들어지는데,
            // 예전엔 "한 번만 setInterval 걸기" 플래그를 최상위 document(재생성돼도 안
            // 사라짐)에 저장해서, 결제 확인 후 rerun으로 이 iframe이 다시 만들어지면
            // "이미 걸려있네" 하고 자기 인터벌을 안 걸어버렸다(그 사이 이전 iframe과 그
            // 인터벌은 이미 사라진 상태 — href가 계속 빈 상태로 멈춰있던 진짜 원인).
            // 매번 새로 만들어지는 이 iframe마다 항상 자기 인터벌을 새로 건다(이전
            // iframe의 인터벌은 그 iframe이 사라지며 자동으로 멎는다).
            setInterval(sync, 800);
            sync();
            // 모바일 OS는 앱이 백그라운드로 가면(전화 받기, 다른 앱 전환 등)
            // setInterval을 강하게 쓰로틀링하거나 아예 멈출 수 있다 — 그 상태에서
            // 게임 생성이 끝나버리면 다시 포그라운드로 돌아와도 폴링이 한동안(또는
            // 영영) 안 도는 채로 남을 수 있다. 화면이 다시 보이는/포커스되는 시점에
            // 한 번 더 확실히 동기화한다(PC에서는 되는데 모바일에서만 결과저장이
            // 이따금 안 된다는 신고의 유력한 원인 중 하나로 보고 방어적으로 추가).
            // 이 리스너는 (setInterval과 달리) 최상위 document에 등록돼서 iframe이
            // 재생성돼도 사라지지 않으니, rerun마다 계속 쌓이지 않도록 한 번만 건다.
            if (!doc.__thVisibilitySyncBound) {
                doc.__thVisibilitySyncBound = true;
                doc.addEventListener('visibilitychange', function() {
                    if (doc.visibilityState === 'visible') sync();
                });
                (doc.defaultView || window).addEventListener('focus', sync);
            }
        })();
        </script>
        """,
        height=0,
    )

    # 안티조합·액땜조합 진입 버튼은 메인 화면 4박스 그리드로 옮겼다(user_page.py) —
    # 여기 있던 건 삭제.

    # ─── 저장내역 (구매내역과 동일한 카드 디자인 — combo_history_ui 공용 모듈) ───
    from combo_history_ui import render_history_section

    from user_scope import history_guest_ids

    render_history_section(
        container_key="th_history_zone_6n36s5",
        guest_id=history_guest_ids(),
        sources=["thunder"],
        blink_flag_key="thunder_history_blink",
    )

# 호출 확인
if __name__ == "__main__":
    render()
