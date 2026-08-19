"""안티조합 · 액땜조합 — 이미 산 번호와 일부러 안 겹치게 새 조합을 만드는 기능.

번개조합 화면과 별도 페이지로 분리했다(번개조합 자체의 조합 생성 로직을 건드리지
않기 위해). 번개조합과 달리 components.html iframe을 쓰지 않고 순수 Streamlit
위젯만으로 만들어서, 저장 버튼이 브라우저 sandbox 정책에 막히는 문제 자체가
없다(번개조합에서 겪었던 iframe→최상위 문서 네비게이션 제한과 무관).
"""

import random
import re

import streamlit as st

from combo_history_ui import render_history_section
from user_scope import get_or_create_guest_id, init_guest_scope

MAX_LINES = 5
_NUMS = range(1, 46)
_MAX_ATTEMPTS = 30000
# 0~2개 허용으로 시도해보고 부족하면 0~3개까지만 완화한다(4개부터는 "안티/액땜"의
# 의미가 퇴색된다는 게 사용자와 합의된 기준) — 이 필터 자체는 UI에 노출하지 않는다.
_OVERLAP_STEPS = (2, 3)

# 동행복권 로또 용지 QR의 v= 값 포맷: {회차4자리}({모드글자1}{번호6개를 2자리씩
# 이어붙인 12자리}) 이 최대 5번 반복. 글자(수동/자동 구분으로 추정) 자체의 의미는
# 우리한테 필요 없어서 그냥 "글자 하나 + 정확히 12자리"만 정규식으로 뽑아낸다 —
# 뒤에 체크섬 등 여분 문자가 더 붙어있어도 자동으로 무시된다. 실물 티켓 여러 장
# (1235~1237회)으로 대조 검증 완료(2026-08).
_QR_LINE_RE = re.compile(r"[A-Za-z](\d{12})")


def _parse_qr_lines(raw: str) -> list[tuple[int, ...]] | None:
    """스캔된 로또 QR 문자열(전체 URL 또는 v= 값)에서 최대 5줄의 번호를 뽑아낸다."""
    if not raw:
        return None
    if "v=" in raw:
        raw = raw.split("v=", 1)[1].split("&", 1)[0]
    lines: list[tuple[int, ...]] = []
    for block in _QR_LINE_RE.findall(raw)[:MAX_LINES]:
        nums = tuple(sorted(int(block[i : i + 2]) for i in range(0, 12, 2)))
        if len(set(nums)) == 6 and all(1 <= n <= 45 for n in nums):
            lines.append(nums)
    return lines or None


def _random_combo() -> tuple[int, ...]:
    return tuple(sorted(random.sample(_NUMS, 6)))


def generate_anti_combinations(lines: list[tuple[int, ...]], count: int) -> list[tuple[int, ...]]:
    """각 입력 줄과 개별적으로 겹침이 적은 조합을 생성 — 안티조합(줄별 방식)."""
    results: list[tuple[int, ...]] = []
    for max_overlap in _OVERLAP_STEPS:
        results = []
        seen: set[tuple[int, ...]] = set()
        for _ in range(_MAX_ATTEMPTS):
            if len(results) >= count:
                break
            candidate = _random_combo()
            if candidate in seen:
                continue
            seen.add(candidate)
            if all(len(set(candidate) & set(line)) <= max_overlap for line in lines):
                results.append(candidate)
        if len(results) >= count:
            break
    return results[:count]


def generate_aekddaem_combinations(lines: list[tuple[int, ...]], count: int) -> list[tuple[int, ...]]:
    """입력된 모든 줄을 합친 전체 번호 풀과 겹침이 적은 조합을 생성 — 액땜조합(전체 방식)."""
    pool: set[int] = set()
    for line in lines:
        pool |= set(line)
    results: list[tuple[int, ...]] = []
    for max_overlap in _OVERLAP_STEPS:
        results = []
        seen: set[tuple[int, ...]] = set()
        for _ in range(_MAX_ATTEMPTS):
            if len(results) >= count:
                break
            candidate = _random_combo()
            if candidate in seen:
                continue
            seen.add(candidate)
            if len(set(candidate) & pool) <= max_overlap:
                results.append(candidate)
        if len(results) >= count:
            break
    return results[:count]


