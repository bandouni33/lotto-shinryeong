import streamlit as st
import streamlit.components.v1 as components
from birthday_db import get_user_birthdays
from lucky_numbers import calculate_all_lucky_numbers
from lotto_stats import get_thunder_filter_config
import json
import uuid

from auth_kakao import current_member_id
from user_scope import current_birthday_scope, init_guest_scope, thunder_reveal_storage_suffix
from wallet_db import calc_thunder_cost
from wallet_ui import deduct_after_result, points_notice_dialog

# ── 번개조합 선택 색상 단일 정의 (삭제수/고정수/행운수) ──
# 이 3가지 색상은 반드시 여기서만 정의합니다. 다른 파일·CSS 블록에 중복 정의하지 마세요.
# 레이아웃·진동·통계 등 다른 작업을 할 때도 이 값을 임의로 변경하지 마세요.
THUNDER_COLOR_DELETE = "#64748B"   # 삭제수: 회색
THUNDER_COLOR_FIXED = "#FF9800"    # 고정수: 오렌지
THUNDER_COLOR_LUCKY = "#F0ABFC"    # 행운수: 연핑크


def render(admin_lucky=None):
    init_guest_scope()
    # ─── 데이터 로드 및 행운수 계산 ───
    if admin_lucky is None:
        admin_lucky = []
    user_id = current_birthday_scope()
    birthdays = get_user_birthdays(user_id)
    
    if birthdays:
        mmdd_list = [b["mmdd"] for b in birthdays]
        family_lucky = calculate_all_lucky_numbers(mmdd_list)
    else:
        family_lucky = []

    js_lucky_array = str(family_lucky)
    js_admin_lucky_array = json.dumps(list(reversed(admin_lucky)))
    js_filter_config = json.dumps(get_thunder_filter_config())
    has_birthdays = bool(birthdays)

    if st.query_params.get("th_action") == "gen":
        try:
            g = int(st.query_params.get("th_games", 5))
        except ValueError:
            g = 5
        for k in ("th_action", "th_games"):
            if k in st.query_params:
                del st.query_params[k]
        from wallet_ui import ensure_member_or_banner

        if ensure_member_or_banner(
            resume="open_thunder_dialog",
            reason="번개조합 생성을 위해 간편인증이 필요합니다.",
            resume_data={"games": g},
        ):
            st.session_state["open_thunder_dialog"] = True
            st.session_state["open_thunder_dialog_games"] = g
        st.rerun()

    if st.query_params.get("th_deduct"):
        try:
            g = int(st.query_params.get("th_deduct"))
        except ValueError:
            g = 5
        if "th_deduct" in st.query_params:
            del st.query_params["th_deduct"]
        st.session_state.pop("thunder_approved", None)
        mid = current_member_id()
        if mid:
            ref = f"thunder:done:{mid}:{uuid.uuid4().hex[:10]}"
            if deduct_after_result(mid, "thunder", ref, game_count=g):
                st.success(f"조합 완료 · {calc_thunder_cost(g):,}P 차감되었습니다.")
            else:
                st.error("적립금 차감에 실패했습니다.")
        cur_ver = st.session_state.get("thunder_reveal_version", 1)
        st.session_state["thunder_reveal_version"] = (cur_ver % 3) + 1
        st.rerun()

    if st.session_state.get("open_thunder_dialog"):
        g = int(st.session_state.get("open_thunder_dialog_games", 5))
        result = points_notice_dialog("thunder", game_count=g)
        if result == "confirm":
            st.session_state["open_thunder_dialog"] = False
            st.session_state["thunder_approved"] = True
            st.session_state["thunder_auto_run"] = g
            st.rerun()
        elif result == "cancel":
            st.session_state["open_thunder_dialog"] = False

    th_auto_run = st.session_state.pop("thunder_auto_run", None)
    th_approved_js = "true" if st.session_state.get("thunder_approved") else "false"
    th_auto_run_js = str(th_auto_run) if th_auto_run else "null"
    reveal_version_js = str(st.session_state.get("thunder_reveal_version", 1))
    reveal_scope_js = thunder_reveal_storage_suffix().replace("\\", "\\\\").replace("'", "\\'")

    # ─── 커스텀 CSS ───
    st.markdown("""
        <style>
        /* PC 녹화용: 480px 이상 뷰포트에서만 폭 제한 (모바일 <480px 미적용) */
        @media (min-width: 480px) {
            .block-container {
                max-width: 480px !important;
                margin-left: auto !important;
                margin-right: auto !important;
                padding-left: 12px !important;
                padding-right: 12px !important;
            }
            div[data-testid="stHtml"] iframe,
            div[data-testid="stHtmlIFrame"] iframe {
                max-width: 480px !important;
                margin-left: auto !important;
                margin-right: auto !important;
                display: block !important;
            }
        }
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
            color: #0F172A !important;
            font-weight: 800 !important;
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

    st.markdown('<div class="main-title">⚡ 번\u200b\u200b개조합</div>', unsafe_allow_html=True)

    ncol1, ncol2 = st.columns(2)
    with ncol1:
        if st.button("⬅️ 홈", key="th_nav_home_6n36s5", use_container_width=True):
            st.query_params.clear()
            st.rerun()
    with ncol2:
        if st.button("📝 생일/행운수 관리", key="th_nav_bday_6n36s5", use_container_width=True):
            st.query_params.clear()
            st.query_params["page"] = "birthday"
            st.rerun()

    components.html("""
    <script>
    window.addEventListener('message', function(e) {
        const d = e.data || {};
        if (d.type === 'thunder_generate') {
            const u = new URL(window.parent.location.href);
            u.searchParams.set('page', 'thunder');
            u.searchParams.set('th_action', 'gen');
            u.searchParams.set('th_games', String(d.count));
            window.parent.location.href = u.toString();
        }
        if (d.type === 'thunder_complete') {
            const u = new URL(window.parent.location.href);
            u.searchParams.set('page', 'thunder');
            u.searchParams.set('th_deduct', String(d.count));
            window.parent.location.href = u.toString();
        }
    });
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
        doc.querySelectorAll('div[data-testid="stButton"] button').forEach(function(btn) {
            if (btn.dataset.thVibrateBound) return;
            const label = (btn.innerText || '').trim();
            if (label.indexOf('홈') !== -1 || label.indexOf('생일/행운수 관리') !== -1) {
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
            :root {{
                --th-delete: {THUNDER_COLOR_DELETE};
                --th-fixed: {THUNDER_COLOR_FIXED};
                --th-lucky: {THUNDER_COLOR_LUCKY};
            }}
            body {{ background-color: #0F172A; color: #F8FAFC; margin: 0 auto; padding: 10px; overflow-x: hidden; width: 100%; max-width: 480px; }}

            /* PC: 부모 창 너비 기준 (iframe 내부 media query는 iframe 폭만 보므로 JS로 pc-layout 부여) */
            html.pc-layout .number-grid {{
                grid-template-columns: repeat(7, 42px);
                justify-content: center;
                width: fit-content;
                max-width: 100%;
                margin-left: auto;
                margin-right: auto;
                min-height: 372px;
            }}
            html.pc-layout .num-cell {{
                width: 42px;
                height: 42px;
                aspect-ratio: unset;
                font-size: 13px;
            }}
            html.pc-layout .tab-container,
            html.pc-layout .control-panel,
            html.pc-layout .result-area {{
                max-width: 360px;
                margin-left: auto;
                margin-right: auto;
            }}

            .lucky-warn-slot {{
                min-height: 22px;
                margin-bottom: 8px;
            }}
            #luckyWarn {{
                color: #fbbf24;
                text-align: center;
                margin: 0;
                font-size: 13px;
                line-height: 22px;
            }}

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
                cursor: pointer; font-weight: 900; font-size: 15px;
                transition: transform 0.12s ease, box-shadow 0.12s ease, background 0.12s ease, color 0.12s ease;
                box-shadow:
                    0 3px 0 rgba(0, 0, 0, 0.25),
                    0 4px 8px rgba(0, 0, 0, 0.2),
                    inset 0 1px 0 rgba(255, 255, 255, 0.12);
            }}
            .tab.active {{
                background: linear-gradient(180deg, #c084fc 0%, #A855F7 55%, #9333ea 100%);
                color: #FFFFFF;
                text-shadow: 0 1px 2px rgba(0, 0, 0, 0.35);
                box-shadow:
                    0 4px 0 #6b21a8,
                    0 7px 14px rgba(168, 85, 247, 0.45),
                    inset 0 1px 0 rgba(255, 255, 255, 0.25);
            }}
            .tab:not(.active) {{
                color: #F1F5F9;
                background: linear-gradient(180deg, #334155 0%, #1e293b 100%);
                text-shadow: 0 1px 2px rgba(0, 0, 0, 0.45);
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
                color: #0F172A; border-radius: 8px; font-weight: 900;
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
            /* 선택 색상: :root 변수만 사용 (Python 상수 THUNDER_COLOR_* 와 동기화) */
            .num-cell.selected-delete {{
                background: var(--th-delete);
                color: #FFFFFF; border-color: var(--th-delete);
                text-shadow: 0 1px 2px rgba(0, 0, 0, 0.35);
                box-shadow:
                    0 3px 0 #334155,
                    0 5px 10px rgba(0, 0, 0, 0.28),
                    inset 0 1px 0 rgba(255, 255, 255, 0.2);
            }}
            .num-cell.selected-fixed {{
                background: var(--th-fixed);
                color: #FFFFFF; border-color: var(--th-fixed);
                text-shadow: 0 1px 2px rgba(0, 0, 0, 0.35);
                box-shadow:
                    0 3px 0 #c2410c,
                    0 5px 10px rgba(255, 152, 0, 0.35),
                    inset 0 1px 0 rgba(255, 255, 255, 0.25);
            }}
            .num-cell.selected-lucky {{
                background: var(--th-lucky);
                color: #831843; border-color: var(--th-lucky);
                text-shadow: 0 1px 1px rgba(255, 255, 255, 0.45);
                box-shadow:
                    0 3px 0 #c026d3,
                    0 5px 10px rgba(240, 171, 252, 0.45),
                    inset 0 1px 0 rgba(255, 255, 255, 0.35);
            }}
            
            .control-panel {{ display: grid; grid-template-columns: 1fr 1fr 1.2fr; gap: 10px; margin-top: 20px; }}
            .select-game {{
                background: linear-gradient(180deg, #334155 0%, #1E293B 100%);
                color: #F8FAFC; border: 2px solid #334155;
                padding: 12px; border-radius: 12px; font-weight: 900; outline: none;
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
                color: #FFFFFF;
                text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
                box-shadow:
                    0 4px 0 #0e7490,
                    0 7px 14px rgba(6, 182, 212, 0.4),
                    inset 0 1px 0 rgba(255, 255, 255, 0.3);
            }}
            .btn-save {{
                background: linear-gradient(180deg, #65a30d 0%, #3F6212 55%, #365314 100%);
                color: #FFFFFF;
                text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
                box-shadow:
                    0 4px 0 #1a2e05,
                    0 7px 14px rgba(63, 98, 18, 0.4),
                    inset 0 1px 0 rgba(255, 255, 255, 0.2);
            }}
            
            .result-area {{ margin-top: 20px; display: flex; flex-direction: column; gap: 10px; }}
            .result-row {{
                background: linear-gradient(145deg, #0A0A0F 0%, #050508 55%, #0D0D1A 100%);
                padding: 15px; border-radius: 12px;
                border: 1px solid #1A1A2E;
                display: flex; justify-content: center; gap: 8px;
                box-shadow:
                    0 4px 0 #000000,
                    0 7px 16px rgba(0, 0, 0, 0.55),
                    inset 0 1px 0 rgba(255, 255, 255, 0.04);
            }}
            .result-row.reveal {{
                opacity: 0;
                will-change: transform, opacity;
                animation: resultRowReveal 1s cubic-bezier(0.34, 1.45, 0.64, 1) forwards;
            }}
            /* 버전1: 슬라이드 업 + 볼 글로우 */
            /* 메인화면(user_page) 로또볼 3D 스타일 재사용 */
            .ball {{
                width: 35px; height: 35px; border-radius: 50%; display: flex;
                align-items: center; justify-content: center; color: white;
                font-weight: 900; font-size: 15px;
                text-shadow: 1px 1px 2px rgba(0,0,0,0.8);
                box-shadow:
                    2px 3px 5px rgba(0,0,0,0.5),
                    inset -3px -3px 5px rgba(0,0,0,0.4),
                    inset 2px 2px 4px rgba(255,255,255,0.6);
            }}
            .result-row.reveal .ball {{
                will-change: box-shadow, filter;
                animation: ballGlowReveal 1.1s ease-out forwards;
            }}
            .result-row.reveal .ball:nth-child(1) {{ animation-delay: 0.04s; }}
            .result-row.reveal .ball:nth-child(2) {{ animation-delay: 0.08s; }}
            .result-row.reveal .ball:nth-child(3) {{ animation-delay: 0.12s; }}
            .result-row.reveal .ball:nth-child(4) {{ animation-delay: 0.16s; }}
            .result-row.reveal .ball:nth-child(5) {{ animation-delay: 0.20s; }}
            .result-row.reveal .ball:nth-child(6) {{ animation-delay: 0.24s; }}

            /* 버전2·3 전용 (버전1 reveal CSS와 완전 분리 — JS Web Animations 구동) */
            .mystic-v2-row, .mystic-v3-row {{
                position: relative;
                overflow: visible;
            }}
            .mystic-v2-track, .mystic-v3-track {{
                display: flex;
                justify-content: center;
                gap: 8px;
                position: relative;
                z-index: 2;
            }}
            .mystic-v2-aura {{
                position: absolute;
                inset: 0;
                border-radius: 12px;
                background: linear-gradient(180deg, rgba(2, 6, 23, 0.9) 0%, rgba(6, 182, 212, 0.35) 45%, rgba(168, 85, 247, 0.65) 100%);
                z-index: 0;
                pointer-events: none;
                transform-origin: bottom center;
            }}
            .mystic-v2-spark {{
                position: absolute;
                width: 6px;
                height: 6px;
                border-radius: 50%;
                background: #e0f2fe;
                box-shadow: 0 0 10px 3px rgba(34, 211, 238, 0.9);
                pointer-events: none;
                z-index: 1;
            }}
            .mystic-v3-rift {{
                position: absolute;
                inset: -6px;
                border-radius: 16px;
                background: radial-gradient(ellipse at center, rgba(168, 85, 247, 0.55) 0%, rgba(15, 23, 42, 0) 72%);
                z-index: 0;
                pointer-events: none;
            }}
            .mystic-v3-row .ball {{
                will-change: transform, opacity, filter;
            }}

            @keyframes resultRowReveal {{
                0% {{
                    opacity: 0;
                    transform: translateY(42px);
                }}
                45% {{
                    opacity: 0.75;
                    transform: translateY(-7px);
                }}
                62% {{
                    opacity: 1;
                    transform: translateY(4px);
                }}
                78% {{
                    transform: translateY(-3px);
                }}
                90% {{
                    transform: translateY(1px);
                }}
                100% {{
                    opacity: 1;
                    transform: translateY(0);
                }}
            }}
            @keyframes ballGlowReveal {{
                0% {{
                    filter: brightness(0.65);
                    box-shadow: 0 0 0 rgba(255, 255, 255, 0);
                }}
                28% {{
                    filter: brightness(1.2);
                    box-shadow:
                        0 0 14px 5px rgba(255, 255, 255, 0.75),
                        0 0 26px 10px rgba(168, 85, 247, 0.42);
                }}
                55% {{
                    filter: brightness(1.08);
                    box-shadow:
                        0 0 18px 7px rgba(255, 255, 255, 0.9),
                        0 0 32px 12px rgba(192, 132, 252, 0.55);
                }}
                78% {{
                    filter: brightness(1.02);
                    box-shadow:
                        0 0 10px 3px rgba(255, 255, 255, 0.45),
                        0 0 18px 6px rgba(168, 85, 247, 0.22);
                }}
                100% {{
                    filter: brightness(1);
                    box-shadow:
                        2px 3px 5px rgba(0,0,0,0.5),
                        inset -3px -3px 5px rgba(0,0,0,0.4),
                        inset 2px 2px 4px rgba(255,255,255,0.6);
                }}
            }}
        </style>
    </head>
    <body>
        <div class="tab-container">
            <div id="tab-delete" class="tab active" onclick="setMode('delete')">삭\u200b제수</div>
            <div id="tab-fixed" class="tab" onclick="setMode('fixed')">고\u200b정수</div>
            <div id="tab-lucky" class="tab" onclick="setMode('lucky')">행\u200b운수</div>
        </div>

        <div class="lucky-warn-slot">
            <p id="luckyWarn" style="display:none;">생일/행운수 관리에서 먼저 등록하세요.</p>
        </div>

        <div class="number-grid" id="numberGrid"></div>

        <div class="control-panel">
            <select class="select-game" id="gameCount">
                <option value="5">5게임</option>
                <option value="10">10게임</option>
                <option value="15">15게임</option>
                <option value="20">20게임</option>
            </select>
            <button class="action-btn btn-start" onclick="generateCombination()">조\u200b합시작</button>
            <button class="action-btn btn-save" onclick="saveResults()">결\u200b과저장</button>
        </div>

        <div class="result-area" id="resultArea"></div>

        <script>
            // ── 1) 초기 상태: 삭제수 탭, 모든 선택 비움, DB 행운수는 보관만 ──
            let thunderApproved = {th_approved_js};
            const autoRunCount = {th_auto_run_js};

            let selectedDelete = new Set();
            let selectedFixed = new Set();
            let luckyNumbers = new Set();
            const registeredFamilyLucky = {js_lucky_array};
            const adminLuckyOrdered = {js_admin_lucky_array};
            const thunderFilter = {js_filter_config};
            const hasBirthdays = {'true' if has_birthdays else 'false'};
            let luckyLoaded = false;
            let currentResults = [];
            const activeRevealVersion = {reveal_version_js};
            const REVEAL_STORE = 'thunder_reveal_cycle_{reveal_scope_js}';
            let runRevealVersion = activeRevealVersion;
            let genRunId = 0;
            let isGenerating = false;
            let activeGenTimers = [];
            let activeGenIntervals = [];

            function clearActiveGeneration() {{
                activeGenTimers.forEach((id) => clearTimeout(id));
                activeGenTimers = [];
                activeGenIntervals.forEach((id) => clearInterval(id));
                activeGenIntervals = [];
            }}

            function setStartButtonEnabled(enabled) {{
                const startBtn = document.querySelector('.btn-start');
                if (startBtn) startBtn.disabled = !enabled;
            }}

            try {{
                if (!localStorage.getItem(REVEAL_STORE)) {{
                    localStorage.setItem(REVEAL_STORE, String(activeRevealVersion));
                }}
            }} catch (e) {{}}

            function consumeRevealVersion() {{
                let v = 1;
                try {{
                    v = parseInt(localStorage.getItem(REVEAL_STORE) || String(activeRevealVersion), 10);
                }} catch (e) {{}}
                if (isNaN(v) || v < 1 || v > 3) v = 1;
                const current = v;
                const next = (v % 3) + 1;
                try {{ localStorage.setItem(REVEAL_STORE, String(next)); }} catch (e) {{}}
                return current;
            }}

            function safeVibrate() {{
                if (typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function') {{
                    try {{ navigator.vibrate(70); }} catch (e) {{}}
                }}
            }}

            function showLuckyWarn(show) {{
                const el = document.getElementById('luckyWarn');
                if (el) el.style.display = show ? 'block' : 'none';
            }}

            function applyPcLayout() {{
                let parentW = window.innerWidth;
                try {{
                    parentW = window.parent.innerWidth || parentW;
                }} catch (e) {{}}
                if (parentW >= 480) {{
                    document.documentElement.classList.add('pc-layout');
                }} else {{
                    document.documentElement.classList.remove('pc-layout');
                }}
            }}
            applyPcLayout();
            window.addEventListener('resize', applyPcLayout);

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

            function longestConsecutiveRun(nums) {{
                if (nums.length === 0) return 0;
                const sorted = [...nums].sort((a, b) => a - b);
                let best = 1;
                let cur = 1;
                for (let i = 1; i < sorted.length; i++) {{
                    if (sorted[i] === sorted[i - 1] + 1) {{
                        cur += 1;
                        best = Math.max(best, cur);
                    }} else {{
                        cur = 1;
                    }}
                }}
                return best;
            }}

            function maxDecadeCount(nums) {{
                const bands = [
                    [1, 9], [10, 19], [20, 29], [30, 39], [40, 45]
                ];
                let best = 0;
                for (const [lo, hi] of bands) {{
                    const c = nums.filter(n => n >= lo && n <= hi).length;
                    best = Math.max(best, c);
                }}
                return best;
            }}

            function maxLastDigitCount(nums) {{
                const counts = {{}};
                nums.forEach(n => {{
                    const d = n % 10;
                    counts[d] = (counts[d] || 0) + 1;
                }});
                return Math.max(0, ...Object.values(counts));
            }}

            function violatesNaturalFilter(nums) {{
                const t = thunderFilter.thresholds;
                if (longestConsecutiveRun(nums) >= t.max_consecutive_run) return true;
                if (maxDecadeCount(nums) >= t.max_decade_count) return true;
                if (maxLastDigitCount(nums) >= t.max_last_digit_count) return true;
                return false;
            }}

            function fillRandomSlots(fixedArr, availablePool) {{
                let game = fixedArr.slice();
                const gameSet = new Set(game);
                const pool = availablePool.filter(n => !selectedFixed.has(n));
                const poolSet = new Set(pool);

                let luckyCandidates = pool.filter(n => luckyNumbers.has(n));
                let targetLucky = pickLuckyCount();
                targetLucky = Math.min(targetLucky, luckyCandidates.length, 6 - game.length);
                luckyCandidates.sort(() => Math.random() - 0.5);
                const pickedLucky = luckyCandidates.slice(0, targetLucky);
                game = game.concat(pickedLucky);
                pickedLucky.forEach(n => gameSet.add(n));

                let targetAdmin = pickAdminCount();
                targetAdmin = Math.min(targetAdmin, 6 - game.length);
                const pickedAdmin = pickWeightedFromOrdered(
                    targetAdmin, adminLuckyOrdered, poolSet, gameSet
                );
                game = game.concat(pickedAdmin);
                pickedAdmin.forEach(n => gameSet.add(n));

                let remainingPool = pool.filter(n => !gameSet.has(n));
                remainingPool.sort(() => Math.random() - 0.5);
                while (game.length < 6 && remainingPool.length > 0) {{
                    game.push(remainingPool.shift());
                }}
                return game;
            }}

            function buildOneGame(availablePool) {{
                const fixedArr = Array.from(selectedFixed);
                const fixedExempt = violatesNaturalFilter(fixedArr);
                const maxRetries = thunderFilter.thresholds.max_retries;
                let game = fixedArr.slice();
                let attempts = 0;
                let gaveUp = false;

                if (fixedArr.length >= 6) {{
                    return {{ game: fixedArr.slice().sort((a, b) => a - b), attempts: 0, gaveUp: false }};
                }}

                do {{
                    game = fillRandomSlots(fixedArr, availablePool);
                    attempts += 1;
                    if (fixedExempt) break;
                    if (!violatesNaturalFilter(game)) break;
                }} while (attempts < maxRetries);

                if (!fixedExempt && violatesNaturalFilter(game) && attempts >= maxRetries) {{
                    gaveUp = true;
                }}

                game.sort((a, b) => a - b);
                return {{ game, attempts, gaveUp }};
            }}

            function scrollResultsIntoView(anchorEl) {{
                const target = anchorEl || document.getElementById('resultArea');
                if (!target) return;

                requestAnimationFrame(() => {{
                    target.scrollIntoView({{ behavior: 'smooth', block: 'start', inline: 'nearest' }});
                    try {{
                        const frame = window.frameElement;
                        const parentWin = window.parent;
                        if (frame && parentWin) {{
                            const targetRect = target.getBoundingClientRect();
                            const frameRect = frame.getBoundingClientRect();
                            const topInParent = frameRect.top + targetRect.top;
                            parentWin.scrollTo({{
                                top: Math.max(0, parentWin.scrollY + topInParent - 12),
                                behavior: 'smooth',
                            }});
                        }}
                    }} catch (e) {{}}
                }});
            }}

            function generateCombination() {{
                if (isGenerating) return;

                safeVibrate();
                clearActiveGeneration();
                genRunId += 1;
                const thisRun = genRunId;
                isGenerating = true;
                setStartButtonEnabled(false);

                runRevealVersion = consumeRevealVersion();

                const count = parseInt(document.getElementById('gameCount').value, 10);
                if (isNaN(count) || count < 1) {{
                    isGenerating = false;
                    setStartButtonEnabled(true);
                    return;
                }}
                showLuckyWarn(false);

                const available = [];
                for (let i = 1; i <= 45; i++) {{
                    if (!selectedDelete.has(i)) available.push(i);
                }}

                currentResults = [];
                const resultArea = document.getElementById('resultArea');
                resultArea.innerHTML = '';
                scrollResultsIntoView(resultArea);

                for (let g = 0; g < count; g++) {{
                    const tid = setTimeout(() => {{
                        if (thisRun !== genRunId) return;
                        const built = buildOneGame(available);
                        currentResults.push(built.game);
                        renderGame(built.game);
                    }}, g * 2000);
                    activeGenTimers.push(tid);
                }}
                const completeId = setTimeout(() => {{
                    if (thisRun !== genRunId) return;
                    isGenerating = false;
                    setStartButtonEnabled(true);
                    window.parent.postMessage({{ type: 'thunder_complete', count: count }}, '*');
                }}, count * 2000 + 600);
                activeGenTimers.push(completeId);
            }}

            /* 메인화면 user_page get_ball_style() / orbit-ball radial-gradient 재사용 */
            function getBallBackground(n) {{
                if (n <= 10) return 'radial-gradient(circle at 35% 35%, #ffeb3b, #f9a825, #f57f17)';
                if (n <= 20) return 'radial-gradient(circle at 35% 35%, #4fc3f7, #1976d2, #0d47a1)';
                if (n <= 30) return 'radial-gradient(circle at 35% 35%, #ef5350, #e53935, #b71c1c)';
                if (n <= 40) return 'radial-gradient(circle at 35% 35%, #bdbdbd, #757575, #424242)';
                return 'radial-gradient(circle at 35% 35%, #81c784, #388e3c, #1b5e20)';
            }}

            function createBallEl(n) {{
                const ball = document.createElement('div');
                ball.className = 'ball';
                ball.style.background = getBallBackground(n);
                ball.innerText = n;
                return ball;
            }}

            /* 버전2: 심해 오라 — 볼이 어둠 속에서 1.6배까지 튀어오르며 계시 (v1과 무관) */
            function renderGameV2(nums) {{
                const row = document.createElement('div');
                row.className = 'result-row mystic-v2-row';

                const aura = document.createElement('div');
                aura.className = 'mystic-v2-aura';
                row.appendChild(aura);

                const track = document.createElement('div');
                track.className = 'mystic-v2-track';
                row.appendChild(track);

                const balls = nums.map(n => {{
                    const b = createBallEl(n);
                    b.style.opacity = '0';
                    b.style.visibility = 'hidden';
                    track.appendChild(b);
                    return b;
                }});

                document.getElementById('resultArea').appendChild(row);
                scrollResultsIntoView(row);

                aura.animate([
                    {{ opacity: 0, transform: 'scaleY(0)' }},
                    {{ opacity: 1, transform: 'scaleY(1)', offset: 0.25 }},
                    {{ opacity: 0.85, transform: 'scaleY(0.55)', offset: 0.75 }},
                    {{ opacity: 0, transform: 'scaleY(0)' }}
                ], {{ duration: 3000, easing: 'ease-in-out', fill: 'forwards' }});

                balls.forEach((ball, i) => {{
                    const tid = setTimeout(() => {{
                        const spark = document.createElement('div');
                        spark.className = 'mystic-v2-spark';
                        spark.style.left = (18 + i * 14) + '%';
                        spark.style.bottom = '6px';
                        row.appendChild(spark);
                        spark.animate([
                            {{ opacity: 0, transform: 'translateY(0) scale(0)' }},
                            {{ opacity: 1, transform: 'translateY(-30px) scale(2)', offset: 0.4 }},
                            {{ opacity: 0, transform: 'translateY(-70px) scale(0)' }}
                        ], {{ duration: 1200, fill: 'forwards' }});
                        setTimeout(() => spark.remove(), 1300);

                        ball.style.visibility = 'visible';
                        ball.animate([
                            {{ opacity: 0, transform: 'translateY(180px) scale(0) rotate(270deg)', filter: 'blur(18px) brightness(0.05)' }},
                            {{ opacity: 0.7, transform: 'translateY(-50px) scale(1.65) rotate(-20deg)', filter: 'blur(0) brightness(2.2) drop-shadow(0 0 28px #22d3ee) drop-shadow(0 0 48px #a855f7)', offset: 0.42 }},
                            {{ opacity: 1, transform: 'translateY(22px) scale(0.82) rotate(10deg)', filter: 'brightness(1.15)', offset: 0.72 }},
                            {{ opacity: 1, transform: 'translateY(0) scale(1) rotate(0deg)', filter: 'none' }}
                        ], {{ duration: 2600, easing: 'cubic-bezier(0.1, 1.45, 0.22, 1)', fill: 'forwards' }});
                    }}, i * 320);
                    activeGenTimers.push(tid);
                }});
            }}

            /* 버전3: 균열 너머 영혼 — 5.5초간 사라졌다 나타났다 후 수렴 (v1과 무관) */
            function renderGameV3(nums) {{
                const row = document.createElement('div');
                row.className = 'result-row mystic-v3-row';

                const rift = document.createElement('div');
                rift.className = 'mystic-v3-rift';
                row.appendChild(rift);

                const track = document.createElement('div');
                track.className = 'mystic-v3-track';
                row.appendChild(track);

                const balls = nums.map(n => {{
                    const b = createBallEl(n);
                    b.style.opacity = '0';
                    track.appendChild(b);
                    return b;
                }});

                document.getElementById('resultArea').appendChild(row);
                scrollResultsIntoView(row);

                rift.animate([
                    {{ opacity: 0, transform: 'scale(0.7) rotate(0deg)' }},
                    {{ opacity: 0.95, transform: 'scale(1.08) rotate(6deg)', offset: 0.35 }},
                    {{ opacity: 0.5, transform: 'scale(1.15) rotate(-8deg)', offset: 0.7 }},
                    {{ opacity: 0, transform: 'scale(1.3) rotate(0deg)' }}
                ], {{ duration: 5500, fill: 'forwards' }});

                const started = performance.now();
                const duration = 5500;
                const baseShadow = '0 4px 0 #000000, 0 7px 16px rgba(0, 0, 0, 0.55), inset 0 1px 0 rgba(255, 255, 255, 0.04)';

                const flickerTimer = setInterval(() => {{
                    const progress = (performance.now() - started) / duration;
                    if (progress >= 1) {{
                        clearInterval(flickerTimer);
                        balls.forEach(b => {{
                            b.style.opacity = '1';
                            b.style.transform = 'translate(0px, 0px) scale(1)';
                            b.style.filter = 'none';
                        }});
                        row.style.boxShadow = baseShadow;
                        row.style.transform = 'scale(1)';
                        return;
                    }}

                    const chaos = 1 - progress * progress;
                    balls.forEach(b => {{
                        if (Math.random() > chaos * 0.85 + 0.08) {{
                            b.style.opacity = String(0.15 + Math.random() * 0.85);
                            b.style.transform = 'translate('
                                + Math.round((Math.random() - 0.5) * 56) + 'px,'
                                + Math.round((Math.random() - 0.5) * 44) + 'px) scale('
                                + (0.35 + Math.random() * 1.35).toFixed(2) + ')';
                            b.style.filter = 'hue-rotate(' + Math.round(Math.random() * 300)
                                + 'deg) brightness(' + (0.4 + Math.random() * 1.6).toFixed(2) + ')';
                        }} else {{
                            b.style.opacity = '0';
                            b.style.transform = 'translate('
                                + Math.round((Math.random() - 0.5) * 80) + 'px,'
                                + Math.round((Math.random() - 0.5) * 60) + 'px) scale(0.15)';
                        }}
                    }});

                    if (Math.random() > 0.45) {{
                        row.style.boxShadow = '0 0 ' + Math.round(18 + Math.random() * 36)
                            + 'px ' + Math.round(6 + Math.random() * 10)
                            + 'px rgba(168, 85, 247, ' + (0.45 + Math.random() * 0.55).toFixed(2) + ')';
                        row.style.transform = 'scale(' + (0.97 + Math.random() * 0.06).toFixed(3) + ')';
                    }} else {{
                        row.style.boxShadow = baseShadow;
                        row.style.transform = 'scale(1)';
                    }}
                }}, 100);
                activeGenIntervals.push(flickerTimer);
            }}

            function renderGame(nums) {{
                const ver = runRevealVersion;
                if (ver === 2 || ver === '2') {{
                    renderGameV2(nums);
                    return;
                }}
                if (ver === 3 || ver === '3') {{
                    renderGameV3(nums);
                    return;
                }}

                const row = document.createElement('div');
                row.className = 'result-row reveal';
                nums.forEach(n => {{
                    const ball = document.createElement('div');
                    ball.className = 'ball';
                    ball.style.background = getBallBackground(n);
                    ball.innerText = n;
                    row.appendChild(ball);
                }});
                document.getElementById('resultArea').appendChild(row);
                scrollResultsIntoView(row);
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
            if (autoRunCount) {{
                document.getElementById('gameCount').value = autoRunCount;
                thunderApproved = true;
                setTimeout(() => {{
                    if (!isGenerating) generateCombination();
                }}, 400);
            }}
        </script>
    </body>
    </html>
    """

    components.html(thunder_ui_html, height=820, scrolling=True)

# 호출 확인
if __name__ == "__main__":
    render()
