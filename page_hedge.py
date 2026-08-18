"""안티조합 · 액땜조합 — 이미 산 번호와 일부러 안 겹치게 새 조합을 만드는 기능.

번개조합 화면과 별도 페이지로 분리했다(번개조합 자체의 조합 생성 로직을 건드리지
않기 위해). 번개조합과 달리 components.html iframe을 쓰지 않고 순수 Streamlit
위젯만으로 만들어서, 저장 버튼이 브라우저 sandbox 정책에 막히는 문제 자체가
없다(번개조합에서 겪었던 iframe→최상위 문서 네비게이션 제한과 무관).
"""

import random

import streamlit as st

from combo_history_ui import render_history_section
from user_scope import get_or_create_guest_id, init_guest_scope

MAX_LINES = 5
_NUMS = range(1, 46)
_MAX_ATTEMPTS = 30000
# 0~2개 허용으로 시도해보고 부족하면 0~3개까지만 완화한다(4개부터는 "안티/액땜"의
# 의미가 퇴색된다는 게 사용자와 합의된 기준) — 이 필터 자체는 UI에 노출하지 않는다.
_OVERLAP_STEPS = (2, 3)


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
    return """
    <div style="display:flex;gap:10px;margin-bottom:12px;">
        <a href="?page=thunder" style="flex:1;text-align:center;background:#fff;color:#1E293B;
           border-radius:12px;padding:12px;font-weight:700;text-decoration:none;min-height:48px;
           display:flex;align-items:center;justify-content:center;box-sizing:border-box;">← 번개조합</a>
        <a href="?" style="flex:1;text-align:center;background:#fff;color:#1E293B;
           border-radius:12px;padding:12px;font-weight:700;text-decoration:none;min-height:48px;
           display:flex;align-items:center;justify-content:center;box-sizing:border-box;">🏠 메인</a>
    </div>
    """


def render():
    init_guest_scope()
    guest_id = get_or_create_guest_id()
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
        .hedge-title {
            text-align: center;
            font-size: 1.5rem;
            font-weight: 900;
            color: #FFB800;
            margin-bottom: 4px;
        }
        .hedge-subtitle {
            text-align: center;
            font-size: 0.8rem;
            color: #64748B;
            margin-bottom: 16px;
        }
        .hedge-section-label {
            font-size: 0.85rem;
            font-weight: 800;
            color: #1E293B;
            margin: 14px 0 6px;
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
        /* 모드 토글 — 요청받은 목업처럼 어두운 알약(pill) 모양 세그먼트, 선택된
           쪽만 안티조합=보라 / 액땜조합=초록으로 강조. */
        .st-key-hedge_mode_toggle div[data-testid="stRadio"] > div[role="radiogroup"] {
            display: flex !important;
            flex-direction: row !important;
            gap: 6px !important;
            background: linear-gradient(180deg, #243044 0%, #1E293B 100%) !important;
            border-radius: 999px !important;
            padding: 5px !important;
        }
        .st-key-hedge_mode_toggle div[data-testid="stRadio"] label {
            flex: 1 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            border-radius: 999px !important;
            padding: 8px 10px !important;
            margin: 0 !important;
            cursor: pointer !important;
            transition: background 0.15s ease !important;
        }
        .st-key-hedge_mode_toggle div[data-testid="stRadio"] label > div:first-child {
            display: none !important;
        }
        .st-key-hedge_mode_toggle div[data-testid="stRadio"] label [data-testid="stWidgetLabel"] p {
            color: #94a3b8 !important;
            font-weight: 800 !important;
            font-size: 14px !important;
        }
        .st-key-hedge_mode_toggle div[data-testid="stRadio"] label:nth-of-type(1):has(input:checked) {
            background: linear-gradient(145deg, #A78BFA, #7C3AED) !important;
        }
        .st-key-hedge_mode_toggle div[data-testid="stRadio"] label:nth-of-type(2):has(input:checked) {
            background: linear-gradient(145deg, #4ADE80, #16A34A) !important;
        }
        .st-key-hedge_mode_toggle div[data-testid="stRadio"] label:has(input:checked) [data-testid="stWidgetLabel"] p {
            color: #0F172A !important;
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
        /* 입력한 줄 / 액땜 풀 미리보기 — 목업처럼 어두운 카드에 숫자만 나열 */
        .hedge-line-row {
            background: linear-gradient(180deg, #243044 0%, #1E293B 100%);
            border-radius: 10px;
            padding: 6px 12px;
            margin-bottom: 4px;
            color: #F8FAFC;
            font-weight: 800;
            font-size: 0.9rem;
            letter-spacing: 0.1em;
            text-align: center;
            word-break: break-word;
            line-height: 1.4;
        }
        /* "입력한 줄" 옆 삭제(✕) 버튼도 줄 높이에 맞춰 낮춘다 — 기본 st.button
           높이가 커서 줄 카드가 불필요하게 늘어져 보였다. hedge_del_line_* 키를
           가진 버튼만 정확히 골라서(다른 버튼에 안 번지게) 낮춘다. */
        div[class*="st-key-hedge_del_line_"] div[data-testid="stButton"] > button {
            min-height: 0 !important;
            padding: 4px 0 !important;
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
    st.markdown('<div class="hedge-title">🛡️ 안티조합 · 액땜조합</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hedge-subtitle">구매한 복권 숫자를 입력하고 또 다른 결과를 확인해 보세요</div>',
        unsafe_allow_html=True,
    )

    with st.container(key="hedge_mode_toggle"):
        mode = st.radio(
            "모드",
            ["안티조합", "액땜조합"],
            horizontal=True,
            label_visibility="collapsed",
            key="hedge_mode",
        )
    if mode == "안티조합":
        st.caption("입력한 5줄 각각과 따로따로 비교해서, 각 줄과 크게 안 겹치는 조합을 만들어요.")
    else:
        st.caption("입력한 번호를 전부 하나로 모아, 그 전체와 크게 안 겹치는 조합을 만들어요.")

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
            st.markdown(
                f'<div class="hedge-section-label">{len(committed) + 1}번째 줄 선택 중 · '
                "6개를 선택하면 자동으로 다음 줄로 넘어가요</div>",
                unsafe_allow_html=True,
            )
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
            for i, line in enumerate(committed):
                lcol, dcol = st.columns([5, 1])
                with lcol:
                    st.markdown(_line_row_html(sorted(line)), unsafe_allow_html=True)
                with dcol:
                    if st.button("✕", key=f"hedge_del_line_{i}", use_container_width=True):
                        committed.pop(i)
                        st.session_state["hedge_committed_lines"] = committed
                        st.rerun()
            for _ in range(MAX_LINES - len(committed)):
                st.markdown('<div class="hedge-line-row hedge-line-row-empty">- - - - - -</div>', unsafe_allow_html=True)

        lines = [tuple(sorted(line)) for line in committed]

    else:
        st.markdown('<div class="hedge-section-label">이미 구매한 번호를 최대한 많이 선택하세요</div>', unsafe_allow_html=True)
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
            # 다음 입력을 위해 줄/풀 선택 상태도 같이 비운다.
            st.session_state.pop("hedge_committed_lines", None)
            for line_idx in range(MAX_LINES):
                for n in range(1, 46):
                    st.session_state.pop(f"hedge_anti_num_{line_idx}_{n}", None)
            for n in range(1, 46):
                st.session_state.pop(f"hedge_aek_num_{n}", None)
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