def _render_nav_html() -> str:
    # 번개조합에서 파생된 하위 화면이던 시절의 흔적("← 번개조합")은 이제 독립
    # 기능(메인에서 바로 진입)이 됐으니 없앤다 — "🏠 메인"만 남긴다.
    return """
    <div style="display:flex;gap:10px;margin-bottom:12px;">
        <a href="?" style="flex:1;text-align:center;background:#fff;color:#1E293B;
           border-radius:12px;padding:12px;font-weight:700;text-decoration:none;min-height:48px;
           display:flex;align-items:center;justify-content:center;box-sizing:border-box;">🏠 메인</a>
    </div>
    """


def _render_input_mode_html() -> str:
    # 메인 화면에서 이 페이지로 들어오면 예전엔 곧장 QR 카메라 화면이 떴는데,
    # 사용자 없이 갑자기 카메라부터 열리면 당황할 수 있다는 판단으로 이 페이지에
    # 먼저 착지시키고, 여기서 "QR스캔"을 직접 고를 때만 카메라를 열게 바꿨다.
    #
    # href의 qrscan=1은 streamlit-webview.tsx의 onShouldStartLoadWithRequest가
    # 가로채 네이티브 카메라 화면으로 보내는 용도였는데, 메인 화면 진입 링크에서는
    # 잘 됐지만 이 페이지 "안"에서(같은 경로, 쿼리만 다른 링크) 누르면 실기기에서
    # 안 걸리고 페이지만 다시 로드되는 문제가 보고됐다(2026-08-19) — 안드로이드
    # 웹뷰가 그런 네비게이션을 이 콜백 없이 처리하는 경우가 있는 것으로 보인다.
    # 더 확실한 postMessage 방식을 우선 시도하고(네이티브 앱 안에서만
    # window.ReactNativeWebView가 존재), 실패해도 href가 폴백으로 남아있다 —
    # 일반 브라우저(테스트 환경)에서는 이 메시지 API 자체가 없어 그냥 평소 링크로
    # 동작한다.
    return """
    <div class="hedge-input-toggle">
        <a href="?page=hedge&qrscan=1" class="hedge-input-pill" onclick="
            if (window.ReactNativeWebView) {
                event.preventDefault();
                window.ReactNativeWebView.postMessage(JSON.stringify({type: 'openQrScan', target: 'hedge'}));
            }
        ">📷 QR스캔</a>
        <div class="hedge-input-pill hedge-input-pill-active">✏️ 직접입력</div>
    </div>
    """


