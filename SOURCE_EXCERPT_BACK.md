# 로또신령 — 소스코드 발췌 (뒷부분)

> 동일 연결본에서 뒤에서 1650줄을 추출했습니다. (시작 위치: 약 8,536줄)

```python
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
    st.markdown("---")
    st.markdown("""
    <div class="main-legal-notices-marker" aria-hidden="true"></div>
    <style>
    .main-legal-notices-marker { display: none !important; }
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) div[data-testid="stExpander"] {
        background-color: #0d1528 !important;
        border: 1px solid #2a3a60 !important;
        border-radius: 10px !important;
        margin-bottom: 10px !important;
    }
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) div[data-testid="stExpander"] details,
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) div[data-testid="stExpander"] summary,
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) div[data-testid="stExpander"] [data-testid="stExpanderDetails"],
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) div[data-testid="stExpander"] [data-testid="stExpanderDetails"] > div {
        background-color: #0d1528 !important;
    }
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) div[data-testid="stExpander"] summary,
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) div[data-testid="stExpander"] summary p,
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) div[data-testid="stExpander"] summary span {
        color: #b39ddb !important;
        font-weight: 700 !important;
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
    with st.expander("📋 회원 고지·약관 (운영 미리보기 — 오픈 전 검토용)"):
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
    st.markdown("---")
    st.markdown("""
    <div class="main-admin-menu-marker" aria-hidden="true"></div>
    <style>
    .main-admin-menu-marker { display: none !important; }

    div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] {
        background-color: #000000 !important;
        border: 1px solid #2a2a2a !important;
        border-radius: 10px !important;
    }
    div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] details {
        background-color: #000000 !important;
    }
    div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] summary {
        background-color: #000000 !important;
        color: #ffffff !important;
    }
    div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] summary:hover {
        background-color: #111111 !important;
        color: #ffffff !important;
    }
    div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] summary p,
    div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] summary span,
    div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] summary div,
    div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] summary svg {
        color: #ffffff !important;
        fill: #ffffff !important;
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
# ===== FILE: wallet_db.py =====
"""회원 지갑 DB — OAuth 해시 식별자만 저장 (PII·결제정보 미보관)."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone

DB_PATH = "lotto.db"
SIGNUP_BONUS = 5000
ADVANCED_PRODUCT = "advanced_filter_monthly"
FREE_SUB_DAYS = 30

KST = timezone(timedelta(hours=9))


def _now_iso() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S.%f")


def oauth_hash(provider: str, provider_user_id: str) -> str:
    raw = f"{provider.strip().lower()}:{str(provider_user_id).strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_wallet_tables() -> None:
    conn = _connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            oauth_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            last_login_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_members_oauth ON members(oauth_hash);

        CREATE TABLE IF NOT EXISTS wallets (
            member_id INTEGER PRIMARY KEY,
            balance INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (member_id) REFERENCES members(id)
        );

        CREATE TABLE IF NOT EXISTS wallet_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            delta INTEGER NOT NULL,
            balance_after INTEGER NOT NULL,
            reason TEXT NOT NULL,
            ref_id TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(ref_id),
            FOREIGN KEY (member_id) REFERENCES members(id)
        );
        CREATE INDEX IF NOT EXISTS idx_ledger_member ON wallet_ledger(member_id, created_at);

        CREATE TABLE IF NOT EXISTS signup_grants (
            member_id INTEGER PRIMARY KEY,
            granted_at TEXT NOT NULL,
            amount INTEGER NOT NULL,
            FOREIGN KEY (member_id) REFERENCES members(id)
        );

        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            product TEXT NOT NULL,
            starts_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            is_free_promo INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (member_id) REFERENCES members(id)
        );
        CREATE INDEX IF NOT EXISTS idx_sub_member_product ON subscriptions(member_id, product, expires_at);

        CREATE TABLE IF NOT EXISTS consent_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            notice_version TEXT NOT NULL,
            agreed_at TEXT NOT NULL,
            FOREIGN KEY (member_id) REFERENCES members(id)
        );

        CREATE TABLE IF NOT EXISTS pg_charges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            pg_ref_id TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'completed',
            created_at TEXT NOT NULL,
            FOREIGN KEY (member_id) REFERENCES members(id)
        );

        CREATE TABLE IF NOT EXISTS auto_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            purchase_type TEXT NOT NULL,
            phone TEXT NOT NULL,
            sms_days TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            ledger_ref_id TEXT UNIQUE,
            sms_queue_id INTEGER,
            draw_round INTEGER,
            combo_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY (member_id) REFERENCES members(id)
        );
        CREATE INDEX IF NOT EXISTS idx_auto_orders_member ON auto_orders(member_id, created_at);
        """
    )
    conn.commit()
    conn.close()


def get_or_create_member(provider: str, provider_user_id: str) -> tuple[int, bool]:
    """returns (member_id, is_new)."""
    ohash = oauth_hash(provider, provider_user_id)
    conn = _connect()
    now = _now_iso()
    row = conn.execute(
        "SELECT id FROM members WHERE oauth_hash = ?", (ohash,)
    ).fetchone()
    if row:
        member_id = int(row["id"])
        conn.execute(
            "UPDATE members SET last_login_at = ? WHERE id = ?", (now, member_id)
        )
        conn.commit()
        conn.close()
        return member_id, False

    cur = conn.execute(
        "INSERT INTO members (provider, oauth_hash, created_at, last_login_at) VALUES (?, ?, ?, ?)",
        (provider.lower(), ohash, now, now),
    )
    member_id = int(cur.lastrowid)
    conn.execute(
        "INSERT INTO wallets (member_id, balance) VALUES (?, 0)", (member_id,)
    )
    conn.commit()
    conn.close()
    return member_id, True


def grant_signup_bonus(member_id: int, amount: int = SIGNUP_BONUS) -> bool:
    conn = _connect()
    exists = conn.execute(
        "SELECT 1 FROM signup_grants WHERE member_id = ?", (member_id,)
    ).fetchone()
    if exists:
        conn.close()
        return False

    row = conn.execute(
        "SELECT balance FROM wallets WHERE member_id = ?", (member_id,)
    ).fetchone()
    if not row:
        conn.close()
        raise ValueError(f"wallet not found: {member_id}")

    new_balance = int(row["balance"]) + amount
    now = _now_iso()
    ref = f"signup_bonus:{member_id}"
    conn.execute(
        "INSERT INTO signup_grants (member_id, granted_at, amount) VALUES (?, ?, ?)",
        (member_id, now, amount),
    )
    conn.execute(
        "UPDATE wallets SET balance = ? WHERE member_id = ?", (new_balance, member_id)
    )
    conn.execute(
        """
        INSERT INTO wallet_ledger (member_id, delta, balance_after, reason, ref_id, created_at)
        VALUES (?, ?, ?, 'signup_bonus', ?, ?)
        """,
        (member_id, amount, new_balance, ref, now),
    )
    conn.commit()
    conn.close()
    return True


def get_balance(member_id: int) -> int:
    conn = _connect()
    row = conn.execute(
        "SELECT balance FROM wallets WHERE member_id = ?", (member_id,)
    ).fetchone()
    conn.close()
    return int(row["balance"]) if row else 0


def deduct_points(member_id: int, amount: int, reason: str, ref_id: str) -> bool:
    if amount <= 0:
        raise ValueError("amount must be positive")
    conn = _connect()
    try:
        dup = conn.execute(
            "SELECT 1 FROM wallet_ledger WHERE ref_id = ?", (ref_id,)
        ).fetchone()
        if dup:
            conn.close()
            return True

        row = conn.execute(
            "SELECT balance FROM wallets WHERE member_id = ?", (member_id,)
        ).fetchone()
        if not row:
            conn.close()
            return False
        balance = int(row["balance"])
        if balance < amount:
            conn.close()
            return False

        new_balance = balance - amount
        now = _now_iso()
        conn.execute(
            "UPDATE wallets SET balance = ? WHERE member_id = ?",
            (new_balance, member_id),
        )
        conn.execute(
            """
            INSERT INTO wallet_ledger (member_id, delta, balance_after, reason, ref_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (member_id, -amount, new_balance, reason, ref_id, now),
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return True


def record_consent(member_id: int, notice_version: str) -> None:
    conn = _connect()
    conn.execute(
        """
        INSERT INTO consent_log (member_id, notice_version, agreed_at)
        VALUES (?, ?, ?)
        """,
        (member_id, notice_version, _now_iso()),
    )
    conn.commit()
    conn.close()


def has_active_subscription(member_id: int, product: str = ADVANCED_PRODUCT) -> bool:
    conn = _connect()
    now = _now_iso()
    row = conn.execute(
        """
        SELECT 1 FROM subscriptions
        WHERE member_id = ? AND product = ? AND expires_at > ?
        ORDER BY expires_at DESC LIMIT 1
        """,
        (member_id, product, now),
    ).fetchone()
    conn.close()
    return row is not None


def eligible_free_advanced_sub(member_id: int) -> bool:
    conn = _connect()
    row = conn.execute(
        """
        SELECT 1 FROM subscriptions
        WHERE member_id = ? AND product = ? AND is_free_promo = 1
        LIMIT 1
        """,
        (member_id, ADVANCED_PRODUCT),
    ).fetchone()
    conn.close()
    return row is None


def activate_free_advanced_sub(member_id: int) -> bool:
    if not eligible_free_advanced_sub(member_id):
        return False
    conn = _connect()
    now = datetime.now(KST)
    starts = now.strftime("%Y-%m-%d %H:%M:%S.%f")
    expires = (now + timedelta(days=FREE_SUB_DAYS)).strftime("%Y-%m-%d %H:%M:%S.%f")
    conn.execute(
        """
        INSERT INTO subscriptions (member_id, product, starts_at, expires_at, is_free_promo)
        VALUES (?, ?, ?, ?, 1)
        """,
        (member_id, ADVANCED_PRODUCT, starts, expires),
    )
    conn.commit()
    conn.close()
    return True


def calc_thunder_cost(game_count: int) -> int:
    n = max(1, int(game_count))
    return ((n + 4) // 5) * 1000


def calc_auto_cost(quantity: int) -> int:
    table = {5: 1000, 10: 2000, 15: 3000, 20: 4000}
    return table.get(int(quantity), ((int(quantity) + 4) // 5) * 1000)


def pg_configured() -> bool:
    import os

    return bool(os.environ.get("PG_MERCHANT_ID", "").strip())


CHARGE_AMOUNTS = (5000, 10000, 20000, 50000)


def charge_points(member_id: int, amount: int, pg_ref_id: str) -> bool:
    """PG 충전 — 카드정보 미저장, ledger ref_id로 멱등."""
    if amount <= 0:
        raise ValueError("amount must be positive")
    conn = _connect()
    try:
        dup = conn.execute(
            "SELECT 1 FROM wallet_ledger WHERE ref_id = ?", (pg_ref_id,)
        ).fetchone()
        if dup:
            conn.close()
            return True

        row = conn.execute(
            "SELECT balance FROM wallets WHERE member_id = ?", (member_id,)
        ).fetchone()
        if not row:
            conn.close()
            return False

        new_balance = int(row["balance"]) + amount
        now = _now_iso()
        conn.execute(
            """
            INSERT INTO pg_charges (member_id, amount, pg_ref_id, status, created_at)
            VALUES (?, ?, ?, 'completed', ?)
            """,
            (member_id, amount, pg_ref_id, now),
        )
        conn.execute(
            "UPDATE wallets SET balance = ? WHERE member_id = ?",
            (new_balance, member_id),
        )
        conn.execute(
            """
            INSERT INTO wallet_ledger (member_id, delta, balance_after, reason, ref_id, created_at)
            VALUES (?, ?, ?, 'pg_charge', ?, ?)
            """,
            (member_id, amount, new_balance, pg_ref_id, now),
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return True


def create_auto_order(
    member_id: int,
    quantity: int,
    purchase_type: str,
    phone: str,
    sms_days: str,
    ledger_ref_id: str,
) -> int:
    conn = _connect()
    cur = conn.execute(
        """
        INSERT INTO auto_orders
            (member_id, quantity, purchase_type, phone, sms_days, status, ledger_ref_id, created_at)
        VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
        """,
        (member_id, int(quantity), purchase_type, phone.strip(), sms_days, ledger_ref_id, _now_iso()),
    )
    order_id = int(cur.lastrowid)
    conn.commit()
    conn.close()
    return order_id


def complete_auto_order(
    order_id: int,
    sms_queue_id: int,
    draw_round: int,
    combo_count: int,
) -> None:
    conn = _connect()
    conn.execute(
        """
        UPDATE auto_orders
        SET status = 'completed', sms_queue_id = ?, draw_round = ?,
            combo_count = ?, completed_at = ?
        WHERE id = ?
        """,
        (sms_queue_id, int(draw_round), int(combo_count), _now_iso(), int(order_id)),
    )
    conn.commit()
    conn.close()


def fail_auto_order(order_id: int) -> None:
    conn = _connect()
    conn.execute(
        "UPDATE auto_orders SET status = 'failed', completed_at = ? WHERE id = ?",
        (_now_iso(), int(order_id)),
    )
    conn.commit()
    conn.close()
# ===== FILE: wallet_ui.py =====
"""지갑 UI — 로그인·적립금 안내 dialog."""

from __future__ import annotations

import html
import uuid

import streamlit as st

from auth_providers import (
    _dev_mock_enabled,
    current_member_id,
    get_kakao_authorize_url,
    kakao_configured,
    logout,
    mock_kakao_login,
)
from legal_notices import (
    AUTH_CONSENT_ITEMS,
    AUTH_PROMPT_SUBTITLE,
    NOTICE_VERSION,
    format_advanced_points_notice,
    format_auto_points_notice,
    format_thunder_points_notice,
    ADVANCED_FILTER_FIRST_SUB_FREE,
)
from wallet_db import (
    CHARGE_AMOUNTS,
    activate_free_advanced_sub,
    calc_auto_cost,
    calc_thunder_cost,
    charge_points,
    deduct_points,
    eligible_free_advanced_sub,
    get_balance,
    has_active_subscription,
    pg_configured,
)


def _dialog_decorator(title: str):
    if hasattr(st, "dialog"):
        return st.dialog(title)
    return st.experimental_dialog(title) if hasattr(st, "experimental_dialog") else _fallback_dialog(title)


def _fallback_dialog(title: str):
    def wrapper(func):
        def inner(*args, **kwargs):
            with st.container(border=True):
                st.subheader(title)
                return func(*args, **kwargs)
        return inner
    return wrapper


AUTH_BANNER_OPEN = "auth_banner_open"
AUTH_BANNER_REASON = "auth_banner_reason"
AUTH_RESUME_FLAG = "auth_resume_flag"
AUTH_RESUME_DATA = "auth_resume_data"


def open_auth_banner(*, reason: str = "", resume: str | None = None, resume_data: dict | None = None) -> None:
    st.session_state[AUTH_BANNER_OPEN] = True
    st.session_state[AUTH_BANNER_REASON] = reason or "이 기능을 이용하려면 간편인증이 필요합니다."
    if resume:
        st.session_state[AUTH_RESUME_FLAG] = resume
    if resume_data:
        st.session_state[AUTH_RESUME_DATA] = resume_data


def close_auth_banner() -> None:
    for key in (AUTH_BANNER_OPEN, AUTH_BANNER_REASON):
        st.session_state.pop(key, None)


def _resume_after_auth() -> None:
    resume = st.session_state.pop(AUTH_RESUME_FLAG, None)
    data = st.session_state.pop(AUTH_RESUME_DATA, None) or {}
    if resume == "auto_show_points":
        st.session_state["auto_show_points"] = True
    elif resume == "open_thunder_dialog":
        st.session_state["open_thunder_dialog"] = True
        st.session_state["open_thunder_dialog_games"] = int(data.get("games", 5))
    elif resume == "af_show_step1_points":
        st.session_state["af_show_step1_points"] = True
    elif resume == "af_show_step2_points":
        st.session_state["af_show_step2_points"] = True
    elif resume == "wallet_show_charge":
        st.session_state["wallet_show_charge"] = True


def _finish_auth_success() -> None:
    _resume_after_auth()
    close_auth_banner()
    st.rerun()


def ensure_member_or_banner(*, resume: str, reason: str, resume_data: dict | None = None) -> bool:
    """로그인됐으면 True. 아니면 배너만 띄우고 False."""
    if current_member_id():
        return True
    open_auth_banner(reason=reason, resume=resume, resume_data=resume_data)
    st.rerun()
    return False


def _inject_auth_banner_css() -> None:
    st.markdown(
        """
<div class="lotto-auth-banner-marker" aria-hidden="true"></div>
<style>
div[data-testid="stVerticalBlock"]:has(> div > .lotto-auth-banner-marker),
div[data-testid="stVerticalBlock"]:has(.lotto-auth-banner-marker) {
    position: sticky !important;
    top: 0 !important;
    z-index: 100 !important;
    margin-bottom: 12px !important;
}
.lotto-auth-banner {
    background: linear-gradient(135deg, #1a2744 0%, #12182b 100%);
    border: 1px solid #3d5a80;
    border-radius: 14px;
    padding: 14px 16px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
}
.lotto-auth-banner .auth-banner-title {
    font-size: 15px;
    font-weight: 800;
    color: #e3f2fd;
    margin: 0 0 4px 0;
}
.lotto-auth-banner .auth-banner-sub {
    font-size: 12px;
    color: #90caf9;
    margin: 0 0 10px 0;
    line-height: 1.45;
}
.lotto-auth-banner .auth-banner-bonus {
    font-size: 12px;
    color: #ffb300;
    font-weight: 700;
    margin: 0 0 10px 0;
}
div[data-testid="stVerticalBlock"]:has(.auth-banner-consent-marker) {
    background: rgba(13, 21, 40, 0.5) !important;
    border: 1px solid #2a3a60 !important;
    border-radius: 10px !important;
    padding: 8px 10px 4px 10px !important;
    margin-bottom: 10px !important;
}
div[data-testid="stVerticalBlock"]:has(.auth-banner-consent-marker) label p {
    color: #cfd8dc !important;
    font-size: 11.5px !important;
    line-height: 1.4 !important;
}
.st-key-auth_banner_kakao a,
.st-key-auth_banner_kakao button[kind="primary"] {
    background: linear-gradient(145deg, #fee500, #f5d900) !important;
    color: #191919 !important;
    border-color: #e6c200 !important;
    border-radius: 10px !important;
    min-height: 42px !important;
    font-weight: 700 !important;
}
.st-key-auth_banner_close button {
    background: transparent !important;
    color: #78909c !important;
    border: 1px solid #37474f !important;
    border-radius: 10px !important;
    min-height: 36px !important;
    font-size: 13px !important;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def _render_auth_banner_form() -> None:
    reason = st.session_state.get(AUTH_BANNER_REASON, "")
    reason_html = html.escape(reason)
    st.markdown(
        f'<div class="lotto-auth-banner">'
        f'<p class="auth-banner-title">간편인증</p>'
        f'<p class="auth-banner-sub">{reason_html}</p>'
        f'<p class="auth-banner-bonus">최초 인증 시 적립금 5,000P 지급 · 현금 환불 불가</p>'
        f"</div>",
        unsafe_allow_html=True,
    )

    with st.container():
        st.markdown('<div class="auth-banner-consent-marker"></div>', unsafe_allow_html=True)
        checks = [st.checkbox(item, key=f"auth_banner_consent_{i}") for i, item in enumerate(AUTH_CONSENT_ITEMS)]
    all_agreed = all(checks)

    return_page = st.query_params.get("page", "main")

    if all_agreed:
        if kakao_configured():
            with st.container(key="auth_banner_kakao"):
                st.link_button(
                    "카카오로 시작하기",
                    get_kakao_authorize_url(return_page),
                    use_container_width=True,
                    type="primary",
                )
            st.caption("카카오 로그인 후 이 페이지로 돌아옵니다.")
        elif _dev_mock_enabled():
            with st.container(key="auth_banner_kakao"):
                if st.button(
                    "카카오로 시작하기",
                    use_container_width=True,
                    type="primary",
                    key="auth_banner_kakao_mock",
                ):
                    mock_kakao_login()
                    _finish_auth_success()
            st.caption("개발 모드 · Mock 간편인증")
        else:
            with st.container(key="auth_banner_kakao"):
                st.button(
                    "카카오로 시작하기",
                    use_container_width=True,
                    disabled=True,
                    key="auth_banner_kakao_unconfigured",
                )
            st.error(
                "카카오 로그인 연동이 아직 설정되지 않았습니다. "
                "`.env`에 `KAKAO_REST_API_KEY`를 넣거나, "
                "개발 중이면 `LOTTO_DEV_MOCK_AUTH=1`로 설정 후 서버를 재시작하세요."
            )
    else:
        with st.container(key="auth_banner_kakao"):
            st.button(
                "카카오로 시작하기",
                use_container_width=True,
                disabled=True,
                key="auth_banner_kakao_locked",
            )
        st.caption("필수 동의를 모두 체크한 뒤 카카오로 시작할 수 있습니다.")

    with st.container(key="auth_banner_close"):
        if st.button("닫기", use_container_width=True, key="auth_banner_dismiss", type="secondary"):
            close_auth_banner()
            st.session_state.pop(AUTH_RESUME_FLAG, None)
            st.session_state.pop(AUTH_RESUME_DATA, None)
            st.rerun()

    if all_agreed:
        st.caption("PASS·금융인증서는 사업자 연동 계약 후 순차 제공 예정입니다.")


def render_auth_banner() -> None:
    if current_member_id() and st.session_state.get(AUTH_RESUME_FLAG):
        _finish_auth_success()
        return
    if not st.session_state.get(AUTH_BANNER_OPEN):
        return
    if current_member_id():
        _finish_auth_success()
        return
    _inject_auth_banner_css()
    _render_auth_banner_form()


def auth_dialog() -> bool:
    """하위 호환 — 배너로 대체됨."""
    open_auth_banner(reason=AUTH_PROMPT_SUBTITLE)
    return False


@_dialog_decorator("적립금 충전")
def charge_dialog() -> None:
    member_id = current_member_id()
    if not member_id:
        return

    balance = get_balance(member_id)
    st.markdown(f"현재 잔액 **{balance:,}P**")
    amount = st.radio(
        "충전 금액",
        CHARGE_AMOUNTS,
        format_func=lambda x: f"{x:,}P",
        horizontal=True,
    )

    if pg_configured():
        st.info("PG 결제창 연동은 계약 후 활성화됩니다. (카드정보는 서버에 저장하지 않습니다.)")
        st.link_button(
            "결제창 열기 (준비중)",
            "#",
            disabled=True,
            use_container_width=True,
        )
    else:
        st.caption("PG 미연동 · 테스트는 Mock 결제를 이용하세요.")
        if st.button("Mock 결제 (테스트)", type="primary", use_container_width=True):
            ref = f"pg:mock:{member_id}:{uuid.uuid4().hex[:10]}"
            if charge_points(member_id, int(amount), ref):
                st.session_state.wallet_toast = f"{int(amount):,}P 충전 완료"
                st.rerun()
            st.error("충전에 실패했습니다.")


@_dialog_decorator("적립금 이용 안내")
def points_notice_dialog(
    service: str,
    *,
    game_count: int = 5,
    quantity: int = 5,
) -> str | None:
    """Returns 'confirm' | 'cancel' | None (closed)."""
    member_id = current_member_id()
    balance = get_balance(member_id) if member_id else 0

    if not member_id:
        return "cancel"

    if service == "thunder":
        st.markdown(format_thunder_points_notice(game_count, balance))
        cost = calc_thunder_cost(game_count)
    elif service == "auto":
        st.markdown(format_auto_points_notice(quantity, balance))
        cost = calc_auto_cost(quantity)
    elif service == "advanced":
        free_ok = ADVANCED_FILTER_FIRST_SUB_FREE and eligible_free_advanced_sub(member_id)
        active = has_active_subscription(member_id)
        st.markdown(format_advanced_points_notice(has_free_sub=free_ok and not active, balance=balance))
        cost = 0 if (free_ok or active) else 15000
    else:
        st.error("알 수 없는 서비스")
        return "cancel"

    if cost > 0 and balance < cost:
        st.error(f"적립금이 부족합니다. (필요 {cost:,}P / 보유 {balance:,}P)")
        return "cancel"

    c1, c2 = st.columns(2)
    with c1:
        if st.button("취소", use_container_width=True):
            return "cancel"
    with c2:
        if st.button("확인 후 진행", type="primary", use_container_width=True):
            return "confirm"
    return None


def render_wallet_bar() -> int | None:
    """로그인 시에만 상단 잔액 바. 미로그인 시 배너는 인증 필요 클릭 때만."""
    from shared_ui_styles import wallet_bar_button_css
    from zero_phone_db import TEST_USER_ID, get_user, init_zero_phone_tables, login_test_user

    init_zero_phone_tables()

    if current_member_id() and st.session_state.get(AUTH_RESUME_FLAG):
        _finish_auth_success()

    toast = st.session_state.pop("wallet_toast", None)
    if toast:
        st.success(toast)

    render_auth_banner()

    zp_uid = st.session_state.get("zp_user_id")
    if zp_uid:
        zp_row = get_user(zp_uid)
        if zp_row:
            st.session_state.zp_point_balance = zp_row["point_balance"]
            st.session_state.zp_is_premium = zp_row["is_premium"]
        else:
            st.session_state.pop("zp_user_id", None)

    member_id = current_member_id() if not zp_uid else None

    if st.session_state.get("wallet_show_charge") and member_id:
        st.session_state.pop("wallet_show_charge", None)
        charge_dialog()

    if not member_id and not zp_uid:
        if _dev_mock_enabled():
            with st.expander("개발용 테스트 로그인", expanded=False):
                if st.button(
                    f"테스트 로그인 (ID: {TEST_USER_ID})",
                    key="zp_test_login_btn",
                    use_container_width=True,
                ):
                    user, is_new = login_test_user(TEST_USER_ID)
                    st.session_state.zp_user_id = user["user_id"]
                    st.session_state.zp_point_balance = user["point_balance"]
                    st.session_state.zp_is_premium = user["is_premium"]
                    if is_new:
                        st.session_state.wallet_toast = "테스트 가입 완료! 5,000점 지급"
                    st.rerun()
        return None

    st.markdown(wallet_bar_button_css(), unsafe_allow_html=True)
    col_a, col_b = st.columns([1.2, 1])
    with col_a:
        if zp_uid:
            bal = int(st.session_state.get("zp_point_balance", 0))
            tag = zp_uid if len(zp_uid) <= 16 else zp_uid[:12] + "…"
            st.markdown(f"**현재 보유 적립금: {bal:,}점** · ID `{tag}`")
        else:
            bal = get_balance(member_id)
            tag = st.session_state.get("oauth_hash_display", "ID")
            st.markdown(f"**적립금 {bal:,}P** · ID `{tag}` · v{NOTICE_VERSION}")
    with col_b:
        if zp_uid:
            if st.button("로그아웃", key="zp_logout_btn", use_container_width=True, type="secondary"):
                for key in ("zp_user_id", "zp_point_balance", "zp_is_premium"):
                    st.session_state.pop(key, None)
                st.rerun()
        else:
            bc1, bc2 = st.columns(2)
            with bc1:
                if st.button("충전", key="wallet_charge_btn", use_container_width=True, type="secondary"):
                    charge_dialog()
            with bc2:
                if st.button("로그아웃", key="wallet_logout_btn", use_container_width=True, type="secondary"):
                    logout()
                    st.rerun()
    return member_id


def require_auth_or_prompt() -> int | None:
    mid = current_member_id()
    if mid:
        return mid
    open_auth_banner(reason="이 기능을 이용하려면 간편인증이 필요합니다.")
    return None


def deduct_after_result(
    member_id: int,
    service: str,
    ref_id: str,
    *,
    game_count: int = 5,
    quantity: int = 5,
) -> bool:
    if service == "advanced":
        if has_active_subscription(member_id):
            return True
        if ADVANCED_FILTER_FIRST_SUB_FREE and eligible_free_advanced_sub(member_id):
            return activate_free_advanced_sub(member_id)
        cost = 15000
        reason = "advanced:monthly"
        return deduct_points(member_id, cost, reason, ref_id)

    if service == "thunder":
        cost = calc_thunder_cost(game_count)
        reason = f"thunder:{game_count}games"
    elif service == "auto":
        cost = calc_auto_cost(quantity)
        reason = f"auto:{quantity}qty"
    else:
        return False

    return deduct_points(member_id, cost, reason, ref_id)
# ===== FILE: zero_phone_db.py =====
"""
Zero-Phone 익명 회원 DB — 전화번호·실명 등 PII 미수집.

카카오 채널 메시지 발송은 msg_queue.user_id 기준 (phone 컬럼 없음).
앱 내 마이페이지 조회가 1차, 채널 메시지가 2차 알림 경로.

────────────────────────────────────────
[향후 연결 예정] 포인트 차감 비즈니스 규칙 (아직 UI·버튼 미연결)
────────────────────────────────────────
규칙 1 — 자동구매: 5개 조합당 1,000점 / 10개 2,000점 (15→3,000 / 20→4,000)
규칙 2 — 번개조합: 5개 조합당 1,000점 / 10개 2,000점
규칙 3 — 고급필터: 월간 구독 15,000점 차감 + is_premium = True
공통 — 현금 결제 불가, 모든 서비스는 point_balance 확인 후 차감만 허용
공통 — 조합·결과 생성 성공 후 차감 (실패·0건 시 미차감)
────────────────────────────────────────
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

DB_PATH = "lotto.db"
SIGNUP_BONUS = 5000
TEST_USER_ID = "test_user_01"

PURCHASE_TYPES = frozenset({"정기구독", "일반구매"})
SEND_STATUSES = frozenset({"WAIT", "SENT"})

KST = timezone(timedelta(hours=9))


def _now_iso() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S.%f")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_zero_phone_tables() -> None:
    """users · msg_queue 테이블 생성 (phone 컬럼 없음)."""
    conn = _connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            point_balance INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            is_premium INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS msg_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            purchase_type TEXT NOT NULL,
            send_status TEXT NOT NULL DEFAULT 'WAIT',
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_msg_queue_status
            ON msg_queue(send_status, created_at);
        CREATE INDEX IF NOT EXISTS idx_msg_queue_user
            ON msg_queue(user_id, created_at);
        """
    )
    conn.commit()
    conn.close()


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if not row:
        return None
    return {
        "user_id": str(row["user_id"]),
        "point_balance": int(row["point_balance"]),
        "created_at": str(row["created_at"]),
        "is_premium": bool(int(row["is_premium"])),
    }


def get_user(user_id: str) -> dict | None:
    conn = _connect()
    row = conn.execute(
        "SELECT user_id, point_balance, created_at, is_premium FROM users WHERE user_id = ?",
        (str(user_id).strip(),),
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


def get_or_create_user(user_id: str) -> tuple[dict, bool]:
    """(user dict, is_new). 신규 가입 시 SIGNUP_BONUS 지급."""
    uid = str(user_id).strip()
    if not uid:
        raise ValueError("user_id is required")

    conn = _connect()
    row = conn.execute(
        "SELECT user_id, point_balance, created_at, is_premium FROM users WHERE user_id = ?",
        (uid,),
    ).fetchone()
    if row:
        conn.close()
        return _row_to_dict(row), False

    now = _now_iso()
    conn.execute(
        """
        INSERT INTO users (user_id, point_balance, created_at, is_premium)
        VALUES (?, ?, ?, 0)
        """,
        (uid, SIGNUP_BONUS, now),
    )
    conn.commit()
    new_row = conn.execute(
        "SELECT user_id, point_balance, created_at, is_premium FROM users WHERE user_id = ?",
        (uid,),
    ).fetchone()
    conn.close()
    return _row_to_dict(new_row), True


def login_test_user(user_id: str = TEST_USER_ID) -> tuple[dict, bool]:
    """테스트 로그인 — 신규면 5,000점 자동 지급."""
    return get_or_create_user(user_id)


def enqueue_msg(
    user_id: str,
    purchase_type: str,
    send_status: str = "WAIT",
) -> int:
    """카카오 채널 메시지 대기열 (user_id만, phone 없음)."""
    uid = str(user_id).strip()
    ptype = str(purchase_type).strip()
    status = str(send_status).strip().upper()

    if not uid:
        raise ValueError("user_id is required")
    if ptype not in PURCHASE_TYPES:
        raise ValueError("purchase_type은 '정기구독' 또는 '일반구매'만 허용")
    if status not in SEND_STATUSES:
        raise ValueError("send_status는 'WAIT' 또는 'SENT'만 허용")

    if get_user(uid) is None:
        raise ValueError(f"unknown user_id: {uid}")

    conn = _connect()
    cur = conn.execute(
        """
        INSERT INTO msg_queue (user_id, purchase_type, send_status, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (uid, ptype, status, _now_iso()),
    )
    row_id = int(cur.lastrowid)
    conn.commit()
    conn.close()
    return row_id
```
