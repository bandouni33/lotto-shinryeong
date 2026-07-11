import streamlit as st
import pandas as pd
import os
import pickle
import time
import re

import importlib
import lotto_engine
importlib.reload(lotto_engine)  # 🔥 캐시된 예전 엔진 무시하고 최신 엔진 강제 로드
from lotto_engine import run_filtering_engine 

FILTER_SAVE_FILE = "user_saved_filters.pkl"
COMBO_STEP1_FILE = "user_step1_combinations.csv"   
COMBO_SAVE_FILE = "user_saved_combinations.csv"     

if 'trigger_step1' not in st.session_state: st.session_state['trigger_step1'] = False
if 'trigger_step2' not in st.session_state: st.session_state['trigger_step2'] = False

def load_recent_win_numbers():
    possible_paths = ["lotto-app/로또최근당첨내역.xlsb", "로또최근당첨내역.xlsb", "lotto-app/로또최근당첨내역.xlsx", "로또최근당첨내역.xlsx"]
    for path in possible_paths:
        if os.path.exists(path):
            try:
                engine_type = "pyxlsb" if path.endswith(".xlsb") else "openpyxl"
                df = pd.read_excel(path, sheet_name="당번", usecols="D:J", skiprows=3, nrows=1, engine=engine_type)
                if not df.empty:
                    values = []
                    for val in df.iloc[0].values:
                        s_val = str(val).strip().replace('+', '')
                        if s_val.isdigit(): values.append(int(s_val))
                        elif s_val.replace('.0', '').isdigit(): values.append(int(float(s_val)))
                    if len(values) >= 6: return values, path
            except Exception: pass
    return [], ""

recent_nums, loaded_path = load_recent_win_numbers()

if recent_nums:
    lotto_engine.PREV_WINNING_NUMS = set(recent_nums[:6])
    neighbor_set = set()
    for n in recent_nums: 
        neighbor_set.add(n)
        if n > 1: neighbor_set.add(n - 1)
        if n < 45: neighbor_set.add(n + 1)
    lotto_engine.PREV_NEIGHBORS = neighbor_set

