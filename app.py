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

# 2026-08-27: 예전엔 is_admin일 때만 admin_view/feedback_view를 등록해서 접근을
# 막았는데, 그 방식은 세션이 새로 시작되면(재배포·Streamlit Cloud 재부팅 등)
# is_admin이 False로 리셋되는 순간 그 페이지의 URL이 더 이상 "존재하지 않는"
# 것이 돼버려 관리자에게 Streamlit의 "Page not found" 영어 에러가 그대로
# 노출됐다. 항상 세 페이지 모두 등록해두고, 실제 접근 제어는 각 admin
# 페이지(admin_dashboard.py/admin_feedback.py) 맨 앞의 is_admin 확인으로
# 옮겼다 — 사이드바 자체가 모든 화면에서 collapsed·CSS로 숨겨져 있어 등록해둬도
# 일반 이용자에게 메뉴로 노출되지는 않는다.
pg = st.navigation([user_view, admin_view, feedback_view])

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