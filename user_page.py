
import streamlit as st
import streamlit.components.v1 as components
import base64
import os
import pandas as pd

# 🚨 [여기에 추가!] 관리자 모드가 켜지면 대시보드 파일로 즉시 강제 점프!
if st.session_state.get("go_to_admin", False):
    st.session_state.go_to_admin = False # 깃발 내리기
    st.switch_page("admin_dashboard.py")  # 👈 이 한 줄이 핵심 치트키입니다.

# 2. ✅ 관리자 모드일 때만 나타나는 사이드바 메뉴
if st.session_state.get("is_admin", False):
    with st.sidebar:
        st.markdown("## ⚙️ 관리자 제어 센터")
        if st.button("📊 대시보드로 바로가기", key="admin_sidebar_dash_6n36s5"):
            st.switch_page("admin_dashboard.py")

# ==========================================
# 1. 페이지 초기 설정 및 상태 관리
# ==========================================
st.set_page_config(page_title="로\u200b또신령", page_icon="K-325.jpg", layout="centered", initial_sidebar_state="collapsed")

from wallet_db import init_wallet_tables
from zero_phone_db import init_zero_phone_tables
from auth_providers import handle_oauth_callback

init_wallet_tables()
init_zero_phone_tables()
if handle_oauth_callback():
    st.rerun()

current_page = st.query_params.get("page", "main")

if current_page in ("main", "thunder", "auto", "stats", "birthday", "advanced"):
    from wallet_ui import render_wallet_bar

    render_wallet_bar()

# ===============================================================================
# ⚠️⚠️⚠️ [관리자 필수 확인] 매주 이 숫자 6개를 직접 수정하세요 ⚠️⚠️⚠️
# 앞 번호일수록 유력한 순서로 입력 (예: 44가 가장 유력, 7이 가장 약함)
# ⚠️⚠️⚠️ 다른 코드는 건드리지 말고 이 줄의 숫자만 바꾸세요 ⚠️⚠️⚠️
lucky_display = [39, 11, 44, 10, 23, 5]
# ===============================================================================

