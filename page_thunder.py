import streamlit as st
import streamlit.components.v1 as components
from birthday_db import get_user_birthdays
from lucky_numbers import calculate_all_lucky_numbers
import json

def render(admin_lucky=None):
    # ─── 데이터 로드 및 행운수 계산 ───
    if admin_lucky is None:
        admin_lucky = []
    user_id = st.session_state.get("user_id") or "guest_local"
    birthdays = get_user_birthdays(user_id)
    
    if birthdays:
        mmdd_list = [b["mmdd"] for b in birthdays]
        family_lucky = calculate_all_lucky_numbers(mmdd_list)
    else:
        family_lucky = []

    js_lucky_array = str(family_lucky)
    js_admin_lucky_array = json.dumps(list(reversed(admin_lucky)))
    has_birthdays = bool(birthdays)

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
        div[data-testid="stButton"] > button {
            background: linear-gradient(180deg, #ffffff 0%, #e2e8f0 100%) !important;
            border: none !important;
            border-radius: 12px !important;
            font-weight: bold !important;
            transition: transform 0.12s ease, box-shadow 0.12s ease !important;
            box-shadow:
                0 4px 0 #94a3b8,
                0 6px 14px rgba(0, 0, 0, 0.28),
                inset 0 1px 0 rgba(255, 255, 255, 0.55) !important;
        }
        div[data-testid="stButton"] > button:hover {
            box-shadow:
                0 5px 0 #94a3b8,
                0 9px 18px rgba(0, 0, 0, 0.34),
                inset 0 1px 0 rgba(255, 255, 255, 0.6) !important;
        }
        div[data-testid="stButton"] > button:active {
            transform: scale(0.97) !important;
            box-shadow:
                0 2px 0 #94a3b8,
                0 4px 8px rgba(0, 0, 0, 0.22),
                inset 0 1px 0 rgba(255, 255, 255, 0.45) !important;
        }
        </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="main-title">⚡ 번개조합</div>', unsafe_allow_html=True)

    ncol1, ncol2 = st.columns(2)
    with ncol1:
        if st.button("⬅️", key="th_nav_home", use_container_width=True):
            st.query_params.clear()
            st.rerun()
    with ncol2:
        if st.button("📝 생일/행운수 관리", key="th_nav_bday", use_container_width=True):
            st.query_params.clear()
            st.query_params["page"] = "birthday"
            st.rerun()

    components.html("""
    <script>
    (function() {
        function safeVibrate() {
            if (typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function') {
                try { navigator.vibrate(70); } catch (e) {}
            }
        }
        const doc = window.parent.document;
        doc.querySelectorAll('div[data-testid="stButton"] button').forEach(function(btn) {
            if (btn.dataset.thVibrateBound) return;
            const label = (btn.innerText || '').trim();
            if (label === '⬅️' || label.indexOf('생일/행운수 관리') !== -1) {
                btn.dataset.thVibrateBound = '1';
                btn.addEventListener('click', safeVibrate, { passive: true });
            }
        });
    })();
    </script>
    """, height=0)

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

            .tab-container {{
                display: flex; background: linear-gradient(180deg, #243044 0%, #1E293B 100%);
                padding: 5px; border-radius: 12px; margin-bottom: 15px; gap: 5px;
                box-shadow:
                    0 6px 0 #0b1220,
                    0 10px 20px rgba(0, 0, 0, 0.35),
                    inset 0 1px 0 rgba(255, 255, 255, 0.08);
                transition: box-shadow 0.12s ease;
            }}
            .tab {{
                flex: 1; padding: 12px; text-align: center; border-radius: 8px;
                cursor: pointer; font-weight: bold; font-size: 15px;
                transition: transform 0.12s ease, box-shadow 0.12s ease, background 0.12s ease, color 0.12s ease;
                box-shadow:
                    0 3px 0 rgba(0, 0, 0, 0.25),
                    0 4px 8px rgba(0, 0, 0, 0.2),
                    inset 0 1px 0 rgba(255, 255, 255, 0.12);
            }}
            .tab.active {{
                background: linear-gradient(180deg, #c084fc 0%, #A855F7 55%, #9333ea 100%);
                color: white;
                box-shadow:
                    0 4px 0 #6b21a8,
                    0 7px 14px rgba(168, 85, 247, 0.45),
                    inset 0 1px 0 rgba(255, 255, 255, 0.25);
            }}
            .tab:not(.active) {{
                color: #94A3B8;
                background: linear-gradient(180deg, #334155 0%, #1e293b 100%);
            }}
            .tab:not(.active):hover {{
                box-shadow:
                    0 4px 0 rgba(0, 0, 0, 0.3),
                    0 6px 12px rgba(0, 0, 0, 0.28),
                    inset 0 1px 0 rgba(255, 255, 255, 0.15);
            }}
            .tab:active {{ transform: scale(0.97); }}

            .number-grid {{
                display: grid; grid-template-columns: repeat(7, 1fr); gap: 8px;
                background: linear-gradient(180deg, #243044 0%, #1E293B 100%);
                padding: 15px; border-radius: 16px; margin-bottom: 20px;
                box-shadow:
                    0 6px 0 #0b1220,
                    0 10px 20px rgba(0, 0, 0, 0.35),
                    inset 0 1px 0 rgba(255, 255, 255, 0.08);
            }}
            .num-cell {{
                aspect-ratio: 1; display: flex; align-items: center; justify-content: center;
                background: linear-gradient(180deg, #ffffff 0%, #e2e8f0 100%);
                color: #1E293B; border-radius: 8px; font-weight: bold;
                cursor: pointer; font-size: 14px; border: 2px solid transparent;
                transition: transform 0.12s ease, box-shadow 0.12s ease, background 0.12s ease, color 0.12s ease;
                box-shadow:
                    0 3px 0 #94a3b8,
                    0 5px 10px rgba(0, 0, 0, 0.22),
                    inset 0 1px 0 rgba(255, 255, 255, 0.55);
            }}
            .num-cell:hover {{
                box-shadow:
                    0 4px 0 #94a3b8,
                    0 7px 14px rgba(0, 0, 0, 0.28),
                    inset 0 1px 0 rgba(255, 255, 255, 0.6);
            }}
            .num-cell:active {{ transform: scale(0.97); }}
            .num-cell.selected-delete {{
                background: linear-gradient(180deg, #64748b 0%, #475569 100%);
                color: white; border-color: #94A3B8;
                box-shadow:
                    0 3px 0 #334155,
                    0 5px 10px rgba(0, 0, 0, 0.28),
                    inset 0 1px 0 rgba(255, 255, 255, 0.2);
            }}
            .num-cell.selected-fixed {{
                background: linear-gradient(180deg, #60a5fa 0%, #3B82F6 100%);
                color: white; border-color: #60A5FA;
                box-shadow:
                    0 3px 0 #1d4ed8,
                    0 5px 10px rgba(59, 130, 246, 0.35),
                    inset 0 1px 0 rgba(255, 255, 255, 0.25);
            }}
            .num-cell.selected-lucky {{
                background: linear-gradient(180deg, #e879f9 0%, #D946EF 100%);
                color: white; border-color: #F0ABFC;
                box-shadow:
                    0 3px 0 #a21caf,
                    0 5px 10px rgba(217, 70, 239, 0.35),
                    inset 0 1px 0 rgba(255, 255, 255, 0.25);
            }}
            
            .control-panel {{ display: grid; grid-template-columns: 1fr 1fr 1.2fr; gap: 10px; margin-top: 20px; }}
            .select-game {{
                background: linear-gradient(180deg, #334155 0%, #1E293B 100%);
                color: white; border: 2px solid #334155;
                padding: 12px; border-radius: 12px; font-weight: bold; outline: none;
                transition: box-shadow 0.12s ease, transform 0.12s ease;
                box-shadow:
                    0 4px 0 #0b1220,
                    0 6px 12px rgba(0, 0, 0, 0.28),
                    inset 0 1px 0 rgba(255, 255, 255, 0.1);
            }}
            .select-game:active {{ transform: scale(0.97); }}
            .action-btn {{
                padding: 12px; border-radius: 12px; border: none; font-weight: 900;
                cursor: pointer; font-size: 16px;
                transition: transform 0.12s ease, box-shadow 0.12s ease, background 0.12s ease;
                box-shadow:
                    0 4px 0 rgba(0, 0, 0, 0.35),
                    0 7px 14px rgba(0, 0, 0, 0.28),
                    inset 0 1px 0 rgba(255, 255, 255, 0.25);
            }}
            .action-btn:hover {{
                box-shadow:
                    0 5px 0 rgba(0, 0, 0, 0.38),
                    0 9px 18px rgba(0, 0, 0, 0.32),
                    inset 0 1px 0 rgba(255, 255, 255, 0.3);
            }}
            .action-btn:active {{ transform: scale(0.97); }}
            .btn-start {{
                background: linear-gradient(180deg, #22d3ee 0%, #06B6D4 55%, #0891b2 100%);
                color: white;
                box-shadow:
                    0 4px 0 #0e7490,
                    0 7px 14px rgba(6, 182, 212, 0.4),
                    inset 0 1px 0 rgba(255, 255, 255, 0.3);
            }}
            .btn-save {{
                background: linear-gradient(180deg, #65a30d 0%, #3F6212 55%, #365314 100%);
                color: white;
                box-shadow:
                    0 4px 0 #1a2e05,
                    0 7px 14px rgba(63, 98, 18, 0.4),
                    inset 0 1px 0 rgba(255, 255, 255, 0.2);
            }}
            
            .result-area {{ margin-top: 20px; display: flex; flex-direction: column; gap: 10px; }}
            .result-row {{
                background: linear-gradient(180deg, #ffffff 0%, #f1f5f9 100%);
                padding: 15px; border-radius: 12px;
                display: flex; justify-content: center; gap: 8px;
                box-shadow:
                    0 4px 0 #cbd5e1,
                    0 7px 14px rgba(0, 0, 0, 0.18),
                    inset 0 1px 0 rgba(255, 255, 255, 0.7);
            }}
            .ball {{
                width: 35px; height: 35px; border-radius: 50%; display: flex;
                align-items: center; justify-content: center; color: white;
                font-weight: bold; font-size: 14px; text-shadow: 1px 1px 1px rgba(0,0,0,0.2);
            }}
        </style>
    </head>
    <body>
        <div class="tab-container">
            <div id="tab-delete" class="tab active" onclick="setMode('delete')">삭제수</div>
            <div id="tab-fixed" class="tab" onclick="setMode('fixed')">고정수</div>
            <div id="tab-lucky" class="tab" onclick="setMode('lucky')">행운수</div>
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
            // ── 1) 초기 상태: 삭제수 탭, 모든 선택 비움, DB 행운수는 보관만 ──
            let currentMode = 'delete';
            let selectedDelete = new Set();
            let selectedFixed = new Set();
            let luckyNumbers = new Set();
            const registeredFamilyLucky = {js_lucky_array};
            const adminLuckyOrdered = {js_admin_lucky_array};
            const hasBirthdays = {'true' if has_birthdays else 'false'};
            let luckyLoaded = false;
            let currentResults = [];

            function safeVibrate() {{
                if (typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function') {{
                    try {{ navigator.vibrate(70); }} catch (e) {{}}
                }}
            }}

            function showLuckyWarn(show) {{
                let el = document.getElementById('luckyWarn');
                if (!el) {{
                    el = document.createElement('p');
                    el.id = 'luckyWarn';
                    el.style.cssText = 'color:#fbbf24;text-align:center;margin-bottom:10px;';
                    el.textContent = '생일/행운수 관리에서 먼저 등록하세요.';
                    document.getElementById('numberGrid').parentNode.insertBefore(
                        el, document.getElementById('numberGrid')
                    );
                }}
                el.style.display = show ? 'block' : 'none';
            }}

            // ── 2) initGrid: 최초 로드 포함 항상 기본 흰색, 핑크는 luckyLoaded 이후만 ──
            function initGrid() {{
                const grid = document.getElementById('numberGrid');
                grid.innerHTML = '';
                for (let i = 1; i <= 45; i++) {{
                    const cell = document.createElement('div');
                    cell.className = 'num-cell';
                    if (selectedDelete.has(i)) {{
                        cell.classList.add('selected-delete');
                    }}
                    if (selectedFixed.has(i)) {{
                        cell.classList.add('selected-fixed');
                    }}
                    if (luckyLoaded && luckyNumbers.has(i)) {{
                        cell.classList.add('selected-lucky');
                    }}
                    cell.innerText = i;
                    cell.onclick = () => toggleNumber(i);
                    grid.appendChild(cell);
                }}
            }}

            // ── 3) setMode: 행운수 탭 클릭 시에만 DB 데이터 로드 후 핑크 렌더링 ──
            function setMode(mode) {{
                safeVibrate();
                currentMode = mode;
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.getElementById('tab-' + mode).classList.add('active');

                if (mode === 'lucky') {{
                    if (!luckyLoaded) {{
                        luckyLoaded = true;
                        if (hasBirthdays && registeredFamilyLucky.length > 0) {{
                            luckyNumbers = new Set(registeredFamilyLucky);
                            showLuckyWarn(false);
                        }} else {{
                            luckyNumbers = new Set();
                            showLuckyWarn(true);
                        }}
                    }}
                }} else {{
                    showLuckyWarn(false);
                }}

                initGrid();
            }}

            function toggleNumber(num) {{
                safeVibrate();
                if (currentMode === 'delete') {{
                    if (selectedDelete.has(num)) {{
                        selectedDelete.delete(num);
                    }} else {{
                        selectedDelete.add(num);
                        selectedFixed.delete(num);
                        luckyNumbers.delete(num);
                    }}
                }} else if (currentMode === 'fixed') {{
                    if (selectedFixed.has(num)) {{
                        selectedFixed.delete(num);
                    }} else {{
                        if (selectedFixed.size >= 5) return;
                        selectedFixed.add(num);
                        selectedDelete.delete(num);
                        luckyNumbers.delete(num);
                    }}
                }} else if (currentMode === 'lucky') {{
                    if (!luckyLoaded) return;
                    if (luckyNumbers.has(num)) {{
                        luckyNumbers.delete(num);
                    }} else {{
                        luckyNumbers.add(num);
                        selectedDelete.delete(num);
                        selectedFixed.delete(num);
                    }}
                }}
                initGrid();
            }}

            function generateCombination() {{
                safeVibrate();
                function pickLuckyCount() {{
                    const r = Math.random();
                    if (r < 0.30) return 0;
                    if (r < 0.65) return 1;
                    if (r < 0.90) return 2;
                    return 3;
                }}

                function pickAdminCount() {{
                    const r = Math.random();
                    if (r < 0.40) return 0;
                    if (r < 0.80) return 1;
                    return 2;
                }}

                function pickWeightedFromOrdered(count, orderedList, poolSet, alreadyInGame) {{
                    const picked = [];
                    let remaining = orderedList.filter(
                        n => poolSet.has(n) && !alreadyInGame.has(n)
                    );

                    for (let p = 0; p < count && remaining.length > 0; p++) {{
                        const weights = remaining.map(
                            n => orderedList.length - orderedList.indexOf(n)
                        );
                        const total = weights.reduce((a, b) => a + b, 0);
                        let r = Math.random() * total;
                        let cum = 0;
                        let chosenIdx = 0;

                        for (let i = 0; i < remaining.length; i++) {{
                            cum += weights[i];
                            if (r < cum) {{
                                chosenIdx = i;
                                break;
                            }}
                        }}

                        picked.push(remaining[chosenIdx]);
                        remaining.splice(chosenIdx, 1);
                    }}

                    return picked;
                }}

                const count = parseInt(document.getElementById('gameCount').value);
                const available = [];
                for (let i = 1; i <= 45; i++) {{
                    if (!selectedDelete.has(i)) available.push(i);
                }}

                currentResults = [];
                const resultArea = document.getElementById('resultArea');
                resultArea.innerHTML = '';

                for (let g = 0; g < count; g++) {{
                    setTimeout(() => {{
                        let game = Array.from(selectedFixed);
                        const gameSet = new Set(game);
                        let pool = available.filter(n => !selectedFixed.has(n));
                        const poolSet = new Set(pool);

                        let luckyCandidates = pool.filter(n => luckyNumbers.has(n));

                        let targetLucky = pickLuckyCount();
                        targetLucky = Math.min(targetLucky, luckyCandidates.length, 6 - game.length);

                        luckyCandidates.sort(() => Math.random() - 0.5);
                        let pickedLucky = luckyCandidates.slice(0, targetLucky);
                        game = game.concat(pickedLucky);
                        pickedLucky.forEach(n => gameSet.add(n));

                        let targetAdmin = pickAdminCount();
                        targetAdmin = Math.min(targetAdmin, 6 - game.length);
                        let pickedAdmin = pickWeightedFromOrdered(
                            targetAdmin, adminLuckyOrdered, poolSet, gameSet
                        );
                        game = game.concat(pickedAdmin);
                        pickedAdmin.forEach(n => gameSet.add(n));

                        let remainingPool = pool.filter(n => !gameSet.has(n));
                        remainingPool.sort(() => Math.random() - 0.5);

                        while (game.length < 6 && remainingPool.length > 0) {{
                            game.push(remainingPool.shift());
                        }}

                        game.sort((a, b) => a - b);
                        currentResults.push(game);
                        renderGame(game);
                    }}, g * 2000);
                }}
            }}

            function getBallColor(n) {{
                if (n <= 10) return '#fbc400';
                if (n <= 20) return '#69c8f2';
                if (n <= 30) return '#ff7272';
                if (n <= 40) return '#aaa';
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
                safeVibrate();
                if (currentResults.length === 0) return;
                window.parent.postMessage({{
                    type: 'save_lotto',
                    results: currentResults
                }}, '*');
                alert('결과가 저장되었습니다!');
            }}

            window.addEventListener('message', function(e) {{
                if (e.data.type === 'nav') {{
                    // Streamlit reruns on query param change
                }}
            }});

            // ── 4) 최초 렌더: setMode 호출 없이 빈 격자만 그림 ──
            initGrid();
        </script>
    </body>
    </html>
    """

    components.html(thunder_ui_html, height=900, scrolling=True)

# 호출 확인
if __name__ == "__main__":
    render()
