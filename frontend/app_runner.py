"""프론트엔드 라우터 — 모바일/PC UI 분기 (백엔드와 완전 분리)."""

import streamlit as st

from frontend.views.desktop_view import render_desktop_view
from frontend.views.mobile_view import render_mobile_view


def is_desktop_mode() -> bool:
    """쿼리 파라미터 ?mode=desktop 으로 PC 화면 미리보기."""
    try:
        mode = st.query_params.get("mode", "mobile")
        if isinstance(mode, list):
            mode = mode[0] if mode else "mobile"
        return mode == "desktop"
    except Exception:
        return False


def run_app() -> None:
    st.set_page_config(
        page_title="프리미엄 로또조합기",
        page_icon="🎱",
        layout="centered",
        initial_sidebar_state="collapsed",
    )

    try:
        if is_desktop_mode():
            render_desktop_view()
        else:
            render_mobile_view()
    except Exception as exc:
        st.error("앱 실행 중 오류가 발생했습니다. 아래 내용을 확인해 주세요.")
        st.exception(exc)
        st.info("터미널에서 `run_server.ps1` 로 서버를 재시작해 보세요.")