def get_image_base64(file_path):
    if os.path.exists(file_path):
        with open(file_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    return ""

icon_base64 = get_image_base64("K-325.jpg")


# ==========================================
# 📺 화면 1: 메인 페이지 (Main View) - 🎨 모바일 앱 고급 UI 적용 완료
# ==========================================
if current_page == "main":
    st.markdown("""
    <style>
        .stApp { background-color: #12182b; color: white; }
        .block-container { padding-top: 5px !important; padding-bottom: 0px !important; padding-left: 12px !important; padding-right: 12px !important; max-width: 600px; }
        section[data-testid="stSidebar"] { display: none; }
        header[data-testid="stHeader"] { display: none; }

        div[data-columns="true"] {
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            align-items: center !important;
            gap: 6px !important;
            width: 100% !important;
        }
        div[data-testid="stColumn"] { padding: 0px !important; margin: 0px !important; }

        div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) {
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            align-items: center !important;
            justify-content: space-between !important;
            gap: 6px !important;
            width: 100% !important;
            background: linear-gradient(145deg, #1c2645, #12182b) !important;
            border-radius: 14px !important;
            padding: 6px 10px !important;
            border: 1px solid #2a3a60 !important;
            box-shadow: 0 4px 8px rgba(0,0,0,0.4) !important;
            min-height: 44px !important;
            box-sizing: border-box !important;
        }
        div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) > div[data-testid="stColumn"]:nth-child(1) {
            flex: 1 1 0 !important;
            min-width: 0 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: flex-start !important;
        }
        div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) > div[data-testid="stColumn"]:nth-child(2) {
            flex: 1 1 0 !important;
            min-width: 0 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }
        div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) > div[data-testid="stColumn"]:nth-child(3) {
            flex: 1 1 0 !important;
            min-width: 0 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: flex-end !important;
        }

        div[data-testid="stPopover"] {
            width: auto !important;
            min-width: 120px !important;
        }
        .stApp div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) div[data-testid="stPopover"] button,
        .stApp div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) div[data-testid="stPopover"] button[data-testid="stBaseButton-secondary"],
        .stApp div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) div[data-testid="stPopover"] button[data-testid="baseButton-secondary"],
        .stApp div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) div[data-testid="stPopover"] button[kind="secondary"],
        .stApp div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) div[data-testid="stButton"] > button {
            background: linear-gradient(145deg, #1e88e5, #1565c0) !important;
            background-color: #1976d2 !important;
            background-image: linear-gradient(145deg, #1e88e5, #1565c0) !important;
            color: #ffffff !important;
            border: 1px solid #0d47a1 !important;
            border-color: #0d47a1 !important;
            border-radius: 10px !important;
            font-size: 11px !important;
            font-weight: 800 !important;
            line-height: 1.2 !important;
            letter-spacing: -0.1px !important;
            padding: 9px 14px !important;
            width: auto !important;
            min-width: 120px !important;
            height: 40px !important;
            min-height: 40px !important;
            box-shadow: 0 3px 6px rgba(0,0,0,0.35) !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            overflow: visible !important;
            white-space: nowrap !important;
            flex-shrink: 0 !important;
            -webkit-font-smoothing: antialiased !important;
            text-rendering: optimizeLegibility !important;
        }
        .stApp div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) div[data-testid="stPopover"] button *,
        .stApp div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) div[data-testid="stPopover"] button p,
        .stApp div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) div[data-testid="stPopover"] button span,
        .stApp div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) div[data-testid="stPopover"] button div,
        .stApp div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) div[data-testid="stButton"] > button * {
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
            background: transparent !important;
            background-color: transparent !important;
        }
        /* 팝업: body 포털 기준 ( .stApp 바깥 렌더링 대응 ) */
        html body div[data-baseweb="popover"],
        body > div[data-baseweb="popover"] {
            z-index: 9999 !important;
            position: fixed !important;
            isolation: isolate !important;
        }
        html body [data-testid="stPopoverBody"],
        body [data-testid="stPopoverBody"] {
            background-color: #1a2542 !important;
            background: #1a2542 !important;
            color: #ffffff !important;
            border: 1px solid #f9a825 !important;
            border-radius: 12px !important;
            min-width: 240px !important;
            padding: 14px 16px !important;
            box-sizing: border-box !important;
            opacity: 1 !important;
            visibility: visible !important;
            z-index: 9999 !important;
            position: fixed !important;
            isolation: isolate !important;
            pointer-events: auto !important;
        }
        html body [data-testid="stPopoverBody"] *,
        html body [data-testid="stPopoverBody"] p,
        html body [data-testid="stPopoverBody"] h1,
        html body [data-testid="stPopoverBody"] h2,
        html body [data-testid="stPopoverBody"] h3,
        html body [data-testid="stPopoverBody"] div[data-testid="stMarkdownContainer"],
        html body [data-testid="stPopoverBody"] div[data-testid="element-container"],
        html body [data-testid="stPopoverBody"] div[data-testid="stMarkdownContainer"] * {
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
            background-color: transparent !important;
            background: transparent !important;
            line-height: 1.6 !important;
            white-space: normal !important;
            word-break: keep-all !important;
            font-size: 14px !important;
            font-weight: 600 !important;
            -webkit-font-smoothing: antialiased !important;
            opacity: 1 !important;
            visibility: visible !important;
        }
        html body [data-testid="stPopoverBody"] h3 {
            font-size: 16px !important;
            font-weight: 800 !important;
            margin-bottom: 8px !important;
        }
    </style>
    """, unsafe_allow_html=True)

    # 엑셀에서 데이터 가져오기
    try:
        df = pd.read_excel("로또최근당첨내역.xlsb", engine='pyxlsb', header=None)
        row = df.iloc[4].tolist() 
        draw_no = str(row[1]).replace(".0", "") + "회" 
        numbers = sorted([int(x) for x in row[3:9]])
        import re
        bonus_val = int(re.sub(r'[^0-9]', '', str(row[9])))
    except Exception as e:
        draw_no = "오류"
        numbers = [3, 8, 9, 22, 28, 42]
        bonus_val = 45

    # 상단 로고 + 회전 볼 오버레이

    def get_ball_color(n):
        if 1 <= n <= 10: return "#f9a825"
        if 11 <= n <= 20: return "#1976d2"
        if 21 <= n <= 30: return "#e53935"
        if 31 <= n <= 40: return "#757575"
        return "#388e3c"

    balls_css = ""
    for i, num in enumerate(lucky_display):
        angle = i * 30
        color = get_ball_color(num)
        balls_css += f"""
        .orbit-ball-{i} {{
            position: absolute; width: 30px; height: 30px; border-radius: 50%;
            background: radial-gradient(circle at 35% 35%, {color}, #000);
            display: flex; align-items: center; justify-content: center;
            color: white; font-weight: 900; font-size: 15px;
            text-shadow: 1px 1px 2px rgba(0,0,0,0.8);
            box-shadow: 2px 3px 5px rgba(0,0,0,0.6), inset 2px 2px 4px rgba(255,255,255,0.4);
            top: 50%; left: 50%;
            margin-top: -11px; margin-left: -11px;
            animation: orbit{i} 6s linear infinite;
        }}
        @keyframes orbit{i} {{
            from {{ transform: rotate({angle}deg) translateX(82px) rotate(-{angle}deg); }}
            to {{ transform: rotate({angle + 360}deg) translateX(82px) rotate(-{angle + 360}deg); }}
        }}
        """


    st.markdown(f"""
    <style>
        @keyframes orbitSpin {{
            0% {{ transform: rotate({0}deg) translateY(-52px) rotate(-{0}deg); opacity: 0.7; }}
            50% {{ opacity: 1; transform: rotate(180deg) translateY(-52px) rotate(-180deg); }}
            100% {{ transform: rotate(360deg) translateY(-52px) rotate(-360deg); opacity: 0.7; }}
        }}
        @keyframes glowPulse {{
            0%, 100% {{ box-shadow: 0 0 15px rgba(255,179,0,0.8), 0 0 30px rgba(255,179,0,0.4); }}
            50% {{ box-shadow: 0 0 25px rgba(255,179,0,1), 0 0 50px rgba(255,179,0,0.6); }}
        }}
        .logo-wrapper {{
            position: relative; width: 175px; height: 175px; margin: 0 auto;
            z-index: 1;
        }}
        /* HERO_BRAND_ANIM: butterfly-fly — 롤백: user_page.py.bak-hero-spirit-mirage 복사 */
        .hero-with-brand {{
            position: relative;
            text-align: center;
            min-height: 198px;
            padding: 16px 0 20px 0;
            margin-top: -5px;
            margin-left: auto;
            margin-right: auto;
            max-width: 360px;
            overflow: hidden;
            box-sizing: border-box;
        }}
        .app-name-fly {{
            position: absolute;
            left: 50%;
            top: 30px;
            width: max-content;
            margin: 0;
            padding: 0;
            z-index: 4;
            pointer-events: none;
            font-size: 26px;
            font-weight: 800;
            line-height: 1;
            letter-spacing: 0.14em;
            white-space: nowrap;
            display: flex;
            flex-direction: row;
            align-items: center;
            gap: 5px;
            will-change: transform, opacity, filter;
            animation: spiritButterflyPath 20s ease-in-out infinite;
        }}
        .app-name-fly span {{
            display: inline-block;
            transform-origin: center center;
            opacity: 0;
            background: linear-gradient(180deg, rgba(255,255,255,0.45) 0%, rgba(255,255,255,0.92) 42%, rgba(200,225,255,0.85) 58%, rgba(255,255,255,0.4) 100%);
            background-size: 100% 220%;
            -webkit-background-clip: text;
            background-clip: text;
            -webkit-text-fill-color: transparent;
            animation: spiritCharShimmer 3.6s ease-in-out infinite,
                       spiritCharCycle 20s ease-in-out infinite,
                       spiritWingFlutter 1.1s ease-in-out infinite;
        }}
        .app-name-fly span:nth-child(1) {{ animation-delay: 0s, 0s, 0s; }}
        .app-name-fly span:nth-child(2) {{ animation-delay: 0.12s, 0.2s, 0.06s; }}
        .app-name-fly span:nth-child(3) {{ animation-delay: 0.24s, 0.4s, 0.12s; }}
        .app-name-fly span:nth-child(4) {{ animation-delay: 0.36s, 0.6s, 0.18s; }}
        @keyframes spiritButterflyPath {{
            0%, 100% {{
                transform: translate(calc(-50% - 150px), 0px) rotate(-3deg);
            }}
            8% {{
                transform: translate(calc(-50% - 118px), -7px) rotate(2deg);
            }}
            14% {{
                transform: translate(calc(-50% - 88px), 5px) rotate(-2deg);
            }}
            20% {{
                transform: translate(calc(-50% - 58px), -11px) rotate(3deg);
            }}
            26% {{
                transform: translate(calc(-50% - 28px), 10px) rotate(-3deg);
            }}
            32% {{
                transform: translate(calc(-50% + 2px), -12px) rotate(2deg);
            }}
            38% {{
                transform: translate(calc(-50% + 32px), 9px) rotate(-2deg);
            }}
            44% {{
                transform: translate(calc(-50% + 62px), -11px) rotate(3deg);
            }}
            50% {{
                transform: translate(calc(-50% + 92px), 8px) rotate(-2deg);
            }}
            56% {{
                transform: translate(calc(-50% + 118px), -9px) rotate(2deg);
            }}
            62% {{
                transform: translate(calc(-50% + 138px), 5px) rotate(-1deg);
            }}
            68% {{
                transform: translate(calc(-50% + 152px), -4px) rotate(1deg);
            }}
            76% {{
                transform: translate(calc(-50% + 158px), 0px) rotate(0deg);
            }}
            84% {{
                transform: translate(calc(-50% + 158px), 0px) rotate(0deg);
            }}
            90%, 100% {{
                transform: translate(calc(-50% - 150px), 0px) rotate(-3deg);
            }}
        }}
        @keyframes spiritCharCycle {{
            /* ── 등장 ── */
            0%, 100% {{
                opacity: 0;
                filter: blur(2.5px);
            }}
            4% {{
                opacity: 0.4;
                filter: blur(1.2px);
            }}
            8% {{
                opacity: 1;
                filter: blur(0);
            }}
            /* ── 비행 중 아지랭이 (희미 ↔ 선명 반복) ── */
            12% {{ opacity: 0.95; filter: blur(0); }}
            15% {{ opacity: 0.1; filter: blur(2.2px); }}
            18% {{ opacity: 0.92; filter: blur(0.2px); }}
            22% {{ opacity: 0.14; filter: blur(2px); }}
            25% {{ opacity: 1; filter: blur(0); }}
            29% {{ opacity: 0.08; filter: blur(2.4px); }}
            32% {{ opacity: 0.88; filter: blur(0.3px); }}
            36% {{ opacity: 0.16; filter: blur(1.9px); }}
            39% {{ opacity: 0.98; filter: blur(0); }}
            43% {{ opacity: 0.11; filter: blur(2.1px); }}
            46% {{ opacity: 0.9; filter: blur(0.25px); }}
            50% {{ opacity: 0.18; filter: blur(1.7px); }}
            53% {{ opacity: 1; filter: blur(0); }}
            57% {{ opacity: 0.12; filter: blur(2px); }}
            60% {{ opacity: 0.93; filter: blur(0.15px); }}
            64% {{ opacity: 0.2; filter: blur(1.5px); }}
            67% {{ opacity: 0.82; filter: blur(0.4px); }}
            /* ── 소멸 ── */
            71% {{ opacity: 0.6; filter: blur(0.7px); }}
            75% {{ opacity: 0.28; filter: blur(1.5px); }}
            79% {{ opacity: 0.08; filter: blur(2.4px); }}
            83% {{ opacity: 0; filter: blur(2.8px); }}
            /* ── 쉼 (재등장 전) ── */
            90%, 98% {{
                opacity: 0;
                filter: blur(2.5px);
            }}
        }}
        @keyframes spiritWingFlutter {{
            0%, 100% {{ transform: translateY(0px); }}
            50% {{ transform: translateY(-2px); }}
        }}
        @keyframes spiritCharShimmer {{
            0%, 100% {{ background-position: 0% 22%; }}
            50% {{ background-position: 0% 82%; }}
        }}
        .logo-img {{
            width: 105px; height: 105px; border-radius: 50%; border: 3px solid #ffb300;
            position: absolute; top: calc(50% - 1px); left: calc(50% - 1px); transform: translate(-50%, -50%);
            object-fit: cover; animation: glowPulse 2s infinite;
        }}
        {balls_css}
    </style>
    <div class="hero-with-brand">
        <div class="logo-wrapper">
            <img class="logo-img" src="data:image/jpeg;base64,{icon_base64}">
            <div class="orbit-ball-0">{lucky_display[0]}</div>
            <div class="orbit-ball-1">{lucky_display[1]}</div>
            <div class="orbit-ball-2">{lucky_display[2]}</div>
            <div class="orbit-ball-3">{lucky_display[3]}</div>
            <div class="orbit-ball-4">{lucky_display[4]}</div>
            <div class="orbit-ball-5">{lucky_display[5]}</div>
        </div>
        <p class="app-name-fly" aria-label="로또신령">
            <span>로</span><span>또</span><span>신</span><span>령</span>
        </p>
    </div>
    """, unsafe_allow_html=True)


    # 🟢 1. 로또볼 디자인 (3D 입체감 & 크기 확대)
    col1 = st.columns([1])[0]
    with col1:
        def get_ball_style(n):
            if 1 <= n <= 10: return "background: radial-gradient(circle at 35% 35%, #ffeb3b, #f9a825, #f57f17);"
            if 11 <= n <= 20: return "background: radial-gradient(circle at 35% 35%, #4fc3f7, #1976d2, #0d47a1);"
            if 21 <= n <= 30: return "background: radial-gradient(circle at 35% 35%, #ef5350, #e53935, #b71c1c);"
            if 31 <= n <= 40: return "background: radial-gradient(circle at 35% 35%, #bdbdbd, #757575, #424242);"
            return "background: radial-gradient(circle at 35% 35%, #81c784, #388e3c, #1b5e20);"

        balls_html = "".join([f'<div style="{get_ball_style(n)} width:34px; height:34px; border-radius:50%; display:flex; align-items:center; justify-content:center; color:white; font-weight:900; font-size:15px; margin-right:4px; box-shadow: 2px 3px 5px rgba(0,0,0,0.5), inset -3px -3px 5px rgba(0,0,0,0.4), inset 2px 2px 4px rgba(255,255,255,0.6); text-shadow: 1px 1px 2px rgba(0,0,0,0.8);">{n}</div>' for n in numbers])
        
        st.markdown(f"""
        <div style="background: linear-gradient(145deg, #1c2645, #12182b); border-radius:16px; padding:12px 10px; border: 1px solid #2a3a60; display: flex; align-items: center; justify-content: space-between; box-shadow: 0 6px 12px rgba(0,0,0,0.5); margin-bottom: 12px;">
            <div style="color:#ffb300; font-size:13px; font-weight:900; line-height:1; margin-right:8px; letter-spacing:-0.5px; white-space:nowrap;">최근당첨번호 <span style="color:#fff;">{draw_no}</span></div>
            <div style="display:flex; align-items:center;">
                {balls_html}
                <span style="color:#aaa; font-weight:900; font-size:18px; margin: 0 4px;">+</span>
                <div style="{get_ball_style(bonus_val)} width:34px; height:34px; border-radius:50%; display:flex; align-items:center; justify-content:center; color:white; font-weight:900; font-size:15px; box-shadow: 2px 3px 5px rgba(0,0,0,0.5), inset -3px -3px 5px rgba(0,0,0,0.4), inset 2px 2px 4px rgba(255,255,255,0.6); text-shadow: 1px 1px 2px rgba(0,0,0,0.8);">{bonus_val}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # 역대 최고 당첨금 (한 줄 정렬 - 3구역 space-between)
    col_title, col_amount, col_btn = st.columns(3)
    with col_title:
        st.markdown("""
        <div style="display:flex; align-items:center; gap:4px; white-space:nowrap; width:100%;">
            <span style="color:#b0bec5; font-size:11px; font-weight:bold; letter-spacing:-0.3px; line-height:1;">🏆 역대 최고 당첨 금액 순위</span>
        </div>
        """, unsafe_allow_html=True)
    with col_amount:
        st.markdown("""
        <div style="display:flex; align-items:center; gap:6px; white-space:nowrap; justify-content:center; width:100%;">
            <div style="background: radial-gradient(circle at 35% 35%, #ef5350, #e53935, #b71c1c); width:18px; height:18px; border-radius:50%; text-align:center; line-height:18px; color:white; font-weight:bold; font-size:11px; box-shadow: 1px 2px 3px rgba(0,0,0,0.5); flex-shrink:0;">1</div>
            <span style="color:#fff; font-weight:900; font-size:16px; letter-spacing:-0.5px; line-height:1;">407억 원</span>
        </div>
        """, unsafe_allow_html=True)
    with col_btn:
        with st.popover("더 보러가기", key="main_rank_more_6n36s5"):
            st.markdown("### 🏆 역대 당\u200b\u200b첨금 TOP 5")
            st.write("1위: 407억 (1회)")
            st.write("2위: 369억 (51회)")
            st.write("3위: 346억 (100회)")

    components.html("""
    <script>
    (function() {
        const doc = window.parent.document;
        if (!doc.getElementById('rank-more-btn-style')) {
            const style = doc.createElement('style');
            style.id = 'rank-more-btn-style';
            style.textContent = `
                html body .stApp div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) div[data-testid="stPopover"] button,
                html body .stApp div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) div[data-testid="stPopover"] button[data-testid="stBaseButton-secondary"],
                html body .stApp div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) div[data-testid="stPopover"] button[data-testid="baseButton-secondary"],
                html body .stApp div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) div[data-testid="stPopover"] button[kind="secondary"],
                html body .stApp div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) div[data-testid="stButton"] > button {
                    background: linear-gradient(145deg, #1e88e5, #1565c0) !important;
                    background-color: #1976d2 !important;
                    background-image: linear-gradient(145deg, #1e88e5, #1565c0) !important;
                    color: #ffffff !important;
                    border: 1px solid #0d47a1 !important;
                    border-color: #0d47a1 !important;
                }
                html body .stApp div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) div[data-testid="stPopover"] button *,
                html body .stApp div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) div[data-testid="stPopover"] button p,
                html body .stApp div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) div[data-testid="stButton"] > button * {
                    color: #ffffff !important;
                    -webkit-text-fill-color: #ffffff !important;
                    background: transparent !important;
                }
            `;
            doc.head.appendChild(style);
        }
        if (!doc.getElementById('rank-popover-layer-fix')) {
            const popStyle = doc.createElement('style');
            popStyle.id = 'rank-popover-layer-fix';
            popStyle.textContent = `
                html body div[data-baseweb="popover"],
                body > div[data-baseweb="popover"] {
                    z-index: 9999 !important;
                    position: fixed !important;
                    isolation: isolate !important;
                }
                html body [data-testid="stPopoverBody"],
                body [data-testid="stPopoverBody"] {
                    background-color: #1a2542 !important;
                    background: #1a2542 !important;
                    color: #ffffff !important;
                    border: 1px solid #f9a825 !important;
                    border-radius: 12px !important;
                    min-width: 240px !important;
                    padding: 14px 16px !important;
                    box-sizing: border-box !important;
                    opacity: 1 !important;
                    visibility: visible !important;
                    z-index: 9999 !important;
                    position: fixed !important;
                    isolation: isolate !important;
                    pointer-events: auto !important;
                }
                html body [data-testid="stPopoverBody"] *,
                html body [data-testid="stPopoverBody"] p,
                html body [data-testid="stPopoverBody"] h3,
                html body [data-testid="stPopoverBody"] div[data-testid="stMarkdownContainer"],
                html body [data-testid="stPopoverBody"] div[data-testid="element-container"],
                html body [data-testid="stPopoverBody"] div[data-testid="stMarkdownContainer"] * {
                    color: #ffffff !important;
                    -webkit-text-fill-color: #ffffff !important;
                    background-color: transparent !important;
                    background: transparent !important;
                    opacity: 1 !important;
                    visibility: visible !important;
                }
            `;
            doc.head.appendChild(popStyle);
        }
    })();
    </script>
    """, height=0)

    components.html("""
    <script>
    (function() {
        function safeVibrate() {
            if (typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function') {
                try { navigator.vibrate(70); } catch (e) {}
            }
        }
        const doc = window.parent.document;
        doc.querySelectorAll('div[data-testid="stPopover"] button').forEach(function(btn) {
            if (btn.dataset.mainVibrateBound) return;
            const label = (btn.innerText || '').trim();
            if (label.indexOf('더 보러가기') !== -1 || label.indexOf('더보러가기') !== -1 || label === '➡️') {
                btn.dataset.mainVibrateBound = '1';
                btn.addEventListener('click', safeVibrate, { passive: true });
            }
        });
    })();
    </script>
    """, height=0)

    # 🟢 2. 하단 4버튼 메뉴 (모바일 앱 스타일, 강한 햅틱 진동 추가)
    st.markdown("""
    <style>
    .menu-grid { display: grid; grid-template-columns: 1fr 1fr; grid-auto-rows: 1fr; gap: 10px; margin-top: 7px; }
    .menu-grid > a { display: flex; min-height: 0; }
    
    .menu-box { 
        background: linear-gradient(145deg, #1c2645, #101628); 
        border-radius: 20px; 
        padding: 18px 10px; 
        min-height: 118px;
        width: 100%;
        flex: 1;
        box-sizing: border-box;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        text-align: center; 
        box-shadow: 6px 8px 16px rgba(0,0,0,0.6), inset 1px 1px 2px rgba(255,255,255,0.1); 
        cursor: pointer; 
        transition: all 0.1s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
    }
    
    /* ⚡ 터치 시 강하게 눌리는 입체 효과 */
    .menu-box:active { 
        transform: scale(0.93) translateY(4px); 
        box-shadow: 2px 3px 6px rgba(0,0,0,0.6), inset 4px 6px 12px rgba(0,0,0,0.8), inset -2px -2px 6px rgba(255,255,255,0.05); 
    }
    
    /* 3D 느낌의 크고 선명한 이모티콘 */
    .menu-icon { font-size: 36px; margin-bottom: 8px; line-height: 1; filter: drop-shadow(2px 4px 6px rgba(0,0,0,0.5)); }
    .menu-title { color: #ffffff; font-weight: 900; font-size: 16px; margin-bottom: 2px; letter-spacing: 0.5px; }
    .menu-sub { color: #9aa5b1; font-size: 13px; font-weight: 600; min-height: 18px; line-height: 18px; }
    
    /* 테두리 글로우 효과 */
    .gold { border: 2px solid rgba(255, 179, 0, 0.7); }
    .blue { border: 2px solid rgba(41, 182, 246, 0.7); }
    .green { border: 2px solid rgba(102, 187, 106, 0.7); }
    .purple { border: 2px solid rgba(171, 71, 188, 0.7); }
    </style>

<div class="menu-grid">
    <a href="?page=thunder&fresh=1" target="_self" style="text-decoration:none; display:block;">
        <div class="menu-box gold">
            <div class="menu-icon">⚡</div>
            <div class="menu-title">번\u200b\u200b개조합</div>
            <div class="menu-sub">빠른 조합</div>
        </div>
    </a>
    <a href="?page=advanced" target="_self" style="text-decoration:none; display:block;">
        <div class="menu-box blue">
            <div class="menu-icon">👑</div>
            <div class="menu-title">고급필터</div>
            <div class="menu-sub">전문가 분석용</div>
        </div>
    </a>
    <a href="?page=auto" target="_self" style="text-decoration:none; display:block;">
        <div class="menu-box purple">
            <div class="menu-icon">💎</div>
            <div class="menu-title">자동구매</div>
            <div class="menu-sub">자동 발송</div>
        </div>
    </a>
    <a href="?page=stats" target="_self" style="text-decoration:none; display:block;">
        <div class="menu-box green">
            <div class="menu-icon">📊</div>
            <div class="menu-title">통계센터</div>
            <div class="menu-sub">데이터분석</div>
        </div>
    </a>
</div>
    """, unsafe_allow_html=True)

    components.html("""
    <script>
    (function() {
        function safeVibrate() {
            if (typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function') {
                try { navigator.vibrate(70); } catch (e) {}
            }
        }
        const doc = window.parent.document;

        doc.querySelectorAll('.menu-grid a').forEach(function(el) {
            if (el.dataset.mainVibrateBound) return;
            el.dataset.mainVibrateBound = '1';
            el.addEventListener('click', safeVibrate, { passive: true });
        });
    })();
    </script>
    """, height=0)

    from feedback_db import init_feedback_tables, save_feedback
    from auth_providers import current_member_id

    init_feedback_tables()

    st.markdown(
        """
<div class="main-feedback-section-marker" aria-hidden="true"></div>
<style>
.main-feedback-section-marker { display: none !important; }
div[data-testid="stVerticalBlock"]:has(.main-feedback-section-marker) {
    margin-top: 6px !important;
    margin-bottom: 0 !important;
    padding-bottom: 0 !important;
}
div[data-testid="stVerticalBlock"]:has(.main-feedback-section-marker) div[data-testid="stExpander"] {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    margin-bottom: 4px !important;
}
div[data-testid="stVerticalBlock"]:has(.main-feedback-section-marker) div[data-testid="stExpander"] summary {
    background: linear-gradient(145deg, #243052 0%, #1a2238 42%, #12182b 100%) !important;
    background-color: transparent !important;
    color: #b8c2d6 !important;
    font-weight: 700 !important;
    font-size: 13px !important;
    line-height: 1.15 !important;
    text-align: center;
    padding: 6px 8px !important;
    min-height: 0 !important;
    border-radius: 10px !important;
    border: 1px solid rgba(100, 126, 170, 0.32) !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.06) !important;
    justify-content: center !important;
}
div[data-testid="stVerticalBlock"]:has(.main-feedback-section-marker) div[data-testid="stExpander"] summary p,
div[data-testid="stVerticalBlock"]:has(.main-feedback-section-marker) div[data-testid="stExpander"] summary span {
    color: #b8c2d6 !important;
    font-weight: 700 !important;
}
div[data-testid="stVerticalBlock"]:has(.main-feedback-section-marker) div[data-testid="stExpander"] [data-testid="stExpanderDetails"] {
    background: #16213e !important;
    border: 2px solid #4a9fc4 !important;
    border-top: none !important;
    border-radius: 0 0 10px 10px !important;
    padding: 8px 10px 4px 10px !important;
}
div[data-testid="stVerticalBlock"]:has(.main-feedback-section-marker) div[data-testid="stForm"] textarea {
    background-color: #0d1528 !important;
    color: #ffffff !important;
    border: 1px solid #2a3a60 !important;
    min-height: 52px !important;
}
div[data-testid="stVerticalBlock"]:has(.main-feedback-section-marker) div[data-testid="stFormSubmitButton"] button {
    background: linear-gradient(135deg, #87CEEB, #5BB5D9) !important;
    color: #102030 !important;
    font-weight: 800 !important;
    min-height: 36px !important;
    padding: 0.35rem 0.75rem !important;
}
</style>
        """,
        unsafe_allow_html=True,
    )

    with st.container():
        st.markdown('<div class="main-feedback-section-marker"></div>', unsafe_allow_html=True)
        with st.expander("개선 요구사항", expanded=False):
            with st.form("main_feedback_form_6n36s5", clear_on_submit=True):
                fb_body = st.text_area(
                    "의견",
                    placeholder="불편한 점·원하는 기능을 짧게 적어 주세요",
                    max_chars=2000,
                    height=52,
                    label_visibility="collapsed",
                )
                submitted = st.form_submit_button("저장", use_container_width=True)
                if submitted:
                    try:
                        mid = current_member_id()
                        save_feedback(
                            fb_body,
                            nickname="익명",
                            category="기타",
                            member_id=mid,
                        )
                        st.success("저장되었습니다. 감사합니다!")
                    except ValueError as exc:
                        st.warning(str(exc))


# ==========================================
# ⚡ 화면 2: 번개조합 (Thunder View) - 로직 분리됨
# ==========================================
elif current_page == "thunder":
    import page_thunder
    page_thunder.render(admin_lucky=lucky_display)

elif current_page == "birthday":
    import page_birthday
    page_birthday.render()

# ==========================================
# 💎 화면: 자동조합 상세 (Auto Combination View)
# ==========================================
elif current_page == "auto":
    import page_auto
    page_auto.render()

# ==========================================
# 🤖 화면 3: 고급필터 상세 페이지 (Advanced Filter View)
# ==========================================
elif current_page == "advanced":
    if os.path.exists("admin_filter.py"):
        with open("admin_filter.py", "r", encoding="utf-8") as f:
            exec(f.read())
    else:
        st.error("admin_filter.py 파일을 찾을 수 없습니다. 파일이 같은 폴더에 있는지 확인해주세요.")

# ==========================================
# 📊 화면 4: 통계 대시보드 (Stats View)
# ==========================================
# ==========================================
# 📊 [안전하게 추가] 통계 대시보드 (Stats View)
# ==========================================
elif current_page == "stats":
    st.markdown("""
    <style>
        .stApp { background-color: #12182b; color: white; }
        .block-container { padding: 10px !important; max-width: 600px; }
        section[data-testid="stSidebar"], header[data-testid="stHeader"] { display: none; }
        
        /* 탭(Tab) 디자인 고급화 */
        button[data-baseweb="tab"] { background-color: transparent !important; color: #888 !important; font-weight: bold; font-size: 15px; padding-bottom: 12px !important; }
        button[data-baseweb="tab"][aria-selected="true"] { color: #ffb300 !important; border-bottom: 3px solid #ffb300 !important; }
        
        /* 통계 카드 디자인 */
        .stat-card { background: linear-gradient(145deg, #1c2645, #12182b); border-radius: 14px; padding: 16px; border: 1px solid #2a3a60; margin-bottom: 14px; box-shadow: 0 4px 8px rgba(0,0,0,0.4); }
        .stat-title { color: #4fc3f7; font-size: 14px; font-weight: 900; margin-bottom: 8px; border-bottom: 1px solid #2a3a60; padding-bottom: 6px; display: flex; justify-content: space-between; align-items: center; }
        .stat-value { color: #ffffff; font-size: 16px; font-weight: bold; line-height: 1.4; }
        .highlight { color: #ffeb3b; font-size: 22px; font-weight: 900; }
        .tag { background: #2a3a60; padding: 2px 8px; border-radius: 12px; font-size: 11px; color: #aaa; }
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
    </style>
    """, unsafe_allow_html=True)

    # 1. 상단 네비게이션
    col_back, col_title = st.columns([3, 7])
    with col_back:
        stats_icon_html = (
            f'<img class="auto-back-main-icon" src="data:image/jpeg;base64,{icon_base64}" alt="로또신령">'
            if icon_base64
            else "🏠"
        )
        st.markdown(
            f'<a href="?" target="_self" class="auto-back-main-btn">{stats_icon_html}<span>메인으로</span></a>',
            unsafe_allow_html=True,
        )
    with col_title:
        st.markdown("<h3 style='color:#ffb300; margin:0; padding-top:2px;'>📊 로또 통계 센터</h3>", unsafe_allow_html=True)

    st.markdown("<div style='margin-top:15px;'></div>", unsafe_allow_html=True)

    # 2. 엑셀 데이터 기반 통계 집계
    try:
        from lotto_stats import compute_all_stats

        stats = compute_all_stats("로또최근당첨내역.xlsb")
        draw_no = stats["latest"]["draw_no"]
        numbers = stats["latest"]["numbers"]
        sum_val = stats["latest"]["sum"]
        ac_val = stats["latest"]["ac"]
        hot_items = stats["hot"]
        hot_display = " · ".join(str(n) for n, _ in hot_items)
        cold_nums = stats["cold"]
        cold_display = ", ".join(str(n) for n in cold_nums) if cold_nums else "없음"
        carry_count = stats["carry"]["count"]
        carry_checked = stats["carry"]["checked"]
        is_sum_good = "🔥 이상적" if 120 <= sum_val <= 150 else "❄️ 주의"
        from lotto_stats import get_marketing_win_rank_summary

        try:
            draw_round_int = int(str(draw_no).replace("회", "").strip())
            st.session_state["marketing_win_rank_summary"] = get_marketing_win_rank_summary(
                draw_round_int
            )
        except (TypeError, ValueError):
            st.session_state["marketing_win_rank_summary"] = {}
    except Exception as e:
        stats = None
        draw_no, numbers, sum_val, ac_val = "오류", [0, 0, 0, 0, 0, 0], 0, "-"
        hot_display, cold_display = "-", "-"
        carry_count, carry_checked = 0, 0
        is_sum_good = "-"
        st.session_state["marketing_win_rank_summary"] = {}
        st.error(f"통계 데이터 로딩 오류: {e}")

    # 3. 3개의 탭으로 모바일 화면 최적화
    tab1, tab2, tab3 = st.tabs(["🧠 전문가 지표", "🔥 출현 빈도", "🎯 패턴 분석"])

    # --- TAB 1: 전문가 지표 ---
    with tab1:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-title"><span>1. AC값 (산술적 복잡도)</span> <span class="tag">최근 {draw_no}회차</span></div>
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span class="stat-value" style="color:#aaa; font-size:13px;">이상적 구간 (7~10)</span>
                <span class="highlight">{ac_val}</span>
            </div>
            <div style="font-size:12px; color:#4fc3f7; margin-top:8px;">💡 AC값이 7 이상일 때 1등 당첨 확률이 통계적으로 가장 높습니다.</div>
        </div>
        
        <div class="stat-card">
            <div class="stat-title"><span>2. 당첨 번호 총합 (Sum)</span> <span class="tag">최근 {draw_no}회차</span></div>
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span class="stat-value">총합: {sum_val}</span>
                <span class="highlight" style="font-size:16px;">{is_sum_good} (120~150 강세)</span>
            </div>
        </div>
        
        <div class="stat-card">
            <div class="stat-title">3. 이월수 출현 패턴</div>
            <div class="stat-value">최근 {carry_checked}회 중 <span style="color:#ffb300;">{carry_count}회</span> 이월수 출현</div>
            <div style="font-size:12px; color:#aaa; margin-top:4px;">직전 회차 당첨번호가 다음 회차에도 포함된 실제 집계입니다.</div>
        </div>
        """, unsafe_allow_html=True)

    # --- TAB 2: 출현 빈도 ---
    with tab2:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-title">4. 역대 최다 출현 (Hot 10)</div>
            <div class="stat-value" style="letter-spacing: 1px;">
                {hot_display}
            </div>
        </div>
        
        <div class="stat-card">
            <div class="stat-title">5. 장기 미출현 (Cold)</div>
            <div class="stat-value">
                <span style="color:#4fc3f7;">{cold_display}</span>
            </div>
            <div style="font-size:12px; color:#aaa; margin-top:4px;">최근 15회차 동안 1~6구에 미출현한 번호입니다.</div>
        </div>
        
        <div class="stat-card">
            <div class="stat-title">6. 색상별 당첨 비율 (최근 10회)</div>
            <div style="display:flex; height:24px; border-radius:12px; overflow:hidden; margin-top:10px;">
                <div style="background:#f9a825; width:20%;" title="노랑 (1~10)"></div>
                <div style="background:#1976d2; width:35%;" title="파랑 (11~20)"></div>
                <div style="background:#e53935; width:25%;" title="빨강 (21~30)"></div>
                <div style="background:#757575; width:10%;" title="회색 (31~40)"></div>
                <div style="background:#388e3c; width:10%;" title="초록 (41~45)"></div>
            </div>
            <div style="font-size:12px; color:#aaa; margin-top:8px; text-align:center;">현재 <span style="color:#4fc3f7; font-weight:bold;">파란공(11~20)</span>이 가장 강세입니다.</div>
        </div>
        """, unsafe_allow_html=True)

    # --- TAB 3: 패턴 분석 (lotto_stats.py 실데이터) ---
    with tab3:
        if stats is not None:
            pattern = stats["pattern"]
            pat_n = pattern["basis_n"]
            oe = pattern["odd_even"]
            lh = pattern["low_high"]
            dec = pattern["decade"]
            ld = pattern["last_digit"]

            odd_even_text = (
                f'현재 누적 트렌드 ➡️ <span style="color:#ffb300;">'
                f'홀 {oe["top_odds"]} : 짝 {oe["top_evens"]}</span> '
                f'(최근 {oe["checked"]}회 중 {oe["top_count"]}회)'
            )
            low_high_text = (
                f'현재 누적 트렌드 ➡️ <span style="color:#ffb300;">'
                f'저 {lh["top_low"]} : 고 {lh["top_high"]}</span> '
                f'(최근 {lh["checked"]}회 중 {lh["top_count"]}회)'
            )

            if dec["warnings"]:
                decade_lines = []
                for w in dec["warnings"]:
                    decade_lines.append(
                        f'⚠️ <span style="color:#e53935;">{w["band"]} 구간({w["range"]})</span> '
                        f'{w["streak"]}주 연속 전멸 현상 발생'
                    )
                decade_text = "<br/>".join(decade_lines)
            else:
                totals = dec["band_totals"]
                summary_parts = [
                    f'{name} {totals[name]}회'
                    for name, _, _ in (
                        ("1번대", 1, 9),
                        ("10번대", 10, 19),
                        ("20번대", 20, 29),
                        ("30번대", 30, 39),
                        ("40번대", 40, 45),
                    )
                ]
                decade_text = (
                    f'최근 {dec["checked"]}회 각 구간 출현: '
                    f'<span style="color:#4fc3f7;">{" · ".join(summary_parts)}</span>'
                )

            last_digit_text = (
                f'최근 동끝수 <span style="color:#4fc3f7;">[ {ld["top_digit"]} ]</span> '
                f'({ld["top_count"]}회 출현, 최근 {ld["checked"]}회 기준)'
            )
        else:
            pat_n = 0
            odd_even_text = low_high_text = decade_text = last_digit_text = "데이터 로딩 오류"

        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-title">7. 홀짝 비율 <span class="tag">최근 {pat_n}회</span></div>
            <div class="stat-value">
                {odd_even_text}
            </div>
        </div>
        
        <div class="stat-card">
            <div class="stat-title">8. 고저 비율 (1~22 vs 23~45) <span class="tag">최근 {pat_n}회</span></div>
            <div class="stat-value">
                {low_high_text}
            </div>
        </div>
        
        <div class="stat-card">
            <div class="stat-title">9. 번호대별 분포 현상 <span class="tag">최근 {pat_n}회</span></div>
            <div class="stat-value">
                {decade_text}
            </div>
        </div>
        
        <div class="stat-card">
            <div class="stat-title">10. 끝수 (일의 자리) 출현 <span class="tag">최근 {pat_n}회</span></div>
            <div class="stat-value">
                {last_digit_text}
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown(
        '<p style="font-size:11px; color:#888; text-align:center; margin-top:20px; line-height:1.5;">'
        "※ 본 통계는 과거 데이터 집계이며, 로또는 완전 무작위 추첨으로 "
        "다음 회차 결과를 보장하지 않습니다"
        "</p>",
        unsafe_allow_html=True,
    )


# ==========================================================
# 📋 메인 화면 — 회원 고지·약관 (운영자 미리보기, 관리자 메뉴 바로 위)
# ==========================================================
if current_page == "main":
    st.markdown("""
    <div class="main-legal-notices-marker" aria-hidden="true"></div>
    <style>
    .main-legal-notices-marker { display: none !important; }
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) {
        margin-top: 0 !important;
        margin-bottom: 0 !important;
        padding-top: 0 !important;
        padding-bottom: 0 !important;
    }
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) div[data-testid="stExpander"] {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        border-radius: 10px !important;
        margin-bottom: 4px !important;
    }
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) div[data-testid="stExpander"] summary {
        background: linear-gradient(145deg, #2a2548 0%, #1c2038 45%, #12182b 100%) !important;
        background-color: transparent !important;
        padding: 6px 8px !important;
        min-height: 0 !important;
        line-height: 1.15 !important;
        border-radius: 10px !important;
        border: 1px solid rgba(120, 100, 170, 0.3) !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.05) !important;
    }
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) div[data-testid="stExpander"] details,
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) div[data-testid="stExpander"] [data-testid="stExpanderDetails"],
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) div[data-testid="stExpander"] [data-testid="stExpanderDetails"] > div {
        background-color: #0d1528 !important;
    }
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) div[data-testid="stExpander"] summary,
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) div[data-testid="stExpander"] summary p,
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) div[data-testid="stExpander"] summary span {
        color: #b39ddb !important;
        font-weight: 700 !important;
        font-size: 13px !important;
        white-space: nowrap !important;
        line-height: 1.15 !important;
    }
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) div[data-testid="stExpander"] [data-testid="stExpanderDetails"] p,
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) div[data-testid="stExpander"] [data-testid="stExpanderDetails"] li {
        color: #e0e0e0 !important;
        font-size: 13px !important;
        line-height: 1.55 !important;
    }
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) button[data-baseweb="tab"] {
        color: #888 !important;
        font-size: 12px !important;
    }
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) button[data-baseweb="tab"][aria-selected="true"] {
        color: #ce93d8 !important;
        border-bottom-color: #ce93d8 !important;
    }
    </style>
    """, unsafe_allow_html=True)
    with st.expander("📋 회원 고지·약관 (오픈 전 검토용)"):
        from legal_notices import render_notice_preview

        render_notice_preview()
        st.info(
            "※ 현재 **운영자만** 메인 하단에서 확인하는 준비 화면입니다. "
            "회원 공개·간편인증·적립금 연동은 다음 단계에서 적용합니다."
        )


# ==========================================================
# 👑 메인 화면 맨 아래 관리자 메뉴
# ==========================================================
if current_page == "main":
    st.markdown("""
    <div class="main-admin-menu-marker" aria-hidden="true"></div>
    <style>
    .main-admin-menu-marker { display: none !important; }
    div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) {
        margin-top: 0 !important;
        margin-bottom: 0 !important;
        padding-top: 0 !important;
    }

    div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        border-radius: 10px !important;
        margin-bottom: 0 !important;
    }
    div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] summary {
        background: linear-gradient(145deg, #1c2838 0%, #141c2a 45%, #0c1018 100%) !important;
        background-color: transparent !important;
        color: #c8d0dc !important;
        padding: 6px 8px !important;
        min-height: 0 !important;
        line-height: 1.15 !important;
        border-radius: 10px !important;
        border: 1px solid rgba(80, 95, 120, 0.35) !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.05) !important;
    }
    div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] details {
        background-color: #000000 !important;
    }
    div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] summary:hover {
        background: linear-gradient(145deg, #243040 0%, #1a2432 45%, #101620 100%) !important;
        color: #e8ecf2 !important;
    }
    div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] summary p,
    div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] summary span,
    div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] summary div,
    div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] summary svg {
        color: #c8d0dc !important;
        fill: #c8d0dc !important;
        font-size: 13px !important;
        line-height: 1.15 !important;
        white-space: nowrap !important;
    }
    div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] [data-testid="stExpanderDetails"] {
        background-color: #000000 !important;
        border-top: 1px solid #333333 !important;
    }
    div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] [data-testid="stExpanderDetails"] > div {
        background-color: #000000 !important;
    }
    div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] button[kind="secondary"],
    div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] button[data-testid="stBaseButton-secondary"],
    div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] button {
        background-color: #3a3a3a !important;
        color: #ffffff !important;
        border: 1px solid #555555 !important;
    }
    div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] button:hover {
        background-color: #4a4a4a !important;
        color: #ffffff !important;
        border-color: #666666 !important;
    }
    div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] button p,
    div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] button span,
    div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] button div {
        color: #ffffff !important;
    }
    </style>
    """, unsafe_allow_html=True)
    with st.expander("🛠️ 시스템 관리자 메뉴"):
        _ADMIN_MENU_PASSWORD = "ns6365"
        if not st.session_state.get("admin_menu_unlocked", False):
            st.text_input(
                "관리자 비밀번호",
                type="password",
                key="admin_menu_pwd_6n36s5",
            )
            if st.button("확인", key="admin_menu_pwd_submit_6n36s5"):
                if st.session_state.get("admin_menu_pwd_6n36s5") == _ADMIN_MENU_PASSWORD:
                    st.session_state.admin_menu_unlocked = True
                    st.rerun()
                else:
                    st.warning("비밀번호가 올바르지 않습니다.")
        elif st.button("📊 대시보드로 이동", key="admin_btn_dashboard"):
            st.session_state.is_admin = True
            st.session_state.go_to_admin = True
            st.rerun()