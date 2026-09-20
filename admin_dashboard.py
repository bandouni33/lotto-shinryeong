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

# 2026-08-27: 이 페이지는 app.py가 is_admin일 때만 st.navigation에 등록해주는
# 방식으로만 접근을 막고 있었다 — 그런데 Streamlit Cloud가 재부팅(재배포·잠깐
# 잠들었다 깨어남 등)되면 세션이 통째로 새로 시작되며 is_admin이 False로
# 초기화되는데, 브라우저 주소창은 여전히 이 페이지의 URL을 그대로 들고 있어
# "Page not found - Running the app's main page"라는 낯선 영어 에러가 관리자
# 화면에 그대로 노출됐다. app.py에서 이 페이지를 항상 등록해두고, 대신 여기서
# 직접 로그인 여부를 확인해 아니면 조용히 메인으로 돌려보낸다 — 사이드바가
# collapsed(위 "🏠 홈으로" 버튼 주석 참고)라 등록해둬도 일반 이용자에게 메뉴로
# 노출되지는 않는다.
if not st.session_state.get("is_admin", False):
    st.switch_page("user_page.py")
    st.stop()

# ==========================================
# 0. 초기화 로직 및 로컬 마스터 파일/데이터 보존 로드
# ==========================================
if "admin_view" not in st.session_state:
    st.session_state.admin_view = "home"
_qp_admin_view = st.query_params.get("admin_view")
if _qp_admin_view in ("home", "filter_manage", "pattern_manage", "dispute_resolution", "ops_manage"):
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

# 2026-08-29: 예전엔 인자 없이 순수 ttl=3600만으로 캐싱해서, 관리자가 실제로
# MASTER_FILE을 새로 저장해도 최대 1시간까지 이전 버전이 계속 보였다(캐시 키가
# 파일 내용과 무관해서 무효화될 방법이 없었음 — "추첨내역 저장해도 반영이
# 느리다"는 신고의 실제 원인). lotto_stats.py의 엑셀 캐시가 이미 쓰던 대로
# 파일 수정시각(mtime)을 캐시 키에 포함시켜, 파일이 바뀌는 즉시 캐시가
# 무효화되면서도 안 바뀐 동안에는 재파싱하지 않게 한다.
def _master_file_mtime() -> float:
    try:
        return os.path.getmtime(MASTER_FILE)
    except OSError:
        return 0.0


@st.cache_data(show_spinner=False)
def _load_lotto_history_cached(mtime: float):
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


def load_lotto_history():
    return _load_lotto_history_cached(_master_file_mtime())


df_history, latest_info = load_lotto_history()

def change_view(view_name):
    st.session_state.admin_view = view_name
    try:
        st.query_params["admin_view"] = view_name
    except Exception:
        pass

st.set_page_config(page_title="운영자 대시보드", layout="centered", initial_sidebar_state="expanded")

