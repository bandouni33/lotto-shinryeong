import streamlit as st
import streamlit.components.v1 as components
from birthday_db import init_birthday_table, get_user_birthdays, upsert_birthday, delete_birthday
from user_scope import current_birthday_scope, init_guest_scope, internal_nav_href
from lucky_numbers import (
    get_life_path_number,
    get_lucky_numbers_from_life_path,
    LIFE_PATH_MEANINGS,
    calculate_lucky_numbers,
    validate_mmdd,
)


def _render_birthday_nav_html() -> str:
    # 2026-08-28: "메인으로"는 네이티브 앱 툴바가 이미 자체 "← 메인" 버튼을 갖고
    # 있어(showBack, streamlit-webview.tsx) 화면 공간만 차지하는 중복이라 제거하고,
    # 자리를 거의 안 차지하는 작은 로고 링크로 대신한다(브라우저로 직접 열었을 땐
    # 툴바가 없어 메인으로 갈 방법이 없어지므로). "← 번개조합"은 툴바가 대신해주지
    # 않는(메인이 아니라 번개조합으로 돌아가는) 이동이라 그대로 남긴다.
    # (주의: 아래 HTML을 여러 줄로 들여써서 반환하면 Streamlit이 마크다운 코드
    # 블록으로 오인해 태그를 그대로 텍스트로 찍어버린다 — 실기기 확인된 버그라
    # 한 줄짜리 문자열로 이어붙인다.)
    from shared_ui_styles import brand_home_link_css, brand_home_link_html

    return (
        brand_home_link_css()
        + brand_home_link_html()
        + f'<a href="{internal_nav_href("thunder")}" style="text-align:center;background:#fff;color:#1E293B;'
        "border-radius:12px;padding:12px;font-weight:700;text-decoration:none;min-height:48px;"
        'display:flex;align-items:center;justify-content:center;box-sizing:border-box;'
        'margin-bottom:12px;">← 번개조합</a>'
    )


