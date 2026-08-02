import streamlit as st
import streamlit.components.v1 as components
from birthday_db import init_birthday_table, get_user_birthdays, upsert_birthday, delete_birthday
from user_scope import current_birthday_scope, init_guest_scope
from lucky_numbers import (
    get_life_path_number,
    get_lucky_numbers_from_life_path,
    LIFE_PATH_MEANINGS,
    calculate_lucky_numbers,
    validate_mmdd,
)


def _render_birthday_nav_html() -> str:
    return """
    <div style="display:flex;gap:10px;margin-bottom:12px;">
        <a href="?page=thunder" style="flex:1;text-align:center;background:#fff;color:#1E293B;
           border-radius:12px;padding:12px;font-weight:700;text-decoration:none;min-height:48px;
           display:flex;align-items:center;justify-content:center;box-sizing:border-box;">← 번개조합</a>
        <a href="?" style="flex:1;text-align:center;background:#fff;color:#1E293B;
           border-radius:12px;padding:12px;font-weight:700;text-decoration:none;min-height:48px;
           display:flex;align-items:center;justify-content:center;box-sizing:border-box;">🏠 메인</a>
    </div>
    """


def render():
    init_birthday_table()
    init_guest_scope()

    user_id = current_birthday_scope()

    birthdays = get_user_birthdays(user_id)
    birthday_dict = {b["slot"]: b for b in birthdays}


    # ─── 커스텀 CSS ───
    st.markdown("""
    <style>
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
                <div class="slot-info">{existing["label"]} ({existing["mmdd"]})</div>
                <div class="slot-lucky">{balls_html}</div>
            </div>
            """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
            <div class="slot-card">
                <div class="slot-header">
                    <span class="slot-label">슬롯 {slot}</span>
                </div>
                <div class="slot-info">{existing["label"]} ({existing["mmdd"]})</div>
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

            # 수정 모드
            if st.session_state.get(f"editing_{slot}"):
                col1, col2, col3 = st.columns([3, 2, 1.5])
                with col1:
                    new_label = st.text_input("별칭", value=existing["label"], key=f"elabel_{slot}", label_visibility="collapsed")
                with col2:
                    new_mmdd = st.text_input("월일", value=existing["mmdd"], key=f"emmdd_{slot}", label_visibility="collapsed")
                with col3:
                    if st.button("저장", key=f"save_{slot}", type="primary"):
                        if new_label and new_mmdd:
                            ok, err = validate_mmdd(new_mmdd)
                            if ok:
                                upsert_birthday(user_id, slot, new_label, new_mmdd)
                                st.session_state[f"editing_{slot}"] = False
                                st.rerun()
                            else:
                                st.toast(err or "월일 형식이 올바르지 않습니다.")
                        else:
                            st.toast("별칭과 월일 4자리를 정확히 입력하세요.")

        else:
            # 미등록 슬롯: 한 줄 입력
            st.markdown(f"""
            <div class="slot-card">
                <div class="slot-label">슬롯 {slot} · 미등록</div>
            </div>
            """, unsafe_allow_html=True)

            col1, col2, col3 = st.columns([3, 2, 1.5])
            with col1:
                label = st.text_input("별칭", placeholder="예: 나, 엄마", key=f"label_{slot}", label_visibility="collapsed")
            with col2:
                mmdd = st.text_input("월일", placeholder="0315", key=f"mmdd_{slot}", label_visibility="collapsed")
            with col3:
                if st.button("등록", key=f"reg_{slot}", type="primary"):
                    if label and mmdd:
                        ok, err = validate_mmdd(mmdd)
                        if ok:
                            upsert_birthday(user_id, slot, label, mmdd)
                            st.rerun()
                        else:
                            st.toast(err or "월일 형식이 올바르지 않습니다.")
                    else:
                        st.toast("별칭과 월일 4자리를 정확히 입력하세요.")

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
