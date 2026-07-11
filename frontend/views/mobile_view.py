from pathlib import Path

import streamlit as st

from frontend.components.haptic import inject_mobile_scripts
from frontend.components.lotto_balls import render_results
from src.models.membership import MembershipTier
from src.services.combination_service import CombinationResult, generate_combinations
from src.services.subscription import get_filter_names_for_tier

CSS_PATH = Path(__file__).resolve().parents[1] / "styles" / "mobile.css"

TIER_OPTIONS = {
    "기본 (FREE)": MembershipTier.FREE,
    "프리미엄 (PREMIUM)": MembershipTier.PREMIUM,
}

BUTTON_LABELS = {
    MembershipTier.FREE: "기본 번호 추출하기",
    MembershipTier.PREMIUM: "프리미엄 번호 추출하기",
}


def _load_css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


def _render_filter_badges(filters: list[str]) -> str:
    badges = "".join(f'<span class="filter-badge">{name}</span>' for name in filters)
    return f'<div class="filter-badge-wrap">{badges}</div>'


def _on_tier_change() -> None:
    st.session_state.pop("last_result", None)


def render_mobile_view() -> None:
    st.markdown(f"<style>{_load_css()}</style>", unsafe_allow_html=True)

    st.markdown(
        """
        <h1 class="mobile-title">프리미엄 로또조합기</h1>
        <p class="mobile-subtitle">모바일 최적화 · 스마트 필터 조합 추출</p>
        """,
        unsafe_allow_html=True,
    )

    if "tier_label" not in st.session_state:
        st.session_state["tier_label"] = "프리미엄 (PREMIUM)"

    with st.container(border=True):
        tier_label = st.radio(
            "멤버십 등급",
            options=list(TIER_OPTIONS.keys()),
            horizontal=True,
            label_visibility="collapsed",
            key="tier_label",
            on_change=_on_tier_change,
        )

    tier = TIER_OPTIONS[tier_label]
    button_label = BUTTON_LABELS[tier]

    inject_mobile_scripts()

    st.markdown(_render_filter_badges(get_filter_names_for_tier(tier)), unsafe_allow_html=True)

    if st.button(button_label, type="primary", use_container_width=True):
        with st.spinner("조합 추출 중..."):
            result = generate_combinations(tier=tier, count=5)
        st.session_state["last_result"] = result

    result: CombinationResult | None = st.session_state.get("last_result")

    if result is None:
        st.markdown(
            '<div class="empty-state">위 버튼을 터치하면 필터가 적용된 조합 5개가 표시됩니다.</div>',
            unsafe_allow_html=True,
        )
        return

    last_draw_text = " ".join(f"{n:02d}" for n in result.last_draw)
    st.markdown(
        f"""
        <div class="last-draw-box">
            직전 회차(가상) · {last_draw_text}<br>
            <strong>{result.tier.display_name}</strong> 필터 적용
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not result.is_complete:
        st.warning(f"{result.requested_count}개 중 {len(result.combinations)}개만 생성되었습니다.")

    st.markdown(render_results(result.combinations), unsafe_allow_html=True)
