"""계정 삭제(회원 탈퇴) 실행 경로 검증용 프로브 — 테스트 전용(운영 라우팅에 없음).

왜 필요한가: Streamlit 다이얼로그 **안**의 버튼 클릭은 AppTest가 재현하지 못한다
(다이얼로그를 다시 만나지 못한다 — tests/test_iap_native_branch.py의 테스터 임시충전
버튼도 같은 이유로 직접 함수 검증을 쓴다). 그래서 확인창의 [회원 탈퇴 실행] 버튼이
부르는 `wallet_ui.perform_account_deletion()`을 그대로 태워, 파기 → 로그아웃 → 완료
안내까지 실제 세션에서 확인한다.

  ?probe=dialog → 확인창(wallet_ui._delete_account_dialog)을 그대로 그린다
  ?probe=run    → wallet_ui.perform_account_deletion()을 그대로 실행한다

member_id는 테스트가 session_state로 미리 심어둔다(로그인된 상태 재현).
"""

import streamlit as st

import wallet_ui

mode = st.query_params.get("probe", "dialog")
if isinstance(mode, list):
    mode = mode[0] if mode else "dialog"

member_id = st.session_state.get("member_id")
if not member_id:
    st.write("NO_MEMBER")
elif mode == "run":
    st.session_state["probe_delete_summary"] = wallet_ui.perform_account_deletion(int(member_id))
    st.write("DELETED")
else:
    wallet_ui._delete_account_dialog(member_id=int(member_id))
