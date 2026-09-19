"""운영자 — 고객불만 / 개선요구사항 목록 (처리상태 관리 포함, 2026-09-19 개편)."""

import pandas as pd
import streamlit as st

from feedback_db import (
    DEFAULT_FEEDBACK_STATUS,
    FEEDBACK_STATUSES,
    count_feedback,
    init_feedback_tables,
    list_feedback,
    update_feedback_status,
)

st.set_page_config(
    page_title="고객불만/개선요구사항",
    layout="centered",
    initial_sidebar_state="expanded",
)

# admin_dashboard.py와 동일한 이유 — app.py가 항상 등록해두는 대신 여기서
# 직접 관리자 여부를 확인한다(재부팅 후 "Page not found" 노출 방지).
if not st.session_state.get("is_admin", False):
    st.switch_page("user_page.py")
    st.stop()

init_feedback_tables()

st.markdown(
    """
<style>
    .stApp { background-color: #0B0C10; color: #FFFFFF; }
    div[data-testid="stMetricValue"] > div { color: #00E676 !important; font-weight: 900 !important; }
    div[data-testid="stDataFrame"] { border: 1px solid #3A4454; border-radius: 8px; }
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    "<h2 style='font-weight:800; color:#FFFFFF; margin-bottom:4px;'>고객불만 / 개선요구사항</h2>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p style='color:#94A3B8; margin-bottom:20px;'>사용자 의견 · 최신순 · 처리상태 관리</p>",
    unsafe_allow_html=True,
)

# 2026-09-19: 상태별 건수를 한눈에 보여주고(대기 건이 쌓이고 있는지 바로 확인),
# 탭으로 필터링해 "아직 처리 안 한 것"만 골라볼 수 있게 한다 — 기존엔 최신순
# 목록 하나뿐이라 처리한 것/안 한 것이 섞여 순서대로 확인해야만 했다.
_counts = {s: count_feedback(status=s) for s in FEEDBACK_STATUSES}
_total = count_feedback()

col_total, col_wait, col_doing, col_done = st.columns(4)
with col_total:
    st.metric("전체", f"{_total:,} 건")
with col_wait:
    st.metric("대기", f"{_counts.get('대기', 0):,} 건")
with col_doing:
    st.metric("처리중", f"{_counts.get('처리중', 0):,} 건")
with col_done:
    st.metric("완료", f"{_counts.get('완료', 0):,} 건")

tab_all, tab_wait, tab_doing, tab_done = st.tabs(["전체", "대기", "처리중", "완료"])
_tab_status_map = {tab_all: None, tab_wait: "대기", tab_doing: "처리중", tab_done: "완료"}

for _tab, _status_filter in _tab_status_map.items():
    with _tab:
        rows = list_feedback(status=_status_filter)
        if not rows:
            st.info("해당 상태의 의견이 없습니다.")
            continue

        df = pd.DataFrame(rows)
        df = df.rename(
            columns={
                "id": "번호",
                "created_at": "접수일시",
                "nickname": "닉네임",
                "category": "분류",
                "body": "내용",
                "member_id": "회원ID",
                "status": "상태",
            }
        )
        display_cols = ["번호", "접수일시", "닉네임", "분류", "상태", "내용"]
        st.dataframe(df[display_cols], use_container_width=True, hide_index=True)

        st.markdown("#### 상세 보기 · 상태 변경")
        for row in rows[:30]:
            mid = row.get("member_id")
            mid_txt = f" · 회원 #{mid}" if mid else ""
            cur_status = row.get("status") or DEFAULT_FEEDBACK_STATUS
            with st.expander(
                f"[{cur_status}] #{row['id']} · {row['created_at']} · {row['nickname']} · {row['category']}{mid_txt}"
            ):
                st.markdown(row["body"])
                new_status = st.selectbox(
                    "처리상태",
                    FEEDBACK_STATUSES,
                    index=FEEDBACK_STATUSES.index(cur_status) if cur_status in FEEDBACK_STATUSES else 0,
                    key=f"fb_status_{_status_filter}_{row['id']}",
                )
                if new_status != cur_status:
                    if st.button("상태 저장", key=f"fb_status_save_{_status_filter}_{row['id']}"):
                        update_feedback_status(row["id"], new_status)
                        st.success(f"#{row['id']} 상태를 '{new_status}'(으)로 변경했습니다.")
                        st.rerun()
