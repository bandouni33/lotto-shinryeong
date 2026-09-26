"""타로 추가뽑기 게이트 검증용 프로브(테스트 전용).

운영 라우팅(app.py)에는 등록되지 않는다 — tests/test_tarot_gate_flow.py가
AppTest로 이 파일을 실행해 실제 페이지를 사용자가 보는 그대로 그린다.

- ?probe=dismiss : 적립금 안내창 X닫기 계약(어떤 세션 플래그가 지워지는가)
- ?probe=gate    : 타로 페이지(tarot_page.render)를 그대로 렌더
- ?probe=extra_gate : 추가뽑기 게이트만 렌더(페이지 전체 로그인 게이트 미경유)

member_id·오늘 뽑기 횟수는 테스트가 session_state로 미리 심어둔다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
for _path in (str(ROOT), str(ROOT / "tarot")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import wallet_ui  # noqa: E402

mode = st.query_params.get("probe", "gate")
if isinstance(mode, list):
    mode = mode[0] if mode else "gate"

if mode == "dismiss":
    # ?flags=a,b,c 로 넘어온 플래그들을 전부 열어둔 상태에서 X로 닫는 상황을
    # 재현한다(테스트가 기준점 표에서 플래그 목록을 파생해 넘긴다 — 이렇게 해야
    # "한 화면만"이 아니라 모든 대상 화면에 대해 같은 계약을 검사할 수 있다).
    raw = st.query_params.get("flags", "") or ""
    if isinstance(raw, (list, tuple)):
        raw = raw[0] if raw else ""
    flags = [f for f in str(raw).split(",") if f]
    for flag in flags:
        st.session_state[flag] = True
    wallet_ui._points_notice_on_dismiss()
    st.session_state["probe_survivors"] = [f for f in flags if st.session_state.get(f)]
    st.session_state["probe_auto_flag"] = bool(st.session_state.get("auto_show_points"))
elif mode == "extra_gate":
    # 타로 추가뽑기 게이트(적립금 안내창 포함)를 단독으로 그린다. 페이지 전체
    # login_gate를 안 거치므로 "로그인 정보가 없는 상태에서 안내창의 '확인 후
    # 진행'을 누르는" 상황을 그대로 재현할 수 있다(그 경로가 무음 return이었음).
    import tarot_page  # noqa: E402

    tarot_page._render_extra_draw_gate()
else:
    import tarot_page  # noqa: E402

    tarot_page.render()
