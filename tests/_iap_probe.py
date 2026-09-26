"""P0-2 검증용 프로브 페이지 (테스트 전용).

운영 라우팅(app.py)에는 등록되지 않는다 — tests/test_iap_native_branch.py가
AppTest로 이 파일을 실행해, 실제 화면 함수(_render_charge_actions /
advanced_subscription_dialog)를 사용자가 보는 그대로 그려본다. 화면 함수를 직접
부르므로 "버튼이 어느 분기로 그려지는가"만 정확히 본다.

- ?probe=charge → 충전 화면(wallet_ui._render_charge_actions)
- ?probe=sub    → 고급필터 구독 안내창(wallet_ui.advanced_subscription_dialog)
- ?probe=resume → 로그인 후 재개(_resume_after_auth)만 실행하고 결과 플래그를 session_state에 남긴다

member_id는 테스트가 session_state로 미리 심어둔다(로그인된 상태 재현).
"""

import streamlit as st

import wallet_ui

mode = st.query_params.get("probe", "charge")
if isinstance(mode, list):
    mode = mode[0] if mode else "charge"

member_id = st.session_state.get("member_id")
if mode == "resume":
    # 로그인 완료 직후 wallet_ui._finish_auth_success()가 하는 일과 같은 순서.
    st.session_state["auth_resume_flag"] = st.query_params.get("resume")
    wallet_ui._resume_after_auth()
    st.session_state["probe_af_show_subscribe"] = bool(st.session_state.get("af_show_subscribe"))
elif not member_id:
    st.write("NO_MEMBER")
elif mode == "sub":
    wallet_ui.advanced_subscription_dialog(on_close=lambda: None)
else:
    wallet_ui._render_charge_actions(int(member_id))
