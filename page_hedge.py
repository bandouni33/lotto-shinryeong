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

    st.markdown(
        """
        <style>
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
        .hedge-line-label {
            font-size: 0.78rem;
            font-weight: 700;
            color: #64748B;
            margin: 10px 0 2px;
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

    st.markdown('<div class="hedge-section-label">이미 구매한 번호 입력 (줄당 6개, 터치로 선택)</div>', unsafe_allow_html=True)
    line_selections = []
    for i in range(1, MAX_LINES + 1):
        st.markdown(f'<div class="hedge-line-label">{i}번째 줄</div>', unsafe_allow_html=True)
        sel = st.pills(
            f"{i}번째 줄 번호",
            options=list(range(1, 46)),
            selection_mode="multi",
            key=f"hedge_line_pills_{i}",
            label_visibility="collapsed",
        )
        sel = sorted(sel or [])
        if sel:
            hint = f"{len(sel)}/6개 선택됨"
            if len(sel) != 6:
                hint += " · 6개를 선택해 주세요"
            st.caption(hint)
        line_selections.append(sel)

    count = st.selectbox("생성할 조합 수", [5, 10, 15, 20], index=0, key="hedge_count")

    if st.button("조합시작", type="primary", use_container_width=True, key="hedge_generate_btn"):
        lines = []
        line_errors = []
        for i, sel in enumerate(line_selections, start=1):
            if not sel:
                continue
            if len(sel) != 6:
                line_errors.append(f"{i}번째 줄은 6개를 선택해야 합니다 (현재 {len(sel)}개).")
            else:
                lines.append(tuple(sel))

        if not lines:
            st.error("최소 1줄 이상 번호를 선택해 주세요.")
        elif line_errors:
            for err in line_errors:
                st.error(err)
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
        dialog_result = points_notice_dialog("hedge", quantity=pending_count)
        if dialog_result == "confirm":
            st.session_state["open_hedge_dialog"] = False
            from auth_kakao import current_member_id
            from wallet_ui import deduct_after_result

            mid = current_member_id()
            pending_lines = st.session_state.pop("hedge_pending_lines", None) or []
            pending_mode = st.session_state.pop("hedge_pending_mode", mode)
            st.session_state.pop("hedge_pending_count", None)
            if mid:
                import uuid

                ref = f"hedge:{mid}:{uuid.uuid4().hex[:10]}"
                if deduct_after_result(mid, "hedge", ref, quantity=pending_count):
                    if pending_mode == "안티조합":
                        results = generate_anti_combinations(pending_lines, pending_count)
                    else:
                        results = generate_aekddaem_combinations(pending_lines, pending_count)
                    st.session_state["hedge_results"] = results
                    st.session_state["hedge_results_mode"] = pending_mode
                else:
                    st.error("적립금 차감에 실패했습니다.")
            st.rerun()
        elif dialog_result == "cancel":
            st.session_state["open_hedge_dialog"] = False
            for key in ("hedge_pending_lines", "hedge_pending_count", "hedge_pending_mode"):
                st.session_state.pop(key, None)

    results = st.session_state.get("hedge_results")
    if results:
        st.markdown('<div class="hedge-section-label">생성 결과</div>', unsafe_allow_html=True)
        rows = "".join(
            '<div class="auto-banner-combo"><div class="auto-banner-ball-row">'
            + "".join(f'<span class="auto-banner-ball">{n:02d}</span>' for n in combo)
            + "</div></div>"
            for combo in results
        )
        st.markdown(
            f'<div class="auto-purchase-banner"><div class="auto-banner-combos">{rows}</div></div>',
            unsafe_allow_html=True,
        )
        if st.button("💾 결과저장", type="primary", use_container_width=True, key="hedge_save_btn"):
            from auto_purchase_service import _next_draw_round
            from marketing_db import init_marketing_tables, save_guest_generated_combos

            init_marketing_tables()
            saved_mode = st.session_state.get("hedge_results_mode", mode)
            source = "anti" if saved_mode == "안티조합" else "aekddaem"
            save_guest_generated_combos(guest_id, source, _next_draw_round(), results)
            st.session_state.pop("hedge_results", None)
            st.session_state.pop("hedge_results_mode", None)
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
