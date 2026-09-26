"""P0-2 검증용 프로브 페이지 (테스트 전용).

운영 라우팅(app.py)에는 등록되지 않는다 — tests/test_iap_native_branch.py가
AppTest로 이 파일을 실행해, 실제 화면 함수(_render_charge_actions /
advanced_subscription_dialog)를 사용자가 보는 그대로 그려본다. 화면 함수를 직접
부르므로 "버튼이 어느 분기로 그려지는가"만 정확히 본다.

- ?probe=charge → 충전 화면(wallet_ui._render_charge_actions)
- ?probe=sub    → 고급필터 구독 안내창(wallet_ui.advanced_subscription_dialog)

member_id는 테스트가 session_state로 미리 심어둔다(로그인된 상태 재현).
"""

import streamlit as st

import wallet_ui

mode = st.query_params.get("probe", "charge")
if isinstance(mode, list):
    mode = mode[0] if mode else "charge"

member_id = st.session_state.get("member_id")
if not member_id:
    st.write("NO_MEMBER")
elif mode == "sub":
    wallet_ui.advanced_subscription_dialog(on_close=lambda: None)
else:
    wallet_ui._render_charge_actions(int(member_id))