st.markdown("""
<style>
    .block-container { max-width: 95% !important; padding-top: 2rem !important; }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #FFFFFF !important; border: 1px solid #E2E8F0 !important;
        border-radius: 10px !important; padding: 15px 20px !important;
    }
    .premium-title {
        font-size: 16px !important; font-weight: 800 !important; color: #1E293B !important;
        margin-bottom: 12px; border-bottom: 1px solid #F1F5F9 !important; padding-bottom: 5px;
    }
    .tooltip-icon {
        color: #EF4444; font-size: 14px; cursor: help; margin-left: 5px; font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("<h2 style='color: #1E293B; font-weight: 800;'>📊 프리미엄 패턴 분석 세팅</h2>", unsafe_allow_html=True)

col_left, col_right = st.columns([6, 4])

def draw_premium_pattern(col, title, tooltip, options, icon):
    with col.container(border=True):
        st.markdown(f'<div class="premium-title">{icon} {title} <span class="tooltip-icon" title="{tooltip}">❓</span></div>', unsafe_allow_html=True)
        cc = st.columns(len(options))
        for i, opt in enumerate(options):
            cc[i].checkbox(opt, value=True, key=f"{title}_{opt}")

with col_left:
    r1_c1, r1_c2 = st.columns(2)
    draw_premium_pattern(r1_c1, "홀짝 비율", "당첨번호 6개의 홀수와 짝수 출현 비율입니다.", ["6:0", "5:1", "4:2", "3:3", "2:4", "1:5", "0:6"], "☯️")
    draw_premium_pattern(r1_c2, "쌍둥이수", "11, 22, 33, 44 처럼 똑같은 숫자가 겹치는 번호의 개수입니다.", ["0", "1", "2", "3", "4"], "👯")

    r2_c1, r2_c2 = st.columns(2)
    draw_premium_pattern(r2_c1, "저고 비율", "1~22(저) 번호와 23~45(고) 번호의 출현 비율입니다.", ["6:0", "5:1", "4:2", "3:3", "2:4", "1:5", "0:6"], "📉")
    draw_premium_pattern(r2_c2, "쌍끝수", "1의 자리가 동일한 번호들의 출현 쌍 개수입니다. (예: 12, 32)", ["0개", "1개", "2개", "3개"], "🎯")

    r3_c1, r3_c2 = st.columns(2)
    draw_premium_pattern(r3_c1, "이월수", "직전 회차 당첨번호가 이번에 다시 등장하는 개수입니다.", ["0", "1", "2", "3", "4", "5", "6"], "🔄")
    draw_premium_pattern(r3_c2, "연속번호", "1, 2, 3 처럼 연속되어 나타나는 번호의 개수입니다.", ["없음", "2연번", "3연번", "4연번"], "🔗")

    r4_c1, r4_c2 = st.columns(2)
    draw_premium_pattern(r4_c1, "이웃수", "직전 회차 당첨번호와 1차이 나는 번호들의 출현 개수입니다.", ["0", "1", "2", "3", "4"], "👥")
    draw_premium_pattern(r4_c2, "볼 색상 수", "당첨번호 6개를 구성하는 볼 색깔의 종류 수입니다.", ["1", "2", "3", "4", "모든"], "🎨")

    r5_c1, r5_c2 = st.columns(2)
    with r5_c1.container(border=True):
        st.markdown('<div class="premium-title">🚀 시작/끝번호 핫존 <span class="tooltip-icon" title="첫 번째 공과 마지막 공의 번호 범위입니다.">❓</span></div>', unsafe_allow_html=True)
        rc1, rc2 = st.columns(2)
        rc1.number_input("시작(1~23)", 1, 23, 1, key="시작번호")
        rc2.number_input("끝(28~45)", 28, 45, 45, key="끝번호")
    
    with r5_c2.container(border=True):
        st.markdown('<div class="premium-title">⚖️ 당첨번호 총합 <span class="tooltip-icon" title="당첨번호 6개를 모두 더한 값의 허용 범위입니다.">❓</span></div>', unsafe_allow_html=True)
        rc3, rc4 = st.columns(2)
        rc3.number_input("최소 총합", 70, 205, 70, key="최소총합")
        rc4.number_input("최대 총합", 70, 205, 205, key="최대총합")

with col_right:
    # 💡 우측 소자배 패널 (레이아웃 밀착형)
    with st.container(border=True):
        st.markdown('<div class="premium-title">🔢 소자배 패턴 <span class="tooltip-icon" title="소수: 2,3,5,7,11,13,17,19,23,29,31,37,41,43&#10;자연수(합성수): 1,4,8,10,14,16,20,22,25,26,28,32,34,35,38,40,44&#10;3배수: 3,6,9,12,15,18,21,24,27,30,33,36,39,42,45">❓</span></div>', unsafe_allow_html=True)
        
        header_cols = st.columns([1.5, 1, 1], gap="small")
        header_cols[0].markdown("<div style='text-align: left; font-weight: bold; color: #475569;'>구분</div>", unsafe_allow_html=True)
        header_cols[1].markdown("<div style='text-align: center; font-weight: bold; color: #475569;'>최소</div>", unsafe_allow_html=True)
        header_cols[2].markdown("<div style='text-align: center; font-weight: bold; color: #475569;'>최대</div>", unsafe_allow_html=True)
        
        for label, key_prefix in [("소수", "소수"), ("자연수(합성수)", "자연수"), ("3배수", "3배수")]:
            row_cols = st.columns([1.5, 1, 1], gap="small")
            row_cols[0].markdown(f"<div style='margin-top: 8px; font-size: 14px;'>{label}</div>", unsafe_allow_html=True)
            row_cols[1].number_input(f"{key_prefix}최소", 0, 6, 0, key=f"{key_prefix}_min", label_visibility="collapsed")
            row_cols[2].number_input(f"{key_prefix}최대", 0, 6, 6, key=f"{key_prefix}_max", label_visibility="collapsed")

    # 💡 우측 10단위 패널 (레이아웃 밀착형)
    with st.container(border=True):
        st.markdown('<div class="premium-title">📏 10단위 출현 패턴 <span class="tooltip-icon" title="각 번호대별로 출현할 수 있는 최소/최대 공의 개수를 지정합니다.">❓</span></div>', unsafe_allow_html=True)
        
        header_cols = st.columns([1.5, 1, 1], gap="small")
        header_cols[0].markdown("<div style='text-align: left; font-weight: bold; color: #475569;'>구분</div>", unsafe_allow_html=True)
        header_cols[1].markdown("<div style='text-align: center; font-weight: bold; color: #475569;'>최소</div>", unsafe_allow_html=True)
        header_cols[2].markdown("<div style='text-align: center; font-weight: bold; color: #475569;'>최대</div>", unsafe_allow_html=True)
        
        for label, key_prefix in [("1~9", "1_9"), ("10~19", "10_19"), ("20~29", "20_29"), ("30~39", "30_39"), ("40~45", "40_45")]:
            row_cols = st.columns([1.5, 1, 1], gap="small")
            row_cols[0].markdown(f"<div style='margin-top: 8px; font-size: 14px;'>{label}</div>", unsafe_allow_html=True)
            row_cols[1].number_input(f"{key_prefix}최소", 0, 6, 0, key=f"{key_prefix}_min", label_visibility="collapsed")
            row_cols[2].number_input(f"{key_prefix}최대", 0, 6, 6, key=f"{key_prefix}_max", label_visibility="collapsed")


st.markdown("<br>", unsafe_allow_html=True)
if st.button("⚡ [1단계 공정] 상단 프리미엄 패턴 전수 연산 실행", use_container_width=True, type="primary"):
    st.session_state['trigger_step1'] = True

if os.path.exists(COMBO_STEP1_FILE) and not st.session_state['trigger_step1']:
    df_step1_check = pd.read_csv(COMBO_STEP1_FILE)
    st.info(f"📋 1단계 패턴 통과 조합: **{len(df_step1_check):,}**개")
    if len(df_step1_check) > 0: st.dataframe(df_step1_check.head(15), use_container_width=True, hide_index=True)

# ==========================================================
# ==========================================================
st.markdown("---")
st.markdown("<h3 style='color: #1E293B; font-weight: 800;'>🛠️ 나만의 고급필터 (2단계 전용)</h3>", unsafe_allow_html=True)

# K-295 엑셀 양식 업로드
uploaded_file = st.file_uploader("K-295 엑셀 파일 업로드", type=["xlsx"])

if uploaded_file:
    try:
        # 지정 영역 J5:L1000 데이터 로드
        df_raw = pd.read_excel(uploaded_file, header=None, usecols="H:L", skiprows=4)
        
        # 위치 기반(.iloc)으로 1번째(H), 3번째(J), 4번째(K), 5번째(L) 열만 강제 추출
        df_filter = df_raw.iloc[:, [0, 2, 3, 4]].copy() 
        df_filter.columns = ["패턴이름", "해당숫자", "최소", "최대"]
        
        # '해당숫자' 칸이 비어있는 행은 제외
        df_filter = df_filter.dropna(subset=["해당숫자"])
        
        st.info("💡 아래 표의 셀을 더블클릭하여 '해당숫자', '최소', '최대' 값을 직접 수정할 수 있습니다.")
        
        # 1. 화면에서 직접 엑셀 데이터를 수정할 수 있는 에디터 (edited_df로 저장)
        edited_df = st.data_editor(df_filter, use_container_width=True, num_rows="dynamic")
        
        if st.button("🚀 2단계: 1단계 결과물에 고급필터 적용하기"):
            try:
                # 1단계 결과 파일 로드
                step1_df = pd.read_csv("user_step1_combinations.csv") 
                step1_df = step1_df.apply(pd.to_numeric, errors='coerce').fillna(0).astype(int)
                
                # 엑셀 필터 데이터 규칙 배열로 추출 (수정된 edited_df 반영)
                rules = []
                for _, row in edited_df.iterrows():
                    clean_str = str(row['해당숫자']).replace(',', ' ')
                    nums = set(map(int, clean_str.split()))
                    rules.append({'targets': nums, 'min': int(row['최소']), 'max': int(row['최대'])})
                
                # 2단계 전용 엔진 실행
                with st.spinner("2단계 고급필터 연산 중..."):
                    final_df = lotto_engine.run_step2_filtering(step1_df, rules)
                
                # 결과 출력 및 다운로드 버튼 생성
                if len(final_df) > 0:
                    st.success(f"🎉 최종 조합 {len(final_df):,}개 추출 완료!")
                    st.dataframe(final_df)
                    
                    # 시스템 내부용 백업 저장
                    final_df.to_csv("user_final_combinations.csv", index=False)
                    
                    # 2. 사용자가 직접 이름/위치를 지정해 다운로드할 수 있는 버튼
                    csv_data = final_df.to_csv(index=False, encoding='utf-8-sig')
                    
                    st.markdown("### 💾 결과물 저장하기")
                    st.download_button(
                        label="📥 최종 조합 결과 PC에 저장하기 (CSV)",
                        data=csv_data,
                        file_name="최종_고급필터_조합.csv", # 기본으로 뜰 파일명
                        mime="text/csv",
                    )
                else:
                    st.warning("⚠️ 산출된 조합이 0개입니다. 엑셀의 최소/최대 조건들이 서로 충돌하지 않는지 확인해주세요.")
                    
            except FileNotFoundError:
                st.error("🚨 1단계 결과 파일('user_step1_combinations.csv')을 찾을 수 없습니다. 1단계 연산을 먼저 실행해주세요.")
                
    except Exception as e:
        st.error(f"엑셀 파일을 읽는 중 오류가 발생했습니다: {e}")