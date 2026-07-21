# 로또신령 — 소스코드 발췌 (앞부분)

> 전체 56개 Python 파일(총 10,129줄)을 경로명 알파벳 순으로 연결한 뒤, 앞에서 1650줄을 추출했습니다. (연결본 전체: 10,185줄, 파일 구분 헤더 포함)

```python
# ===== FILE: admin_dashboard.py =====
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

            # ==========================================
            # 5. [마케팅 DB] 추출 조합 익명 저장 (백엔드)
            # ==========================================
            from marketing_db import (
                bulk_insert_lotto_combinations,
                get_combination_count_by_draw,
                init_marketing_tables,
                parse_combination_rows_from_dataframe,
                parse_combination_rows_from_text,
            )

            init_marketing_tables()
            st.markdown("---")
            st.subheader("📥 추출 조합 DB 저장")
            draw_round_save = st.number_input(
                "저장할 회차",
                min_value=1,
                step=1,
                key="admin_marketing_draw_round",
            )
            combo_input_mode = st.radio(
                "입력 방식",
                ["현재 추출 결과 사용", "텍스트 직접 입력", "CSV 파일 업로드"],
                horizontal=True,
                key="admin_combo_input_mode",
            )

            rows_to_save = None
            if combo_input_mode == "현재 추출 결과 사용":
                rows_to_save = df_export.values.tolist()
            elif combo_input_mode == "텍스트 직접 입력":
                combo_text = st.text_area(
                    "조합 입력 (한 줄에 6개 번호, 쉼표 또는 공백 구분)",
                    height=150,
                    key="admin_combo_text_bulk",
                )
                if combo_text.strip():
                    rows_to_save = parse_combination_rows_from_text(combo_text)
            else:
                combo_upload = st.file_uploader(
                    "CSV 업로드 (번호1~6 또는 num1~6)",
                    type=["csv"],
                    key="admin_combo_csv_bulk",
                )
                if combo_upload is not None:
                    rows_to_save = parse_combination_rows_from_dataframe(
                        pd.read_csv(combo_upload)
                    )

            if st.button("추출 조합 저장", type="primary", key="admin_save_combos_db"):
                try:
                    if not rows_to_save:
                        st.warning("저장할 조합이 없습니다.")
                    else:
                        saved_count = bulk_insert_lotto_combinations(
                            int(draw_round_save),
                            rows_to_save,
                        )
                        total_in_db = get_combination_count_by_draw(int(draw_round_save))
                        st.success(
                            f"회차 {int(draw_round_save)}: {saved_count:,}개 조합 저장 완료 "
                            f"(해당 회차 DB 누적 {total_in_db:,}개)"
                        )
                except Exception as e:
                    st.error(f"저장 오류: {e}")
# ===== FILE: admin_filter.py =====
import streamlit as st
import pandas as pd
import os
import pickle
import time
import re
import html
import base64
from datetime import date

import importlib
import lotto_engine
importlib.reload(lotto_engine)  # 🔥 캐시된 예전 엔진 무시하고 최신 엔진 강제 로드
from lotto_engine import run_filtering_engine 

FILTER_SAVE_FILE = "user_saved_filters.pkl"
COMBO_STEP1_FILE = "user_step1_combinations.csv"   
COMBO_SAVE_FILE = "user_saved_combinations.csv"     

USERS_DATA_ROOT = "data/users"
PREMIUM_SETTINGS_FILENAME = "premium_settings.pkl"
ADVANCED_FILTER_FILENAME = "saved_advanced_filter.csv"
SHOW_EMAIL_PROMPT = False  # True로 변경 시 이메일 입력 UI 재활성화
GUEST_EMAIL_FALLBACK = "_guest@local"
AF_NOTICE_DISMISS_FILE = os.path.join("data", ".af_mobile_notice_dismiss_date")

if 'trigger_step1' not in st.session_state: st.session_state['trigger_step1'] = False
if 'trigger_step2' not in st.session_state: st.session_state['trigger_step2'] = False
if 'settings_saved' not in st.session_state: st.session_state['settings_saved'] = False
if 'saved_settings' not in st.session_state: st.session_state['saved_settings'] = None

_PREMIUM_CHECKBOX_PATTERNS = [
    ("홀짝 비율", ["6:0", "5:1", "4:2", "3:3", "2:4", "1:5", "0:6"]),
    ("저고 비율", ["6:0", "5:1", "4:2", "3:3", "2:4", "1:5", "0:6"]),
    ("이월수", ["0", "1", "2", "3", "4", "5", "6"]),
    ("이웃수", ["0", "1", "2", "3", "4"]),
    ("쌍둥이수", ["0", "1", "2", "3", "4"]),
    ("쌍끝수", ["0개", "1개", "2개", "3개"]),
    ("연속번호", ["없음", "2연번", "3연번", "4연번"]),
    ("볼 색상 수", ["1", "2", "3", "4", "모든"]),
]
_PREMIUM_RANGE_PREFIXES = ["1_9", "10_19", "20_29", "30_39", "40_45"]


def _collect_premium_settings() -> dict:
    """화면 위젯(session_state)에서 프리미엄 패턴 세팅 스냅샷 수집."""
    settings = {}
    for title, options in _PREMIUM_CHECKBOX_PATTERNS:
        settings[title] = [
            opt for opt in options if st.session_state.get(f"{title}_{opt}", False)
        ]
    settings["소수"] = (
        st.session_state.get("소수_min", 0),
        st.session_state.get("소수_max", 6),
    )
    settings["자연수"] = (
        st.session_state.get("자연수_min", 0),
        st.session_state.get("자연수_max", 6),
    )
    settings["3배수"] = (
        st.session_state.get("3배수_min", 0),
        st.session_state.get("3배수_max", 6),
    )
    for prefix in _PREMIUM_RANGE_PREFIXES:
        settings[prefix] = (
            st.session_state.get(f"{prefix}_min", 0),
            st.session_state.get(f"{prefix}_max", 6),
        )
    settings["시작번호"] = st.session_state.get("시작번호", 1)
    settings["끝번호"] = st.session_state.get("끝번호", 45)
    settings["최소총합"] = st.session_state.get("최소총합", 70)
    settings["최대총합"] = st.session_state.get("최대총합", 205)
    return settings


def _sync_settings_saved_state() -> None:
    """저장 후 값이 바뀌면 저장 상태 무효화."""
    if not st.session_state.get("settings_saved"):
        return
    if st.session_state.get("saved_settings") != _collect_premium_settings():
        st.session_state["settings_saved"] = False


def _run_step1_with_saved_settings() -> None:
    """저장된 세팅값으로 1단계 프리미엄 패턴 전수 연산 실행."""
    progress_bar = st.progress(0)
    status_text = st.empty()

    def _progress(current: int, total: int) -> None:
        ratio = current / total if total else 0
        progress_bar.progress(min(ratio, 1.0))
        status_text.text(f"1단계 연산 중... {current:,} / {total:,}")

    results = run_filtering_engine(
        {},
        premium_settings=st.session_state.saved_settings,
        progress_callback=_progress,
    )
    df_out = pd.DataFrame(results, columns=[f"번호{i + 1}" for i in range(6)])
    df_out.to_csv(COMBO_STEP1_FILE, index=False)
    progress_bar.empty()
    status_text.success(f"✅ 1단계 완료 — 패턴 통과 조합 {len(df_out):,}개")


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _is_valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def get_user_data_dir(email: str | None = None) -> str:
    """data/users/{이메일}/ 폴더 경로 반환 및 생성."""
    user_email = _normalize_email(email or st.session_state.get("user_email", ""))
    user_dir = os.path.join(USERS_DATA_ROOT, user_email)
    os.makedirs(user_dir, exist_ok=True)
    return user_dir


def get_user_premium_settings_path(email: str | None = None) -> str:
    """data/users/{이메일}/premium_settings.pkl 경로 반환."""
    return os.path.join(get_user_data_dir(email), PREMIUM_SETTINGS_FILENAME)


def _load_premium_settings_from_disk() -> dict | None:
    """디스크에 저장된 프리미엄 세팅 불러오기."""
    path = get_user_premium_settings_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            payload = pickle.load(f)
        if isinstance(payload, dict) and payload.get("saved_settings"):
            return payload
    except Exception:
        return None
    return None


def _save_premium_settings_to_disk(settings: dict) -> None:
    """프리미엄 세팅을 사용자별 pkl 파일에 영구 저장."""
    path = get_user_premium_settings_path()
    payload = {
        "saved_settings": settings,
        "settings_saved": True,
    }
    with open(path, "wb") as f:
        pickle.dump(payload, f)


def _apply_premium_settings_to_session(settings: dict) -> None:
    """저장된 스냅샷을 위젯 session_state 키에 반영 (렌더 전 호출)."""
    if not settings:
        return
    for title, options in _PREMIUM_CHECKBOX_PATTERNS:
        selected = set(settings.get(title, []))
        for opt in options:
            st.session_state[f"{title}_{opt}"] = opt in selected
    for key in ("소수", "자연수", "3배수"):
        pair = settings.get(key, (0, 6))
        if isinstance(pair, (list, tuple)) and len(pair) >= 2:
            st.session_state[f"{key}_min"] = int(pair[0])
            st.session_state[f"{key}_max"] = int(pair[1])
    for prefix in _PREMIUM_RANGE_PREFIXES:
        pair = settings.get(prefix, (0, 6))
        if isinstance(pair, (list, tuple)) and len(pair) >= 2:
            st.session_state[f"{prefix}_min"] = int(pair[0])
            st.session_state[f"{prefix}_max"] = int(pair[1])
    for key in ("시작번호", "끝번호", "최소총합", "최대총합"):
        if key in settings:
            st.session_state[key] = int(settings[key])


def _hydrate_premium_settings_from_disk() -> None:
    """페이지 로드 시 디스크 세팅 → session_state + UI 위젯 동기화."""
    if st.session_state.get("_premium_settings_hydrated"):
        return
    payload = _load_premium_settings_from_disk()
    if payload and payload.get("settings_saved") and payload.get("saved_settings"):
        settings = payload["saved_settings"]
        _apply_premium_settings_to_session(settings)
        st.session_state.saved_settings = settings
        st.session_state.settings_saved = True
    st.session_state["_premium_settings_hydrated"] = True


def get_advanced_filter_cache_path(email: str | None = None) -> str:
    """data/users/{이메일}/saved_advanced_filter.csv 경로 반환."""
    return os.path.join(get_user_data_dir(email), ADVANCED_FILTER_FILENAME)


def _parse_k295_excel(uploaded_file) -> pd.DataFrame:
    """K-295 엑셀 양식에서 고급필터 규칙 데이터프레임 추출."""
    df_raw = pd.read_excel(uploaded_file, header=None, usecols="H:L", skiprows=4)
    df_filter = df_raw.iloc[:, [0, 2, 3, 4]].copy()
    df_filter.columns = ["패턴이름", "해당숫자", "최소", "최대"]
    df_filter = df_filter.dropna(subset=["해당숫자"])
    df_filter["패턴이름"] = df_filter["패턴이름"].astype(str)
    df_filter["해당숫자"] = df_filter["해당숫자"].astype(str)
    df_filter["최소"] = pd.to_numeric(df_filter["최소"], errors="coerce").fillna(0).astype(int)
    df_filter["최대"] = pd.to_numeric(df_filter["최대"], errors="coerce").fillna(0).astype(int)
    return df_filter.reset_index(drop=True)


def _load_advanced_filter_from_disk() -> pd.DataFrame | None:
    """디스크에 저장된 고급필터 규칙 불러오기."""
    path = get_advanced_filter_cache_path()
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
        expected = ["패턴이름", "해당숫자", "최소", "최대"]
        if list(df.columns) != expected:
            df.columns = expected[: len(df.columns)]
        df = df.dropna(subset=["해당숫자"])
        df["패턴이름"] = df["패턴이름"].astype(str)
        df["해당숫자"] = df["해당숫자"].astype(str)
        df["최소"] = pd.to_numeric(df["최소"], errors="coerce").fillna(0).astype(int)
        df["최대"] = pd.to_numeric(df["최대"], errors="coerce").fillna(0).astype(int)
        return df.reset_index(drop=True)
    except Exception:
        return None


def _save_advanced_filter_to_disk(df: pd.DataFrame) -> None:
    """고급필터 규칙을 사용자별 CSV 캐시에 영구 저장."""
    path = get_advanced_filter_cache_path()
    df.to_csv(path, index=False, encoding="utf-8-sig")


def _hydrate_advanced_filter_from_disk() -> None:
    """페이지 로드 시 디스크 고급필터 → session_state 복구."""
    if st.session_state.get("_advanced_filter_hydrated"):
        return
    cached = _load_advanced_filter_from_disk()
    if cached is not None and not cached.empty:
        st.session_state["af_advanced_filter_df"] = cached
    st.session_state["_advanced_filter_hydrated"] = True


def _get_icon_base64(file_path: str = "K-325.jpg") -> str:
    if os.path.exists(file_path):
        with open(file_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    return ""


def _af_notice_dismissed_today() -> bool:
    if st.session_state.get("af_mobile_notice_dismissed"):
        return True
    if os.path.exists(AF_NOTICE_DISMISS_FILE):
        try:
            with open(AF_NOTICE_DISMISS_FILE, "r", encoding="utf-8") as f:
                return f.read().strip() == date.today().isoformat()
        except OSError:
            pass
    return False


def _save_af_notice_dismiss_today() -> None:
    os.makedirs(os.path.dirname(AF_NOTICE_DISMISS_FILE), exist_ok=True)
    with open(AF_NOTICE_DISMISS_FILE, "w", encoding="utf-8") as f:
        f.write(date.today().isoformat())
    st.session_state.af_mobile_notice_dismissed = True


def _prompt_user_email() -> None:
    """session_state에 이메일이 없으면 최상단에서 1회 입력받음."""
    if not SHOW_EMAIL_PROMPT:
        if not st.session_state.get("user_email"):
            st.session_state["user_email"] = GUEST_EMAIL_FALLBACK
            get_user_data_dir(GUEST_EMAIL_FALLBACK)
        return

    if st.session_state.get("user_email"):
        return

    email_input = st.text_input(
        "설정을 저장/불러오려면 이메일을 입력하세요 (인증 없음, 식별용)",
        key="user_email_input_6n36s5",
    )
    if st.button("이메일 확인", key="user_email_submit_6n36s5"):
        email = _normalize_email(email_input or "")
        if _is_valid_email(email):
            st.session_state["user_email"] = email
            get_user_data_dir(email)
            st.rerun()
        else:
            st.warning("올바른 이메일 형식을 입력해주세요.")
    st.stop()


_prompt_user_email()

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
    /* ── Trading Desk Dark Palette ── */
    :root {
        --af-bg-deep: #050508;
        --af-bg-mid: #0A0A0F;
        --af-bg-card: #141428;
        --af-bg-card-alt: #1c1c38;
        --af-text: #E2E8F0;
        --af-text-muted: #94A3B8;
        --af-text-dim: #64748B;
        --af-cyan: #06B6D4;
        --af-violet: #8B5CF6;
        --af-blue: #3B82F6;
        --af-teal: #14B8A6;
        --af-purple: #A855F7;
        --af-amber: #F59E0B;
        --af-rose: #F43F5E;
        --af-emerald: #10B981;
        --af-indigo: #6366F1;
    }

    .stApp, [data-testid="stAppViewContainer"], .main {
        background: linear-gradient(165deg, #050508 0%, #0A0A0F 50%, #07070C 100%) !important;
        color: var(--af-text) !important;
    }

    .block-container {
        max-width: min(98vw, 1760px) !important;
        width: 100% !important;
        margin-left: auto !important;
        margin-right: auto !important;
        padding-top: 1.1rem !important;
        padding-bottom: 2.1rem !important;
        padding-left: 0.75rem !important;
        padding-right: 0.75rem !important;
    }

    /* ── Layout density (column / block gaps) ── */
    div[data-testid="stVerticalBlock"] {
        gap: 0.45rem !important;
    }
    div[data-testid="stHorizontalBlock"] {
        gap: 0.55rem !important;
        align-items: flex-start !important;
    }
    /* 패턴 3열 그리드: 열 간격·카드 폭 확보 */
    div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] .af-col3-stack) {
        gap: 1rem !important;
    }
    div[data-testid="column"] {
        gap: 0.35rem !important;
    }
    div[data-testid="column"] > div[data-testid="stVerticalBlock"] {
        gap: 0.55rem !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"],
    div[data-testid="column"]:has(.premium-card-marker) > div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlock"]:has(.premium-card-marker) {
        overflow: visible !important;
    }
    /* ── 패턴 3열 그리드: K-493 스타일 개별 카드 박스 (stVerticalBlock) ── */
    div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] .af-col3-stack)
        div[data-testid="column"]:not(:has(.af-col3-stack)) > div[data-testid="stVerticalBlock"]
        > div[data-testid="stVerticalBlock"]:has(.premium-card-marker):not(:has(.af-placeholder-card)) {
        background: linear-gradient(165deg, #181832 0%, #141428 52%, #10101f 100%) !important;
        border: 2px solid rgba(203, 213, 225, 0.28) !important;
        border-radius: 10px !important;
        padding: 16px 18px !important;
        margin-bottom: 0 !important;
        box-shadow:
            0 6px 22px rgba(0, 0, 0, 0.62),
            0 0 0 1px rgba(255, 255, 255, 0.06),
            inset 0 1px 0 rgba(255, 255, 255, 0.09) !important;
    }
    /* 1·2열: 카드 사이 간격 균일 */
    div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] .af-col3-stack)
        div[data-testid="column"]:not(:has(.af-col3-stack)) > div[data-testid="stVerticalBlock"] {
        gap: 14px !important;
    }
    /* 3열: 카드 간격 + 개별 카드 박스 (stVerticalBlock + container key) */
    div[data-testid="column"]:has(.af-col3-stack) > div[data-testid="stVerticalBlock"] {
        gap: 14px !important;
    }
    div[data-testid="column"]:has(.af-col3-stack) > div[data-testid="stVerticalBlock"]
        > div[data-testid="stVerticalBlock"]:has(.premium-card-marker),
    div[data-testid="column"]:has(.af-col3-stack) div[data-testid="stVerticalBlock"][class*="af_col3_soja"],
    div[data-testid="column"]:has(.af-col3-stack) div[data-testid="stVerticalBlock"][class*="af_col3_decade"],
    div[data-testid="column"]:has(.af-col3-stack) div[data-testid="stVerticalBlock"][class*="af_col3_hotzone"],
    div[data-testid="column"]:has(.af-col3-stack) div[data-testid="stVerticalBlock"][class*="af_col3_total"] {
        box-sizing: border-box !important;
        width: 100% !important;
        background: linear-gradient(165deg, #181832 0%, #141428 52%, #10101f 100%) !important;
        border: 2px solid rgba(203, 213, 225, 0.28) !important;
        border-radius: 10px !important;
        padding: 16px 18px !important;
        margin-bottom: 0 !important;
        box-shadow:
            0 6px 22px rgba(0, 0, 0, 0.62),
            0 0 0 1px rgba(255, 255, 255, 0.06),
            inset 0 1px 0 rgba(255, 255, 255, 0.09) !important;
    }
    div[data-testid="column"]:has(.af-col3-stack) > div[data-testid="stVerticalBlock"]
        > div[data-testid="stVerticalBlock"]:has(.accent-teal),
    div[data-testid="column"]:has(.af-col3-stack) div[data-testid="stVerticalBlock"][class*="af_col3_soja"] {
        border: 2px solid rgba(20, 184, 166, 0.62) !important;
        box-shadow: 0 6px 22px rgba(0,0,0,0.62), 0 0 0 1px rgba(20,184,166,0.18), 0 0 24px rgba(20,184,166,0.12) !important;
    }
    div[data-testid="column"]:has(.af-col3-stack) > div[data-testid="stVerticalBlock"]
        > div[data-testid="stVerticalBlock"]:has(.accent-violet),
    div[data-testid="column"]:has(.af-col3-stack) div[data-testid="stVerticalBlock"][class*="af_col3_decade"] {
        border: 2px solid rgba(139, 92, 246, 0.62) !important;
        box-shadow: 0 6px 22px rgba(0,0,0,0.62), 0 0 0 1px rgba(139,92,246,0.18), 0 0 24px rgba(139,92,246,0.12) !important;
    }
    div[data-testid="column"]:has(.af-col3-stack) > div[data-testid="stVerticalBlock"]
        > div[data-testid="stVerticalBlock"]:has(.accent-amber),
    div[data-testid="column"]:has(.af-col3-stack) div[data-testid="stVerticalBlock"][class*="af_col3_hotzone"] {
        border: 2px solid rgba(245, 158, 11, 0.62) !important;
        box-shadow: 0 6px 22px rgba(0,0,0,0.62), 0 0 0 1px rgba(245,158,11,0.18), 0 0 24px rgba(245,158,11,0.12) !important;
    }
    div[data-testid="column"]:has(.af-col3-stack) > div[data-testid="stVerticalBlock"]
        > div[data-testid="stVerticalBlock"]:has(.accent-indigo),
    div[data-testid="column"]:has(.af-col3-stack) div[data-testid="stVerticalBlock"][class*="af_col3_total"] {
        border: 2px solid rgba(99, 102, 241, 0.62) !important;
        box-shadow: 0 6px 22px rgba(0,0,0,0.62), 0 0 0 1px rgba(99,102,241,0.18), 0 0 24px rgba(99,102,241,0.12) !important;
    }
    /* 개발중 placeholder 카드 (1·2열 하단) */
    div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] .af-col3-stack)
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.af-placeholder-card) {
        box-sizing: border-box !important;
        width: 100% !important;
        background: linear-gradient(165deg, #152238 0%, #122033 52%, #0f1a2b 100%) !important;
        border: 2px solid rgba(96, 165, 250, 0.48) !important;
        border-radius: 10px !important;
        padding: 16px 18px !important;
        margin-bottom: 0 !important;
        min-height: 126px !important;
        display: flex !important;
        flex-direction: column !important;
        box-shadow:
            0 6px 22px rgba(0, 0, 0, 0.62),
            0 0 0 1px rgba(96, 165, 250, 0.16),
            0 0 18px rgba(59, 130, 246, 0.12),
            inset 0 1px 0 rgba(147, 197, 253, 0.1) !important;
    }
    div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] .af-col3-stack)
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.af-placeholder-card)
        > div[data-testid="stVerticalBlock"] {
        box-sizing: border-box !important;
        flex: 1 1 auto !important;
        width: 100% !important;
        min-height: 100% !important;
        display: flex !important;
        flex-direction: column !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 0 !important;
    }
    div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] .af-col3-stack)
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.af-placeholder-card)
        [data-testid="stMarkdownContainer"]:has(.af-placeholder-card) {
        display: none !important;
        height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
        overflow: hidden !important;
    }
    .af-placeholder-card { display: none !important; }
    .af-placeholder-body {
        box-sizing: border-box !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        flex: 1 1 auto !important;
        width: 100% !important;
        min-height: 92px !important;
        margin: 0 !important;
        padding: 0 !important;
        text-align: center !important;
    }
    .af-placeholder-body span {
        color: rgba(186, 230, 253, 0.92);
        font-size: 17px;
        font-weight: 700;
        letter-spacing: 0.03em;
        text-shadow: 0 1px 4px rgba(0, 0, 0, 0.65), 0 0 12px rgba(59, 130, 246, 0.25);
    }
    /* 카드 내 7열 체크박스 행: 옵션 텍스트가 잘리지 않도록 */
    div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stHorizontalBlock"] {
        overflow: visible !important;
        gap: 0.4rem !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
        overflow: visible !important;
        min-width: 0 !important;
        flex: 1 1 0 !important;
    }

    /* ── Page titles ── */
    .af-page-title {
        color: #F8FAFC !important;
        font-weight: 800 !important;
        font-size: 1.65rem !important;
        margin-bottom: 0.25rem !important;
        text-shadow: 0 0 24px rgba(139, 92, 246, 0.35);
    }
    .af-page-title span {
        background: linear-gradient(90deg, #67e8f9, #a78bfa, #818cf8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    .auto-back-main-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        width: 100%;
        min-height: 48px;
        padding: 8px 12px;
        box-sizing: border-box;
        background: #000000 !important;
        color: #ffffff !important;
        border: 2px solid #333333 !important;
        border-radius: 12px !important;
        text-decoration: none !important;
        font-weight: 700 !important;
        font-size: 14px !important;
    }
    .auto-back-main-btn:hover {
        background: #111111 !important;
        border-color: #555555 !important;
        color: #ffffff !important;
    }
    .auto-back-main-icon {
        width: 28px;
        height: 28px;
        border-radius: 50%;
        object-fit: cover;
        border: 2px solid #ffb300;
        flex-shrink: 0;
    }
    .af-section-title {
        color: #F1F5F9 !important;
        font-weight: 800 !important;
        font-size: 1.25rem !important;
        margin: 0.7rem 0 0.5rem 0 !important;
        padding-bottom: 0.35rem !important;
        border-bottom: 1px solid rgba(139, 92, 246, 0.35) !important;
        text-shadow: 0 0 18px rgba(99, 102, 241, 0.25);
    }

    /* ── Card containers (그리드 외 영역) ── */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: linear-gradient(145deg, var(--af-bg-card) 0%, var(--af-bg-card-alt) 55%, #12122a 100%) !important;
        border-radius: 12px !important;
        padding: 14px 16px !important;
        border: 2px solid rgba(100, 116, 139, 0.42) !important;
        margin-bottom: 0.75rem !important;
        box-shadow:
            0 10px 28px rgba(0, 0, 0, 0.55),
            0 0 0 1px rgba(255, 255, 255, 0.05),
            inset 0 1px 0 rgba(255, 255, 255, 0.06) !important;
        transition: box-shadow 0.2s ease, border-color 0.2s ease;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        box-shadow:
            0 14px 36px rgba(0, 0, 0, 0.58),
            0 0 0 1px rgba(255, 255, 255, 0.07),
            inset 0 1px 0 rgba(255, 255, 255, 0.08) !important;
    }

    .premium-card-marker { display: none; }
    .af-col3-stack { display: none !important; height: 0 !important; margin: 0 !important; padding: 0 !important; }
    /* 패턴 그리드 카드: accent 색상 테두리 유지 */
    div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] .af-col3-stack)
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.accent-cyan) {
        border: 2px solid rgba(6, 182, 212, 0.62) !important;
        box-shadow: 0 6px 22px rgba(0,0,0,0.62), 0 0 0 1px rgba(6,182,212,0.18), 0 0 24px rgba(6,182,212,0.12) !important;
    }
    div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] .af-col3-stack)
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.accent-violet) {
        border: 2px solid rgba(139, 92, 246, 0.62) !important;
        box-shadow: 0 6px 22px rgba(0,0,0,0.62), 0 0 0 1px rgba(139,92,246,0.18), 0 0 24px rgba(139,92,246,0.12) !important;
    }
    div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] .af-col3-stack)
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.accent-blue) {
        border: 2px solid rgba(59, 130, 246, 0.62) !important;
        box-shadow: 0 6px 22px rgba(0,0,0,0.62), 0 0 0 1px rgba(59,130,246,0.18), 0 0 24px rgba(59,130,246,0.12) !important;
    }
    div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] .af-col3-stack)
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.accent-teal) {
        border: 2px solid rgba(20, 184, 166, 0.62) !important;
        box-shadow: 0 6px 22px rgba(0,0,0,0.62), 0 0 0 1px rgba(20,184,166,0.18), 0 0 24px rgba(20,184,166,0.12) !important;
    }
    div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] .af-col3-stack)
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.accent-purple) {
        border: 2px solid rgba(168, 85, 247, 0.62) !important;
        box-shadow: 0 6px 22px rgba(0,0,0,0.62), 0 0 0 1px rgba(168,85,247,0.18), 0 0 24px rgba(168,85,247,0.12) !important;
    }
    div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] .af-col3-stack)
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.accent-amber) {
        border: 2px solid rgba(245, 158, 11, 0.62) !important;
        box-shadow: 0 6px 22px rgba(0,0,0,0.62), 0 0 0 1px rgba(245,158,11,0.18), 0 0 24px rgba(245,158,11,0.12) !important;
    }
    div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] .af-col3-stack)
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.accent-rose) {
        border: 2px solid rgba(244, 63, 94, 0.62) !important;
        box-shadow: 0 6px 22px rgba(0,0,0,0.62), 0 0 0 1px rgba(244,63,94,0.18), 0 0 24px rgba(244,63,94,0.12) !important;
    }
    div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] .af-col3-stack)
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.accent-emerald) {
        border: 2px solid rgba(16, 185, 129, 0.62) !important;
        box-shadow: 0 6px 22px rgba(0,0,0,0.62), 0 0 0 1px rgba(16,185,129,0.18), 0 0 24px rgba(16,185,129,0.12) !important;
    }
    div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] .af-col3-stack)
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.accent-indigo) {
        border: 2px solid rgba(99, 102, 241, 0.62) !important;
        box-shadow: 0 6px 22px rgba(0,0,0,0.62), 0 0 0 1px rgba(99,102,241,0.18), 0 0 24px rgba(99,102,241,0.12) !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.accent-cyan) {
        border: 2px solid rgba(6, 182, 212, 0.62) !important;
        box-shadow: 0 10px 28px rgba(0,0,0,0.55), 0 0 0 1px rgba(6,182,212,0.18), 0 0 24px rgba(6,182,212,0.12) !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.accent-violet) {
        border: 2px solid rgba(139, 92, 246, 0.62) !important;
        box-shadow: 0 10px 28px rgba(0,0,0,0.55), 0 0 0 1px rgba(139,92,246,0.18), 0 0 24px rgba(139,92,246,0.12) !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.accent-blue) {
        border: 2px solid rgba(59, 130, 246, 0.62) !important;
        box-shadow: 0 10px 28px rgba(0,0,0,0.55), 0 0 0 1px rgba(59,130,246,0.18), 0 0 24px rgba(59,130,246,0.12) !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.accent-teal) {
        border: 2px solid rgba(20, 184, 166, 0.62) !important;
        box-shadow: 0 10px 28px rgba(0,0,0,0.55), 0 0 0 1px rgba(20,184,166,0.18), 0 0 24px rgba(20,184,166,0.12) !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.accent-purple) {
        border: 2px solid rgba(168, 85, 247, 0.62) !important;
        box-shadow: 0 10px 28px rgba(0,0,0,0.55), 0 0 0 1px rgba(168,85,247,0.18), 0 0 24px rgba(168,85,247,0.12) !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.accent-amber) {
        border: 2px solid rgba(245, 158, 11, 0.62) !important;
        box-shadow: 0 10px 28px rgba(0,0,0,0.55), 0 0 0 1px rgba(245,158,11,0.18), 0 0 24px rgba(245,158,11,0.12) !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.accent-rose) {
        border: 2px solid rgba(244, 63, 94, 0.62) !important;
        box-shadow: 0 10px 28px rgba(0,0,0,0.55), 0 0 0 1px rgba(244,63,94,0.18), 0 0 24px rgba(244,63,94,0.12) !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.accent-emerald) {
        border: 2px solid rgba(16, 185, 129, 0.62) !important;
        box-shadow: 0 10px 28px rgba(0,0,0,0.55), 0 0 0 1px rgba(16,185,129,0.18), 0 0 24px rgba(16,185,129,0.12) !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.accent-indigo) {
        border: 2px solid rgba(99, 102, 241, 0.62) !important;
        box-shadow: 0 10px 28px rgba(0,0,0,0.55), 0 0 0 1px rgba(99,102,241,0.18), 0 0 24px rgba(99,102,241,0.12) !important;
    }

    /* ── Section titles with glow underline ── */
    .premium-title {
        font-size: 18px !important;
        font-weight: 900 !important;
        color: #FFFFFF !important;
        margin-bottom: 10px !important;
        padding-bottom: 6px !important;
        border-bottom: none !important;
        position: relative;
        letter-spacing: -0.01em;
        text-shadow: 0 1px 4px rgba(0, 0, 0, 0.85), 0 0 1px rgba(0, 0, 0, 1);
        overflow: visible !important;
        z-index: 1;
    }
    .premium-title::after {
        content: '';
        display: block;
        height: 2px;
        margin-top: 6px;
        border-radius: 2px;
        opacity: 0.85;
    }
    .premium-title.accent-cyan::after {
        background: linear-gradient(90deg, transparent, var(--af-cyan), transparent);
        box-shadow: 0 0 10px rgba(6, 182, 212, 0.65);
    }
    .premium-title.accent-violet::after {
        background: linear-gradient(90deg, transparent, var(--af-violet), transparent);
        box-shadow: 0 0 10px rgba(139, 92, 246, 0.65);
    }
    .premium-title.accent-blue::after {
        background: linear-gradient(90deg, transparent, var(--af-blue), transparent);
        box-shadow: 0 0 10px rgba(59, 130, 246, 0.65);
    }
    .premium-title.accent-teal::after {
        background: linear-gradient(90deg, transparent, var(--af-teal), transparent);
        box-shadow: 0 0 10px rgba(20, 184, 166, 0.65);
    }
    .premium-title.accent-purple::after {
        background: linear-gradient(90deg, transparent, var(--af-purple), transparent);
        box-shadow: 0 0 10px rgba(168, 85, 247, 0.65);
    }
    .premium-title.accent-amber::after {
        background: linear-gradient(90deg, transparent, var(--af-amber), transparent);
        box-shadow: 0 0 10px rgba(245, 158, 11, 0.65);
    }
    .premium-title.accent-rose::after {
        background: linear-gradient(90deg, transparent, var(--af-rose), transparent);
        box-shadow: 0 0 10px rgba(244, 63, 94, 0.65);
    }
    .premium-title.accent-emerald::after {
        background: linear-gradient(90deg, transparent, var(--af-emerald), transparent);
        box-shadow: 0 0 10px rgba(16, 185, 129, 0.65);
    }
    .premium-title.accent-indigo::after {
        background: linear-gradient(90deg, transparent, var(--af-indigo), transparent);
        box-shadow: 0 0 10px rgba(99, 102, 241, 0.65);
    }

    .tooltip-icon {
        position: relative;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 18px;
        height: 18px;
        margin-left: 6px;
        vertical-align: middle;
        color: #FCA5A5;
        font-size: 12px;
        line-height: 1;
        font-weight: 900;
        cursor: help;
        opacity: 0.95;
        border-radius: 50%;
        outline: none;
        user-select: none;
        z-index: 2;
    }
    .tooltip-icon::after {
        content: attr(data-tip);
        position: absolute;
        left: 50%;
        bottom: calc(100% + 12px);
        transform: translateX(-50%) translateY(4px);
        min-width: 200px;
        max-width: min(280px, 72vw);
        padding: 10px 12px;
        border-radius: 10px;
        background: linear-gradient(145deg, rgba(15, 23, 42, 0.98), rgba(30, 27, 75, 0.96));
        border: 1px solid rgba(139, 92, 246, 0.45);
        box-shadow:
            0 10px 28px rgba(0, 0, 0, 0.55),
            0 0 18px rgba(139, 92, 246, 0.22);
        color: #E2E8F0;
        font-size: 12px;
        font-weight: 600;
        line-height: 1.55;
        letter-spacing: 0;
        text-shadow: none;
        white-space: normal;
        text-align: left;
        pointer-events: none;
        visibility: hidden;
        opacity: 0;
        transition: opacity 0.18s ease, transform 0.18s ease, visibility 0.18s ease;
        z-index: 9999;
    }
    .tooltip-icon::before {
        content: "";
        position: absolute;
        left: 50%;
        bottom: calc(100% + 4px);
        transform: translateX(-50%);
        border: 7px solid transparent;
        border-top-color: rgba(139, 92, 246, 0.55);
        visibility: hidden;
        opacity: 0;
        transition: opacity 0.18s ease, visibility 0.18s ease;
        pointer-events: none;
        z-index: 9998;
    }
    .tooltip-icon:hover::after,
    .tooltip-icon:focus::after,
    .tooltip-icon:focus-visible::after {
        visibility: visible;
        opacity: 1;
        transform: translateX(-50%) translateY(0);
    }
    .tooltip-icon:hover::before,
    .tooltip-icon:focus::before,
    .tooltip-icon:focus-visible::before {
        visibility: visible;
        opacity: 1;
    }
    .tooltip-icon:hover,
    .tooltip-icon:focus,
    .tooltip-icon:focus-visible {
        color: #FFFFFF;
        background: rgba(139, 92, 246, 0.35);
        box-shadow: 0 0 12px rgba(139, 92, 246, 0.45);
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.tooltip-icon) {
        overflow: visible !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.tooltip-icon) > div[data-testid="stVerticalBlock"] {
        overflow: visible !important;
    }

    .af-table-header {
        text-align: center;
        font-weight: 800;
        color: #FFFFFF !important;
        font-size: 15px;
        letter-spacing: 0.02em;
        text-shadow: 0 1px 3px rgba(0, 0, 0, 0.8);
    }
    .af-table-label {
        margin-top: 5px;
        font-size: 16px;
        color: #FFFFFF !important;
        font-weight: 700;
        text-shadow: 0 1px 3px rgba(0, 0, 0, 0.8);
    }

    /* ── Checkbox: Streamlit Base Web Checkmark only (native input stays hidden) ── */
    div[data-testid="stCheckbox"] {
        margin-bottom: 4px;
    }
    div[data-testid="stCheckbox"] label,
    div[data-testid="stCheckbox"] [data-baseweb="checkbox"] {
        display: inline-flex !important;
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        align-items: center !important;
        justify-content: flex-start !important;
        gap: 8px !important;
        min-width: 0 !important;
        width: 100% !important;
        padding: 6px 10px !important;
        border-radius: 999px !important;
        background: rgba(15, 15, 30, 0.85) !important;
        border: 1px solid rgba(100, 116, 139, 0.35) !important;
        color: #FFFFFF !important;
        font-size: 17px !important;
        font-weight: 700 !important;
        cursor: pointer !important;
        transition: all 0.18s ease !important;
        box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.35) !important;
        text-shadow: 0 1px 3px rgba(0, 0, 0, 0.85), 0 0 1px rgba(0, 0, 0, 1) !important;
        white-space: nowrap !important;
    }
    div[data-testid="stCheckbox"] label:hover,
    div[data-testid="stCheckbox"] [data-baseweb="checkbox"]:hover {
        border-color: rgba(6, 182, 212, 0.55) !important;
        color: #FFFFFF !important;
    }
    div[data-testid="stCheckbox"] label:has(input:checked),
    div[data-testid="stCheckbox"] [data-baseweb="checkbox"]:has(input:checked) {
        background: linear-gradient(135deg, rgba(6, 182, 212, 0.25) 0%, rgba(139, 92, 246, 0.28) 100%) !important;
        border-color: rgba(139, 92, 246, 0.65) !important;
        color: #FFFFFF !important;
        box-shadow:
            0 0 14px rgba(139, 92, 246, 0.35),
            inset 0 1px 0 rgba(255, 255, 255, 0.12) !important;
        text-shadow: 0 1px 4px rgba(0, 0, 0, 0.9), 0 0 2px rgba(0, 0, 0, 1) !important;
    }

    /* Streamlit Checkmark span: clear square box + filled check state */
    div[data-testid="stCheckbox"] [data-baseweb="checkbox"] > span:first-of-type {
        flex-shrink: 0 !important;
        width: 22px !important;
        height: 22px !important;
        min-width: 22px !important;
        min-height: 22px !important;
        margin: 0 !important;
        box-sizing: border-box !important;
        border: 2px solid rgba(255, 255, 255, 0.92) !important;
        border-radius: 5px !important;
        background-color: rgba(8, 8, 16, 0.75) !important;
        background-repeat: no-repeat !important;
        background-position: center !important;
        background-size: 13px 10px !important;
        box-shadow:
            inset 0 2px 4px rgba(0, 0, 0, 0.45),
            0 0 0 1px rgba(255, 255, 255, 0.08) !important;
        transition: border-color 0.15s ease, background-color 0.15s ease, box-shadow 0.15s ease !important;
    }
    div[data-testid="stCheckbox"] [data-baseweb="checkbox"]:not(:has(input:checked)) > span:first-of-type {
        background-image: none !important;
    }
    div[data-testid="stCheckbox"] [data-baseweb="checkbox"]:hover > span:first-of-type {
        border-color: #67E8F9 !important;
        box-shadow:
            inset 0 2px 4px rgba(0, 0, 0, 0.45),
            0 0 8px rgba(103, 232, 249, 0.25) !important;
    }
    div[data-testid="stCheckbox"] [data-baseweb="checkbox"]:has(input:checked) > span:first-of-type {
        border: 2px solid #C4B5FD !important;
        background-color: #8B5CF6 !important;
        background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' fill='none'%3E%3Cpath d='M3.5 8.2 L6.8 11.5 L12.5 4.5' stroke='%23FFFFFF' stroke-width='1.35' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E") !important;
        background-size: 12px 12px !important;
        box-shadow:
            inset 0 1px 0 rgba(255, 255, 255, 0.25),
            0 0 10px rgba(139, 92, 246, 0.55) !important;
    }

    /* Option label text only (not the Checkmark span) */
    div[data-testid="stCheckbox"] [data-testid="stWidgetLabel"],
    div[data-testid="stCheckbox"] [data-testid="stWidgetLabel"] p {
        margin: 0 !important;
        padding: 0 !important;
        color: #FFFFFF !important;
        font-size: 17px !important;
        font-weight: 700 !important;
        line-height: 1.2 !important;
        white-space: nowrap !important;
        word-break: keep-all !important;
        overflow: visible !important;
        text-overflow: clip !important;
        text-shadow: 0 1px 3px rgba(0, 0, 0, 0.85), 0 0 1px rgba(0, 0, 0, 1) !important;
    }

    /* ── Inset number inputs ── */
    div[data-testid="stNumberInput"] input {
        background: #0a0a14 !important;
        color: #FFFFFF !important;
        border: 1px solid rgba(6, 182, 212, 0.35) !important;
        border-radius: 10px !important;
        font-weight: 800 !important;
        font-size: 20px !important;
        text-shadow: 0 1px 3px rgba(0, 0, 0, 0.85), 0 0 1px rgba(0, 0, 0, 1) !important;
        box-shadow:
            inset 0 3px 8px rgba(0, 0, 0, 0.65),
            inset 0 1px 2px rgba(0, 0, 0, 0.5),
            0 1px 0 rgba(255, 255, 255, 0.04) !important;
    }
    div[data-testid="stNumberInput"] input:focus {
        border-color: rgba(139, 92, 246, 0.65) !important;
        box-shadow:
            inset 0 3px 8px rgba(0, 0, 0, 0.65),
            0 0 12px rgba(139, 92, 246, 0.25) !important;
    }
    div[data-testid="stNumberInput"] button {
        background: #1A1A2E !important;
        border-color: rgba(100, 116, 139, 0.4) !important;
        color: #FFFFFF !important;
        font-size: 18px !important;
        font-weight: 800 !important;
    }
    /* 카드 내 최소/최대 숫자 입력: 셀 좁히기, +/- 버튼 키우기 */
    div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stNumberInput"] {
        max-width: 88px !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stNumberInput"] input {
        max-width: 52px !important;
        min-width: 44px !important;
        padding-left: 6px !important;
        padding-right: 6px !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stNumberInput"] button {
        min-width: 34px !important;
        min-height: 34px !important;
        font-size: 20px !important;
    }

    /* ── Primary execute button ── */
    div[data-testid="stButton"] > button[kind="primary"],
    div[data-testid="stButton"] > button[data-testid="stBaseButton-primary"] {
        background: linear-gradient(135deg, #6366F1 0%, #8B5CF6 45%, #A855F7 100%) !important;
        color: #FFFFFF !important;
        font-weight: 800 !important;
        font-size: 24px !important;
        border: 1px solid rgba(167, 139, 250, 0.5) !important;
        border-radius: 12px !important;
        padding: 0.75rem 1.25rem !important;
        box-shadow:
            0 0 24px rgba(139, 92, 246, 0.45),
            0 4px 16px rgba(99, 102, 241, 0.35),
            inset 0 1px 0 rgba(255, 255, 255, 0.2) !important;
        transition: transform 0.15s ease, box-shadow 0.15s ease !important;
    }
    div[data-testid="stButton"] > button[kind="primary"]:hover,
    div[data-testid="stButton"] > button[data-testid="stBaseButton-primary"]:hover {
        transform: translateY(-1px) !important;
        box-shadow:
            0 0 32px rgba(139, 92, 246, 0.55),
            0 6px 20px rgba(99, 102, 241, 0.4),
            inset 0 1px 0 rgba(255, 255, 255, 0.25) !important;
    }

    /* ── Secondary buttons ── */
    div[data-testid="stButton"] > button[kind="secondary"] {
        background: linear-gradient(145deg, #1c1c38, #141428) !important;
        color: var(--af-text) !important;
        border: 1px solid rgba(100, 116, 139, 0.4) !important;
        border-radius: 10px !important;
    }

    /* ── Text input (email) ── */
    div[data-testid="stTextInput"] input {
        background: #0a0a14 !important;
        color: #E2E8F0 !important;
        border: 1px solid rgba(99, 102, 241, 0.35) !important;
        border-radius: 10px !important;
        box-shadow: inset 0 3px 8px rgba(0, 0, 0, 0.55) !important;
    }

    /* ── Alerts & info boxes ── */
    div[data-testid="stAlert"] {
        background: rgba(20, 20, 40, 0.92) !important;
        border: 1px solid rgba(100, 116, 139, 0.3) !important;
        color: var(--af-text) !important;
        border-radius: 10px !important;
    }
    div[data-testid="stNotificationContentInfo"] {
        color: #93C5FD !important;
    }
    /* 1단계 실행 버튼 — af_bottom_center 내부 100% 폭, 텍스트 왼쪽 정렬 */
    .af-step1-run-wrap { display: none !important; height: 0 !important; margin: 0 !important; padding: 0 !important; }
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"]:has(.af-step1-run-wrap) div[data-testid="stButton"]:has(button[data-testid="stBaseButton-primary"]) {
        width: 100% !important;
        max-width: 100% !important;
    }
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"]:has(.af-step1-run-wrap) button[data-testid="stBaseButton-primary"] {
        width: 100% !important;
        justify-content: flex-start !important;
        text-align: left !important;
    }

    /* 1단계 패턴 통과 조합 info — 가독성 (흰색 통일, 큰 글씨) */
    .af-step1-info-marker { display: none !important; height: 0 !important; margin: 0 !important; padding: 0 !important; }
    div[data-testid="stVerticalBlock"]:has(.af-results-zone):has(.af-step1-info-marker)
        div[data-testid="stElementContainer"]:has(.af-step1-info-marker)
        + div[data-testid="stElementContainer"] div[data-testid="stAlert"] {
        background: rgba(20, 28, 48, 0.95) !important;
        border: 1px solid rgba(148, 163, 184, 0.35) !important;
    }
    div[data-testid="stVerticalBlock"]:has(.af-results-zone):has(.af-step1-info-marker)
        div[data-testid="stElementContainer"]:has(.af-step1-info-marker)
        + div[data-testid="stElementContainer"] div[data-testid="stAlert"] p,
    div[data-testid="stVerticalBlock"]:has(.af-results-zone):has(.af-step1-info-marker)
        div[data-testid="stElementContainer"]:has(.af-step1-info-marker)
        + div[data-testid="stElementContainer"] div[data-testid="stAlert"] strong,
    div[data-testid="stVerticalBlock"]:has(.af-results-zone):has(.af-step1-info-marker)
        div[data-testid="stElementContainer"]:has(.af-step1-info-marker)
        + div[data-testid="stElementContainer"] [data-testid="stNotificationContentInfo"] {
        font-size: 32px !important;
        color: #FFFFFF !important;
        font-weight: 700 !important;
        text-shadow: 0 1px 3px rgba(0, 0, 0, 0.65) !important;
    }

    /* 2단계 필터 편집 안내 info — 가독성 */
    .af-filter-tip-marker { display: none !important; height: 0 !important; margin: 0 !important; padding: 0 !important; }
    div[data-testid="stVerticalBlock"]:has(.af-filter-tip-marker)
        div[data-testid="stElementContainer"]:has(.af-filter-tip-marker)
        + div[data-testid="stElementContainer"] div[data-testid="stAlert"] {
        background: rgba(20, 28, 48, 0.95) !important;
        border: 1px solid rgba(148, 163, 184, 0.35) !important;
    }
    div[data-testid="stVerticalBlock"]:has(.af-filter-tip-marker)
        div[data-testid="stElementContainer"]:has(.af-filter-tip-marker)
        + div[data-testid="stElementContainer"] div[data-testid="stAlert"] p,
    div[data-testid="stVerticalBlock"]:has(.af-filter-tip-marker)
        div[data-testid="stElementContainer"]:has(.af-filter-tip-marker)
        + div[data-testid="stElementContainer"] [data-testid="stNotificationContentInfo"] {
        font-size: 20px !important;
        color: #FFFFFF !important;
        font-weight: 700 !important;
        text-shadow: 0 1px 3px rgba(0, 0, 0, 0.65) !important;
        line-height: 1.45 !important;
    }

    /* ── Secondary buttons ── */
    hr {
        border-color: rgba(100, 116, 139, 0.25) !important;
        margin: 1rem 0 !important;
    }

    /* ── File uploader ── */
    [data-testid="stFileUploader"] section {
        background: rgba(20, 20, 40, 0.85) !important;
        border: 1px dashed rgba(139, 92, 246, 0.4) !important;
        border-radius: 12px !important;
    }
    [data-testid="stFileUploader"] label, [data-testid="stFileUploader"] span {
        color: var(--af-text-muted) !important;
    }

    /* ── Dataframe / editor (전역 기본) ── */
    [data-testid="stDataFrame"], [data-testid="stDataEditor"] {
        border: 1px solid rgba(100, 116, 139, 0.25);
        border-radius: 10px;
        overflow: hidden;
    }

    .af-results-zone { display: none !important; height: 0 !important; margin: 0 !important; padding: 0 !important; }

    /* 하단 영역 그룹 — 화면 중앙 정렬 (75% 폭, 상단 3열 미적용) */
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"] {
        box-sizing: border-box !important;
        max-width: 75% !important;
        width: 100% !important;
        margin-left: auto !important;
        margin-right: auto !important;
    }

    /* af_bottom_center 내부 박스형 요소 폭 100% 통일 (결과표/데이터에디터 제외) */
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"] div[data-testid="stElementContainer"] {
        width: 100% !important;
        max-width: 100% !important;
    }
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"] div[data-testid="stButton"],
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"] div[data-testid="stAlert"],
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"] [data-testid="stFileUploader"],
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"] [data-testid="stFileUploader"] section {
        width: 100% !important;
        max-width: 100% !important;
        box-sizing: border-box !important;
    }
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"] div[data-testid="stButton"] > button {
        width: 100% !important;
        max-width: 100% !important;
        box-sizing: border-box !important;
    }
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"] div[data-testid="stElementContainer"]:has(.af-step1-info-marker)
        + div[data-testid="stElementContainer"] div[data-testid="stAlert"],
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"] div[data-testid="stElementContainer"]:has(.af-filter-tip-marker)
        + div[data-testid="stElementContainer"] div[data-testid="stAlert"] {
        width: 100% !important;
        max-width: 100% !important;
        box-sizing: border-box !important;
    }

    /* admin_dashboard style_dataframe — 하단 결과표 전용 (상단 3열 레이아웃 미적용, 테이블만 내용폭) */
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"] [data-testid="stDataEditor"],
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"] [data-testid="stDataFrame"],
    div[data-testid="stVerticalBlock"]:has(.af-results-zone) [data-testid="stDataEditor"],
    div[data-testid="stVerticalBlock"]:has(.af-results-zone) [data-testid="stDataFrame"] {
        border: 1px solid #334155 !important;
        border-radius: 8px !important;
        max-width: max-content !important;
    }
    div[data-testid="stVerticalBlock"]:has(.af-results-zone) [data-testid="stDataEditor"] [role="gridcell"],
    div[data-testid="stVerticalBlock"]:has(.af-results-zone) [data-testid="stDataEditor"] td,
    div[data-testid="stVerticalBlock"]:has(.af-results-zone) [data-testid="stDataFrame"] td {
        background-color: #1E293B !important;
        color: #F8FAFC !important;
        border-color: #334155 !important;
        font-size: 14px !important;
        font-weight: 500 !important;
        padding: 6px 10px !important;
    }
    div[data-testid="stVerticalBlock"]:has(.af-results-zone) [data-testid="stDataEditor"] [role="columnheader"],
    div[data-testid="stVerticalBlock"]:has(.af-results-zone) [data-testid="stDataFrame"] th {
        background-color: #1E293B !important;
        color: #F8FAFC !important;
        border-color: #334155 !important;
        font-size: 14px !important;
        font-weight: 500 !important;
    }

    label[data-testid="stWidgetLabel"] p {
        color: var(--af-text-muted) !important;
    }

    /* ── 세팅완료 저장 버튼 전용 (key=save_settings_btn, 기존 CSS 미변경·추가만) ── */
    .af-save-settings-btn-marker { display: none !important; height: 0 !important; margin: 0 !important; padding: 0 !important; }
    div[data-testid="column"]:has(.af-save-settings-btn-marker) div[data-testid="stButton"] {
        width: 100% !important;
        max-width: 100% !important;
    }
    div[data-testid="column"]:has(.af-save-settings-btn-marker) div[data-testid="stButton"] > button[data-testid="stBaseButton-secondary"],
    div[data-testid="column"]:has(.af-save-settings-btn-marker) div[data-testid="stButton"] > button[kind="secondary"] {
        width: 100% !important;
        background: linear-gradient(135deg, #0ea5e9 0%, #2563eb 52%, #1d4ed8 100%) !important;
        color: #FFFFFF !important;
        font-size: 18px !important;
        font-weight: 700 !important;
        border: 1px solid rgba(125, 211, 252, 0.78) !important;
        border-radius: 10px !important;
        padding: 0.7rem 1.15rem !important;
        box-shadow:
            0 0 20px rgba(14, 165, 233, 0.38),
            0 4px 16px rgba(37, 99, 235, 0.32),
            inset 0 1px 0 rgba(255, 255, 255, 0.24) !important;
        text-shadow: 0 1px 3px rgba(0, 0, 0, 0.55) !important;
        transition: transform 0.15s ease, box-shadow 0.15s ease !important;
    }
    div[data-testid="column"]:has(.af-save-settings-btn-marker) div[data-testid="stButton"] > button[data-testid="stBaseButton-secondary"]:hover,
    div[data-testid="column"]:has(.af-save-settings-btn-marker) div[data-testid="stButton"] > button[kind="secondary"]:hover {
        transform: translateY(-1px) !important;
        color: #FFFFFF !important;
        border-color: rgba(186, 230, 253, 0.95) !important;
        box-shadow:
            0 0 28px rgba(56, 189, 248, 0.48),
            0 6px 18px rgba(37, 99, 235, 0.38),
            inset 0 1px 0 rgba(255, 255, 255, 0.28) !important;
    }

    /* 1단계 완료 success 박스 가독성 — af_bottom_center 전용 (추가만) */
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"] div[data-testid="stAlert"]:has([data-testid="stNotificationContentSuccess"]),
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"] div[data-testid="stAlert"]:has([data-testid="stNotificationContentSuccess"]) p,
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"] div[data-testid="stAlert"]:has([data-testid="stNotificationContentSuccess"]) span,
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"] [data-testid="stNotificationContentSuccess"],
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"] [data-testid="stNotificationContentSuccess"] * {
        color: #FFFFFF !important;
        font-size: 16px !important;
        font-weight: 600 !important;
    }

    /* af_bottom_center 결과표 — 헤더·셀 중앙 정렬 (추가만) */
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"] [data-testid="stDataEditor"] [role="columnheader"],
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"] [data-testid="stDataEditor"] [role="gridcell"],
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"] [data-testid="stDataEditor"] td,
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"] [data-testid="stDataFrame"] th,
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"] [data-testid="stDataFrame"] td,
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"] div[data-testid="stTable"] th,
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"] div[data-testid="stTable"] td {
        text-align: center !important;
        justify-content: center !important;
    }

    /* 1단계 연산 대기 warning 박스 — af_bottom_center 전용 (추가만) */
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"] div[data-testid="stAlert"]:has([data-testid="stNotificationContentWarning"]) *,
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"] [data-testid="stNotificationContentWarning"],
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"] [data-testid="stNotificationContentWarning"] * {
        color: #FFFFFF !important;
        font-size: 16px !important;
        font-weight: 600 !important;
        z-index: 999 !important;
    }

    /* Streamlit rerun 깜빡임/어두워짐 억제 (추가만) */
    .stApp,
    .stApp [data-testid="stAppViewContainer"],
    .stApp [data-testid="stAppViewContainer"] > section,
    .stApp .main,
    .stApp .main .block-container {
        opacity: 1 !important;
        filter: none !important;
        transition: none !important;
    }
    .stApp[data-testscript-state="running"] [data-testid="stAppViewContainer"],
    .stApp[data-testscript-state="running"] .main .block-container {
        opacity: 1 !important;
        filter: none !important;
    }
    div[data-testid="stStatusWidget"] {
        opacity: 0 !important;
        visibility: hidden !important;
        pointer-events: none !important;
    }

    /* K-295 고급필터 표 — 제목행 강조·글씨 확대 (af-k295-filter-table-marker 전용, 추가만) */
    .af-k295-filter-table-marker { display: none !important; height: 0 !important; margin: 0 !important; padding: 0 !important; }
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"]:has(.af-k295-filter-table-marker) [data-testid="stDataEditor"] [role="columnheader"],
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"]:has(.af-k295-filter-table-marker) [data-testid="stDataEditor"] th,
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"]:has(.af-k295-filter-table-marker) [data-testid="stTable"] th,
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"]:has(.af-k295-filter-table-marker) [data-testid="stDataFrame"] th {
        font-weight: 800 !important;
        font-size: 16px !important;
        color: #FFFFFF !important;
        text-align: center !important;
        justify-content: center !important;
    }
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"]:has(.af-k295-filter-table-marker) [data-testid="stDataEditor"] [role="gridcell"],
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"]:has(.af-k295-filter-table-marker) [data-testid="stDataEditor"] td,
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"]:has(.af-k295-filter-table-marker) [data-testid="stTable"] td,
    div[data-testid="stVerticalBlock"][class*="af_bottom_center"]:has(.af-k295-filter-table-marker) [data-testid="stDataFrame"] td {
        font-size: 15px !important;
        text-align: center !important;
        justify-content: center !important;
    }

    /* K-502/K-538 — 프리미엄 3열 그리드 열 간격·구분선 (상단 패턴 영역 전용, 추가만) */
    div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] .af-col3-stack) {
```