def render():
    init_birthday_table()
    init_guest_scope()


    # ─── 커스텀 CSS ───
    st.markdown("""
    <style>
    /* 이 페이지만 .stApp에 어두운 배경을 안 걸어놔서, 다른 페이지들과 달리
       Streamlit 기본 밝은 배경(연보라)이 그대로 보였다 — 어두운 네이티브 앱
       틀 안에서 위쪽이 텅 빈 밝은 사각형처럼 보이는 원인이었다(실측: DOM 여백
       자체는 정상이라 "빈 공간"이 아니라 배경색 불일치 문제였음). */
    .stApp { background-color: #12182b; }
    html, body, #root, .stApp, [data-testid="stAppViewContainer"],
    [data-testid="stAppViewContainer"] > section.main {
        overflow-x: hidden !important;
    }
    /* .block-container가 기본적으로 위쪽 96px를 Streamlit 자체 헤더 자리로 비워둔다
       — 배경색 불일치 말고 이 여백도 실제로 있었다(뒤늦게 실측 확인). 헤더는 화면에
       없는데 자리만 남아있던 것 — 자동구매 페이지와 동일하게 맞춘다. */
    .block-container { padding-top: 10px !important; }
    header[data-testid="stHeader"], section[data-testid="stSidebar"] {
        display: none !important;
    }
    .birthday-title {
        text-align: center;
        font-size: 1.4rem;
        font-weight: bold;
        color: #ffb300;
        margin-bottom: 0.2rem;
    }
    .birthday-subtitle {
        text-align: center;
        font-size: 0.78rem;
        color: #aaa;
        margin-bottom: 1.2rem;
    }
    .slot-card {
        background: linear-gradient(135deg, #1e2740 0%, #1a1f35 100%);
        border: 1px solid #2a3555;
        border-radius: 12px;
        padding: 12px 14px;
        margin-bottom: 10px;
    }
    .slot-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .slot-label {
        font-size: 0.7rem;
        color: #888;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .slot-info {
        font-size: 0.95rem;
        color: #fff;
        font-weight: 600;
        margin-top: 4px;
    }
    .slot-lucky {
        margin-top: 6px;
    }
    .lucky-ball {
        display: inline-block;
        width: 26px;
        height: 26px;
        line-height: 26px;
        text-align: center;
        border-radius: 50%;
        background: linear-gradient(135deg, #e040fb, #ab47bc);
        color: #fff;
        font-size: 0.7rem;
        font-weight: bold;
        margin: 1px 2px;
    }
    .life-path-badge {
        display: inline-block;
        background: linear-gradient(135deg, #ffb300, #ff8f00);
        color: #000;
        font-size: 0.65rem;
        font-weight: bold;
        padding: 2px 7px;
        border-radius: 10px;
        margin-left: 6px;
    }
    .section-divider {
        border: none;
        border-top: 1px solid #2a3555;
        margin: 1.2rem 0;
    }
    .info-box {
        background: #1a1f35;
        border: 1px solid #2a3555;
        border-radius: 10px;
        padding: 12px 14px;
        margin-top: 0.8rem;
    }
    .info-box h4 {
        color: #ffb300;
        font-size: 0.85rem;
        margin-bottom: 6px;
    }
    .info-box p {
        color: #aaa;
        font-size: 0.75rem;
        line-height: 1.5;
        margin: 0;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown(_render_birthday_nav_html(), unsafe_allow_html=True)

    # 2026-09-11(사용자 지시): 로그인 없이도 행운수 생일을 등록·수정·삭제할 수
    # 있었다. 더 심각한 건 birthday_scope_for()가 미로그인 시 회원별/기기별
    # 구분 없이 전부 같은 값("guest_local") 하나로 스코프된다는 점 — 로그인 안 한
    # 모든 방문자가 사실상 하나의 공유 등록 목록을 같이 보고 수정·삭제할 수 있는
    # 상태였다(guest_id별도 아니고 완전 전역 공유, 저장내역보다 더 심각한 경우).
    # 로그인하면 스코프가 회원별("m_{member_id}")로 바뀌는데, 로그인 전에 등록한
    # 건 이 공유 버킷에만 남아 있어서 "번개조합에서 행운수를 못 불러온다"는 신고로
    # 이어졌다. 페이지 전체를 로그인 게이트로 막아 앞으로는 항상 회원 스코프로만
    # 저장·조회되게 한다(로그인 안내는 통합 login_gate로만 — 사용자 지시).
    from wallet_ui import login_gate

    # 2026-09-12(사용자 지시 — 타로와 동일하게 적용): 이 화면도 전체가 로그인
    # 없인 빈 화면뿐이라, ×로 닫아도 그 자리에 "로그인이 필요합니다"만 남으면
    # 자동구매 등 부분 게이트 화면과 경험이 달라 보인다 — ×를 누르면 메인
    # 화면으로 돌려보낸다.
    if not login_gate(dismiss_redirect="main"):
        from combo_history_ui import render_login_required_notice

        render_login_required_notice()
        return

    user_id = current_birthday_scope()
    birthdays = get_user_birthdays(user_id)
    birthday_dict = {b["slot"]: b for b in birthdays}

    # ─── 타이틀 ───
    st.markdown('<div class="birthday-title">🎯 행운수 생일 등록</div>', unsafe_allow_html=True)
    st.markdown('<div class="birthday-subtitle">월일 4자리 등록 → 수비학 행운수 자동 산출 (최대 4명)</div>', unsafe_allow_html=True)

    # ─── 슬롯 1~4 ───
    for slot in range(1, 5):
        existing = birthday_dict.get(slot)

        if existing:
            mmdd_ok, mmdd_err = validate_mmdd(existing["mmdd"])
            if mmdd_ok:
                lp = get_life_path_number(existing["mmdd"])
                lucky = get_lucky_numbers_from_life_path(lp)
                balls_html = "".join([f'<span class="lucky-ball">{n}</span>' for n in lucky])

                st.markdown(f"""
            <div class="slot-card">
                <div class="slot-header">
                    <span class="slot-label">슬롯 {slot}</span>
                    <span class="life-path-badge">생명수 {lp}</span>
                </div>
                <div class="slot-info">{existing["mmdd"]}</div>
                <div class="slot-lucky">{balls_html}</div>
            </div>
            """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
            <div class="slot-card">
                <div class="slot-header">
                    <span class="slot-label">슬롯 {slot}</span>
                </div>
                <div class="slot-info">{existing["mmdd"]}</div>
            </div>
            """, unsafe_allow_html=True)
                st.warning(f"월일 형식 오류: {mmdd_err} (예: 0315)")

            # 수정/삭제 버튼 (한 줄)
            c1, c2, c3 = st.columns([4, 3, 3])
            with c2:
                if st.button("✏️ 수정", key=f"edit_{slot}", type="secondary"):
                    st.session_state[f"editing_{slot}"] = True
                    st.rerun()
            with c3:
                if st.button("🗑️ 삭제", key=f"del_{slot}", type="secondary"):
                    delete_birthday(user_id, slot)
                    st.rerun()

            # 수정 모드 — 2026-09-11(사용자 지시): "나/엄마" 같은 별칭 입력을 없앤다.
            # 개인정보 노출 우려("이 생일은 누구 것"이라는 라벨을 서버에 남기지
            # 않음) + 애초에 행운수 계산(get_life_path_number 등)엔 월일만 쓰이고
            # 별칭은 화면 표시용일 뿐이라 없어도 기능에 지장 없다.
            if st.session_state.get(f"editing_{slot}"):
                col1, col2 = st.columns([3, 1.5])
                with col1:
                    new_mmdd = st.text_input("월일", value=existing["mmdd"], key=f"emmdd_{slot}", label_visibility="collapsed")
                with col2:
                    if st.button("저장", key=f"save_{slot}", type="primary"):
                        if new_mmdd:
                            ok, err = validate_mmdd(new_mmdd)
                            if ok:
                                upsert_birthday(user_id, slot, "", new_mmdd)
                                st.session_state[f"editing_{slot}"] = False
                                st.rerun()
                            else:
                                st.toast(err or "월일 형식이 올바르지 않습니다.")
                        else:
                            st.toast("월일 4자리를 정확히 입력하세요.")

        else:
            # 미등록 슬롯: 한 줄 입력
            st.markdown(f"""
            <div class="slot-card">
                <div class="slot-label">슬롯 {slot} · 미등록</div>
            </div>
            """, unsafe_allow_html=True)

            # 2026-09-11(사용자 지시): "나/엄마" 같은 별칭 입력칸을 없앤다 — 개인정보
            # 노출 우려. 월일만 등록하면 바로 행운수가 산출되게 한다(별칭은 애초에
            # 화면 표시용일 뿐, get_life_path_number 등 계산엔 안 쓰임). DB
            # 컬럼(label)은 NOT NULL이라 빈 문자열로 채운다.
            col1, col2 = st.columns([3, 1.5])
            with col1:
                mmdd = st.text_input("월일", placeholder="0315", key=f"mmdd_{slot}", label_visibility="collapsed")
            with col2:
                if st.button("등록", key=f"reg_{slot}", type="primary"):
                    if mmdd:
                        ok, err = validate_mmdd(mmdd)
                        if ok:
                            upsert_birthday(user_id, slot, "", mmdd)
                            st.rerun()
                        else:
                            st.toast(err or "월일 형식이 올바르지 않습니다.")
                    else:
                        st.toast("월일 4자리를 정확히 입력하세요.")

    # [문제5] 하단에도 네비 유지 (수정·삭제 폼 아래)
    st.markdown(_render_birthday_nav_html(), unsafe_allow_html=True)

    # ─── 수비학 설명 ───
    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
    st.markdown("""
    <div class="info-box">
        <h4>📖 수비학(Numerology) 행운수 원리</h4>
        <p>
        월일 숫자를 한 자릿수로 축소 → 생명수(1~9) → 행운수 3개 산출  

        예) 0315 → 0+3+1+5 = 9 → 생명수 9 → 행운수 [9, 18, 27]
        </p>
    </div>
    """, unsafe_allow_html=True)
