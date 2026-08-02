from env_loader import load_dotenv_file

load_dotenv_file()

import streamlit as st

st.set_page_config(page_title="로또신령", page_icon="K-325.jpg", layout="wide", initial_sidebar_state="collapsed")

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

pg.run()