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

USERS_DATA_ROOT = "data/users"
PREMIUM_SETTINGS_FILENAME = "premium_settings.pkl"
ADVANCED_FILTER_FILENAME = "saved_advanced_filter.csv"

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


def _prompt_user_email() -> None:
    """session_state에 이메일이 없으면 최상단에서 1회 입력받음."""
    if st.session_state.get("user_email"):
        return

    email_input = st.text_input(
        "설정을 저장/불러오려면 이메일을 입력하세요 (인증 없음, 식별용)",
        key="user_email_input",
    )
    if st.button("이메일 확인", key="user_email_submit"):
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
        color: #F87171;
        font-size: 13px;
        cursor: help;
        margin-left: 4px;
        font-weight: bold;
        opacity: 0.9;
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
        gap: 1.75rem !important;
    }
    div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] .af-col3-stack) > div[data-testid="column"] {
        padding: 0 10px !important;
        box-sizing: border-box !important;
        border-right: 1px solid rgba(255, 255, 255, 0.1) !important;
    }
    div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] .af-col3-stack) > div[data-testid="column"]:last-child {
        border-right: none !important;
    }

    /* K-503 — 3열 카드 세로 간격 확대 (1·2열 높이 균형, 추가만) */
    div[data-testid="column"]:has(.af-col3-stack) > div[data-testid="stVerticalBlock"] {
        gap: 22px !important;
    }

    /* K-538 — 프리미엄 3열 그리드 폰트 가독성 (상단 패턴 영역 전용, 추가만) */
    div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] .af-col3-stack) .premium-title {
        font-size: 19px !important;
    }
    div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] .af-col3-stack) div[data-testid="stCheckbox"] label,
    div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] .af-col3-stack) div[data-testid="stCheckbox"] [data-testid="stWidgetLabel"],
    div[data-testid="stHorizontalBlock"]:has(> div[data-testid="column"] .af-col3-stack) div[data-testid="stCheckbox"] [data-testid="stWidgetLabel"] p {
        font-size: 18px !important;
    }
    div[data-testid="column"]:has(.af-col3-stack) .af-table-header {
        font-size: 16px !important;
    }
    div[data-testid="column"]:has(.af-col3-stack) .af-table-label {
        font-size: 17px !important;
    }

    /* K-558 — Streamlit 네이티브 border=True 카드 그리드 강제 오버라이드 (추가만) */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 4px !important;
        border: 2px solid rgba(255, 255, 255, 0.15) !important;
        background: linear-gradient(135deg, #171730 0%, #0f0f1c 100%) !important;
        padding: 2px !important;
        margin-bottom: 16px !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] > div {
        border: none !important;
        padding: 16px !important;
    }
    div[data-testid="column"] > div[data-testid="stVerticalBlock"] {
        gap: 16px !important;
    }
    div[data-testid="column"]:nth-child(1) div[data-testid="stVerticalBlockBorderWrapper"]:nth-last-child(-n+2),
    div[data-testid="column"]:nth-child(2) div[data-testid="stVerticalBlockBorderWrapper"]:nth-last-child(-n+2) {
        border: 2px dashed rgba(52, 152, 219, 0.4) !important;
        min-height: 120px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }
    div[data-testid="stMarkdownContainer"] p strong,
    div[data-testid="stMarkdownContainer"] h3 {
        font-size: 19px !important;
        font-weight: 700 !important;
        color: #FFFFFF !important;
    }
    div[data-testid="stCheckbox"] label span {
        font-size: 18px !important;
        font-weight: 600 !important;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("<h2 class='af-page-title'>📊 <span>프리미엄 패턴 분석 세팅</span></h2>", unsafe_allow_html=True)

_hydrate_premium_settings_from_disk()
_hydrate_advanced_filter_from_disk()

col1, col2, col3 = st.columns(3, gap="large")

def draw_premium_pattern(col, title, tooltip, options, icon, accent="cyan"):
    with col.container(border=True):
        st.markdown(f'<div class="premium-title accent-{accent}">{icon} {title} <span class="tooltip-icon" title="{tooltip}">❓</span></div>', unsafe_allow_html=True)
        cc = st.columns(len(options))
        for i, opt in enumerate(options):
            cc[i].checkbox(opt, value=True, key=f"{title}_{opt}")

def draw_placeholder_card(col):
    with col.container(border=True):
        st.markdown('<div class="af-placeholder-body"><span>🔒 개발중</span></div>', unsafe_allow_html=True)

# ── 1열: 홀짝, 저고, 이월, 이웃 ──
draw_premium_pattern(col1, "홀짝 비율", "당첨번호 6개의 홀수와 짝수 출현 비율입니다.", ["6:0", "5:1", "4:2", "3:3", "2:4", "1:5", "0:6"], "☯️", "cyan")
draw_premium_pattern(col1, "저고 비율", "1~22(저) 번호와 23~45(고) 번호의 출현 비율입니다.", ["6:0", "5:1", "4:2", "3:3", "2:4", "1:5", "0:6"], "📉", "blue")
draw_premium_pattern(col1, "이월수", "직전 회차 당첨번호가 이번에 다시 등장하는 개수입니다.", ["0", "1", "2", "3", "4", "5", "6"], "🔄", "purple")
draw_premium_pattern(col1, "이웃수", "직전 회차 당첨번호와 1차이 나는 번호들의 출현 개수입니다.", ["0", "1", "2", "3", "4"], "👥", "rose")
draw_placeholder_card(col1)
draw_placeholder_card(col1)

# ── 2열: 쌍둥이, 쌍끝, 연속, 볼색상 ──
draw_premium_pattern(col2, "쌍둥이수", "11, 22, 33, 44 처럼 똑같은 숫자가 겹치는 번호의 개수입니다.", ["0", "1", "2", "3", "4"], "👯", "violet")
draw_premium_pattern(col2, "쌍끝수", "1의 자리가 동일한 번호들의 출현 쌍 개수입니다. (예: 12, 32)", ["0개", "1개", "2개", "3개"], "🎯", "teal")
draw_premium_pattern(col2, "연속번호", "1, 2, 3 처럼 연속되어 나타나는 번호의 개수입니다.", ["없음", "2연번", "3연번", "4연번"], "🔗", "amber")
draw_premium_pattern(col2, "볼 색상 수", "당첨번호 6개를 구성하는 볼 색깔의 종류 수입니다.", ["1", "2", "3", "4", "모든"], "🎨", "emerald")
draw_placeholder_card(col2)
draw_placeholder_card(col2)

# ── 3열: 소자배, 10단위, 핫존, 총합 ──
with col3:
    st.markdown('<div class="af-col3-stack" aria-hidden="true"></div>', unsafe_allow_html=True)
    with st.container(border=True, key="af_col3_soja"):
        st.markdown('<div class="premium-title accent-teal">🔢 소자배 패턴 <span class="tooltip-icon" title="소수: 2,3,5,7,11,13,17,19,23,29,31,37,41,43&#10;자연수(합성수): 1,4,8,10,14,16,20,22,25,26,28,32,34,35,38,40,44&#10;3배수: 3,6,9,12,15,18,21,24,27,30,33,36,39,42,45">❓</span></div>', unsafe_allow_html=True)

        header_cols = st.columns([2, 0.55, 0.55], gap="small")
        header_cols[0].markdown("<div class='af-table-header' style='text-align:left;'>구분</div>", unsafe_allow_html=True)
        header_cols[1].markdown("<div class='af-table-header'>최소</div>", unsafe_allow_html=True)
        header_cols[2].markdown("<div class='af-table-header'>최대</div>", unsafe_allow_html=True)

        for label, key_prefix in [("소수", "소수"), ("자연수(합성수)", "자연수"), ("3배수", "3배수")]:
            row_cols = st.columns([2, 0.55, 0.55], gap="small")
            row_cols[0].markdown(f"<div class='af-table-label'>{label}</div>", unsafe_allow_html=True)
            row_cols[1].number_input(f"{key_prefix}최소", 0, 6, 0, key=f"{key_prefix}_min", label_visibility="collapsed")
            row_cols[2].number_input(f"{key_prefix}최대", 0, 6, 6, key=f"{key_prefix}_max", label_visibility="collapsed")

    with st.container(border=True, key="af_col3_decade"):
        st.markdown('<div class="premium-title accent-violet">📏 10단위 출현 패턴 <span class="tooltip-icon" title="각 번호대별로 출현할 수 있는 최소/최대 공의 개수를 지정합니다.">❓</span></div>', unsafe_allow_html=True)

        header_cols = st.columns([2, 0.55, 0.55], gap="small")
        header_cols[0].markdown("<div class='af-table-header' style='text-align:left;'>구분</div>", unsafe_allow_html=True)
        header_cols[1].markdown("<div class='af-table-header'>최소</div>", unsafe_allow_html=True)
        header_cols[2].markdown("<div class='af-table-header'>최대</div>", unsafe_allow_html=True)

        for label, key_prefix in [("1~9", "1_9"), ("10~19", "10_19"), ("20~29", "20_29"), ("30~39", "30_39"), ("40~45", "40_45")]:
            row_cols = st.columns([2, 0.55, 0.55], gap="small")
            row_cols[0].markdown(f"<div class='af-table-label'>{label}</div>", unsafe_allow_html=True)
            row_cols[1].number_input(f"{key_prefix}최소", 0, 6, 0, key=f"{key_prefix}_min", label_visibility="collapsed")
            row_cols[2].number_input(f"{key_prefix}최대", 0, 6, 6, key=f"{key_prefix}_max", label_visibility="collapsed")

    with st.container(border=True, key="af_col3_hotzone"):
        st.markdown('<div class="premium-title accent-amber">🚀 시작/끝번호 핫존 <span class="tooltip-icon" title="첫 번째 공과 마지막 공의 번호 범위입니다.">❓</span></div>', unsafe_allow_html=True)
        rc1, rc2 = st.columns(2)
        rc1.number_input("시작(1~23)", 1, 23, 1, key="시작번호")
        rc2.number_input("끝(28~45)", 28, 45, 45, key="끝번호")

    with st.container(border=True, key="af_col3_total"):
        st.markdown('<div class="premium-title accent-indigo">⚖️ 당첨번호 총합 <span class="tooltip-icon" title="당첨번호 6개를 모두 더한 값의 허용 범위입니다.">❓</span></div>', unsafe_allow_html=True)
        rc3, rc4 = st.columns(2)
        rc3.number_input("최소 총합", 70, 205, 70, key="최소총합")
        rc4.number_input("최대 총합", 70, 205, 205, key="최대총합")

_sync_settings_saved_state()

st.markdown("""
<style>
    /* 세팅완료 저장 버튼 — late inject (stElementContainer 형제 DOM, save_settings_btn 전용) */
    div[data-testid="stElementContainer"]:has(.af-save-settings-btn-marker) + div[data-testid="stElementContainer"] div[data-testid="stButton"] {
        width: 100% !important;
        max-width: 100% !important;
    }
    div[data-testid="stElementContainer"]:has(.af-save-settings-btn-marker) + div[data-testid="stElementContainer"] div[data-testid="stButton"] > button,
    div[data-testid="stElementContainer"]:has(.af-save-settings-btn-marker) + div[data-testid="stElementContainer"] div[data-testid="stButton"] > button[data-testid="stBaseButton-secondary"],
    div[data-testid="stElementContainer"]:has(.af-save-settings-btn-marker) + div[data-testid="stElementContainer"] div[data-testid="stButton"] > button[kind="secondary"] {
        width: 100% !important;
        background: linear-gradient(90deg, #0ea5e9, #2563eb, #1d4ed8) !important;
        color: #FFFFFF !important;
        font-size: 18px !important;
        font-weight: 700 !important;
        border: 1px solid rgba(125, 211, 252, 0.78) !important;
        border-radius: 10px !important;
        padding: 0.7rem 1.15rem !important;
        box-shadow:
            0 0 20px rgba(14, 165, 233, 0.42) !important,
            0 4px 16px rgba(37, 99, 235, 0.34) !important,
            inset 0 1px 0 rgba(255, 255, 255, 0.24) !important;
        text-shadow: 0 1px 3px rgba(0, 0, 0, 0.55) !important;
        transition: transform 0.15s ease, box-shadow 0.15s ease !important;
    }
    div[data-testid="stElementContainer"]:has(.af-save-settings-btn-marker) + div[data-testid="stElementContainer"] div[data-testid="stButton"] > button:hover,
    div[data-testid="stElementContainer"]:has(.af-save-settings-btn-marker) + div[data-testid="stElementContainer"] div[data-testid="stButton"] > button[data-testid="stBaseButton-secondary"]:hover,
    div[data-testid="stElementContainer"]:has(.af-save-settings-btn-marker) + div[data-testid="stElementContainer"] div[data-testid="stButton"] > button[kind="secondary"]:hover {
        transform: translateY(-1px) !important;
        color: #FFFFFF !important;
        border-color: rgba(186, 230, 253, 0.95) !important;
        box-shadow:
            0 0 28px rgba(56, 189, 248, 0.52) !important,
            0 6px 18px rgba(37, 99, 235, 0.4) !important,
            inset 0 1px 0 rgba(255, 255, 255, 0.28) !important;
    }
</style>
""", unsafe_allow_html=True)

_save_left, _save_mid, _save_right = st.columns([0.125, 0.75, 0.125])
with _save_mid:
    st.markdown('<div class="af-save-settings-btn-marker"></div>', unsafe_allow_html=True)
    if st.button("세팅완료 저장", use_container_width=True, key="save_settings_btn"):
        snapshot = _collect_premium_settings()
        st.session_state.saved_settings = snapshot
        st.session_state.settings_saved = True
        _save_premium_settings_to_disk(snapshot)
        st.rerun()

# admin_dashboard.py style_dataframe 재사용
def style_dataframe(df):
    return df.style.set_properties(**{
        'background-color': '#1E293B',
        'color': '#F8FAFC',
        'border-color': '#334155',
        'font-weight': '500',
        'font-size': '14px'
    })


def _normalize_combo_df(df: pd.DataFrame) -> pd.DataFrame:
    """결과표 컬럼명을 번호1~번호6 기본 텍스트로 정제."""
    out = df.copy()
    out.columns = [f"번호{i + 1}" for i in range(len(out.columns))]
    return out


def _combo_column_config(df):
    cfg = {}
    for i, col in enumerate(df.columns):
        label = f"번호{i + 1}" if str(col).strip().startswith("번호") else str(col).strip()
        cfg[col] = st.column_config.NumberColumn(
            label,
            width="small",
            format="%d",
            alignment="center",
        )
    return cfg


def _filter_column_config(df):
    cfg = {}
    for col in df.columns:
        name = str(col)
        if name in ("최소", "최대"):
            cfg[col] = st.column_config.NumberColumn(
                name, width="small", format="%d", alignment="center", disabled=False
            )
        elif name == "패턴이름":
            cfg[col] = st.column_config.TextColumn(
                name, width="medium", alignment="center", disabled=False
            )
        elif name == "해당숫자":
            cfg[col] = st.column_config.TextColumn(
                name, width="large", alignment="center", disabled=False
            )
        else:
            cfg[col] = st.column_config.TextColumn(
                name, width="medium", alignment="center", disabled=False
            )
    return cfg

# ── 하단 결과표 영역 (상단 3열 패턴 설정과 분리) ──
with st.container(key="af_bottom_center"):
    st.markdown('<div class="af-results-zone" aria-hidden="true"></div>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="af-step1-run-wrap" aria-hidden="true"></div>', unsafe_allow_html=True)
    if not st.session_state.get("settings_saved"):
        warning_html = """
        <div style="
            background-color: rgba(255, 171, 0, 0.15);
            border: 1px solid rgba(255, 171, 0, 0.4);
            padding: 15px;
            border-radius: 8px;
            color: #FFFFFF !important;
            font-size: 16px !important;
            font-weight: 700 !important;
            text-align: center;
            margin-bottom: 15px;
        ">
            ⏸️ 패턴 세팅 후 상단 [세팅완료 저장]을 눌러야 1단계 연산이 가능합니다.
        </div>
        """
        st.markdown(warning_html, unsafe_allow_html=True)
    if st.button("⚡ [1단계 공정] 상단 프리미엄 패턴 전수 연산 실행", use_container_width=True, type="primary"):
        if not st.session_state.get("settings_saved"):
            st.warning("⚠️ 세팅이 저장되지 않았거나 저장 후 값이 변경되었습니다. [세팅완료 저장]을 다시 눌러주세요.")
        else:
            st.session_state["trigger_step1"] = True

    if st.session_state.get("trigger_step1") and st.session_state.get("settings_saved"):
        try:
            _run_step1_with_saved_settings()
        except Exception as e:
            st.error(f"1단계 연산 중 오류가 발생했습니다: {e}")
        finally:
            st.session_state["trigger_step1"] = False

    if os.path.exists(COMBO_STEP1_FILE) and not st.session_state.get("trigger_step1"):
        df_step1_check = _normalize_combo_df(pd.read_csv(COMBO_STEP1_FILE))
        st.markdown('<div class="af-step1-info-marker" aria-hidden="true"></div>', unsafe_allow_html=True)
        st.info(f"📋 1단계 패턴 통과 조합: **{len(df_step1_check):,}**개")
        if len(df_step1_check) > 0:
            st.data_editor(
                df_step1_check.head(15),
                column_config=_combo_column_config(df_step1_check),
                use_container_width=False,
                hide_index=True,
                key="af_step1_combo_editor",
            )

    # ==========================================================
    # ==========================================================
    st.markdown("---")
    st.markdown("<h3 class='af-section-title'>🛠️ 나만의 고급필터 (2단계 전용)</h3>", unsafe_allow_html=True)

    # K-295 엑셀 양식 업로드
    uploaded_file = st.file_uploader("K-295 엑셀 파일 업로드", type=["xlsx"])

    df_filter = None

    if uploaded_file is not None:
        upload_key = (uploaded_file.name, uploaded_file.size)
        if st.session_state.get("_af_upload_key") != upload_key:
            try:
                df_filter = _parse_k295_excel(uploaded_file)
                _save_advanced_filter_to_disk(df_filter)
                st.session_state["af_advanced_filter_df"] = df_filter
                st.session_state["_af_upload_key"] = upload_key
                if "af_k295_filter_editor" in st.session_state:
                    del st.session_state["af_k295_filter_editor"]
            except Exception as e:
                st.error(f"엑셀 파일을 읽는 중 오류가 발생했습니다: {e}")
        else:
            df_filter = st.session_state.get("af_advanced_filter_df")
    else:
        st.session_state.pop("_af_upload_key", None)
        df_filter = st.session_state.get("af_advanced_filter_df")
        if df_filter is None:
            df_filter = _load_advanced_filter_from_disk()
            if df_filter is not None:
                st.session_state["af_advanced_filter_df"] = df_filter

    if df_filter is not None and not df_filter.empty:
        st.markdown('<div class="af-filter-tip-marker" aria-hidden="true"></div>', unsafe_allow_html=True)
        st.info("💡 아래 표의 셀을 더블클릭하여 '패턴이름', '해당숫자', '최소', '최대' 값을 직접 수정할 수 있습니다.")

        st.markdown('<div class="af-k295-filter-table-marker" aria-hidden="true"></div>', unsafe_allow_html=True)
        edited_df = st.data_editor(
            df_filter,
            column_config=_filter_column_config(df_filter),
            use_container_width=False,
            num_rows="dynamic",
            hide_index=True,
            key="af_k295_filter_editor",
        )
        _save_advanced_filter_to_disk(edited_df)
        st.session_state["af_advanced_filter_df"] = edited_df

        if st.button("🚀 2단계: 1단계 결과물에 고급필터 적용하기"):
            if not st.session_state.get("settings_saved"):
                st.warning("⚠️ 세팅이 저장되지 않았거나 저장 후 값이 변경되었습니다. [세팅완료 저장]을 다시 눌러주세요.")
            else:
                try:
                    if not os.path.exists(COMBO_STEP1_FILE):
                        raise FileNotFoundError(COMBO_STEP1_FILE)

                    # 1단계 필터링 통과 조합만 입력으로 사용 (전체 풀 사용 금지)
                    step1_df = _normalize_combo_df(pd.read_csv(COMBO_STEP1_FILE))
                    step1_df = step1_df.apply(pd.to_numeric, errors="coerce").fillna(0).astype(int)

                    rules = []
                    for _, row in edited_df.iterrows():
                        clean_str = str(row["해당숫자"]).replace(",", " ")
                        nums = set(map(int, clean_str.split()))
                        rules.append({"targets": nums, "min": int(row["최소"]), "max": int(row["최대"])})

                    with st.spinner("2단계 고급필터 연산 중..."):
                        final_df = lotto_engine.run_step2_filtering(step1_df, rules)

                    if len(final_df) > 0:
                        final_count = len(final_df)
                        success_html = f"""
                        <div style="
                            background-color: rgba(46, 204, 113, 0.15);
                            border: 1px solid rgba(46, 204, 113, 0.4);
                            padding: 15px;
                            border-radius: 8px;
                            color: #FFFFFF !important;
                            font-size: 18px !important;
                            font-weight: 700 !important;
                            text-align: center;
                            margin-top: 15px;
                            margin-bottom: 15px;
                        ">
                            🎉 최종 조합 {final_count:,}개 추출 완료!
                        </div>
                        """
                        st.markdown(success_html, unsafe_allow_html=True)
                        st.data_editor(
                            _normalize_combo_df(final_df),
                            column_config=_combo_column_config(final_df),
                            use_container_width=False,
                            hide_index=True,
                            key="af_final_combo_editor",
                        )

                        final_df.to_csv("user_final_combinations.csv", index=False)

                        csv_data = final_df.to_csv(index=False, encoding="utf-8-sig")

                        st.markdown("### 💾 결과물 저장하기")
                        st.download_button(
                            label="📥 최종 조합 결과 PC에 저장하기 (CSV)",
                            data=csv_data,
                            file_name="최종_고급필터_조합.csv",
                            mime="text/csv",
                        )
                    else:
                        st.warning("⚠️ 산출된 조합이 0개입니다. 엑셀의 최소/최대 조건들이 서로 충돌하지 않는지 확인해주세요.")

                except FileNotFoundError:
                    st.error(f"🚨 1단계 결과 파일('{COMBO_STEP1_FILE}')을 찾을 수 없습니다. 1단계 연산을 먼저 실행해주세요.")