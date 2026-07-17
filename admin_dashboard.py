import streamlit as st
import pandas as pd
import datetime
import io
import os
import random
import pickle

from lotto_engine import run_filtering_engine

# ==========================================
# 0. 초기화 로직 및 로컬 마스터 파일/데이터 보존 로드
# ==========================================
if "admin_view" not in st.session_state:
    st.session_state.admin_view = "home"

MASTER_FILE = "로또기록 앱 업로드용.xlsb"
FILTER_SAVE_FILE = "saved_filters.pkl"     # 필터 유지용 저장 파일 (로그아웃해도 유지)
COMBO_SAVE_FILE = "saved_combinations.csv" # 조합 결과 유지용 저장 파일 (로그아웃해도 유지)

@st.cache_data(ttl=3600)
def load_lotto_history():
    if os.path.exists(MASTER_FILE):
        try:
            df = pd.read_excel(MASTER_FILE, sheet_name='당번', engine='pyxlsb')
            df_clean = df.dropna(how='all').reset_index(drop=True)
            if df_clean.empty:
                return None, "‘당번’ 시트 내에 읽을 수 있는 데이터가 존재하지 않습니다."
            latest_row = df_clean.iloc[-1]
            return df_clean, latest_row
        except Exception as e:
            return None, f"파일 읽기 오류: {e}"
    return None, "파일 없음"

df_history, latest_info = load_lotto_history()

def change_view(view_name):
    st.session_state.admin_view = view_name

st.set_page_config(page_title="운영자 대시보드", layout="centered", initial_sidebar_state="collapsed")

# ==========================================
# 🎨 고대비/시인성 극대화 커스텀 CSS (탭 글자 흰색 처리 및 지표 흰색 처리)
# ==========================================
st.markdown("""
<style>
    .stApp { background-color: #0B0C10; color: #FFFFFF; font-family: 'Pretendard', sans-serif; }
    
    div[data-testid="metric-container"] { 
        background-color: #1F2330 !important; border: 2px solid #4F5B73 !important; 
        border-radius: 12px !important; padding: 20px !important; 
        box-shadow: 0 4px 15px rgba(0,0,0,0.4);
    }
    
    /* 🔥 지표(Metric) 라벨 텍스트 완벽한 흰색 강제 적용 (어떤 상황에서도 강제 오버라이드) */
    div[data-testid="stMetricLabel"] * { 
        color: #FFFFFF !important; font-size: 1.1rem !important; font-weight: 700 !important; 
    }
    
    div[data-testid="stMetricValue"] > div { 
        color: #00E676 !important; font-size: 2.2rem !important; font-weight: 900 !important; 
    }
    
    .stButton > button { 
        width: 100%; border-radius: 10px; background-color: #1F2330; color: #FFFFFF !important; 
        border: 2px solid #3A4454; padding: 18px 20px; text-align: left; font-size: 1.1rem !important; font-weight: 700 !important;
    }
    .stButton > button:hover { border-color: #FFB300 !important; color: #FFB300 !important; background-color: #2D3446; }
    
    /* 4종 필터 탭 글자 시인성 강화 */
    div[data-testid="stTabs"] button p {
        color: #FFFFFF !important;
        font-weight: 700 !important;
        font-size: 1.1rem !important;
    }
    div[data-testid="stTabs"] button[aria-selected="true"] p {
        color: #00E676 !important;
    }

    /* K-589 — 엑셀 다운로드: 파일명 SKY / 배포 다운로드 ORANGE (추가만) */
    .admin-export-filename-marker,
    .admin-export-download-marker { display: none !important; }

    div[data-testid="stVerticalBlock"]:has(.admin-export-filename-marker) div[data-testid="stTextInput"] input {
        background-color: #87CEEB !important;
        color: #102030 !important;
        border: 2px solid #5BB5D9 !important;
        font-weight: 700 !important;
    }
    div[data-testid="stVerticalBlock"]:has(.admin-export-filename-marker) div[data-testid="stTextInput"] label,
    div[data-testid="stVerticalBlock"]:has(.admin-export-filename-marker) div[data-testid="stTextInput"] label p {
        color: #FFFFFF !important;
        font-weight: 700 !important;
    }

    div[data-testid="stVerticalBlock"]:has(.admin-export-download-marker) div[data-testid="stElementContainer"]:has(.admin-export-download-marker)
        + div[data-testid="stElementContainer"] [data-testid="stDownloadButton"] > button,
    div[data-testid="stVerticalBlock"]:has(.admin-export-download-marker) div[data-testid="stElementContainer"]:has(.admin-export-download-marker)
        + div[data-testid="stElementContainer"] [data-testid="stDownloadButton"] > a,
    div[data-testid="stVerticalBlock"]:has(.admin-export-download-marker) [data-testid="stDownloadButton"] > button,
    div[data-testid="stVerticalBlock"]:has(.admin-export-download-marker) [data-testid="stDownloadButton"] > a {
        background: linear-gradient(135deg, #FFB74D 0%, #FF9800 52%, #F57C00 100%) !important;
        background-color: #FF9800 !important;
        background-image: none !important;
        color: #FFFFFF !important;
        border: 2px solid #EF6C00 !important;
        font-weight: 700 !important;
        box-shadow: none !important;
    }
    div[data-testid="stVerticalBlock"]:has(.admin-export-download-marker) div[data-testid="stElementContainer"]:has(.admin-export-download-marker)
        + div[data-testid="stElementContainer"] [data-testid="stDownloadButton"] > button:hover,
    div[data-testid="stVerticalBlock"]:has(.admin-export-download-marker) div[data-testid="stElementContainer"]:has(.admin-export-download-marker)
        + div[data-testid="stElementContainer"] [data-testid="stDownloadButton"] > a:hover,
    div[data-testid="stVerticalBlock"]:has(.admin-export-download-marker) [data-testid="stDownloadButton"] > button:hover,
    div[data-testid="stVerticalBlock"]:has(.admin-export-download-marker) [data-testid="stDownloadButton"] > a:hover {
        background: linear-gradient(135deg, #FFCC80 0%, #FB8C00 52%, #EF6C00 100%) !important;
        background-color: #FB8C00 !important;
        color: #FFFFFF !important;
        border-color: #E65100 !important;
    }
    div[data-testid="stVerticalBlock"]:has(.admin-export-download-marker) [data-testid="stDownloadButton"] > button p,
    div[data-testid="stVerticalBlock"]:has(.admin-export-download-marker) [data-testid="stDownloadButton"] > a p,
    div[data-testid="stVerticalBlock"]:has(.admin-export-download-marker) [data-testid="stDownloadButton"] > button span,
    div[data-testid="stVerticalBlock"]:has(.admin-export-download-marker) [data-testid="stDownloadButton"] > a span {
        color: #FFFFFF !important;
    }
</style>
""", unsafe_allow_html=True)

