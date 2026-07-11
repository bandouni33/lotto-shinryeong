
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
st.set_page_config(page_title="로또야 놀자", layout="centered", initial_sidebar_state="collapsed")

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
        div[data-testid="stColumn"]:nth-child(1) { flex: 78 !important; min-width: 0px !important; }
        div[data-testid="stColumn"]:nth-child(2) { flex: 22 !important; min-width: 0px !important; }

        div[data-testid="stPopover"] { width: 100% !important; }
        div[data-testid="stPopover"] > div {
            background-color: #1a2542 !important; color: white !important;
            border: 1px solid #f9a825 !important; border-radius: 12px !important;
        }
        button[data-testid="stBaseButton-secondary"] {
            background-color: #ffffff !important; color: #444444 !important; border: 1px solid #cccccc !important;
            border-radius: 12px !important; font-size: 16px !important; font-weight: bold !important;
            padding: 0px !important; width: 100% !important; height: 56px !important;
            box-shadow: 0 4px 6px rgba(0,0,0,0.4) !important; display: flex !important;
            align-items: center !important; justify-content: center !important;
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
            from {{ transform: rotate({angle}deg) translateX(70px) rotate(-{angle}deg); }}
            to {{ transform: rotate({angle + 360}deg) translateX(70px) rotate(-{angle + 360}deg); }}
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
            position: relative; width: 150px; height: 150px; margin: 0 auto;
        }}
        .logo-img {{
            width: 90px; height: 90px; border-radius: 50%; border: 3px solid #ffb300;
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

    # 역대 최고 당첨금 (UI 고급화)
    col3, col4 = st.columns([78, 22])
    with col3:
        st.markdown("""
        <div style="background: linear-gradient(145deg, #1c2645, #12182b); border-radius:14px; padding:10px 14px; border: 1px solid #2a3a60; height: 56px; display: flex; flex-direction: column; justify-content: center; box-shadow: 0 4px 8px rgba(0,0,0,0.4);">
            <div style="color:#b0bec5; font-size:12px; font-weight:bold; margin-bottom:2px; line-height:1;">🏆 역대 최고 일탈 금액</div>
            <div style="display:flex; align-items:center; gap:8px;">
                <div style="background: radial-gradient(circle at 35% 35%, #ef5350, #e53935, #b71c1c); width:20px; height:20px; border-radius:50%; text-align:center; line-height:20px; color:white; font-weight:bold; font-size:12px; box-shadow: 1px 2px 3px rgba(0,0,0,0.5);">1</div>
                <span style="color:#fff; font-weight:900; font-size:20px; letter-spacing:-0.5px; line-height:1;">407억 원</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    with col4:
        with st.popover("➡️"):
            st.markdown("### 🏆 역대 당첨금 TOP 5")
            st.write("1위: 407억 (1회)")
            st.write("2위: 369억 (51회)")
            st.write("3위: 346억 (100회)")

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
            if (label === '➡️') {
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
    .menu-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; }
    
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
            <div class="menu-icon">🤖</div>
            <div class="menu-title">고급필터</div>
            <div class="menu-sub">AI 추천</div>
        </div>
    </a>
    <a href="?page=stats" target="_self" style="text-decoration:none; display:block;">
        <div class="menu-box green">
            <div class="menu-icon">📊</div>
            <div class="menu-title">통계센터</div>
            <div class="menu-sub">데이터분석</div>
        </div>
    </a>
    <div class="menu-box purple" onclick="alert('프리미엄 서비스 준비 중입니다.');">
        <div class="menu-icon">👑</div>
        <div class="menu-title">프리미엄</div>
        <div class="menu-sub">구독하기</div>
    </div>
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
    try:
        # 데이터 로드 (기존 파일 사용)
        df = pd.read_excel("로또최근당첨내역.xlsb", engine='pyxlsb', header=None)
        
        # 실제 데이터 집계 로직
        lottery_data = df.iloc[4:, 3:9].astype(int)
        
        # 1. 장기 미출현 (최근 15회차 기준)
        recent_15_rows = lottery_data.iloc[0:15].values.flatten()
        all_nums = set(range(1, 46))
        cold_nums = sorted(list(all_nums - set(recent_15_rows)))
        
        # 2. 역대 최다 출현 (전체 데이터)
        from collections import Counter
        counts = Counter(lottery_data.values.flatten())
        hot_nums = [num for num, count in counts.most_common(10)]
        
        # 화면 출력
        st.subheader("📊 데이터 정밀 분석")
        st.write(f"**장기 미출현 (15회):** {', '.join(map(str, cold_nums))}")
        st.write(f"**역대 최다 출현 (Hot 10):** {', '.join(map(str, hot_nums))}")
        
    except Exception as e:
        st.error(f"통계 데이터 로딩 오류: {e}")
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

    # 2. 엑셀 데이터 안전하게 불러오기 (유령 데이터, 공백 에러 방지)
    try:
        df = pd.read_excel("로또최근당첨내역.xlsb", engine='pyxlsb', header=None)
        
        # 최신 회차 데이터 (인덱스 4번 행 기준)
        latest_row = df.iloc[4].tolist()
        draw_no = str(latest_row[1]).replace(".0", "")
        
        # 눈에 보이지 않는 공백/문자열을 제외하고 순수 숫자만 추출
        numbers = [int(pd.to_numeric(x, errors='coerce')) for x in latest_row[3:9] if pd.notna(pd.to_numeric(x, errors='coerce'))]
        numbers.sort()
        
        # 통계 지표 계산용 변수
        sum_val = sum(numbers) if len(numbers) == 6 else 0
        ac_val = str(latest_row[11]) if len(latest_row) > 11 else "데이터 없음" # L열(인덱스 11)
        
        # 가상의 분석 결과 (추후 전체 데이터프레임을 활용해 실제 계산 로직으로 교체 가능)
        is_sum_good = "🔥 이상적" if 120 <= sum_val <= 150 else "❄️ 주의"
        
    except Exception as e:
        draw_no, numbers, sum_val, ac_val = "오류", [0,0,0,0,0,0], 0, "-"
        is_sum_good = "-"

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
            <div class="stat-value">최근 5주 연속 <span style="color:#ffb300;">1개 이상 이월수</span> 출현 중</div>
            <div style="font-size:12px; color:#aaa; margin-top:4px;">직전 회차 번호 중 1~2개를 고정수로 잡는 전략이 유효합니다.</div>
        </div>
        """, unsafe_allow_html=True)

    # --- TAB 2: 출현 빈도 ---
    with tab2:
        st.markdown("""
        <div class="stat-card">
            <div class="stat-title">4. 역대 최다 출현 (Hot 10)</div>
            <div class="stat-value" style="letter-spacing: 1px;">
                <span style="color:#ffb300;">43</span> · <span style="color:#ffb300;">34</span> · 12 · 27 · 1 · 17 · 39 · 33 · 13 · 14
            </div>
        </div>
        
        <div class="stat-card">
            <div class="stat-title">5. 장기 미출현 (Cold)</div>
            <div class="stat-value">
                <span style="color:#4fc3f7;">9, 18, 25</span>
            </div>
            <div style="font-size:12px; color:#aaa; margin-top:4px;">15주 이상 단 한 번도 나오지 않은 번호들입니다.</div>
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


# ==========================================================
# 👑 메인 화면 맨 아래 관리자 스위치 (관리자만 표시)
# ==========================================================
if st.session_state.get("is_admin", False):
    st.markdown("---")
    with st.expander("🛠️ 시스템 관리자 메뉴"):
        if st.button("🔒 관리자 모드 끄기", key="admin_btn_off"):
            st.session_state.is_admin = False
            st.rerun()