def render():
    init_guest_scope()
    guest_id = get_or_create_guest_id()

    # 네이티브 앱에서 QR 촬영 화면을 거쳐 들어오면 스캔된 문자열이 ?qr=로 실려온다.
    # 1회성 파라미터라 읽자마자 지운다(다음 rerun에서 또 덮어쓰지 않도록, th_save와
    # 동일한 패턴). 안티조합용 committed_lines와 액땜조합용 풀 체크박스 둘 다 채워둬서
    # 스캔 한 번으로 두 모드를 이어서 쓸 수 있게 한다(사용자 요청 시나리오: 안티 조합
    # 생성 후 바로 이어서 액땜 조합도 생성).
    qr_raw = st.query_params.get("qr")
    if qr_raw:
        del st.query_params["qr"]
        parsed = _parse_qr_lines(qr_raw)
        if parsed:
            st.session_state["hedge_committed_lines"] = parsed
            for n in range(1, 46):
                st.session_state.pop(f"hedge_aek_num_{n}", None)
            for line in parsed:
                for n in line:
                    st.session_state[f"hedge_aek_num_{n}"] = True
            st.session_state["hedge_aek_from_qr"] = True
            st.session_state["hedge_qr_loaded"] = len(parsed)
        else:
            st.session_state["hedge_qr_error"] = True
    # 게스트 식별자 쿠키 동기화(components.html 1줄)를 여기 추가했었는데, 구글
    # 비공개 테스트 앱에서 이 페이지가 "불러오는 중"에 멈춘 채 흐릿하게만 보이는
    # 신고가 들어왔다 — 이 화면은 원래(문서 맨 위 설명대로) iframe을 아예 안 써서
    # 그 부류의 멈춤 문제 자체가 없게 설계했었는데, 그 예외를 만든 게 원인일
    # 가능성이 높아 되돌린다. 게스트 식별자 쿠키 동기화는 네이티브 앱(항상 ?gid=를
    # 실어줌)에는 애초에 필요 없고, 모바일 브라우저 직접 접속 폴백에서만 의미가
    # 있었던 부가 기능이라 — 화면이 아예 안 열리는 것보다는 이 편의 기능을 포기하는
    # 쪽이 낫다.

    st.markdown(
        """
        <style>
        /* 안드로이드 강제 다크모드 대응 — iframe(JS) 방식보다 먼저 적용되도록 일반
           CSS로도 걸어둔다(page_thunder.py와 동일 이유, "결과저장" 등 진짜 새로고침
           직후 화면이 잠깐 반전됐다 정상으로 돌아오는 현상 완화). */
        :root { color-scheme: light !important; }
        html, body, #root, .stApp, [data-testid="stAppViewContainer"],
        [data-testid="stAppViewContainer"] > section.main {
            overflow-x: hidden !important;
        }
        .hedge-section-label {
            font-size: 0.85rem;
            font-weight: 800;
            color: #1E293B;
            margin: 14px 0 6px;
        }
        /* 모드 설명 — 안티/액땜 두 규칙을 매번 토글에 따라 하나씩만 보여줬었는데,
           선택하기 전에 둘 다 비교해볼 수 있게 항상 같이 보여달라는 요청으로 바꿈.
           각 줄 앞의 점 색으로 위 모드 토글(안티=보라/액땜=초록)과 시각적으로 잇는다. */
        .hedge-mode-desc {
            display: block !important;
            width: 100% !important;
            height: auto !important;
            max-height: none !important;
            overflow: visible !important;
            white-space: normal !important;
            box-sizing: border-box !important;
            background: linear-gradient(180deg, #243044 0%, #1E293B 100%);
            border-radius: 10px;
            padding: 10px 14px;
            margin: 10px 0 14px;
            color: #E2E8F0;
            font-weight: 700;
            font-size: 0.85rem;
            line-height: 1.4;
        }
        .hedge-mode-desc-line {
            display: flex !important;
            align-items: flex-start;
            gap: 7px;
        }
        .hedge-mode-desc-line + .hedge-mode-desc-line {
            margin-top: 6px;
        }
        .hedge-mode-desc-dot {
            flex: 0 0 auto;
            width: 9px;
            height: 9px;
            margin-top: 4px;
            border-radius: 50%;
        }
        .hedge-mode-desc-anti .hedge-mode-desc-dot {
            background: #A78BFA;
        }
        .hedge-mode-desc-aek .hedge-mode-desc-dot {
            background: #4ADE80;
        }
        div[data-testid="stButton"] > button {
            background: linear-gradient(180deg, #ffffff 0%, #e2e8f0 100%) !important;
            border: none !important;
            border-radius: 12px !important;
            color: #0F172A !important;
            font-weight: 800 !important;
            box-shadow:
                0 4px 0 #94a3b8,
                0 6px 14px rgba(0, 0, 0, 0.28),
                inset 0 1px 0 rgba(255, 255, 255, 0.55) !important;
        }
        div[data-testid="stButton"] > button[kind="primary"] {
            background: linear-gradient(180deg, #65a30d 0%, #3F6212 55%, #365314 100%) !important;
            color: #FFFFFF !important;
            box-shadow:
                0 4px 0 #1a2e05,
                0 7px 14px rgba(63, 98, 18, 0.4),
                inset 0 1px 0 rgba(255, 255, 255, 0.2) !important;
        }
        /* 입력방법(QR스캔/직접입력) — 실제 라디오가 아니라 링크 2개다("QR스캔"을
           누르면 실제 페이지 이동이 일어나야 네이티브 카메라 인터셉트가 걸리기
           때문 — st.radio는 그냥 rerun이라 안 걸림). "직접입력"은 지금 이
           페이지 자체가 그 상태라 눌러도 할 일이 없어 그냥 강조 표시만 한다.
           모드 토글(보라/초록 알약)과 나란히 놓이니 헷갈리지 않게, 금색 계열의
           "고급 스위치" 느낌으로 확실히 차별화한다(로또용지 버튼과 같은 금색
           톤으로 이 앱 전체의 프리미엄 포인트 컬러에 맞춤). */
        .hedge-input-toggle {
            display: flex;
            gap: 6px;
            height: 100%;
            width: 85%;
            margin: 0 auto;
            background: linear-gradient(180deg, #241f14 0%, #17130c 100%);
            border: 1px solid rgba(212, 175, 55, 0.4);
            border-radius: 999px;
            padding: 5px;
            box-sizing: border-box;
        }
        .hedge-input-pill {
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 4px;
            border-radius: 999px;
            padding: 8px 6px;
            font-weight: 800;
            font-size: 14px;
            line-height: 20px;
            color: #FFFFFF;
            /* 안드로이드 웹뷰 강제 다크모드가 <a> 링크 글자색은 유독 별도로
               재해석해서 색을 지정해도 무시하고 뒤집는 경우가 있다(이 프로젝트에서
               이미 여러 번 겪은 패턴) — text-fill-color까지 같이 못박아 강제
               다크모드의 링크 색 재해석을 무력화한다. */
            -webkit-text-fill-color: #FFFFFF;
            text-decoration: none;
            box-sizing: border-box;
            white-space: nowrap;
        }
        .hedge-input-pill-active {
            background: linear-gradient(160deg, #ffe9a8 0%, #f0c552 55%, #d4a017 100%);
            color: #241a06;
            box-shadow:
                0 2px 6px rgba(212, 160, 23, 0.45),
                inset 0 1px 0 rgba(255, 255, 255, 0.5);
        }
        /* QR스캔/직접입력 토글과 모드(안티/액땜) 토글을 한 줄에 나란히 — st.columns는
           좁은 화면에서 기본적으로 세로로 쌓이므로(번호 그리드에서도 겪은 문제),
           이 둘을 감싼 wrap 안에서만 가로 배치를 강제한다. */
        .st-key-hedge_toggles_row div[data-testid="stHorizontalBlock"] {
            display: flex !important;
            flex-direction: row !important;
            gap: 8px !important;
            align-items: stretch !important;
        }
        .st-key-hedge_toggles_row div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
            flex: 1 1 0 !important;
            width: auto !important;
            min-width: 0 !important;
        }
        /* 모드 토글 — 요청받은 목업처럼 어두운 알약(pill) 모양 세그먼트, 선택된
           쪽만 안티조합=보라 / 액땜조합=초록으로 강조.
           label_visibility="collapsed"로 숨긴 "모드" 라벨이 실제로는 자리를
           그대로 차지하고 있었다(stWidgetLabel 높이 36.8px 실측 — Streamlit이
           collapsed에서도 레이아웃 공간은 안 없앰). 그 여백 때문에 옆 QR스캔
           토글까지 늘어난 칸 안에서 위쪽에 붕 떠 보이던 원인이라, 라벨을 아예
           display:none으로 지운다. 라디오그룹도 폭을 100%로 채워야 옆 QR스캔
           토글과 실측 너비가 같아진다(원래는 내용 크기만큼만 좁게 잡혀 있었음). */
        .st-key-hedge_mode_toggle div[data-testid="stRadio"] label[data-testid="stWidgetLabel"] {
            display: none !important;
        }
        /* stElementContainer/stRadio가 내용 크기(144px)로만 잡혀서 radiogroup의
           width:100%가 무의미했다 — 실측으로 확인(번호 그리드 체크박스 때와
           같은 패턴). 컬럼 폭까지 명시적으로 채워야 한다. */
        .st-key-hedge_mode_toggle div[data-testid="stElementContainer"],
        .st-key-hedge_mode_toggle div[data-testid="stRadio"] {
            width: 100% !important;
        }
        .st-key-hedge_mode_toggle div[data-testid="stRadio"] > div[role="radiogroup"] {
            display: flex !important;
            flex-direction: row !important;
            width: 85% !important;
            margin: 0 auto !important;
            gap: 6px !important;
            background: linear-gradient(180deg, #243044 0%, #1E293B 100%) !important;
            border-radius: 999px !important;
            padding: 5px !important;
            box-sizing: border-box !important;
        }
        .st-key-hedge_mode_toggle div[data-testid="stRadio"] label {
            flex: 1 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            border-radius: 999px !important;
            padding: 8px 6px !important;
            margin: 0 !important;
            cursor: pointer !important;
            transition: background 0.15s ease !important;
        }
        /* 라디오 기본 점(radio dot) 숨기기 — 이 Streamlit 버전의 실제 DOM은
           label > div(z0lit3) > div(19nzcwv) > div(원 아이콘 감싸는 wrapper, 첫
           번째 자식) + div[data-testid="stMarkdownContainer"](글자, 두 번째 자식)
           구조다. 예전엔 "label > div:first-child"로 숨기려 했는데, label의 실제
           첫 자식은 화면에 안 보이는 원본 <input>을 감싼 <span>이라 이 셀렉터가
           애초에 아무것도 안 걸려서(매치 X) 점이 계속 그대로 보이던 버그였다
           (선택된 쪽 배경은 보라/초록으로 바뀌는데 점은 Streamlit 기본 색 그대로라
           안 어울려 보임 — 실기기 스크린샷으로 확인). 실제 중첩 구조를 그대로
           따라가 정확히 그 wrapper만 숨긴다. */
        .st-key-hedge_mode_toggle div[data-testid="stRadio"] label > div > div > div:first-child {
            display: none !important;
        }
        .st-key-hedge_mode_toggle div[data-testid="stRadio"] label [data-testid="stMarkdownContainer"] p {
            color: #FFFFFF !important;
            font-weight: 800 !important;
            font-size: 14px !important;
            line-height: 20px !important;
            margin: 0 !important;
        }
        .st-key-hedge_mode_toggle div[data-testid="stRadio"] label:nth-of-type(1):has(input:checked) {
            background: linear-gradient(145deg, #A78BFA, #7C3AED) !important;
        }
        .st-key-hedge_mode_toggle div[data-testid="stRadio"] label:nth-of-type(2):has(input:checked) {
            background: linear-gradient(145deg, #4ADE80, #16A34A) !important;
        }
        .st-key-hedge_mode_toggle div[data-testid="stRadio"] label:has(input:checked) [data-testid="stMarkdownContainer"] p {
            color: #FFFFFF !important;
        }
        /* 번호 그리드 — 어두운 카드 안에 흰색 둥근사각 버튼(목업 참고). st.columns가
           좁은 화면에서는 기본적으로 세로로 쌓이므로, 번호 그리드만은 강제로 가로
           배치를 유지시킨다(7칸씩 한 줄). */
        /* 번개조합 .number-grid와 완전히 동일한 값(그라디언트·그림자·여백)을 그대로
           맞춘다 — 번개조합은 순수 HTML(iframe)로 그리고 여긴 st.checkbox 위젯이라
           만드는 방식은 다르지만, 최종 CSS 수치는 픽셀 단위로 동일하게. */
        .st-key-hedge_num_grid_wrap {
            background: linear-gradient(180deg, #243044 0%, #1E293B 100%) !important;
            border-radius: 16px !important;
            padding: 10px !important;
            box-shadow:
                0 6px 0 #0b1220,
                0 10px 20px rgba(0, 0, 0, 0.35),
                inset 0 1px 0 rgba(255, 255, 255, 0.08) !important;
        }
        .st-key-hedge_num_grid_wrap div[data-testid="stHorizontalBlock"] {
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            gap: 3px !important;
            margin-bottom: 2px !important;
        }
        .st-key-hedge_num_grid_wrap div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
            flex: 1 1 0 !important;
            width: auto !important;
            min-width: 0 !important;
        }
        /* Streamlit이 stElementContainer(체크박스 위젯을 감싸는 바깥 래퍼)를 콘텐츠
           크기(16px)로만 만들어서, 그 안의 stCheckbox/label에 width:100%를 줘도
           16px 기준 100%라 그대로 작게 나온다(실측 확인된 문제) — 래퍼부터 폭을
           채워야 한다. */
        .st-key-hedge_num_grid_wrap div[data-testid="stElementContainer"] {
            width: 100% !important;
        }
        /* Streamlit 내장 체크박스 스타일이 !important + 나중에 삽입되는 순서로
           width:16px 같은 고정값을 계속 덮어써서, 클래스를 두 번 겹쳐 써
           명시도(specificity)를 인위적으로 더 높여야 이긴다(실측 확인된 문제). */
        .st-key-hedge_num_grid_wrap.st-key-hedge_num_grid_wrap div[data-testid="stCheckbox"] {
            width: 100% !important;
            flex: 1 1 auto !important;
        }
        /* 로또용지 느낌의 고급스러운 버튼 — 흰 플라스틱 버튼 대신 아이보리 종이 질감
           + 금색 테두리로, 선택되면 보라(안티)/금 링 조합으로 포인트를 준다. */
        .st-key-hedge_num_grid_wrap.st-key-hedge_num_grid_wrap div[data-testid="stCheckbox"] label {
            display: flex !important;
            flex-direction: column !important;
            align-items: center !important;
            justify-content: center !important;
            width: 90% !important;
            margin: 0 auto !important;
            height: auto !important;
            aspect-ratio: 1 !important;
            padding: 0 !important;
            border-radius: 9px !important;
            background: linear-gradient(160deg, #fffdf7 0%, #f3ead2 60%, #e8dcb8 100%) !important;
            border: 1px solid rgba(191, 155, 66, 0.55) !important;
            box-shadow:
                0 3px 0 #a9895a,
                0 5px 10px rgba(41, 27, 5, 0.32),
                inset 0 1px 0 rgba(255, 255, 255, 0.75) !important;
            transition: transform 0.12s ease, box-shadow 0.12s ease !important;
            cursor: pointer !important;
        }
        .st-key-hedge_num_grid_wrap div[data-testid="stCheckbox"] label:has(input:checked) {
            background: linear-gradient(145deg, #A855F7, #6D28D9) !important;
            border: 1px solid #FFD966 !important;
            text-shadow: 0 1px 2px rgba(0, 0, 0, 0.4) !important;
            box-shadow:
                0 3px 0 #5b21b6,
                0 5px 12px rgba(168, 85, 247, 0.5),
                0 0 0 1px rgba(255, 217, 102, 0.55),
                inset 0 1px 0 rgba(255, 255, 255, 0.3) !important;
        }
        .st-key-hedge_num_grid_wrap.st-key-hedge_num_grid_wrap div[data-testid="stCheckbox"] label > div:not([data-testid="stWidgetLabel"]) {
            display: none !important;
        }
        .st-key-hedge_num_grid_wrap div[data-testid="stCheckbox"] [data-testid="stWidgetLabel"] {
            margin: 0 !important;
        }
        .st-key-hedge_num_grid_wrap div[data-testid="stCheckbox"] [data-testid="stWidgetLabel"] p {
            margin: 0 !important;
            color: #241a06 !important;
            font-weight: 900 !important;
            font-size: 15px !important;
        }
        .st-key-hedge_num_grid_wrap div[data-testid="stCheckbox"] label:has(input:checked) [data-testid="stWidgetLabel"] p {
            color: #FFFFFF !important;
        }
        /* 입력한 줄 / 액땜 풀 미리보기 — 목업처럼 어두운 카드에 숫자만 나열.
           삭제(✕) 버튼 줄을 없애서 번호 줄만 촘촘히 쌓이게 하고, 그만큼 생긴
           여유로 숫자 자체는 크게 키운다(작은 화면에서 정보 밀도 최대화 — 항상
           지켜야 하는 기준). */
        .hedge-line-row {
            background: linear-gradient(180deg, #243044 0%, #1E293B 100%);
            border-radius: 10px;
            padding: 8px 12px;
            margin-bottom: 3px;
            color: #F8FAFC;
            font-weight: 800;
            font-size: 1.25rem;
            letter-spacing: 0.08em;
            text-align: center;
            word-break: break-word;
            line-height: 1.3;
        }
        .hedge-line-row.hedge-line-row-empty {
            color: #475569;
            font-weight: 600;
            background: linear-gradient(180deg, #1B2536 0%, #16202E 100%);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    # 조합 미리보기(저장 전)에도 저장내역 카드와 같은 볼 스타일을 쓰기 위해 공용 CSS를
    # 먼저 주입한다 — 아래 render_history_section이 다시 한번 주입하지만(동일 정의라
    # 안전), 미리보기가 그보다 먼저 렌더링되므로 여기서도 걸어둔다.
    from combo_history_ui import history_css

    st.markdown(history_css("hedge_history_zone_6n36s5"), unsafe_allow_html=True)

    st.markdown(_render_nav_html(), unsafe_allow_html=True)
    qr_loaded = st.session_state.pop("hedge_qr_loaded", None)
    if qr_loaded:
        st.success(f"✅ QR로 {qr_loaded}줄 번호를 불러왔어요. 아래에서 확인하고 조합시작을 눌러주세요.")
    if st.session_state.pop("hedge_qr_error", False):
        st.error("QR 인식에 실패했어요. 로또 용지 QR이 맞는지 확인 후 다시 시도하거나 직접 입력해 주세요.")

    # 입력방법(QR스캔/직접입력)과 모드(안티/액땜) 토글을 한 줄에 나란히 배치.
    with st.container(key="hedge_toggles_row"):
        col_input, col_mode = st.columns(2)
        with col_input:
            st.markdown(_render_input_mode_html(), unsafe_allow_html=True)
        with col_mode:
            with st.container(key="hedge_mode_toggle"):
                mode = st.radio(
                    "모드",
                    ["안티조합", "액땜조합"],
                    horizontal=True,
                    label_visibility="collapsed",
                    key="hedge_mode",
                )
    st.markdown(
        '<div class="hedge-mode-desc">'
        '<div class="hedge-mode-desc-line hedge-mode-desc-anti"><span class="hedge-mode-desc-dot"></span>'
        "안티조합: 구매복권 5줄과 상반된 반전조합 5줄 생성.</div>"
        '<div class="hedge-mode-desc-line hedge-mode-desc-aek"><span class="hedge-mode-desc-dot"></span>'
        "액땜조합: 구매복권 전체숫자와 상반된 반전조합 5줄 생성.</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    def _grid_selected(prefix: str) -> list[int]:
        return sorted(n for n in range(1, 46) if st.session_state.get(f"{prefix}{n}"))

    def _render_num_grid(prefix: str) -> None:
        # st.multiselect/st.pills는 이 세션에서 한 번도 안 쓰인 위젯이라, 실기기(느린
        # 모바일 네트워크)에서 그 전용 JS 청크를 새로 받아오다가 응답이 없으면 화면이
        # "불러오는 중"에서 멈추는 문제가 있었다(재현·확인됨) — 앱 전체에서 이미 여러
        # 번 쓰여서 항상 로드돼 있는 st.checkbox + st.columns 조합으로 대신한다.
        with st.container(key="hedge_num_grid_wrap"):
            nums = list(range(1, 46))
            # 로또용지처럼 한 줄에 10개씩 5줄(마지막 줄만 5개) — 7개씩 쓰던 것보다
            # 줄 수가 줄어서 세로 공간을 아껴, 그리드 밑의 "입력한 줄" 카드가 스크롤
            # 없이 바로 보이게 한다(요청: "밑 입력창 안보이니까 완전 깜깜이").
            cols_per_row = 10
            for row_start in range(0, len(nums), cols_per_row):
                cols = st.columns(cols_per_row)
                for col, n in zip(cols, nums[row_start : row_start + cols_per_row]):
                    with col:
                        st.checkbox(str(n), key=f"{prefix}{n}", label_visibility="visible")

    def _line_row_html(combo) -> str:
        return '<div class="hedge-line-row">' + " ".join(f"{n:02d}" for n in combo) + "</div>"

    lines: list[tuple[int, ...]] = []

    if mode == "안티조합":
        committed = st.session_state.setdefault("hedge_committed_lines", [])

        if len(committed) < MAX_LINES:
            # 줄마다 프리픽스를 다르게 줘서(hedge_anti_num_{줄번호}_N) 매번 완전히 새
            # 체크박스 위젯을 쓴다 — 예전엔 모든 줄이 같은 키(hedge_anti_num_N)를
            # 재사용해서, 줄이 넘어갈 때 session_state.pop()으로 체크 해제를
            # 시도했는데 브라우저 쪽 체크박스는 여전히 눌려있는 상태라 다음 rerun에
            # 그 값이 되살아나 같은 6개로 계속 다음 줄이 자동 커밋되는 문제가 있었다
            # (줄이 안 늘어야 하는데 계속 늘어나며 조합시작이 제대로 안 눌리던 원인).
            line_prefix = f"hedge_anti_num_{len(committed)}_"
            _render_num_grid(line_prefix)
            current = _grid_selected(line_prefix)
            if len(current) == 6:
                committed.append(current)
                st.session_state["hedge_committed_lines"] = committed
                st.rerun()
            elif current:
                st.caption(f"{len(current)}/6개 선택됨")
        else:
            st.success(f"{MAX_LINES}줄 모두 입력했습니다. 아래 조합시작을 눌러주세요.")

        if committed:
            st.markdown('<div class="hedge-section-label">입력한 줄</div>', unsafe_allow_html=True)
            rows = "".join(_line_row_html(sorted(line)) for line in committed)
            rows += "".join(
                '<div class="hedge-line-row hedge-line-row-empty">- - - - - -</div>'
                for _ in range(MAX_LINES - len(committed))
            )
            st.markdown(rows, unsafe_allow_html=True)

        lines = [tuple(sorted(line)) for line in committed]

    else:
        pool = _grid_selected("hedge_aek_num_")
        # QR 스캔으로 이미 6개 이상 채워져 있으면 번호판을 또 보여줄 필요가 없다 —
        # 안티조합 저장 후 이어서 액땜조합도 스캔 한 번으로 바로 만들 수 있어야 한다는
        # 요청. 직접 고치고 싶으면 다시 스캔하면 되므로 별도 "직접입력" 전환은 안 둔다.
        from_qr = bool(st.session_state.get("hedge_aek_from_qr")) and len(pool) >= 6
        if from_qr:
            st.success(f"QR로 불러온 {len(pool)}개 번호로 바로 조합할 수 있어요.")
        else:
            _render_num_grid("hedge_aek_num_")
            pool = _grid_selected("hedge_aek_num_")
        st.caption(f"{len(pool)}개 선택됨" + (" · 6개 이상 선택해 주세요" if pool and len(pool) < 6 else ""))
        if pool:
            st.markdown('<div class="hedge-section-label">선택한 번호</div>', unsafe_allow_html=True)
            st.markdown(_line_row_html(pool), unsafe_allow_html=True)
            lines = [tuple(pool)]

    count = st.selectbox("생성할 조합 수", [5, 10, 15, 20], index=0, key="hedge_count")

    if st.button("조합시작", type="primary", use_container_width=True, key="hedge_generate_btn"):
        if mode == "안티조합" and not lines:
            st.error("최소 1줄 이상 입력해 주세요 (6개씩 선택).")
        elif mode == "액땜조합" and (not lines or len(lines[0]) < 6):
            st.error("번호를 6개 이상 선택해 주세요.")
        else:
            from wallet_ui import ensure_member_or_banner

            if ensure_member_or_banner(
                resume="open_hedge_dialog",
                reason="조합 생성을 위해 간편인증이 필요합니다.",
                resume_data={"lines": lines, "count": count, "mode": mode},
            ):
                st.session_state["open_hedge_dialog"] = True
                st.session_state["hedge_pending_lines"] = lines
                st.session_state["hedge_pending_count"] = count
                st.session_state["hedge_pending_mode"] = mode
                st.rerun()

    if st.session_state.get("open_hedge_dialog"):
        from wallet_ui import points_notice_dialog

        pending_count = int(st.session_state.get("hedge_pending_count", 5))

        def _hedge_dialog_close(confirmed: bool, pending_count: int = pending_count) -> None:
            st.session_state["open_hedge_dialog"] = False
            from auth_kakao import current_member_id
            from wallet_ui import deduct_after_result

            pending_lines = st.session_state.pop("hedge_pending_lines", None) or []
            pending_mode = st.session_state.pop("hedge_pending_mode", mode)
            st.session_state.pop("hedge_pending_count", None)
            if confirmed:
                mid = current_member_id()
                if mid:
                    import uuid

                    ref = f"hedge:{mid}:{uuid.uuid4().hex[:10]}"
                    deduct_after_result(mid, "hedge", ref, quantity=pending_count)
            # 테스트 기간이라 취소를 눌러도 그대로 생성을 진행시킨다.
            if pending_mode == "안티조합":
                results = generate_anti_combinations(pending_lines, pending_count)
            else:
                results = generate_aekddaem_combinations(pending_lines, pending_count)
            st.session_state["hedge_results"] = results
            st.session_state["hedge_results_mode"] = pending_mode

        points_notice_dialog("hedge", quantity=pending_count, on_close=_hedge_dialog_close)

    results = st.session_state.get("hedge_results")
    if results:
        st.markdown('<div class="hedge-section-label">생성 결과</div>', unsafe_allow_html=True)
        rows = "".join(_line_row_html(combo) for combo in results)
        st.markdown(rows, unsafe_allow_html=True)
        if st.button("💾 결과저장", type="primary", use_container_width=True, key="hedge_save_btn"):
            from auto_purchase_service import _next_draw_round
            from marketing_db import init_marketing_tables, save_guest_generated_combos

            init_marketing_tables()
            saved_mode = st.session_state.get("hedge_results_mode", mode)
            source = "anti" if saved_mode == "안티조합" else "aekddaem"
            save_guest_generated_combos(guest_id, source, _next_draw_round(), results)
            st.session_state.pop("hedge_results", None)
            st.session_state.pop("hedge_results_mode", None)
            # 방금 저장한 모드의 입력 상태만 비운다 — 두 모드 다 비우면, QR 스캔 한 번으로
            # 안티조합 저장 후 이어서 액땜조합도 만들려는 흐름에서 액땜용 번호 풀까지
            # 같이 날아가 다시 스캔해야 하는 문제가 있었다(사용자 확인, 2026-08-19).
            if saved_mode == "안티조합":
                st.session_state.pop("hedge_committed_lines", None)
                for line_idx in range(MAX_LINES):
                    for n in range(1, 46):
                        st.session_state.pop(f"hedge_anti_num_{line_idx}_{n}", None)
            else:
                for n in range(1, 46):
                    st.session_state.pop(f"hedge_aek_num_{n}", None)
                st.session_state.pop("hedge_aek_from_qr", None)
            st.session_state["hedge_history_blink"] = True
            st.rerun()

    render_history_section(
        container_key="hedge_history_zone_6n36s5",
        guest_id=guest_id,
        sources=["anti", "aekddaem"],
        blink_flag_key="hedge_history_blink",
        label_for_source={"anti": "안티조합", "aekddaem": "액땜조합"},
    )


if __name__ == "__main__":
    render()
