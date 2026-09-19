"""AppTest가 빈 쿼리스트링으로 시작한 앱의 st.query_params 변경을 관찰할 수 있는지 확인.

관찰 지점: 테스트에서 파라미터를 하나도 seed하지 않고 클릭했을 때, 클릭 후
at.query_params에 app이 설정한 'page'가 보이는가?
"""

import os
import sys

from streamlit.testing.v1 import AppTest

SRC = """
import streamlit as st

if st.button("go", key="probe_btn"):
    st.query_params["page"] = "birthday"
    st.rerun()

st.write("page=" + str(st.query_params.get("page")))
"""


def probe(label, seed):
    at = AppTest.from_string(SRC, default_timeout=20)
    at.query_params.update(seed)
    at.run()
    at.button(key="probe_btn").click().run()
    print(f"{label}: seed={seed} -> after_click={dict(at.query_params)}")
    sys.stdout.flush()


probe("empty_seed", {})
probe("seeded_page", {"page": "thunder"})

os._exit(0)