# ==========================================
# 🎨 고대비/시인성 극대화 커스텀 CSS (탭 글자 흰색 처리 및 지표 흰색 처리)
# ==========================================
st.markdown("""
<style>
    .stApp { background-color: #0B0C10; color: #FFFFFF; font-family: 'Pretendard', sans-serif; }

    /* 위젯 라벨(입력창 설명글)·캡션·라디오 옵션 글씨가 어두운 배경에서 거의 안 보이던
       문제 — 그동안 특정 섹션(marker class)에만 개별적으로 패치해왔는데, 새로 추가되는
       섹션(예: "배포용 엑셀 재업로드", "저장할 회차")마다 계속 빠지고 있었다. 전체에
       한 번에 적용되는 공통 규칙으로 통일한다. */
    .stApp [data-testid="stWidgetLabel"] p,
    .stApp [data-testid="stWidgetLabel"] label,
    .stApp [data-testid="stCaptionContainer"] p,
    .stApp [data-testid="stRadio"] label p,
    .stApp [data-testid="stFileUploaderDropzone"] span,
    .stApp [data-testid="stFileUploaderDropzone"] small,
    .stApp [data-testid="stNumberInput"] label p {
        color: #E8ECF2 !important;
        font-weight: 600 !important;
        opacity: 1 !important;
    }
    .stApp [data-testid="stFileUploaderDropzone"] svg {
        fill: #E8ECF2 !important;
        opacity: 0.9 !important;
    }
    .stApp [data-testid="stNumberInput"] button svg {
        fill: #E8ECF2 !important;
    }

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
    .admin-export-upload-marker,
    .admin-update-banner-marker { display: none !important; }

    /* 업데이트 안내 배너 설정 — 아코디언 헤더(어두운 배경)는 흰 글씨,
       입력창(흰 배경)은 진한 글씨로 명암 대비 확보 */
    div[data-testid="stVerticalBlock"]:has(.admin-update-banner-marker) div[data-testid="stExpander"] summary,
    div[data-testid="stVerticalBlock"]:has(.admin-update-banner-marker) div[data-testid="stExpander"] summary p,
    div[data-testid="stVerticalBlock"]:has(.admin-update-banner-marker) div[data-testid="stExpander"] summary span {
        color: #FFFFFF !important;
        font-weight: 700 !important;
    }
    div[data-testid="stVerticalBlock"]:has(.admin-update-banner-marker) div[data-testid="stTextInput"] input,
    div[data-testid="stVerticalBlock"]:has(.admin-update-banner-marker) div[data-testid="stTextArea"] textarea {
        color: #102030 !important;
        font-weight: 600 !important;
    }
    div[data-testid="stVerticalBlock"]:has(.admin-update-banner-marker) div[data-testid="stTextInput"] input::placeholder,
    div[data-testid="stVerticalBlock"]:has(.admin-update-banner-marker) div[data-testid="stTextArea"] textarea::placeholder {
        color: #5A6472 !important;
        opacity: 1 !important;
    }
    div[data-testid="stVerticalBlock"]:has(.admin-update-banner-marker) div[data-testid="stTextInput"] label,
    div[data-testid="stVerticalBlock"]:has(.admin-update-banner-marker) div[data-testid="stTextInput"] label p,
    div[data-testid="stVerticalBlock"]:has(.admin-update-banner-marker) div[data-testid="stTextArea"] label,
    div[data-testid="stVerticalBlock"]:has(.admin-update-banner-marker) div[data-testid="stTextArea"] label p,
    div[data-testid="stVerticalBlock"]:has(.admin-update-banner-marker) div[data-testid="stCaptionContainer"],
    div[data-testid="stVerticalBlock"]:has(.admin-update-banner-marker) div[data-testid="stCaptionContainer"] p {
        color: #FFFFFF !important;
        font-weight: 700 !important;
    }

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
# 🏠 로또신령 메인(사용자 화면)으로 돌아가는 버튼 — 지금까지 없었다.
# 사이드바가 collapsed 상태라 내비게이션 메뉴가 안 보여서, 관리자 대시보드에
# 들어오면 메인으로 돌아갈 방법이 사실상 없었다. 모든 admin_view에서 항상
# 보이도록 분기 위에 놓는다.
# ==========================================
if st.button("🏠 홈으로", key="admin_go_home_6n36s5"):
    st.switch_page("user_page.py")

# ==========================================
# 📂 사이드바 메뉴 — 2026-09-20 추가. 기존 화면(홈/필터관리/패턴관리)은
# 하나도 옮기거나 지우지 않았다 — 사이드바는 그 화면들로 가는 "추가 경로"일
# 뿐이라, 기존 버튼(🚀 3종필터 업로드, 📐 기준값패턴 업로드)도 그대로 남아
# 있다. change_view()는 위에서 이미 쓰던 함수 그대로 재사용 — 새 전환
# 방식을 만들지 않았다.
# ==========================================
with st.sidebar:
    st.markdown("### ⚙️ 관리자 메뉴")
    if st.button("🏠 홈", key="admin_nav_home_6n36s5", use_container_width=True):
        change_view("home")
        st.rerun()
    if st.button("🎯 필터/조합 관리", key="admin_nav_filter_6n36s5", use_container_width=True):
        change_view("filter_manage")
        st.rerun()
    if st.button("📐 패턴 관리", key="admin_nav_pattern_6n36s5", use_container_width=True):
        change_view("pattern_manage")
        st.rerun()
    if st.button("💳 결제 분쟁 처리", key="admin_nav_dispute_6n36s5", use_container_width=True):
        change_view("dispute_resolution")
        st.rerun()
    if st.button("⚙️ 운영관리", key="admin_nav_ops_6n36s5", use_container_width=True):
        change_view("ops_manage")
        st.rerun()

# ==========================================
# 🏠 화면 A: 대시보드 홈
# ==========================================
if st.session_state.admin_view == "home":
    st.markdown("<h2 style='font-weight:800; color:#FFFFFF; margin-bottom:5px;'>운영자 메인 대시보드</h2>", unsafe_allow_html=True)
    st.markdown("<p style='color:#94A3B8; margin-bottom:25px;'>대시보드 운영 현황</p>", unsafe_allow_html=True)

    @st.cache_data(ttl=60, show_spinner=False)
    def _member_activity_counts() -> tuple[int, int]:
        """(누적 가입자 수, 오늘 활동 인원). last_login_at은 로그인 시마다 갱신됨.

        관리자 대시보드는 위젯 하나만 눌러도 이 블록이 재실행되는데, 캐싱 없이
        COUNT(*) 쿼리 2개를 매번 다시 날리고 있었다(2026-08-27, 전체 코드베이스
        캐싱 누락 점검 중 발견) — 관리자 전용 화면이라 트래픽은 낮지만 같은
        패턴이라 60초 캐시를 씌운다."""
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

    # ── 🔔 보안 알림 — 관리자 비밀번호 무차별 대입 시도, 다운로드 남용 등
    # "침입 흔적"으로 볼 수 있는 이벤트를 admin_auth_guard가 기록해둔 걸 여기서 보여준다.
    st.markdown("<h4 style='margin-top:40px; color:#FFB300; font-weight:700;'>🔔 보안 알림</h4>", unsafe_allow_html=True)
    try:
        import security_log

        _sec_recent_count = security_log.count_recent_events(hours=24)
    except Exception as e:
        _sec_recent_count = 0
        st.warning(f"보안 이벤트 조회 실패: {e}")

    if _sec_recent_count > 0:
        st.error(f"🚨 최근 24시간 안에 침입 시도로 의심되는 기록이 {_sec_recent_count}건 있습니다.")
    else:
        st.success("최근 24시간 안에 특이사항이 없습니다.")

    with st.expander(f"침입 흔적 기록 보기 (최근 {_sec_recent_count}건 · 전체 최대 50건)"):
        try:
            _sec_events = security_log.list_recent_events(limit=50)
        except Exception as e:
            _sec_events = []
            st.warning(f"기록을 불러오지 못했습니다: {e}")

        if not _sec_events:
            st.caption("아직 기록된 이벤트가 없습니다.")
        else:
            _sec_df = pd.DataFrame(
                [
                    {
                        "시각(KST)": ev["created_at"],
                        "유형": security_log.EVENT_LABELS.get(ev["event_type"], ev["event_type"]),
                        "상세": ev["detail"] or "",
                        "IP(참고용)": ev["ip_address"] or "확인 불가",
                    }
                    for ev in _sec_events
                ]
            )
            st.caption("※ IP는 스푸핑(위조)될 수 있어 참고용입니다 — 차단 근거로만 쓰지 마세요.")
            st.dataframe(_sec_df, use_container_width=True, hide_index=True)

    st.markdown("<h4 style='margin-top:40px; color:#FFB300; font-weight:700;'>작업 프로세스 메뉴</h4>", unsafe_allow_html=True)

    # 🔥 기존의 1단계, 2단계 버튼을 완전히 없애고 이 버튼 하나로 통합했습니다.
    if st.button("🚀 3종 필터 업로드 및 원스톱 조합 생성 시작", type="primary"):
        change_view("filter_manage")
        st.rerun()

    # 3종필터(자동구매 전용)와 완전히 별개 기능이라 헷갈리지 않게 별도 섹션·버튼으로 뺐다
    # — 번개조합·안티/액땜조합이 과거 데이터 근거 유형지표를 채점할 때 쓰는 기준값 파일.
    st.markdown("<h4 style='margin-top:40px; color:#FFB300; font-weight:700;'>🧭 번개조합·안티/액땜조합 기준값패턴</h4>", unsafe_allow_html=True)
    if st.button("📐 기준값패턴 업로드"):
        change_view("pattern_manage")
        st.rerun()

    # 2026-09-20(사용자 지시): 아래 있던 배너/유력수/동시접속상한/UA보안/
    # 구매전환현황 5개 섹션은 홈 화면이 너무 어수선하다는 지적으로 "⚙️
    # 운영관리"(사이드바)로 이동했다. 위젯 key·내부 로직은 전혀 안 건드렸고
    # 위치만 옮김 — 이 아래(admin_view == "ops_manage" 블록) 참고.

    st.markdown("<h4 style='margin-top:40px; color:#FFB300; font-weight:700;'>📥 최신 회차 추출 조합 다운로드</h4>", unsafe_allow_html=True)
    from marketing_db import get_draw_extraction_stats, get_combinations_by_draw
    import admin_auth_guard

    # 조합저장본 전체를 통째로 내보내는 기능이라, 비밀번호가 뚫리거나 세션이
    # 탈취된 뒤 스크립트로 반복 다운로드해 긁어가는 걸 막기 위한 최소한의
    # 방어선. 로그인 잠금(admin_auth_guard._state)과 동일하게 프로세스
    # 전역으로 카운트해서, 짧은 시간에 여러 번 요청하면 버튼 자체를 숨긴다.
    _DL_MAX_PER_WINDOW = 3
    _DL_WINDOW_SECONDS = 300  # 5분

    _dl_remaining = admin_auth_guard.downloads_remaining(_DL_MAX_PER_WINDOW, _DL_WINDOW_SECONDS)
    if _dl_remaining <= 0:
        _dl_wait = int(admin_auth_guard.seconds_until_download_slot(_DL_WINDOW_SECONDS)) + 1
        st.warning(
            f"다운로드 요청이 너무 잦습니다 (5분당 최대 {_DL_MAX_PER_WINDOW}회). "
            f"{_dl_wait}초 후 다시 시도해 주세요."
        )
        # 매 렌더마다(카운트다운 표시 중에도) 다시 기록되지 않도록, 이 "막힘" 국면에서
        # 한 번만 남긴다 — 막힘이 풀리면(_dl_remaining > 0) 플래그가 리셋돼 다음 번
        # 막힐 때 다시 기록된다.
        if not st.session_state.get("_dl_block_logged"):
            st.session_state["_dl_block_logged"] = True
            try:
                import security_log

                security_log.log_event(
                    "download_rate_limited",
                    f"5분당 {_DL_MAX_PER_WINDOW}회 제한 초과",
                )
            except Exception:
                pass
    else:
        st.session_state["_dl_block_logged"] = False

        @st.cache_data(ttl=60, show_spinner=False)
        def _dl_latest_draw_cached():
            """최신 회차 조합 전체를 다운로드 버튼용으로 미리 불러온다 — 실제로
            다운로드를 누르든 안 누르든 홈 화면이 재렌더될 때마다 회차 하나 분
            조합 전체(수천 건)를 매번 다시 조회하고 있었다(2026-08-27, 전체
            코드베이스 캐싱 누락 점검 중 발견) — 60초 캐시로 방어."""
            stats = get_draw_extraction_stats(limit=1)
            if not stats:
                return None
            draw_round = int(stats[0]["draw_round"])
            count = int(stats[0]["total_count"])
            combos = get_combinations_by_draw(draw_round)
            return draw_round, count, combos

        _dl_latest = _dl_latest_draw_cached()
        if _dl_latest is None:
            st.caption("다운로드할 회차 데이터가 없습니다.")
        else:
            _dl_draw_round, _dl_count, _dl_combos = _dl_latest
            _dl_df = pd.DataFrame(
                [
                    {
                        "번호1": c["combo"][0],
                        "번호2": c["combo"][1],
                        "번호3": c["combo"][2],
                        "번호4": c["combo"][3],
                        "번호5": c["combo"][4],
                        "번호6": c["combo"][5],
                        "당첨등수": c["win_rank"] or "",
                    }
                    for c in _dl_combos
                ]
            )
            _dl_clicked = st.download_button(
                f"⬇️ {_dl_draw_round}회차 조합 {_dl_count:,}개 다운로드 (남은 시도 {_dl_remaining}/{_DL_MAX_PER_WINDOW})",
                data=_dl_df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"lotto_combinations_{_dl_draw_round}.csv",
                mime="text/csv",
                key="admin_dl_download_6n36s5",
                use_container_width=True,
            )
            if _dl_clicked:
                admin_auth_guard.record_download()

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
            _filters_pickle_bytes = pickle.dumps(filters_data)
            with open(FILTER_SAVE_FILE, "wb") as f:
                f.write(_filters_pickle_bytes)

            # Streamlit Cloud는 재배포마다 로컬 디스크를 초기화해서, 로컬 파일만
            # 믿으면 관리자가 업로드한 필터가 다음 배포 때 조용히 사라진다
            # (2026-08-22 실제로 발생했던 사고) — Turso DB에도 미러링해둔다.
            from app_settings import save_blob_setting

            save_blob_setting("saved_filters_pickle_b64", _filters_pickle_bytes)

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
            total_rows = sum(int(v) for v in val_summary.values())
            cap = " · ".join(f"{k}={v}" for k, v in val_summary.items())
            st.caption(f"총 {total_rows:,}개 패턴 — {cap}")
        except Exception as e:
            st.error(f"❌ 시트명 또는 양식 오류: {e}")

    # 로컬 파일이 없는데(재배포로 사라졌을 수 있음) DB엔 미러본이 있으면 복원한다 —
    # 이 복원만 해두면 아래의 모든 기존 os.path.exists(FILTER_SAVE_FILE) 분기가
    # 손댈 필요 없이 그대로 정상 동작한다.
    if not os.path.exists(FILTER_SAVE_FILE):
        from app_settings import load_blob_setting

        _restored_filters = load_blob_setting("saved_filters_pickle_b64")
        if _restored_filters:
            with open(FILTER_SAVE_FILE, "wb") as f:
                f.write(_restored_filters)

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
        # 로컬 파일이 없는데(재배포로 사라졌을 수 있음) DB엔 미러본이 있으면 복원.
        if not os.path.exists(COMBO_SAVE_FILE):
            from app_settings import get_setting, init_settings_table

            init_settings_table()
            _restored_combos = get_setting("saved_combinations_csv", "")
            if _restored_combos:
                with open(COMBO_SAVE_FILE, "w", encoding="utf-8") as f:
                    f.write(_restored_combos)

        if os.path.exists(COMBO_SAVE_FILE):
            df_export = pd.read_csv(COMBO_SAVE_FILE)
            total_created = len(df_export)

            # 백그라운드 워커가 방금 새로 썼을 수도 있는 최신 내용을 DB에도
            # 미러링 — 다음 배포 때도 살아남도록. 관리자 전용 저빈도 화면이라
            # 렌더마다 다시 써도 부담 없다.
            from app_settings import init_settings_table, set_setting

            init_settings_table()
            set_setting("saved_combinations_csv", df_export.to_csv(index=False))
            
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(f"""
            <div style="background-color: #161B26; border: 2px solid #00E676; padding: 25px; border-radius: 12px; text-align: center; box-shadow: 0 4px 15px rgba(0,230,118,0.15);">
                <h2 style="color: #00E676; margin: 0; font-weight: 900;">🎉 총 {total_created:,}개의 조합이 생성됐습니다.</h2>
                <p style="color: #94A3B8; margin-top: 8px; margin-bottom: 0;">데이터가 시스템에 안전하게 저장되었습니다. (로그아웃 후에도 유지)</p>
            </div>
            <br>
            """, unsafe_allow_html=True)

            # ==========================================
            # 🎯 조합 수량 조정 — 기준값패턴 적합도가 가장 낮은 것부터 제외
            # ==========================================
            st.markdown("<h4 style='color:#FFB300; margin-top:10px;'>🎯 조합 수량 조정</h4>", unsafe_allow_html=True)
            st.caption(
                "기준값패턴(번개조합·안티/액땜조합이 쓰는 그 기준)에 가장 적게 부합하는 "
                "조합부터 제외해서 원하는 수량으로 줄입니다. 3종필터와는 별개 기준입니다."
            )
            trim_col1, trim_col2 = st.columns([2, 1])
            with trim_col1:
                target_qty = st.number_input(
                    "원하는 조정 수량 (개)",
                    min_value=1,
                    max_value=int(total_created),
                    value=int(total_created),
                    step=100,
                    key="admin_combo_trim_target",
                )
            with trim_col2:
                st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
                trim_clicked = st.button(
                    "✂️ 이 수량으로 줄이기", key="admin_combo_trim_btn", use_container_width=True
                )

            if trim_clicked:
                if int(target_qty) >= total_created:
                    st.warning(f"현재 수량({total_created:,}개)보다 크거나 같아 줄일 필요가 없습니다.")
                else:
                    from lotto_stats import get_resolved_pattern_rules, score_combo_against_pattern_rules

                    rules = get_resolved_pattern_rules()
                    if not rules:
                        st.warning(
                            "업로드된 기준값패턴이 없어 적합도 순위를 매길 수 없습니다. "
                            "먼저 '🧭 번개조합·안티/액땜조합 기준값패턴'에서 패턴을 업로드해 주세요."
                        )
                    else:
                        with st.spinner(f"{total_created:,}개 조합의 기준값패턴 적합도를 계산하는 중..."):
                            def _pattern_score(row):
                                combo = (
                                    row["번호1"], row["번호2"], row["번호3"],
                                    row["번호4"], row["번호5"], row["번호6"],
                                )
                                _, matched, _total = score_combo_against_pattern_rules(combo, rules)
                                return matched

                            df_scored = df_export.copy()
                            df_scored["_pattern_score"] = df_scored.apply(_pattern_score, axis=1)
                            df_trimmed = (
                                df_scored.sort_values("_pattern_score", ascending=False)
                                .head(int(target_qty))
                                .drop(columns=["_pattern_score"])
                                .reset_index(drop=True)
                            )
                            df_trimmed.to_csv(COMBO_SAVE_FILE, index=False)

                            from app_settings import init_settings_table, set_setting

                            init_settings_table()
                            set_setting("saved_combinations_csv", df_trimmed.to_csv(index=False))

                        st.success(
                            f"✅ {total_created:,}개 → {len(df_trimmed):,}개로 줄였습니다 "
                            f"(기준값패턴 적합도가 가장 낮은 {total_created - len(df_trimmed):,}개 제외)."
                        )
                        st.rerun()

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
                MAX_BULK_INSERT_ROWS,
                bulk_insert_lotto_combinations,
                delete_lotto_combinations_by_draw,
                get_combination_count_by_draw,
                init_marketing_tables,
                parse_combination_rows_from_dataframe,
                parse_combination_rows_from_text,
                record_draw_pattern_count,
            )

            init_marketing_tables()

            def _current_filter_pattern_count() -> int | None:
                """조합을 방금 추출한 이 순간 값을 회차에 기록해두기 위함(회차별
                당첨번호 배출 화면에서 회차마다 같은 값이 나오던 문제의 수정: 추출
                시점 값을 고정 기록해서 나중에 이 값이 바뀌어도 그 회차는 당시 값을
                유지한다).

                2026-08-30: 예전엔 "로또최근당첨내역.xlsb" 당번시트 N5 셀을 관리자가
                손으로 입력해둔 값을 그대로 읽었는데, 3종필터를 새로 업로드·연산해도
                N5를 따로 안 고치면 "적용패턴수"가 그 연산 결과와 따로 놀았다(관리자
                지적, 재확인 요청) — .xlsb는 읽기 전용 라이브러리(pyxlsb)만 있어
                이 서버에서 직접 써넣을 방법이 없어 그동안 수동 입력에 의존했다.
                이제 filter_worker.py가 3종필터 연산 완료 직후 그 결과(필터를 전부
                통과한 조합 수)를 DB 설정값으로 저장해두므로, N5 대신 그 값을
                그대로 읽어온다 — 수동 입력 없이 항상 최신 연산 결과와 맞물린다."""
                try:
                    from app_settings import get_setting, init_settings_table

                    init_settings_table()
                    raw = get_setting("latest_filter_pattern_count", "")
                    return int(raw) if raw.strip() else None
                except Exception:
                    return None

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
                # 2026-09-19: 용량 한도 검사는 "기존 데이터 삭제"보다 먼저 한다 —
                # 순서가 반대면 한도 초과로 저장이 거부될 때 그 회차 데이터가
                # 이미 지워진 뒤라(delete 후 insert 실패) 복구할 수 없다.
                if len(rows) > MAX_BULK_INSERT_ROWS:
                    st.error(
                        f"❌ 저장 중단: 한 번에 저장할 수 있는 조합은 최대 "
                        f"{MAX_BULK_INSERT_ROWS:,}개입니다(요청 {len(rows):,}개). "
                        "파일을 나눠 올려주세요 — 기존 데이터는 지우지 않았습니다."
                    )
                    return
                if replace_existing:
                    delete_lotto_combinations_by_draw(draw_round)
                saved_count = bulk_insert_lotto_combinations(draw_round, rows)
                total_in_db = get_combination_count_by_draw(draw_round)
                pattern_count = _current_filter_pattern_count()
                if pattern_count is not None:
                    record_draw_pattern_count(draw_round, pattern_count)
                st.success(
                    f"회차 {draw_round}: {saved_count:,}개 조합 저장 완료 "
                    f"(해당 회차 DB 누적 {total_in_db:,}개)"
                )

            # 2026-08-30: 이미 조합이 저장(배포)된 회차는 그 시점의 적용패턴수가
            # 고정 기록된다(record_draw_pattern_count) — 그 뒤 3종필터를 다시
            # 연산해도 이미 배포된 회차 조합을 그대로 두면서 "적용패턴수" 기록만
            # 최신 값으로 바로잡고 싶을 때(조합 재추출·재배포 없이) 쓰는 수동
            # 보정 도구. 실제 조합 데이터는 전혀 건드리지 않고 draw_pattern_counts
            # 기록 한 줄만 갱신한다.
            with st.expander("🔧 회차별 적용패턴수 수동 보정"):
                st.caption(
                    "이미 조합이 저장된 회차의 '적용패턴수' 기록만 바로잡습니다"
                    "(조합 자체는 건드리지 않음)."
                )
                pc_col1, pc_col2 = st.columns(2)
                with pc_col1:
                    pc_round = st.number_input(
                        "회차", min_value=1, step=1, key="admin_pc_fix_round"
                    )
                with pc_col2:
                    pc_value = st.number_input(
                        "적용패턴수", min_value=0, step=1, key="admin_pc_fix_value"
                    )
                if st.button("보정 저장", key="admin_pc_fix_submit"):
                    record_draw_pattern_count(int(pc_round), int(pc_value))
                    st.success(f"{int(pc_round)}회차 적용패턴수를 {int(pc_value):,}(으)로 기록했습니다.")

            # 2026-09-19(사용자 지시): "메인화면 유력수 보정"은 여기(3종필터 업로드
            # 화면) 안에 있어서 운영자가 못 찾는다는 지적으로 홈 화면(작업 프로세스
            # 메뉴 위쪽, 📣 업데이트 안내 배너 section 바로 옆)으로 옮겼다 — 코드는
            # admin_view == "home" 블록 안에 그대로 있으니 그쪽 참고.

            # 2026-09-01: 당첨번호를 "로또최근당첨내역.xlsb 로컬 수정 → git 커밋·푸시"
            # 하던 걸 DB(draw_results)로 옮겼다 — pyxlsb가 읽기 전용이라 그 xlsb
            # 파일에는 더 이상 자동으로 못 써넣으니, 이제부터는 신규 회차가 전부
            # 이 테이블에만 쌓인다. 동행복권 공식 사이트에 인증 없이 최신 회차를
            # 그대로 내려주는 엔드포인트가 있어(2026-09-01 실측 확인) 매시간
            # 자동으로 확인해서 채워 넣지만(lotto_stats._auto_sync_latest_draw_cached),
            # 그게 실패하거나(사이트 구조 변경 등) 급하게 바로 반영하고 싶을 때를
            # 위해 수동 등록·즉시 동기화 도구도 같이 둔다.
            with st.expander("🔧 당첨번호 회차 관리 (자동 동기화 + 수동 등록)"):
                import draw_results_db as _drdb

                _drdb.init_draw_results_table()
                _latest_local = _drdb.get_latest_draw_round()
                _total_local = _drdb.get_draw_results_count()
                st.caption(
                    f"현재 DB에 등록된 최신 회차: {_latest_local if _latest_local else '없음(이관 전)'}"
                    f" (전체 {_total_local:,}건)"
                    " — 매시간 자동으로 동행복권 사이트를 확인해 새 회차를 채웁니다."
                )

                if st.button("지금 바로 동행복권에서 확인", key="admin_draw_sync_now"):
                    synced = _drdb.sync_latest_from_dhlottery()
                    if synced:
                        st.success(f"{synced}회차를 새로 가져와 저장했습니다.")
                    else:
                        remote = _drdb.fetch_latest_from_dhlottery()
                        if remote is None:
                            st.error("동행복권 사이트에서 가져오지 못했습니다(네트워크 또는 사이트 구조 변경 가능성) — 아래 수동 등록을 이용해 주세요.")
                        else:
                            st.info(f"이미 최신 상태입니다(사이트 최신 회차: {remote['draw_round']}).")

                st.markdown("---")
                st.caption("자동 동기화가 안 될 때, 회차와 번호를 직접 입력해 등록/수정합니다.")
                dr_col1, dr_col2 = st.columns(2)
                with dr_col1:
                    dr_round = st.number_input(
                        "회차", min_value=1, step=1,
                        value=(int(_latest_local) + 1) if _latest_local else 1,
                        key="admin_draw_round_input",
                    )
                with dr_col2:
                    dr_bonus = st.number_input(
                        "보너스 번호", min_value=1, max_value=45, step=1, key="admin_draw_bonus_input"
                    )
                dr_numbers = st.text_input(
                    "당첨번호 6개 (쉼표 구분)", placeholder="예: 11,13,22,32,33,36",
                    key="admin_draw_numbers_input",
                )
                if st.button("회차 저장", key="admin_draw_result_submit"):
                    try:
                        nums = [int(x.strip()) for x in dr_numbers.split(",") if x.strip()]
                        _drdb.upsert_draw_result(int(dr_round), nums, int(dr_bonus))
                        st.success(f"{int(dr_round)}회차를 저장했습니다.")
                    except Exception as exc:
                        st.error(f"저장 실패: {exc}")

                st.markdown("---")
                st.caption(
                    "최초 1회용 — 기존 xlsb 파일의 과거 회차 전체를 이 DB로 이관합니다"
                    "(이미 있는 회차는 건드리지 않고 값만 최신으로 덮어씁니다, 여러 번 눌러도 안전)."
                )
                if st.button("xlsb 과거 이력 전체 이관", key="admin_draw_migrate_xlsb"):
                    from lotto_stats import _load_lotto_data_cached, _xlsb_mtime, lotto_data_path, COL_DRAW, COL_NUM_START, COL_NUM_END, COL_BONUS
                    import pandas as _pd

                    _xlsb_path = lotto_data_path()
                    _df = _load_lotto_data_cached(_xlsb_path, _xlsb_mtime(_xlsb_path))
                    migrated = 0
                    skipped = 0
                    for _, _row in _df.iterrows():
                        _rnd = _pd.to_numeric(_row[COL_DRAW], errors="coerce")
                        if _pd.isna(_rnd):
                            continue
                        _nums = []
                        for _i in range(COL_NUM_START, COL_NUM_END):
                            _v = _pd.to_numeric(_row[_i], errors="coerce")
                            if _pd.notna(_v):
                                _nums.append(int(_v))
                        _bonus = _pd.to_numeric(_row[COL_BONUS], errors="coerce")
                        if len(_nums) != 6 or _pd.isna(_bonus):
                            skipped += 1
                            continue
                        try:
                            _drdb.upsert_draw_result(int(_rnd), _nums, int(_bonus))
                            migrated += 1
                        except Exception:
                            skipped += 1
                    st.success(f"이관 완료: {migrated}건 저장, {skipped}건 건너뜀.")

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

# ==========================================
# 📐 번개조합·안티/액땜조합 — 기준값패턴 관리
# ==========================================
# 3종필터(자동구매 전용, filter_manage 뷰)와 완전히 별개 기능이다 — 헷갈리지
# 않게 홈 화면에서도 별도 버튼, 여기서도 별도 뷰로 분리했다. 번개조합·안티/
# 액땜조합이 조합 후보를 채점할 때(lotto_stats.score_combo_against_pattern_rules)
# 쓰는 "역대 데이터 근거 기준값패턴"을 관리자가 엑셀로 관리한다(2026-08-21,
# 하드코딩했던 8개 유형지표를 완전히 대체함).
elif st.session_state.admin_view == "pattern_manage":
    st.session_state.admin_view = "pattern_manage"
    try:
        st.query_params["admin_view"] = "pattern_manage"
    except Exception:
        pass
    if st.button("⬅️ 대시보드 홈으로 이동", key="pattern_manage_back_btn"):
        change_view("home")
        st.rerun()

    st.markdown("<h3 style='color:#FFB300; font-weight:800;'>📐 기준값패턴 업로드</h3>", unsafe_allow_html=True)
    st.info(
        "💡 **기준값패턴.xlsx** — H열(그룹명) / J열(입력데이터, 앞뒤 콤마 형식 또는 "
        "`AUTO`) / K열(최소) / L열(최대) / M열(설명, 참고용) · 헤더는 2행, 데이터는 3행부터. "
        "번개조합·안티/액땜조합 조합 생성 시 이 기준으로 채점됩니다(자동구매용 3종필터와는 무관)."
    )

    uploaded_pattern = st.file_uploader(
        "📂 기준값패턴 엑셀 업로드 (.xlsx)", type=["xlsx"], key="pattern_rules_uploader"
    )

    if uploaded_pattern:
        try:
            from lotto_engine import _parse_targets

            raw = pd.read_excel(
                uploaded_pattern, sheet_name=0, skiprows=2, usecols="H,J,K,L,M", header=None
            )
            raw.columns = ["그룹명", "입력데이터", "최소", "최대", "설명"]
            raw = raw.dropna(subset=["최소", "최대"])

            def _clean_int(val):
                try:
                    return int(float(val))
                except (TypeError, ValueError):
                    return None

            rules = []
            skipped = []
            for _, row in raw.iterrows():
                raw_input = str(row["입력데이터"]).strip() if pd.notna(row["입력데이터"]) else ""
                min_v = _clean_int(row["최소"])
                max_v = _clean_int(row["최대"])
                group_name = str(row["그룹명"]).strip() if pd.notna(row["그룹명"]) else ""
                note = str(row["설명"]).strip() if pd.notna(row["설명"]) else ""

                if min_v is None or max_v is None:
                    continue

                if raw_input.upper() == "AUTO":
                    rules.append(
                        {
                            "group_name": group_name,
                            "type": "auto",
                            "targets": None,
                            "min": min_v,
                            "max": max_v,
                            "note": note,
                        }
                    )
                else:
                    targets = _parse_targets(raw_input)
                    if not targets:
                        # 입력데이터가 비어있으면(빈 칸) 그냥 미완성/미사용 행으로 보고
                        # 조용히 건너뛴다 — 글자가 있는데도 번호로 못 읽은 경우만
                        # "이상함"으로 보고 아래에 알림.
                        if raw_input:
                            skipped.append(group_name or raw_input or "(이름 없음)")
                        continue
                    rules.append(
                        {
                            "group_name": group_name,
                            "type": "fixed",
                            "targets": sorted(targets),
                            "min": min_v,
                            "max": max_v,
                            "note": note,
                        }
                    )

            from app_settings import init_settings_table, set_setting

            init_settings_table()
            set_setting("pattern_rules_json", json.dumps(rules))

            auto_count = sum(1 for r in rules if r["type"] == "auto")
            fixed_count = len(rules) - auto_count
            st.success(
                f"✅ 저장 완료 — 고정 패턴 {fixed_count}개, AUTO(매주 자동계산) 패턴 {auto_count}개."
            )
            if skipped:
                st.warning(f"⚠️ 번호를 못 읽어 건너뛴 행: {', '.join(skipped[:20])}"
                           + (f" 외 {len(skipped) - 20}건" if len(skipped) > 20 else ""))

            if auto_count:
                st.markdown("**AUTO 패턴 목록** (실제 번호는 조합 생성 시점에 최신 데이터로 계산)")
                st.dataframe(
                    pd.DataFrame(
                        [
                            {"그룹명": r["group_name"], "최소": r["min"], "최대": r["max"], "설명": r["note"]}
                            for r in rules
                            if r["type"] == "auto"
                        ]
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

            with st.expander(f"고정 패턴 미리보기 ({fixed_count}개)"):
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "그룹명": r["group_name"],
                                "번호": ",".join(str(n) for n in r["targets"]),
                                "최소": r["min"],
                                "최대": r["max"],
                            }
                            for r in rules
                            if r["type"] == "fixed"
                        ]
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
        except Exception as e:
            st.error(f"업로드 처리 중 오류: {e}")
    else:
        from app_settings import get_setting, init_settings_table

        init_settings_table()
        _existing_raw = get_setting("pattern_rules_json", "")
        if _existing_raw:
            _existing_rules = json.loads(_existing_raw)
            _auto_n = sum(1 for r in _existing_rules if r["type"] == "auto")
            st.caption(f"현재 저장된 기준값패턴: 고정 {len(_existing_rules) - _auto_n}개, AUTO {_auto_n}개")
        else:
            st.caption("아직 업로드된 기준값패턴이 없습니다.")

# ==========================================
# 💳 결제 분쟁 처리 — 2026-09-20 신규.
#
# 배경: toss_pg.py는 "결제창 → successUrl 콜백 → 승인 → 적립" 흐름만 구현돼
# 있고(비동기 웹훅은 별도 서버리스 함수로 분리 예정, 아직 없음), 이 흐름은
# 고객 브라우저가 successUrl로 무사히 돌아오는 것에 전부 의존한다. 토스
# 개발자 커뮤니티에 실제로 보고된 사례(앱 웹뷰 환경에서 결제 완료 직후
# successUrl로 이동하지 않고 웹뷰가 그냥 닫혀버림 — 로또신령과 정확히 같은
# 구조)처럼 콜백이 아예 안 오면, toss_pending_orders가 'pending' 상태로
# 영원히 멈춘다. 이 화면은 그런 주문을 관리자가 찾아서, "토스 공식 기록"을
# 직접 조회해 확인한 뒤에만, 이미 검증된 charge_points()를 그대로 재사용해
# 안전하게(ref_id 중복지급 방지 그대로 적용) 지급할 수 있게 한다. 새 자금
# 이동 로직은 추가하지 않았다 — 기존 함수 재사용이 핵심 안전장치.
# ==========================================
elif st.session_state.admin_view == "dispute_resolution":
    st.session_state.admin_view = "dispute_resolution"
    if st.button("⬅️ 대시보드 홈으로 이동", key="dispute_resolution_back_btn"):
        change_view("home")
        st.rerun()

    st.markdown(
        "<h2 style='font-weight:800; color:#FFFFFF; margin-bottom:5px;'>💳 결제 분쟁 처리</h2>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='color:#94A3B8; margin-bottom:25px;'>"
        "고객이 '결제했는데 포인트가 안 들어왔다'고 문의했을 때, 토스 공식 기록을 "
        "직접 확인한 뒤에만 안전하게 지급하는 화면입니다.</p>",
        unsafe_allow_html=True,
    )

    import security_log
    import toss_pg
    import wallet_db

    # ── 1) 정체된 결제 자동 감지 ──
    st.markdown(
        "<h4 style='margin-top:10px; color:#FFB300; font-weight:700;'>🔍 정체된 결제 (자동 감지)</h4>",
        unsafe_allow_html=True,
    )
    st.caption(
        "결제창에서 성공했지만 앱으로 돌아오는 콜백이 없어 'pending' 상태로 멈춰있는 "
        "주문입니다. 특히 웹뷰(앱) 환경에서 결제 직후 화면이 닫히는 경우 발생할 수 "
        "있습니다 — 고객이 문의하기 전에 먼저 확인해 보세요."
    )

    _stale_minutes = st.number_input(
        "몇 분 이상 멈춰있으면 보여줄지", min_value=1, max_value=1440, value=10, step=1,
        key="dispute_stale_minutes",
    )
    if st.button("🔄 새로고침", key="dispute_refresh_stuck"):
        st.rerun()

    try:
        _stuck_orders = wallet_db.list_stuck_toss_orders(stale_minutes=int(_stale_minutes))
    except Exception as e:
        _stuck_orders = []
        st.warning(f"조회 실패: {e}")

    if not _stuck_orders:
        st.success("현재 정체된 결제가 없습니다.")
    else:
        st.error(f"🚨 정체된 결제 {len(_stuck_orders)}건 발견")
        _stuck_df = pd.DataFrame(
            [
                {
                    "주문ID": o["order_id"],
                    "회원ID": o["member_id"],
                    "결제금액": f"{o['won_amount']:,}원",
                    "지급예정P": f"{o['points']:,}P",
                    "생성시각": o["created_at"],
                }
                for o in _stuck_orders
            ]
        )
        st.dataframe(_stuck_df, use_container_width=True, hide_index=True)
        st.caption("아래 '주문 조회·처리'에 주문ID를 그대로 복사해서 붙여넣으세요.")

    st.markdown("---")

    # ── 2) 주문 조회 · 처리 ──
    st.markdown(
        "<h4 style='margin-top:10px; color:#FFB300; font-weight:700;'>🔎 주문 조회 · 처리</h4>",
        unsafe_allow_html=True,
    )

    _lookup_mode = st.radio(
        "조회 방법", ["주문ID로 조회", "회원ID로 전체 내역 보기"],
        key="dispute_lookup_mode", horizontal=True,
    )

    if _lookup_mode == "회원ID로 전체 내역 보기":
        _member_id_input = st.number_input(
            "회원 ID", min_value=1, step=1, key="dispute_member_id_input"
        )
        if st.button("조회", key="dispute_search_by_member"):
            try:
                _member_orders = wallet_db.find_toss_orders_by_member(int(_member_id_input))
            except Exception as e:
                _member_orders = []
                st.warning(f"조회 실패: {e}")
            if not _member_orders:
                st.info("해당 회원의 토스 결제 내역이 없습니다.")
            else:
                _mo_df = pd.DataFrame(
                    [
                        {
                            "주문ID": o["order_id"],
                            "금액": f"{o['won_amount']:,}원",
                            "포인트": f"{o['points']:,}P",
                            "상태": o["status"],
                            "생성시각": o["created_at"],
                            "승인시각": o["confirmed_at"] or "",
                        }
                        for o in _member_orders
                    ]
                )
                st.dataframe(_mo_df, use_container_width=True, hide_index=True)
                st.caption("처리할 주문의 '주문ID'를 복사해서 아래 입력창에 붙여넣으세요.")

    _target_order_id = st.text_input(
        "주문 ID (order_id)", key="dispute_order_id_input",
        help="위 목록에서 복사하거나, 고객이 알려준 결제 화면 정보로 찾은 주문 ID를 입력하세요.",
    ).strip()

    if _target_order_id:
        _order = wallet_db.get_toss_pending_order(_target_order_id)
        if not _order:
            st.error("해당 주문ID를 DB에서 찾을 수 없습니다. 오타를 확인해 주세요.")
        else:
            st.markdown(
                f"**DB 기록**: 회원ID `{_order['member_id']}` · "
                f"결제금액 `{_order['won_amount']:,}원` · "
                f"지급예정 `{_order['points']:,}P` · "
                f"현재상태 `{_order['status']}`"
            )

            if _order["status"] == "confirmed":
                st.success("이미 정상적으로 처리 완료된 주문입니다 — 추가 조치가 필요 없습니다.")
            else:
                if st.button("🔍 토스에서 실제 결제 상태 확인", key="dispute_query_toss"):
                    _ok, _result = toss_pg.query_toss_order(_target_order_id)
                    st.session_state["dispute_toss_result"] = (_ok, _result)
                    st.session_state["dispute_toss_result_order_id"] = _target_order_id

                _cached = st.session_state.get("dispute_toss_result")
                _cached_order_id = st.session_state.get("dispute_toss_result_order_id")
                if _cached and _cached_order_id == _target_order_id:
                    _ok, _result = _cached
                    if not _ok:
                        st.error(f"토스 조회 실패: {_result}")
                    else:
                        _toss_status = _result.get("status")
                        _toss_amount = _result.get("totalAmount")
                        if isinstance(_toss_amount, (int, float)):
                            st.info(f"**토스 측 기록**: 상태 `{_toss_status}` · 승인금액 `{_toss_amount:,.0f}원`")
                        else:
                            st.info(f"**토스 측 기록**: 상태 `{_toss_status}`")

                        _amount_match = _toss_amount == _order["won_amount"]
                        if _toss_status == "DONE" and _amount_match:
                            st.success("토스 기록상 결제가 정상 승인됐고 금액도 일치합니다 — 지급을 진행할 수 있습니다.")
                            st.warning("아래 버튼을 누르면 실제로 포인트가 지급됩니다 — 신중하게 확인 후 눌러주세요.")
                            if st.button(
                                f"✅ 회원ID {_order['member_id']}에게 {_order['points']:,}P 지급",
                                type="primary", key="dispute_credit_confirm",
                            ):
                                _ref_id = f"pg:toss:{_target_order_id}"
                                _credited = wallet_db.charge_points(
                                    _order["member_id"], _order["points"], _ref_id
                                )
                                wallet_db.mark_toss_order_status(
                                    _target_order_id, "confirmed" if _credited else "credit_failed"
                                )
                                try:
                                    security_log.log_event(
                                        "admin_toss_dispute_resolved",
                                        f"order_id={_target_order_id} member_id={_order['member_id']} "
                                        f"points={_order['points']} credited={_credited}",
                                    )
                                except Exception:
                                    pass
                                if _credited:
                                    st.success(
                                        "지급 처리 완료했습니다 "
                                        "(이미 지급돼 있던 건이면 중복 지급 없이 그대로 유지됩니다)."
                                    )
                                    st.session_state.pop("dispute_toss_result", None)
                                    st.session_state.pop("dispute_toss_result_order_id", None)
                                    st.rerun()
                                else:
                                    st.error("지급에 실패했습니다 — 해당 회원의 지갑이 존재하는지 확인해 주세요.")
                        elif _toss_status == "DONE" and not _amount_match:
                            st.error(
                                f"⚠️ 금액 불일치 — DB 기록({_order['won_amount']:,}원)과 "
                                f"토스 승인금액이 다릅니다. 지급하지 말고 수동으로 다시 확인하세요."
                            )
                        else:
                            st.warning(f"토스 기록상 결제가 완료되지 않았습니다(상태: {_toss_status}). 지급 대상이 아닙니다.")

# ==========================================
# ⚙️ 운영관리 — 2026-09-20 추가. 홈 화면에 있던 5개 섹션(업데이트 배너 /
# 메인화면 유력수 보정 / 동시접속 상한 / 게스트 자동로그인 보안(UA 대조) /
# 회차별 구매 전환 현황)을 그대로 옮겨왔다 — 위젯 key·내부 로직은 전혀
# 손대지 않았고 위치만 옮겼다("home" 블록에 남겨둔 이동 주석 참고).
# ==========================================
elif st.session_state.admin_view == "ops_manage":
    st.session_state.admin_view = "ops_manage"
    if st.button("⬅️ 대시보드 홈으로 이동", key="ops_manage_back_btn"):
        change_view("home")
        st.rerun()

    st.markdown(
        "<h2 style='font-weight:800; color:#FFFFFF; margin-bottom:5px;'>⚙️ 운영관리</h2>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='color:#94A3B8; margin-bottom:25px;'>사용자 화면에 즉시 반영되는 운영 설정 모음입니다.</p>",
        unsafe_allow_html=True,
    )

    # 2026-09-20(사용자 지시): 앱 설치 현황 + 요일별(월~일) 활동 유저를 한눈에
    # 보는 표. member_daily_activity는 오늘부터 새로 쌓기 시작한 표라(과거
    # last_login_at은 로그인마다 덮어써져서 요일별 집계가 불가능했음, wallet_db.py
    # 주석 참고) 도입 초반 며칠은 앞 요일이 0으로 보이는 게 정상이다.
    st.markdown("<h4 style='margin-top:10px; color:#FFB300; font-weight:700;'>📈 앱 설치 현황 / 일간 활동 유저</h4>", unsafe_allow_html=True)

    @st.cache_data(ttl=60, show_spinner=False)
    def _ops_install_and_weekly_activity_cached():
        import wallet_db

        return wallet_db.get_total_installed_members(), wallet_db.get_weekly_active_users()

    try:
        _ops_total_installed, _ops_weekly_rows = _ops_install_and_weekly_activity_cached()
    except Exception as e:
        _ops_total_installed, _ops_weekly_rows = 0, []
        st.warning(f"설치·활동 현황 조회 실패: {e}")

    st.metric("앱 설치 현황 (누적 가입자)", f"{_ops_total_installed:,} 명")
    if _ops_weekly_rows:
        st.caption("이번 주(월~일, KST) 일간 활동 유저 수 — 2026-09-20부터 집계를 시작해 그 이전 요일은 0으로 표시됩니다.")
        st.dataframe(
            pd.DataFrame(_ops_weekly_rows),
            use_container_width=True,
            hide_index=True,
        )

    # 2026-09-20(사용자 지시): "배포본이 어디 저장돼 있고 화요일 배포에
    # 문제없는지 확인하고 싶다"는 요청 — 실제 화요일부터 판매(배포)에 쓰이는
    # 저장본은 파일이 아니라 Turso DB(marketing_db.lotto_combinations)에만
    # 있고, lotto-app 폴더의 CSV들(조합_확인용.csv, 1242회차_배포후보.csv
    # 등)은 감사/검증용이거나 일회성 백업이라 실제 배포 로직이 읽지 않는다
    # (파일을 옮겨도 화요일 배포엔 영향 없음) — 그래서 파일 경로를 바꾸는
    # 대신, DB에 실제로 뭐가 들어있는지 한눈에 보이는 현황판만 추가한다.
    st.markdown("<h4 style='margin-top:40px; color:#FFB300; font-weight:700;'>📦 현재 배포현황</h4>", unsafe_allow_html=True)
    st.caption("화요일 09:00부터 판매(배포)되는 조합은 이 회차 기준입니다 — 로컬 CSV 파일이 아니라 DB(Turso)에 저장된 값입니다.")

    @st.cache_data(ttl=60, show_spinner=False)
    def _ops_latest_distribution_cached():
        from marketing_db import get_draw_extraction_stats

        stats = get_draw_extraction_stats(limit=1)
        return stats[0] if stats else None

    try:
        _ops_latest_dist = _ops_latest_distribution_cached()
    except Exception as e:
        _ops_latest_dist = None
        st.warning(f"배포현황 조회 실패: {e}")

    if _ops_latest_dist is None:
        st.caption("등록된 배포 회차가 없습니다.")
    else:
        _dist_col1, _dist_col2 = st.columns(2)
        with _dist_col1:
            st.metric("최신 배포 회차", f"{_ops_latest_dist['draw_round']}회차")
        with _dist_col2:
            st.metric("등록된 조합 개수", f"{_ops_latest_dist['total_count']:,} 개")

    st.markdown("<h4 style='margin-top:40px; color:#FFB300; font-weight:700;'>📣 업데이트 안내 배너</h4>", unsafe_allow_html=True)
    st.markdown('<div class="admin-update-banner-marker" aria-hidden="true"></div>', unsafe_allow_html=True)
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

    # 2026-08-31: 메인화면 아이콘 주변에 도는 숫자 6개(user_page.py의
    # lucky_display)가 예전엔 코드에 직접 박혀있어서, 매주 값을 바꿀 때마다
    # git 커밋·푸시를 잊으면 화면이 옛날 숫자로 며칠씩 멈춰있는 사고가
    # 반복됐다 — 여기서 입력하면 배포 없이 바로 반영되도록 DB 설정값으로
    # 옮겼다.
    # 2026-09-19(사용자 지시): 원래 "3종필터 업로드" 화면 안에 묻혀있어서
    # 운영자가 못 찾겠다고 지적 — 홈 화면의, 역시 사용자 메인화면에 즉시
    # 반영되는 다른 설정(업데이트 배너)과 나란히 보이도록 옮겼다. 기능은
    # 그대로다.
    st.markdown("<h4 style='margin-top:40px; color:#FFB300; font-weight:700;'>🔧 메인화면 유력수 보정</h4>", unsafe_allow_html=True)
    with st.expander("아이콘 주변에 도는 숫자 6개 (사용자 화면에 즉시 반영)"):
        from app_settings import get_setting as _gs, init_settings_table as _ist, set_setting as _ss

        _ist()
        _current_lucky = _gs("main_lucky_numbers", "5, 17, 26, 41, 30, 44")
        st.caption("앞 번호일수록 유력한 순서로, 쉼표로 구분해 6개 입력하세요 (1~45).")
        lucky_input = st.text_input(
            "유력수 6개", value=_current_lucky, key="admin_lucky_numbers_input"
        )
        if st.button("유력수 저장", key="admin_lucky_numbers_submit"):
            nums = [x.strip() for x in lucky_input.split(",") if x.strip()]
            valid = (
                len(nums) == 6
                and all(n.isdigit() and 1 <= int(n) <= 45 for n in nums)
            )
            if not valid:
                st.error("숫자 6개를 쉼표로 구분해서, 1~45 범위로 입력해 주세요.")
            else:
                _ss("main_lucky_numbers", ", ".join(nums))
                st.success(f"메인화면 유력수를 [{', '.join(nums)}]로 저장했습니다 — 즉시 반영됩니다.")

    st.markdown("<h4 style='margin-top:40px; color:#FFB300; font-weight:700;'>🚦 동시접속 상한 (입장 제한)</h4>", unsafe_allow_html=True)
    with st.expander("이용자 폭증 시 신규 유입을 막는 상한값 설정"):
        import admission_control
        from app_settings import get_max_concurrent_sessions, set_max_concurrent_sessions

        _live_count, _live_cap = admission_control.get_live_status()
        st.caption(f"지금 활동 중(최근 {admission_control._HEARTBEAT_TTL_SECONDS}초 이내): **{_live_count}명** / 현재 상한 **{_live_cap}명**")
        st.caption("이미 입장한 사용자는 상한을 넘어도 절대 쫓아내지 않습니다 — 신규 유입만 막습니다. 값을 바꾸면 최대 30초 안에 반영됩니다.")

        _cur_cap = get_max_concurrent_sessions(default=admission_control.DEFAULT_MAX_CONCURRENT_SESSIONS)
        _new_cap = st.number_input(
            "동시접속 상한 (명)", min_value=1, max_value=100000, value=_cur_cap, step=10, key="admin_max_concurrent_input",
        )
        if st.button("저장", key="admin_max_concurrent_save"):
            set_max_concurrent_sessions(int(_new_cap))
            st.success(f"상한을 {int(_new_cap)}명으로 저장했습니다. 최대 30초 안에 반영됩니다.")
            st.rerun()

    st.markdown("<h4 style='margin-top:40px; color:#FFB300; font-weight:700;'>🔐 게스트 자동로그인 보안(UA 대조)</h4>", unsafe_allow_html=True)
    with st.expander("guest_id 링크공유 계정탈취 대응 — 코드 배포 없이 즉시 켜고 끌 수 있는 킬스위치"):
        from app_settings import get_auth_require_ua_match, set_auth_require_ua_match

        st.caption(
            "켜짐(기본): 로그인 링크를 남에게 공유해도 다른 기기(다른 User-Agent)에서는 "
            "자동로그인되지 않고 재인증을 요구합니다. 웹 자동로그인이 광범위하게 "
            "안 되는 등 문제가 생기면 여기서 즉시 꺼서 이전 동작으로 되돌릴 수 있습니다 "
            "(최대 30초 안에 반영)."
        )
        _ua_check_on = get_auth_require_ua_match(default=True)
        _new_ua_check_on = st.toggle("UA 대조 자동로그인 보호 사용", value=_ua_check_on, key="admin_auth_ua_toggle")
        if _new_ua_check_on != _ua_check_on:
            set_auth_require_ua_match(_new_ua_check_on)
            st.success("저장했습니다. 최대 30초 안에 반영됩니다.")
            st.rerun()

    st.markdown("<h4 style='margin-top:40px; color:#FFB300; font-weight:700;'>📊 회차별 구매 전환 현황</h4>", unsafe_allow_html=True)
    from marketing_db import get_draw_purchase_conversion_stats

    @st.cache_data(ttl=60, show_spinner=False)
    def _conv_stats_cached(limit: int):
        return get_draw_purchase_conversion_stats(limit=limit)

    _conv_stats = _conv_stats_cached(10)
    if not _conv_stats:
        st.caption("데이터가 없습니다.")
    else:
        _conv_df = pd.DataFrame(
            [
                {
                    "회차": s["draw_round"],
                    "추출수량": s["total_count"],
                    "구매전환": s["purchased_count"],
                    "전환율": (
                        f"{s['purchased_count'] / s['total_count'] * 100:.1f}%"
                        if s["total_count"]
                        else "0.0%"
                    ),
                }
                for s in _conv_stats
            ]
        )
        st.dataframe(_conv_df, use_container_width=True, hide_index=True)