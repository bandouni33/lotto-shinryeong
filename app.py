from env_loader import load_dotenv_file

load_dotenv_file()

import streamlit as st

st.set_page_config(page_title="로또신령", page_icon="K-325.jpg", layout="wide", initial_sidebar_state="collapsed")

from admission_control import check_admission

check_admission()

if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

# 방 등록
user_view = st.Page("user_page.py", title="로또 번호 조합", icon="🎰")
admin_view = st.Page("admin_dashboard.py", title="운영자 대시보드", icon="⚙️")
feedback_view = st.Page("admin_feedback.py", title="개선 요구사항", icon="💬")

# 권한에 따라 메뉴 구성
if st.session_state.is_admin:
    pg = st.navigation([user_view, admin_view, feedback_view])
else:
    pg = st.navigation([user_view])

if st.session_state.pop("go_to_admin", False):
    st.switch_page("admin_dashboard.py")

try:
    pg.run()
except Exception:
    # DB(Turso) 장애 등으로 페이지 실행 중 예외가 나면 원래 Streamlit이 파이썬
    # 트레이스백을 그대로 사용자 화면에 보여준다 — 실사용자에게는 무슨 뜻인지도
    # 모를 에러 화면일 뿐이라 혼란만 준다(2026-08-23 실제로 겪음). 서버 로그에는
    # 그대로 남기고, 화면에는 안내 메시지만 보여준다.
    import traceback

    traceback.print_exc()
    st.markdown(
        """
        <style>
        .stApp { background-color: #12182b; }
        </style>
        <div style="
            max-width: 420px; margin: 15vh auto 0; text-align: center;
            padding: 32px 24px; border-radius: 16px;
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(212,175,55,0.35);
        ">
            <div style="font-size: 44px; margin-bottom: 12px;">🛠️</div>
            <div style="font-size: 19px; font-weight: 700; color: #f5e6b8; margin-bottom: 10px;">
                일시적으로 서비스 점검 중입니다
            </div>
            <div style="font-size: 14px; line-height: 1.6; color: #d8d8d8;">
                이용에 불편을 드려 죄송합니다.<br>
                잠시 후 다시 접속해 주세요.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )