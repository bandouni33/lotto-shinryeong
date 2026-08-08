import streamlit as st
import pandas as pd
import datetime
import io
import json
import os
import pickle
import random
import subprocess
import sys
from datetime import timedelta

# ==========================================
# 0. 초기화 로직 및 로컬 마스터 파일/데이터 보존 로드
# ==========================================
if "admin_view" not in st.session_state:
    st.session_state.admin_view = "home"
_qp_admin_view = st.query_params.get("admin_view")
if _qp_admin_view in ("home", "filter_manage"):
    st.session_state.admin_view = _qp_admin_view

MASTER_FILE = "로또기록 앱 업로드용.xlsb"
FILTER_SAVE_FILE = "saved_filters.pkl"     # 필터 유지용 저장 파일 (로그아웃해도 유지)
COMBO_SAVE_FILE = "saved_combinations.csv" # 조합 결과 유지용 저장 파일 (로그아웃해도 유지)
FILTER_JOB_STATUS_FILE = "filter_job.status"
FILTER_WORKER_SCRIPT = os.path.join(os.path.dirname(__file__), "filter_worker.py")


def _read_filter_job_status() -> dict | None:
    if not os.path.exists(FILTER_JOB_STATUS_FILE):
        return None
    try:
        with open(FILTER_JOB_STATUS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    if sys.platform == "win32":
        try:
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
            )
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        except Exception:
            return False
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def _sync_filter_job_status() -> dict | None:
    status = _read_filter_job_status()
    if not status or status.get("state") != "running":
        return status
    if _pid_alive(status.get("pid")):
        return status
    status["state"] = "error"
    status["message"] = "연산 프로세스가 중단되었습니다."
    try:
        with open(FILTER_JOB_STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(status, f, ensure_ascii=False)
    except OSError:
        pass
    return status


def _load_combo_upload_as_export_df(uploaded) -> pd.DataFrame:
    """배포용 엑셀/CSV 업로드 → saved_combinations.csv 형식(번호1~6)."""
    from marketing_db import parse_combination_rows_from_dataframe

    name = (uploaded.name or "").lower()
    if name.endswith((".xlsx", ".xls")):
        xl = pd.ExcelFile(uploaded)
        sheet = "배포조합" if "배포조합" in xl.sheet_names else xl.sheet_names[0]
        df_raw = pd.read_excel(uploaded, sheet_name=sheet)
    elif name.endswith(".csv"):
        df_raw = pd.read_csv(uploaded)
    else:
        raise ValueError("xlsx, xls, csv 파일만 업로드할 수 있습니다.")

    cols_ko = [f"번호{i}" for i in range(1, 7)]
    cols_num = [f"num{i}" for i in range(1, 7)]
    if not (
        all(c in df_raw.columns for c in cols_ko)
        or all(c in df_raw.columns for c in cols_num)
    ):
        if df_raw.shape[1] < 6:
            raise ValueError("조합 데이터는 6열(번호 6개) 이상이어야 합니다.")
        df_raw = df_raw.iloc[:, :6].copy()
        df_raw.columns = cols_ko

    rows = parse_combination_rows_from_dataframe(df_raw)
    if not rows:
        raise ValueError("유효한 6개 번호 조합을 찾지 못했습니다.")
    return pd.DataFrame(rows, columns=cols_ko)


def _start_filter_job() -> None:
    if not os.path.exists(FILTER_SAVE_FILE):
        raise FileNotFoundError("saved_filters.pkl 이 없습니다. 필터를 먼저 업로드해 주세요.")
    import pickle
    from filter_sheet_validation import normalize_three_filter_data, validate_three_filter_sheets

    with open(FILTER_SAVE_FILE, "rb") as f:
        saved_filters = normalize_three_filter_data(pickle.load(f))
    val_errors, _ = validate_three_filter_sheets(saved_filters)
    if val_errors:
        raise ValueError(
            "3종 필터 검증 오류 — 연산을 시작할 수 없습니다. "
            f"(첫 오류: {val_errors[0]})"
        )
    worker = FILTER_WORKER_SCRIPT
    if not os.path.exists(worker):
        raise FileNotFoundError("filter_worker.py 를 찾을 수 없습니다.")
    subprocess.Popen(
        [sys.executable, worker],
        cwd=os.path.dirname(__file__) or ".",
        close_fds=True,
    )

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
    try:
        st.query_params["admin_view"] = view_name
    except Exception:
        pass

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
    
    /* 3종 필터 탭 글자 시인성 강화 */
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
    .admin-export-download-marker,
    .admin-export-upload-marker { display: none !important; }

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

    def _member_activity_counts() -> tuple[int, int]:
        """(누적 가입자 수, 오늘 활동 인원). last_login_at은 로그인 시마다 갱신됨."""
        import datetime as _dt
        import wallet_db

        conn = wallet_db._connect()
        total_row = conn.execute("SELECT COUNT(*) AS c FROM members").fetchone()
        today = _dt.datetime.now(wallet_db.KST).strftime("%Y-%m-%d")
        active_row = conn.execute(
            "SELECT COUNT(*) AS c FROM members WHERE substr(last_login_at, 1, 10) = ?",
            (today,),
        ).fetchone()
        conn.close()
        return int(total_row["c"]) if total_row else 0, int(active_row["c"]) if active_row else 0

    try:
        _total_members, _active_today = _member_activity_counts()
    except Exception as e:
        _total_members, _active_today = 0, 0
        st.warning(f"회원 통계 조회 실패: {e}")

    col1, col2 = st.columns(2)
    with col1: st.metric("누적 가입자 수 (설치인원)", f"{_total_members:,} 명")
    with col2: st.metric("오늘 활동 인원", f"{_active_today:,} 명")

    st.markdown("<h4 style='margin-top:40px; color:#FFB300; font-weight:700;'>작업 프로세스 메뉴</h4>", unsafe_allow_html=True)

    # 🔥 기존의 1단계, 2단계 버튼을 완전히 없애고 이 버튼 하나로 통합했습니다.
    if st.button("🚀 3종 필터 업로드 및 원스톱 조합 생성 시작", type="primary"):
        change_view("filter_manage")
        st.rerun()

    st.markdown("<h4 style='margin-top:40px; color:#FFB300; font-weight:700;'>📣 업데이트 안내 배너</h4>", unsafe_allow_html=True)
    with st.expander("배너 설정 (사용자 화면 상단에 노출)"):
        from app_settings import get_update_notice, set_update_notice

        _notice = get_update_notice()
        st.caption("배포 버전을 비워두면 배너가 표시되지 않습니다.")
        _new_version = st.text_input("배포 버전 (예: 1.0.2)", value=_notice["version"], key="admin_update_version")
        _new_url = st.text_input("업데이트 링크 (APK/스토어 URL)", value=_notice["url"], key="admin_update_url")
        _new_message = st.text_area("안내 문구", value=_notice["message"], key="admin_update_message")
        if st.button("저장", key="admin_update_notice_save"):
            set_update_notice(_new_version, _new_url, _new_message)
            st.success("저장했습니다. 사용자 화면에 즉시 반영됩니다.")
            st.rerun()

# ==========================================
# 🔧 [통합] 3종 필터 관리 및 원스톱 조합 생성 시스템
# ==========================================
elif st.session_state.admin_view == "filter_manage":
    st.session_state.admin_view = "filter_manage"
    try:
        st.query_params["admin_view"] = "filter_manage"
    except Exception:
        pass
    if st.button("⬅️ 대시보드 홈으로 이동"):
        change_view("home")
        st.rerun()
    
    st.markdown("<h3 style='color:#FFB300; font-weight:800;'>🔧 3종 필터 통합 관리 및 조합 생성</h3>", unsafe_allow_html=True)
    st.info("💡 **3종필터.xlsx** (기본·절대·이격수 시트) 업로드 후 3단계 연산을 실행하세요. 특수필터 시트는 사용하지 않습니다.")
    
    uploaded_excel = st.file_uploader("📂 3종필터 엑셀 업로드 (.xlsx)", type=["xlsx"])

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
                "basic": get_clean_data("기본필터"),
                "absolute": get_clean_data("절대필터"),
                "interval": get_clean_data("이격수필터"),
            }
            with open(FILTER_SAVE_FILE, "wb") as f:
                pickle.dump(filters_data, f)

            from filter_sheet_validation import validate_three_filter_sheets

            val_errors, val_summary = validate_three_filter_sheets(filters_data)
            st.session_state["admin_filter_validation_summary"] = val_summary
            if val_errors:
                st.error(
                    "⚠️ 필터는 저장됐지만 **검증 오류**가 있습니다. "
                    "연산 전 엑셀(I·J 열)을 수정·재업로드해 주세요."
                )
                for msg in val_errors[:20]:
                    st.warning(msg)
                if len(val_errors) > 20:
                    st.caption(f"… 외 {len(val_errors) - 20}건")
            else:
                st.success("✅ 필터 업로드·검증 성공! 데이터가 시스템에 안전하게 저장되었습니다.")
            cap = " · ".join(f"{k}={v}" for k, v in val_summary.items())
            st.caption(cap)
        except Exception as e:
            st.error(f"❌ 시트명 또는 양식 오류: {e}")

    # 2. 업로드 여부와 상관없이 저장된 파일이 있으면 무조건 렌더링
    if os.path.exists(FILTER_SAVE_FILE):
        from filter_sheet_validation import normalize_three_filter_data

        with open(FILTER_SAVE_FILE, "rb") as f:
            saved_filters = normalize_three_filter_data(pickle.load(f))

        if "admin_filter_validation_summary" not in st.session_state:
            from filter_sheet_validation import validate_three_filter_sheets

            _, val_summary = validate_three_filter_sheets(saved_filters)
            st.session_state["admin_filter_validation_summary"] = val_summary
            
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
        
        tab_basic, tab_absolute, tab_interval = st.tabs(["① 기본", "② 절대", "③ 이격수"])

        with tab_basic:
            st.dataframe(
                style_dataframe(remove_decimals_from_df_cache(saved_filters["basic"])),
                use_container_width=True,
                hide_index=True,
            )
        with tab_absolute:
            st.dataframe(
                style_dataframe(remove_decimals_from_df_cache(saved_filters["absolute"])),
                use_container_width=True,
                hide_index=True,
            )
        with tab_interval:
            st.dataframe(
                style_dataframe(remove_decimals_from_df_cache(saved_filters["interval"])),
                use_container_width=True,
                hide_index=True,
            )
            
        st.markdown("---")
        st.markdown(
            "<p style='color:#94A3B8;margin-bottom:8px;'>3단계 연산 순서 (한 번에 실행)</p>",
            unsafe_allow_html=True,
        )
        step_col1, step_col2, step_col3 = st.columns(3)
        summary = st.session_state.get("admin_filter_validation_summary") or {}
        with step_col1:
            st.markdown(
                f"**① 기본**  \n"
                f"<span style='color:#00E676;'>{int(summary.get('basic_rows', len(saved_filters['basic'])))} 규칙</span>",
                unsafe_allow_html=True,
            )
        with step_col2:
            st.markdown(
                f"**② 절대**  \n"
                f"<span style='color:#00E676;'>{int(summary.get('absolute_rows', len(saved_filters['absolute'])))} 규칙</span>",
                unsafe_allow_html=True,
            )
        with step_col3:
            st.markdown(
                f"**③ 이격수**  \n"
                f"<span style='color:#00E676;'>{int(summary.get('interval_rows', len(saved_filters['interval'])))} 규칙</span>",
                unsafe_allow_html=True,
            )
        if int(summary.get("basic_rows", 0)) == 0:
            st.caption(
                "① 기본필터에 활성 규칙이 없으면 1단계는 **전체 814만 조합**을 그대로 넘깁니다. "
                "(구 **특수필터** 시트는 더 이상 적용하지 않습니다 — 엑셀 재업로드 권장)"
            )

        st.markdown("---") 
        
        # ==========================================
        # 3. [통합 연동] 조합 생성 엔진 가동 버튼
        # ==========================================
        job_status = _sync_filter_job_status()
        job_running = bool(job_status and job_status.get("state") == "running")

        if job_running:
            st.info(
                "🚀 8,145,060 조합 전수 검사 **백그라운드 연산 중**입니다. "
                "이 화면을 유지한 채 완료될 때까지 기다려 주세요. "
                "(다른 브라우저·기기의 **메인 화면**은 이용 가능합니다.)"
            )

            @st.fragment(run_every=timedelta(seconds=4))
            def _poll_filter_job_status() -> None:
                status = _sync_filter_job_status()
                if status and status.get("state") == "running":
                    st.caption("연산 진행 중… 자동 확인 중")
                elif status and status.get("state") in ("done", "error"):
                    st.rerun()

            _poll_filter_job_status()
            if st.button("상태 새로고침", key="admin_filter_job_refresh"):
                st.rerun()
        elif job_status and job_status.get("state") == "done":
            st.success(
                f"✅ 백그라운드 연산 완료 — {int(job_status.get('total', 0)):,}개 조합 생성"
            )
            stage_stats = job_status.get("stage_stats") or {}
            if stage_stats:
                s1 = int(
                    stage_stats.get("stage1_basic")
                    or stage_stats.get("stage1_basic_special")
                    or 0
                )
                st.caption(
                    "3단계 잔량: "
                    f"① 기본 {s1:,} → "
                    f"② 절대 {int(stage_stats.get('stage2_absolute', 0)):,} → "
                    f"③ 이격수 {int(stage_stats.get('stage3_interval', 0)):,} "
                    f"(전체 풀 {int(stage_stats.get('total_pool', 8145060)):,})"
                )
        elif job_status and job_status.get("state") == "error":
            st.error(f"연산 오류: {job_status.get('message', '알 수 없는 오류')}")
            for msg in (job_status.get("validation_errors") or [])[:10]:
                st.warning(str(msg))

        if st.button(
            "⚡ 3단계 조합 연산 실행 (① 기본 → ② 절대 → ③ 이격수)",
            type="primary",
            disabled=job_running,
        ):
            try:
                if job_running:
                    st.warning("이미 연산이 진행 중입니다.")
                else:
                    _start_filter_job()
                    st.rerun()
            except Exception as e:
                st.error(f"연산 시작 오류: {e}")
        
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

            st.markdown('<div class="admin-export-upload-marker" aria-hidden="true"></div>', unsafe_allow_html=True)
            uploaded_redeploy = st.file_uploader(
                "⬆️ 배포용 엑셀 재업로드 (xlsx · csv)",
                type=["xlsx", "xls", "csv"],
                key="admin_export_combo_reupload",
            )
            if uploaded_redeploy is not None:
                reupload_token = f"{uploaded_redeploy.name}:{uploaded_redeploy.size}"
                if st.session_state.get("admin_combo_reupload_token") != reupload_token:
                    try:
                        df_reupload = _load_combo_upload_as_export_df(uploaded_redeploy)
                        df_reupload.to_csv(COMBO_SAVE_FILE, index=False)
                        st.session_state["admin_combo_reupload_token"] = reupload_token
                        st.session_state.admin_view = "filter_manage"
                        try:
                            st.query_params["admin_view"] = "filter_manage"
                        except Exception:
                            pass
                        st.session_state["admin_combo_reupload_flash"] = (
                            f"✅ 업로드 저장 완료: {len(df_reupload):,}개 조합이 "
                            f"시스템({COMBO_SAVE_FILE})에 반영되었습니다."
                        )
                        st.rerun()
                    except Exception as e:
                        st.session_state.admin_view = "filter_manage"
                        try:
                            st.query_params["admin_view"] = "filter_manage"
                        except Exception:
                            pass
                        st.error(f"❌ 업로드 저장 실패: {e}")
            if st.session_state.get("admin_combo_reupload_flash"):
                st.success(st.session_state.pop("admin_combo_reupload_flash"))

            # ==========================================
            # 5. [마케팅 DB] 추출 조합 익명 저장 (백엔드)
            # ==========================================
            from marketing_db import (
                bulk_insert_lotto_combinations,
                delete_lotto_combinations_by_draw,
                get_combination_count_by_draw,
                init_marketing_tables,
                parse_combination_rows_from_dataframe,
                parse_combination_rows_from_text,
            )

            init_marketing_tables()

            def _admin_dialog(title: str):
                if hasattr(st, "dialog"):
                    return st.dialog(title)
                if hasattr(st, "experimental_dialog"):
                    return st.experimental_dialog(title)

                def _wrap(func):
                    def _inner(*args, **kwargs):
                        with st.container(border=True):
                            st.subheader(title)
                            return func(*args, **kwargs)

                    return _inner

                return _wrap

            def _admin_perform_combo_save(
                draw_round: int,
                rows: list,
                *,
                replace_existing: bool,
            ) -> None:
                draw_round = int(draw_round)
                if replace_existing:
                    delete_lotto_combinations_by_draw(draw_round)
                saved_count = bulk_insert_lotto_combinations(draw_round, rows)
                total_in_db = get_combination_count_by_draw(draw_round)
                st.success(
                    f"회차 {draw_round}: {saved_count:,}개 조합 저장 완료 "
                    f"(해당 회차 DB 누적 {total_in_db:,}개)"
                )

            @_admin_dialog("저장 확인")
            def _admin_combo_save_conflict_dialog() -> None:
                pending = st.session_state.get("admin_combo_save_pending") or {}
                draw_round = int(pending.get("draw_round") or 0)
                existing = int(pending.get("existing_count") or 0)
                rows = pending.get("rows") or []

                st.warning(
                    f"회차 **{draw_round}**에 이미 **{existing:,}개** 조합이 저장되어 있습니다.\n\n"
                    "어떻게 저장할까요?"
                )

                btn_replace, btn_rename = st.columns(2)
                with btn_replace:
                    if st.button(
                        "삭제후 신규저장",
                        type="primary",
                        use_container_width=True,
                        key="admin_combo_save_replace",
                    ):
                        try:
                            _admin_perform_combo_save(
                                draw_round,
                                rows,
                                replace_existing=True,
                            )
                        except Exception as e:
                            st.error(f"저장 오류: {e}")
                        else:
                            for key in (
                                "admin_combo_save_pending",
                                "admin_combo_save_alt_mode",
                            ):
                                st.session_state.pop(key, None)
                            st.rerun()

                with btn_rename:
                    if st.button(
                        "다른이름으로 저장",
                        use_container_width=True,
                        key="admin_combo_save_rename",
                    ):
                        st.session_state["admin_combo_save_alt_mode"] = True
                        st.rerun()

                if st.session_state.get("admin_combo_save_alt_mode"):
                    alt_round = st.number_input(
                        "새 저장 회차",
                        min_value=1,
                        step=1,
                        key="admin_combo_save_alt_round",
                    )
                    if st.button(
                        "이 회차로 저장",
                        type="primary",
                        key="admin_combo_save_alt_confirm",
                    ):
                        alt_round = int(alt_round)
                        if alt_round == draw_round:
                            st.error("현재와 다른 회차 번호를 입력해 주세요.")
                        elif get_combination_count_by_draw(alt_round) > 0:
                            st.error(
                                f"회차 {alt_round}에도 이미 저장된 조합이 있습니다. "
                                "다른 회차를 입력해 주세요."
                            )
                        else:
                            try:
                                _admin_perform_combo_save(
                                    alt_round,
                                    rows,
                                    replace_existing=False,
                                )
                            except Exception as e:
                                st.error(f"저장 오류: {e}")
                            else:
                                for key in (
                                    "admin_combo_save_pending",
                                    "admin_combo_save_alt_mode",
                                ):
                                    st.session_state.pop(key, None)
                                st.rerun()

                if st.button("취소", key="admin_combo_save_cancel"):
                    for key in (
                        "admin_combo_save_pending",
                        "admin_combo_save_alt_mode",
                    ):
                        st.session_state.pop(key, None)
                    st.rerun()

            st.markdown("---")
            st.subheader("📥 추출 조합 DB 저장")
            draw_round_save = st.number_input(
                "저장할 회차",
                min_value=1,
                step=1,
                key="admin_marketing_draw_round",
            )
            if st.session_state.get("admin_combo_input_mode") == "현재 추출 결과 사용":
                st.session_state["admin_combo_input_mode"] = "재업로드 저장본 사용"
            combo_input_mode = st.radio(
                "입력 방식",
                ["재업로드 저장본 사용", "텍스트 직접 입력", "CSV 파일 업로드"],
                horizontal=True,
                key="admin_combo_input_mode",
            )

            rows_to_save = None
            if combo_input_mode == "재업로드 저장본 사용":
                if os.path.exists(COMBO_SAVE_FILE):
                    rows_to_save = parse_combination_rows_from_dataframe(
                        pd.read_csv(COMBO_SAVE_FILE)
                    )
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
                    if combo_input_mode == "재업로드 저장본 사용" and os.path.exists(COMBO_SAVE_FILE):
                        rows_to_save = parse_combination_rows_from_dataframe(
                            pd.read_csv(COMBO_SAVE_FILE)
                        )
                    if not rows_to_save:
                        st.warning("저장할 조합이 없습니다.")
                    else:
                        target_round = int(draw_round_save)
                        existing_count = get_combination_count_by_draw(target_round)
                        if existing_count > 0:
                            st.session_state["admin_combo_save_pending"] = {
                                "draw_round": target_round,
                                "existing_count": existing_count,
                                "rows": rows_to_save,
                            }
                            st.session_state.pop("admin_combo_save_alt_mode", None)
                            st.rerun()
                        else:
                            _admin_perform_combo_save(
                                target_round,
                                rows_to_save,
                                replace_existing=False,
                            )
                except Exception as e:
                    st.error(f"저장 오류: {e}")

            if st.session_state.get("admin_combo_save_pending"):
                _admin_combo_save_conflict_dialog()