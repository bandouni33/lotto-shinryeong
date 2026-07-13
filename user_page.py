
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
        if st.button("📊 대시보드로 바로가기"):
            st.switch_page("admin_dashboard.py")

# ==========================================
# 1. 페이지 초기 설정 및 상태 관리
# ==========================================
st.set_page_config(page_title="로또신령", page_icon="K-325.jpg", layout="centered", initial_sidebar_state="collapsed")

current_page = st.query_params.get("page", "main")

# ===============================================================================
# ⚠️⚠️⚠️ [관리자 필수 확인] 매주 이 숫자 6개를 직접 수정하세요 ⚠️⚠️⚠️
# 앞 번호일수록 유력한 순서로 입력 (예: 44가 가장 유력, 7이 가장 약함)
# ⚠️⚠️⚠️ 다른 코드는 건드리지 말고 이 줄의 숫자만 바꾸세요 ⚠️⚠️⚠️
lucky_display = [44, 10, 23, 5, 40, 7]
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
        }}
        .logo-img {{
            width: 105px; height: 105px; border-radius: 50%; border: 3px solid #ffb300;
            position: absolute; top: calc(50% - 1px); left: calc(50% - 1px); transform: translate(-50%, -50%);
            object-fit: cover; animation: glowPulse 2s infinite;
        }}
        {balls_css}
    </style>
    <div style="text-align:center; padding: 10px 0 15px 0; margin-top: -5px;">
        <div class="logo-wrapper">
            <img class="logo-img" src="data:image/jpeg;base64,{icon_base64}">
            <div class="orbit-ball-0">{lucky_display[0]}</div>
            <div class="orbit-ball-1">{lucky_display[1]}</div>
            <div class="orbit-ball-2">{lucky_display[2]}</div>
            <div class="orbit-ball-3">{lucky_display[3]}</div>
            <div class="orbit-ball-4">{lucky_display[4]}</div>
            <div class="orbit-ball-5">{lucky_display[5]}</div>
        </div>
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
        with st.popover("더 보러가기"):
            st.markdown("### 🏆 역대 당첨금 TOP 5")
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
    .menu-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 7px; }
    
    .menu-box { 
        background: linear-gradient(145deg, #1c2645, #101628); 
        border-radius: 20px; 
        padding: 18px 10px; 
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
    .menu-sub { color: #9aa5b1; font-size: 13px; font-weight: 600; }
    
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
            <div class="menu-title">번개조합</div>
            <div class="menu-sub">빠른 조합</div>
        </div>
    </a>
    <a href="?page=advanced" target="_self" style="text-decoration:none; display:block;">
        <div class="menu-box blue">
            <div class="menu-icon">💎</div>
            <div class="menu-title">고급필터</div>
            <div class="menu-sub">전문가 분석용</div>
        </div>
    </a>
    <div class="menu-box purple" onclick="alert('프리미엄 서비스 준비 중입니다.');">
        <div class="menu-icon">👑</div>
        <div class="menu-title">프리미엄</div>
        <div class="menu-sub">준비중입니다</div>
    </div>
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

        const premium = doc.querySelector('.menu-box.purple');
        if (premium && !premium.dataset.mainVibrateBound) {
            premium.dataset.mainVibrateBound = '1';
            premium.addEventListener('click', safeVibrate, { passive: true });
        }
    })();
    </script>
    """, height=0)


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
    </style>
    """, unsafe_allow_html=True)

    # 1. 상단 네비게이션
    col_back, col_title = st.columns([3, 7])
    with col_back:
        if st.button("⬅️ 메인으로", use_container_width=True):
            st.query_params.clear()
            st.rerun()
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
    except Exception as e:
        stats = None
        draw_no, numbers, sum_val, ac_val = "오류", [0, 0, 0, 0, 0, 0], 0, "-"
        hot_display, cold_display = "-", "-"
        carry_count, carry_checked = 0, 0
        is_sum_good = "-"
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

    # ⚠️ TODO: 아래 Tab3 항목들은 실데이터 미연동 상태 (목업 문구)
    # lotto_stats.py에 계산 함수 추가 필요
    # 우선순위: 다음 작업 세션에서 처리
    # --- TAB 3: 패턴 분석 ---
    with tab3:
        st.markdown("""
        <div class="stat-card">
            <div class="stat-title">7. 홀짝 비율</div>
            <div class="stat-value">
                현재 누적 트렌드 ➡️ <span style="color:#ffb300;">홀 3 : 짝 3</span> (가장 안정적)
            </div>
        </div>
        
        <div class="stat-card">
            <div class="stat-title">8. 고저 비율 (1~22 vs 23~45)</div>
            <div class="stat-value">
                현재 누적 트렌드 ➡️ <span style="color:#ffb300;">저 2 : 고 4</span>
            </div>
        </div>
        
        <div class="stat-card">
            <div class="stat-title">9. 번호대별 분포 현상</div>
            <div class="stat-value">
                ⚠️ <span style="color:#e53935;">30번대 구간</span> 2주 연속 전멸 현상 발생
            </div>
        </div>
        
        <div class="stat-card">
            <div class="stat-title">10. 끝수 (일의 자리) 출현</div>
            <div class="stat-value">
                최근 동끝수 <span style="color:#4fc3f7;">[ 4 ]</span> (14, 24, 34) 패턴 강세
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
# 👑 메인 화면 맨 아래 관리자 메뉴
# ==========================================================
if current_page == "main":
    st.markdown("---")
    with st.expander("🛠️ 시스템 관리자 메뉴"):
        if st.button("📊 대시보드로 이동", key="admin_btn_dashboard"):
            st.session_state.is_admin = True
            st.session_state.go_to_admin = True
            st.rerun()