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

if 'trigger_step1' not in st.session_state: st.session_state['trigger_step1'] = False
if 'trigger_step2' not in st.session_state: st.session_state['trigger_step2'] = False


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
        max-width: 95% !important;
        padding-top: 1.1rem !important;
        padding-bottom: 2.1rem !important;
    }

    /* ── Layout density (column / block gaps) ── */
    div[data-testid="stVerticalBlock"] {
        gap: 0.45rem !important;
    }
    div[data-testid="stHorizontalBlock"] {
        gap: 0.55rem !important;
        align-items: stretch !important;
    }
    div[data-testid="column"] {
        gap: 0.35rem !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        margin-bottom: 0.15rem !important;
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

    /* ── Card containers ── */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: linear-gradient(145deg, var(--af-bg-card) 0%, var(--af-bg-card-alt) 55%, #12122a 100%) !important;
        border-radius: 12px !important;
        padding: 12px 14px !important;
        border: 1px solid rgba(100, 116, 139, 0.25) !important;
        box-shadow:
            0 8px 24px rgba(0, 0, 0, 0.45),
            0 2px 8px rgba(0, 0, 0, 0.3),
            inset 0 1px 0 rgba(255, 255, 255, 0.04) !important;
        transition: box-shadow 0.2s ease, border-color 0.2s ease;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        box-shadow:
            0 12px 32px rgba(0, 0, 0, 0.5),
            0 4px 12px rgba(0, 0, 0, 0.35),
            inset 0 1px 0 rgba(255, 255, 255, 0.06) !important;
    }

    .premium-card-marker { display: none; }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.accent-cyan) {
        border-color: rgba(6, 182, 212, 0.45) !important;
        box-shadow: 0 8px 24px rgba(0,0,0,0.45), 0 0 0 1px rgba(6,182,212,0.12), 0 0 20px rgba(6,182,212,0.08) !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.accent-violet) {
        border-color: rgba(139, 92, 246, 0.45) !important;
        box-shadow: 0 8px 24px rgba(0,0,0,0.45), 0 0 0 1px rgba(139,92,246,0.12), 0 0 20px rgba(139,92,246,0.08) !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.accent-blue) {
        border-color: rgba(59, 130, 246, 0.45) !important;
        box-shadow: 0 8px 24px rgba(0,0,0,0.45), 0 0 0 1px rgba(59,130,246,0.12), 0 0 20px rgba(59,130,246,0.08) !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.accent-teal) {
        border-color: rgba(20, 184, 166, 0.45) !important;
        box-shadow: 0 8px 24px rgba(0,0,0,0.45), 0 0 0 1px rgba(20,184,166,0.12), 0 0 20px rgba(20,184,166,0.08) !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.accent-purple) {
        border-color: rgba(168, 85, 247, 0.45) !important;
        box-shadow: 0 8px 24px rgba(0,0,0,0.45), 0 0 0 1px rgba(168,85,247,0.12), 0 0 20px rgba(168,85,247,0.08) !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.accent-amber) {
        border-color: rgba(245, 158, 11, 0.45) !important;
        box-shadow: 0 8px 24px rgba(0,0,0,0.45), 0 0 0 1px rgba(245,158,11,0.12), 0 0 20px rgba(245,158,11,0.08) !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.accent-rose) {
        border-color: rgba(244, 63, 94, 0.45) !important;
        box-shadow: 0 8px 24px rgba(0,0,0,0.45), 0 0 0 1px rgba(244,63,94,0.12), 0 0 20px rgba(244,63,94,0.08) !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.accent-emerald) {
        border-color: rgba(16, 185, 129, 0.45) !important;
        box-shadow: 0 8px 24px rgba(0,0,0,0.45), 0 0 0 1px rgba(16,185,129,0.12), 0 0 20px rgba(16,185,129,0.08) !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.accent-indigo) {
        border-color: rgba(99, 102, 241, 0.45) !important;
        box-shadow: 0 8px 24px rgba(0,0,0,0.45), 0 0 0 1px rgba(99,102,241,0.12), 0 0 20px rgba(99,102,241,0.08) !important;
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
        overflow: hidden !important;
        text-overflow: ellipsis !important;
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

    /* ── Primary execute button ── */
    div[data-testid="stButton"] > button[kind="primary"],
    div[data-testid="stButton"] > button[data-testid="stBaseButton-primary"] {
        background: linear-gradient(135deg, #6366F1 0%, #8B5CF6 45%, #A855F7 100%) !important;
        color: #FFFFFF !important;
        font-weight: 800 !important;
        font-size: 16px !important;
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

    /* ── Divider ── */
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

    /* ── Dataframe / editor ── */
    [data-testid="stDataFrame"], [data-testid="stDataEditor"] {
        border: 1px solid rgba(100, 116, 139, 0.25);
        border-radius: 10px;
        overflow: hidden;
    }

    label[data-testid="stWidgetLabel"] p {
        color: var(--af-text-muted) !important;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("<h2 class='af-page-title'>📊 <span>프리미엄 패턴 분석 세팅</span></h2>", unsafe_allow_html=True)

col_left, col_right = st.columns([6, 4])

def draw_premium_pattern(col, title, tooltip, options, icon, accent="cyan"):
    with col.container(border=True):
        st.markdown(f'<div class="premium-card-marker accent-{accent}"></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="premium-title accent-{accent}">{icon} {title} <span class="tooltip-icon" title="{tooltip}">❓</span></div>', unsafe_allow_html=True)
        cc = st.columns(len(options))
        for i, opt in enumerate(options):
            cc[i].checkbox(opt, value=True, key=f"{title}_{opt}")

with col_left:
    r1_c1, r1_c2 = st.columns(2)
    draw_premium_pattern(r1_c1, "홀짝 비율", "당첨번호 6개의 홀수와 짝수 출현 비율입니다.", ["6:0", "5:1", "4:2", "3:3", "2:4", "1:5", "0:6"], "☯️", "cyan")
    draw_premium_pattern(r1_c2, "쌍둥이수", "11, 22, 33, 44 처럼 똑같은 숫자가 겹치는 번호의 개수입니다.", ["0", "1", "2", "3", "4"], "👯", "violet")

    r2_c1, r2_c2 = st.columns(2)
    draw_premium_pattern(r2_c1, "저고 비율", "1~22(저) 번호와 23~45(고) 번호의 출현 비율입니다.", ["6:0", "5:1", "4:2", "3:3", "2:4", "1:5", "0:6"], "📉", "blue")
    draw_premium_pattern(r2_c2, "쌍끝수", "1의 자리가 동일한 번호들의 출현 쌍 개수입니다. (예: 12, 32)", ["0개", "1개", "2개", "3개"], "🎯", "teal")

    r3_c1, r3_c2 = st.columns(2)
    draw_premium_pattern(r3_c1, "이월수", "직전 회차 당첨번호가 이번에 다시 등장하는 개수입니다.", ["0", "1", "2", "3", "4", "5", "6"], "🔄", "purple")
    draw_premium_pattern(r3_c2, "연속번호", "1, 2, 3 처럼 연속되어 나타나는 번호의 개수입니다.", ["없음", "2연번", "3연번", "4연번"], "🔗", "amber")

    r4_c1, r4_c2 = st.columns(2)
    draw_premium_pattern(r4_c1, "이웃수", "직전 회차 당첨번호와 1차이 나는 번호들의 출현 개수입니다.", ["0", "1", "2", "3", "4"], "👥", "rose")
    draw_premium_pattern(r4_c2, "볼 색상 수", "당첨번호 6개를 구성하는 볼 색깔의 종류 수입니다.", ["1", "2", "3", "4", "모든"], "🎨", "emerald")

    r5_c1, r5_c2 = st.columns(2)
    with r5_c1.container(border=True):
        st.markdown('<div class="premium-card-marker accent-amber"></div>', unsafe_allow_html=True)
        st.markdown('<div class="premium-title accent-amber">🚀 시작/끝번호 핫존 <span class="tooltip-icon" title="첫 번째 공과 마지막 공의 번호 범위입니다.">❓</span></div>', unsafe_allow_html=True)
        rc1, rc2 = st.columns(2)
        rc1.number_input("시작(1~23)", 1, 23, 1, key="시작번호")
        rc2.number_input("끝(28~45)", 28, 45, 45, key="끝번호")
    
    with r5_c2.container(border=True):
        st.markdown('<div class="premium-card-marker accent-indigo"></div>', unsafe_allow_html=True)
        st.markdown('<div class="premium-title accent-indigo">⚖️ 당첨번호 총합 <span class="tooltip-icon" title="당첨번호 6개를 모두 더한 값의 허용 범위입니다.">❓</span></div>', unsafe_allow_html=True)
        rc3, rc4 = st.columns(2)
        rc3.number_input("최소 총합", 70, 205, 70, key="최소총합")
        rc4.number_input("최대 총합", 70, 205, 205, key="최대총합")

with col_right:
    # 💡 우측 소자배 패널 (레이아웃 밀착형)
    with st.container(border=True):
        st.markdown('<div class="premium-card-marker accent-teal"></div>', unsafe_allow_html=True)
        st.markdown('<div class="premium-title accent-teal">🔢 소자배 패턴 <span class="tooltip-icon" title="소수: 2,3,5,7,11,13,17,19,23,29,31,37,41,43&#10;자연수(합성수): 1,4,8,10,14,16,20,22,25,26,28,32,34,35,38,40,44&#10;3배수: 3,6,9,12,15,18,21,24,27,30,33,36,39,42,45">❓</span></div>', unsafe_allow_html=True)
        
        header_cols = st.columns([1.5, 1, 1], gap="small")
        header_cols[0].markdown("<div class='af-table-header' style='text-align:left;'>구분</div>", unsafe_allow_html=True)
        header_cols[1].markdown("<div class='af-table-header'>최소</div>", unsafe_allow_html=True)
        header_cols[2].markdown("<div class='af-table-header'>최대</div>", unsafe_allow_html=True)
        
        for label, key_prefix in [("소수", "소수"), ("자연수(합성수)", "자연수"), ("3배수", "3배수")]:
            row_cols = st.columns([1.5, 1, 1], gap="small")
            row_cols[0].markdown(f"<div class='af-table-label'>{label}</div>", unsafe_allow_html=True)
            row_cols[1].number_input(f"{key_prefix}최소", 0, 6, 0, key=f"{key_prefix}_min", label_visibility="collapsed")
            row_cols[2].number_input(f"{key_prefix}최대", 0, 6, 6, key=f"{key_prefix}_max", label_visibility="collapsed")

    # 💡 우측 10단위 패널 (레이아웃 밀착형)
    with st.container(border=True):
        st.markdown('<div class="premium-card-marker accent-violet"></div>', unsafe_allow_html=True)
        st.markdown('<div class="premium-title accent-violet">📏 10단위 출현 패턴 <span class="tooltip-icon" title="각 번호대별로 출현할 수 있는 최소/최대 공의 개수를 지정합니다.">❓</span></div>', unsafe_allow_html=True)
        
        header_cols = st.columns([1.5, 1, 1], gap="small")
        header_cols[0].markdown("<div class='af-table-header' style='text-align:left;'>구분</div>", unsafe_allow_html=True)
        header_cols[1].markdown("<div class='af-table-header'>최소</div>", unsafe_allow_html=True)
        header_cols[2].markdown("<div class='af-table-header'>최대</div>", unsafe_allow_html=True)
        
        for label, key_prefix in [("1~9", "1_9"), ("10~19", "10_19"), ("20~29", "20_29"), ("30~39", "30_39"), ("40~45", "40_45")]:
            row_cols = st.columns([1.5, 1, 1], gap="small")
            row_cols[0].markdown(f"<div class='af-table-label'>{label}</div>", unsafe_allow_html=True)
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
st.markdown("<h3 class='af-section-title'>🛠️ 나만의 고급필터 (2단계 전용)</h3>", unsafe_allow_html=True)

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