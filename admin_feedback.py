"""운영자 — 개선 요구사항 목록."""

import pandas as pd
import streamlit as st

from feedback_db import count_feedback, init_feedback_tables, list_feedback

st.set_page_config(
    page_title="개선 요구사항",
    layout="centered",
    initial_sidebar_state="expanded",
)

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
    "<h2 style='font-weight:800; color:#FFFFFF; margin-bottom:4px;'>개선 요구사항</h2>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p style='color:#94A3B8; margin-bottom:20px;'>테스트 기간 사용자 의견 · 최신순</p>",
    unsafe_allow_html=True,
)

total = count_feedback()
st.metric("접수 건수", f"{total:,} 건")

rows = list_feedback()
if not rows:
    st.info("아직 접수된 의견이 없습니다.")
else:
    df = pd.DataFrame(rows)
    df = df.rename(
        columns={
            "id": "번호",
            "created_at": "접수일시",
            "nickname": "닉네임",
            "category": "분류",
            "body": "내용",
            "member_id": "회원ID",
        }
    )
    display_cols = ["번호", "접수일시", "닉네임", "분류", "내용"]
    st.dataframe(df[display_cols], use_container_width=True, hide_index=True)

    st.markdown("#### 상세 보기")
    for row in rows[:30]:
        mid = row.get("member_id")
        mid_txt = f" · 회원 #{mid}" if mid else ""
        with st.expander(
            f"#{row['id']} · {row['created_at']} · {row['nickname']} · {row['category']}{mid_txt}"
        ):
            st.markdown(row["body"])
