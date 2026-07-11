import streamlit as st
import streamlit.components.v1 as components
from birthday_db import get_user_birthdays
from lucky_numbers import calculate_all_lucky_numbers
import json

def render():
    # ─── 데이터 로드 및 행운수 계산 ───
    user_id = st.session_state.get("user_id") or "guest_local"
    birthdays = get_user_birthdays(user_id)
    
    if birthdays:
        mmdd_list = [b["mmdd"] for b in birthdays]
        family_lucky = calculate_all_lucky_numbers(mmdd_list)
    else:
        family_lucky = st.session_state.get("temp_lucky", [])

    js_lucky_array = str(family_lucky)

    # ─── 커스텀 CSS ───
    st.markdown("""
        <style>
        .main-title {
            font-size: 32px;
            font-weight: 800;
            color: #FFB800;
            text-align: center;
            margin-bottom: 20px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        div[data-testid="stVerticalBlock"] > div:has(div.main-title) {
            padding: 0;
        }
        </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="main-title">⚡ 번개조합</div>', unsafe_allow_html=True)

    # ─── 메인 UI HTML (Grid & Logic) ───
    thunder_ui_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700;900&display=swap" rel="stylesheet">
        <style>
            * {{ font-family: 'Noto Sans KR', sans-serif; box-sizing: border-box; }}
            body {{ background-color: #0F172A; color: white; margin: 0; padding: 10px; overflow-x: hidden; }}
            
            .nav-container {{ display: flex; gap: 10px; margin-bottom: 20px; }}
            .nav-btn {{
                flex: 1; padding: 12px; border-radius: 12px; border: none;
                cursor: pointer; font-weight: bold; font-size: 14px;
                display: flex; align-items: center; justify-content: center; gap: 8px;
                transition: all 0.2s; background: white; color: #1E293B;
            }}
            .nav-btn:hover {{ transform: translateY(-2px ); box-shadow: 0 4px 12px rgba(0,0,0,0.3); }}

            .tab-container {{ display: flex; background: #1E293B; padding: 5px; border-radius: 12px; margin-bottom: 15px; gap: 5px; }}
            .tab {{
                flex: 1; padding: 12px; text-align: center; border-radius: 8px;
                cursor: pointer; font-weight: bold; transition: all 0.2s; font-size: 15px;
            }}
            .tab.active {{ background: #A855F7; color: white; }}
            .tab:not(.active) {{ color: #94A3B8; }}

            .number-grid {{
                display: grid; grid-template-columns: repeat(7, 1fr); gap: 8px;
                background: #1E293B; padding: 15px; border-radius: 16px; margin-bottom: 20px;
            }}
            .num-cell {{
                aspect-ratio: 1; display: flex; align-items: center; justify-content: center;
                background: white; color: #1E293B; border-radius: 8px; font-weight: bold;
                cursor: pointer; transition: all 0.2s; font-size: 14px; border: 2px solid transparent;
            }}
            .num-cell.selected-delete {{ background: #475569; color: white; border-color: #94A3B8; }}
            .num-cell.selected-fixed {{ background: #3B82F6; color: white; border-color: #60A5FA; }}
            .num-cell.selected-lucky {{ background: #D946EF; color: white; border-color: #F0ABFC; }}
            
            .control-panel {{ display: grid; grid-template-columns: 1fr 1fr 1.2fr; gap: 10px; margin-top: 20px; }}
            .select-game {{
                background: #1E293B; color: white; border: 2px solid #334155;
                padding: 12px; border-radius: 12px; font-weight: bold; outline: none;
            }}
            .action-btn {{
                padding: 12px; border-radius: 12px; border: none; font-weight: 900;
                cursor: pointer; transition: all 0.2s; font-size: 16px;
            }}
            .btn-start {{ background: #06B6D4; color: white; }}
            .btn-save {{ background: #3F6212; color: white; }}
            
            .result-area {{ margin-top: 20px; display: flex; flex-direction: column; gap: 10px; }}
            .result-row {{
                background: white; padding: 15px; border-radius: 12px;
                display: flex; justify-content: center; gap: 8px;
            }}
            .ball {{
                width: 35px; height: 35px; border-radius: 50%; display: flex;
                align-items: center; justify-content: center; color: white;
                font-weight: bold; font-size: 14px; text-shadow: 1px 1px 1px rgba(0,0,0,0.2);
            }}
        </style>
    </head>
    <body>
        <div class="nav-container">
            <button class="nav-btn" onclick="window.parent.postMessage({{type: 'nav', page: 'user'}}, '*')">⬅️</button>
            <button class="nav-btn" onclick="window.parent.postMessage({{type: 'nav', page: 'birthday'}}, '*')">📝 생일/행운수 관리</button>
        </div>

        <div class="tab-container">
            <div id="tab-delete" class="tab" onclick="setMode('delete')">삭제수</div>
            <div id="tab-fixed" class="tab" onclick="setMode('fixed')">고정수</div>
            <div id="tab-lucky" class="tab active" onclick="setMode('lucky')">행운수</div>
        </div>

        <div class="number-grid" id="numberGrid"></div>

        <div class="control-panel">
            <select class="select-game" id="gameCount">
                <option value="5">5게임</option>
                <option value="10">10게임</option>
                <option value="15">15게임</option>
                <option value="20">20게임</option>
            </select>
            <button class="action-btn btn-start" onclick="generateCombination()">조합시작</button>
            <button class="action-btn btn-save" onclick="saveResults()">결과저장</button>
        </div>

        <div class="result-area" id="resultArea"></div>

        <script>
            let currentMode = 'lucky';
            let selectedDelete = new Set();
            let selectedFixed = new Set();
            let luckyNumbers = new Set({js_lucky_array});
            let currentResults = [];

            function initGrid() {{
                const grid = document.getElementById('numberGrid');
                grid.innerHTML = '';
                for(let i=1; i<=45; i++) {{
                    const cell = document.createElement('div');
                    cell.className = 'num-cell';
                    if(selectedDelete.has(i)) cell.classList.add('selected-delete');
                    if(selectedFixed.has(i)) cell.classList.add('selected-fixed');
                    if(luckyNumbers.has(i)) cell.classList.add('selected-lucky');
                    cell.innerText = i;
                    cell.onclick = () => toggleNumber(i);
                    grid.appendChild(cell);
                }}
            }}

            function setMode(mode) {{
                currentMode = mode;
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.getElementById('tab-' + mode).classList.add('active');
            }}

            function toggleNumber(num) {{
                if(currentMode === 'delete') {{
                    if(selectedDelete.has(num)) selectedDelete.delete(num);
                    else {{
                        selectedDelete.add(num);
                        selectedFixed.delete(num);
                        luckyNumbers.delete(num);
                    }}
                }} else if(currentMode === 'fixed') {{
                    if(selectedFixed.has(num)) selectedFixed.delete(num);
                    else {{
                        if(selectedFixed.size >= 5) return;
                        selectedFixed.add(num);
                        selectedDelete.delete(num);
                        luckyNumbers.delete(num);
                    }}
                }} else if(currentMode === 'lucky') {{
                    if(luckyNumbers.has(num)) luckyNumbers.delete(num);
                    else {{
                        luckyNumbers.add(num);
                        selectedDelete.delete(num);
                        selectedFixed.delete(num);
                    }}
                }}
                initGrid();
            }}

            function generateCombination() {{
                const count = parseInt(document.getElementById('gameCount').value);
                const available = [];
                for(let i=1; i<=45; i++) {{
                    if(!selectedDelete.has(i)) available.push(i);
                }}

                currentResults = [];
                const resultArea = document.getElementById('resultArea');
                resultArea.innerHTML = '';

                for(let g=0; g<count; g++) {{
                    let game = Array.from(selectedFixed);
                    let pool = available.filter(n => !selectedFixed.has(n));
                    
                    // 행운수 우선 적용 로직
                    let luckyPool = pool.filter(n => luckyNumbers.has(n));
                    let normalPool = pool.filter(n => !luckyNumbers.has(n));
                    
                    // 행운수 섞기
                    luckyPool.sort(() => Math.random() - 0.5);
                    normalPool.sort(() => Math.random() - 0.5);
                    
                    let combinedPool = [...luckyPool, ...normalPool];
                    
                    while(game.length < 6 && combinedPool.length > 0) {{
                        game.push(combinedPool.shift());
                    }}
                    
                    game.sort((a,b) => a-b);
                    currentResults.push(game);
                    renderGame(game);
                }}
            }}

            function getBallColor(n) {{
                if(n <= 10) return '#fbc400';
                if(n <= 20) return '#69c8f2';
                if(n <= 30) return '#ff7272';
                if(n <= 40) return '#aaa';
                return '#b0d840';
            }}

            function renderGame(nums) {{
                const row = document.createElement('div');
                row.className = 'result-row';
                nums.forEach(n => {{
                    const ball = document.createElement('div');
                    ball.className = 'ball';
                    ball.style.backgroundColor = getBallColor(n);
                    ball.innerText = n;
                    row.appendChild(ball);
                }});
                document.getElementById('resultArea').appendChild(row);
            }}

            function saveResults() {{
                if(currentResults.length === 0) return;
                window.parent.postMessage({{
                    type: 'save_lotto',
                    results: currentResults
                }}, '*');
                alert('결과가 저장되었습니다!');
            }}

            window.addEventListener('message', function(e) {{
                if(e.data.type === 'nav') {{
                    // Streamlit reruns on query param change
                }}
            }});

            initGrid();
        </script>
    </body>
    </html>
    """

    components.html(thunder_ui_html, height=900, scrolling=True)

    # ─── 시스템 관리자 메뉴 (필요 시) ───
    with st.expander("🛠️ 시스템 관리자 메뉴"):
        if st.button("세션 초기화"):
            st.session_state.clear()
            st.rerun()

# 호출 확인
if __name__ == "__main__":
    render()
