"""AppTest가 앱 안에서의 st.query_params 변경을 밖에서 관찰 가능하게 해 주는지 확인.

이 관찰 가능 여부가 확정되어야 '생일/행운수 이동 버튼' 테스트를 쓸 수 있다.
"""

from streamlit.testing.v1 import AppTest

SRC = """
import streamlit as st

if st.button("go", key="probe_btn"):
    st.query_params["page"] = "birthday"
    st.rerun()

st.write("page=" + str(st.query_params.get("page")))
"""

at = AppTest.from_string(SRC, default_timeout=20)
at.query_params.update({"page": "thunder", "gid": "abc123", "native": "1"})
at.run()

print("초기 run 후 at.query_params =", dict(at.query_params))
print("초기 run 예외 =", at.exception)
print("버튼 개수 =", len(at.button))

at.button(key="probe_btn").click().run()

print("클릭 run 후 at.query_params =", dict(at.query_params))
print("클릭 run 예외 =", at.exception)
print("화면 write 값 =", [m.value for m in at.markdown])