# 데이터를 명확하게 보여주기 위한 스타일링 함수 (가독성 텍스트 칼라 적용)
def style_dataframe(df):
    return df.style.set_properties(**{
        'background-color': '#1E293B',
        'color': '#F8FAFC',
        'border-color': '#334155',
        'font-weight': '500',
        'font-size': '14px'
    })

# ==========================================
# 🏠 화면 A: 대시보드 홈
# ==========================================
if st.session_state.admin_view == "home":
    st.markdown("<h2 style='font-weight:800; color:#FFFFFF; margin-bottom:5px;'>운영자 메인 대시보드</h2>", unsafe_allow_html=True)
    st.markdown("<p style='color:#94A3B8; margin-bottom:25px;'>대시보드 운영 현황</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    with col1: st.metric("총 회원 수", "1,248 명")
    with col2: st.metric("프리미엄 회원수", "312 명")
    with col3: st.metric("배포 대기 건수", "645 건")
        
    st.markdown("<h4 style='margin-top:40px; color:#FFB300; font-weight:700;'>작업 프로세스 메뉴</h4>", unsafe_allow_html=True)
    
    # 🔥 기존의 1단계, 2단계 버튼을 완전히 없애고 이 버튼 하나로 통합했습니다.
    if st.button("🚀 4종 필터 업로드 및 원스톱 조합 생성 시작", type="primary"):
        change_view("filter_manage")
        st.rerun()

# ==========================================
# 🔧 [통합] 4종 필터 관리 및 원스톱 조합 생성 시스템
# ==========================================
elif st.session_state.admin_view == "filter_manage":
    if st.button("⬅️ 대시보드 홈으로 이동"):
        change_view("home")
        st.rerun()
    
    st.markdown("<h3 style='color:#FFB300; font-weight:800;'>🔧 4종 필터 통합 관리 및 조합 생성</h3>", unsafe_allow_html=True)
    st.info("💡 엑셀 업로드 후 하단에서 즉시 엔진을 가동하여 조합을 생성할 수 있습니다.")
    
    uploaded_excel = st.file_uploader("📂 주간 통합 패턴 엑셀 업로드 (.xlsx)", type=["xlsx"])

    # 1. 엑셀 업로드 시 파일 파싱 및 로컬 저장
    if uploaded_excel:
        try:
            def get_clean_data(sheet_name):
                df = pd.read_excel(uploaded_excel, sheet_name=sheet_name, skiprows=3, usecols="H:L")
                df.columns = ["그룹명", "구분", "입력데이터", "최소", "최대"]
                df = df.dropna(how='all')
                
                def remove_decimals(val):
                    try:
                        if pd.isna(val) or str(val).strip() == "": return ""
                        return str(int(float(val))) 
                    except:
                        return str(val)
                
                df["구분"] = df["구분"].apply(remove_decimals)
                df["최소"] = df["최소"].apply(remove_decimals)
                df["최대"] = df["최대"].apply(remove_decimals)
                
                df = df.fillna("")
                return df[df["입력데이터"] != ""].reset_index(drop=True)

            filters_data = {
                'basic': get_clean_data('기본필터'),
                'special': get_clean_data('특수필터'),
                'interval': get_clean_data('이격수필터'),
                'absolute': get_clean_data('절대필터')
            }
            with open(FILTER_SAVE_FILE, 'wb') as f:
                pickle.dump(filters_data, f)
                
            st.success("✅ 필터 업로드 성공! 데이터가 시스템에 안전하게 저장되었습니다.")
        except Exception as e:
            st.error(f"❌ 시트명 또는 양식 오류: {e}")

    # 2. 업로드 여부와 상관없이 저장된 파일이 있으면 무조건 렌더링
    if os.path.exists(FILTER_SAVE_FILE):
        with open(FILTER_SAVE_FILE, 'rb') as f:
            saved_filters = pickle.load(f)
            
        def remove_decimals_from_df_cache(df):
            df_safe = df.copy()
            for col in ["구분", "최소", "최대"]:
                if col in df_safe.columns:
                    def force_to_int_str(val):
                        try:
                            if pd.isna(val) or str(val).strip() == "": return ""
                            return str(int(float(val)))
                        except:
                            return str(val)
                    df_safe[col] = df_safe[col].apply(force_to_int_str)
            return df_safe

        st.markdown("<h5 style='color:#00E676; margin-top:20px;'>저장된 필터 데이터 현황 (텍스트 가독성 최적화)</h5>", unsafe_allow_html=True)
        
        tab1, tab2, tab3, tab4 = st.tabs(["기본", "특수", "이격수", "절대"])
        
        with tab1: st.dataframe(style_dataframe(remove_decimals_from_df_cache(saved_filters['basic'])), use_container_width=True, hide_index=True)
        with tab2: st.dataframe(style_dataframe(remove_decimals_from_df_cache(saved_filters['special'])), use_container_width=True, hide_index=True)
        with tab3: st.dataframe(style_dataframe(remove_decimals_from_df_cache(saved_filters['interval'])), use_container_width=True, hide_index=True)
        with tab4: st.dataframe(style_dataframe(remove_decimals_from_df_cache(saved_filters['absolute'])), use_container_width=True, hide_index=True)
            
        st.markdown("---") 
        
        # ==========================================
        # 3. [통합 연동] 조합 생성 엔진 가동 버튼
        # ==========================================
        if st.button("⚡ 4종 필터 기반 조합 연산 실행 (엔진 정밀 필터링)", type="primary"):
            with st.spinner("🚀 8,145,060 조합 전수 검사 엔진 가동 중..."):
                final_data = run_filtering_engine(
                    saved_filters,
                    apply_premium_patterns=False,
                )
                
                df_generated = pd.DataFrame(final_data, columns=["번호1", "번호2", "번호3", "번호4", "번호5", "번호6"])
                df_generated.to_csv(COMBO_SAVE_FILE, index=False)
                st.rerun()
        
        # ==========================================
        # 4. [통합 연동] 결과물 화면 노출 및 다운로드
        # ==========================================
        if os.path.exists(COMBO_SAVE_FILE):
            df_export = pd.read_csv(COMBO_SAVE_FILE)
            total_created = len(df_export)
            
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(f"""
            <div style="background-color: #161B26; border: 2px solid #00E676; padding: 25px; border-radius: 12px; text-align: center; box-shadow: 0 4px 15px rgba(0,230,118,0.15);">
                <h2 style="color: #00E676; margin: 0; font-weight: 900;">🎉 총 {total_created:,}개의 조합이 생성됐습니다.</h2>
                <p style="color: #94A3B8; margin-top: 8px; margin-bottom: 0;">데이터가 시스템에 안전하게 저장되었습니다. (로그아웃 후에도 유지)</p>
            </div>
            <br>
            """, unsafe_allow_html=True)
            
            st.markdown("#### 📊 생성 조합 실시간 모니터링 (상위 15개 추출 분)")
            st.dataframe(style_dataframe(df_export.head(15)), use_container_width=True, hide_index=True)
            
            st.markdown("<h4 style='color:#FFB300; margin-top:30px;'>💾 엑셀 다운로드 (6셀 개별 분할)</h4>", unsafe_allow_html=True)
            
            st.markdown('<div class="admin-export-filename-marker" aria-hidden="true"></div>', unsafe_allow_html=True)
            user_file_name = st.text_input("📝 저장할 파일명을 입력하세요 (확장자 제외):", value=f"필터적용_최종결과_{total_created}조합")
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_export.to_excel(writer, index=False, sheet_name='배포조합')
            
            st.markdown('<div class="admin-export-download-marker" aria-hidden="true"></div>', unsafe_allow_html=True)
            st.download_button(
                label="⬇️ 배포용 엑셀 다운로드 (클릭 시 저장 위치 묻기)",
                data=output.getvalue(),
                file_name=f"{user_file_name}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )