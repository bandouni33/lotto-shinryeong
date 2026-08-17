"""
로또신령 - 타로 위로 페이지
tarot_data.py, images/ 폴더와 같은 위치에 두고 사용하세요.

플로우:
  1) 카테고리 10개 중 선택
  2) 소분류 3개 중 선택 → 도입부 표시
  3) [카드 뽑기] 버튼 → 78장 중 랜덤 1장 → 손편지 스타일로 결과 표시
  4) [다시 뽑기] → 처음부터 다시

사용법 (기존 앱에 넣을 때):
    import tarot_page
    tarot_page.render()   # 원하는 위치(버튼 클릭 시 등)에서 호출
"""

import base64
import json
import random
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from tarot_data import SUBCATEGORIES, CARDS, SPREADS
from user_scope import get_or_create_guest_id, guest_id_cookie_sync_html

BASE_DIR = Path(__file__).parent
IMAGE_DIR = BASE_DIR / "images"

KST = timezone(timedelta(hours=9))

# 지금 실제로 연결되어 있는 스프레드. 유료 스프레드를 추가할 때는
# SPREADS에 항목을 늘리고 이 값을 상황에 맞게 분기하면 된다.
ACTIVE_SPREAD = "single"

MAX_DAILY_DRAWS = 1  # 하루 1장

# 카드 스프레드에 펼쳐 보여줄 메이저 아르카나 22장 (뒷면 상태로 노출)
MAJOR_KEYS = [k for k in CARDS if CARDS[k]["arcana"] == "major"]

# ── 카테고리별 편지지 색상 (10종, 톤에 맞춰 배정) ──
CATEGORY_THEME = {
    "번아웃 / 무기력": "#FBF5E7",
    "인간관계 상처": "#FBF0E9",
    "미래에 대한 불안": "#EFF3F7",
    "자존감 흔들림": "#F3EFF7",
    "외로움": "#EAF1F5",
    "반복되는 일상에 지침": "#EEF6F0",
    "후회 / 미련": "#F7F0E3",
    "화 / 억울함": "#FBEAEA",
    "사랑 / 연애 고민": "#FCEFF5",
    "작은 희망이 필요할 때": "#FFF8E6",
}

CATEGORY_ICON = {
    "번아웃 / 무기력": "🕯️",
    "인간관계 상처": "🤍",
    "미래에 대한 불안": "🌫️",
    "자존감 흔들림": "🪞",
    "외로움": "🌙",
    "반복되는 일상에 지침": "🔁",
    "후회 / 미련": "🍂",
    "화 / 억울함": "🔥",
    "사랑 / 연애 고민": "💌",
    "작은 희망이 필요할 때": "✦",
}


# ────────────────────────────────────────────────
# 유틸
# ────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def _img_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _inject_base_css():
    css = textwrap.dedent("""
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Gaegu:wght@400;700&family=Gamja+Flower&family=Black+Han+Sans&family=Nanum+Pen+Script&display=swap" rel="stylesheet">
        <style>
        html, body, #root, .stApp, [data-testid="stAppViewContainer"],
        [data-testid="stAppViewContainer"] > section.main {
            overflow-x: hidden !important;
        }
        .st-key-tarot_page_root_6n36s5 * { box-sizing: border-box; }
        .st-key-tarot_page_root_6n36s5 { font-family: 'Gaegu', sans-serif; }

        /* 타로 전 화면 공통 글자 크기 체계 — 예전엔 화면마다 13px~24px로 제각각이라
           들쭉날쭉했다. 제목 20px / 버튼·본문 16px / 힌트·캡션 14px / 해석 본문 24px로
           통일한다. */
        .st-key-tarot_page_root_6n36s5 h5 {
            font-size: 20px !important;
            font-weight: 700 !important;
        }
        .st-key-tarot_page_root_6n36s5 div[data-testid="stButton"] > button,
        .st-key-tarot_page_root_6n36s5 div[data-testid="stButton"] > button p {
            font-size: 16px !important;
            font-weight: 700 !important;
        }
        .st-key-tarot_page_root_6n36s5 [data-testid="stCaptionContainer"],
        .st-key-tarot_page_root_6n36s5 [data-testid="stCaptionContainer"] p {
            font-size: 14px !important;
        }

        /* 카테고리 그리드 */
        .cat-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-top: 6px;
        }

        /* 카테고리·소분류 선택 버튼 — 폭 40% 축소(60%) + 가로 중앙 정렬 */
        .st-key-tarot_cat_grid_6n36s5 div[data-testid="stButton"] > button,
        .st-key-tarot_sub_list_6n36s5 div[data-testid="stButton"] > button {
            width: 60% !important;
            margin: 0 auto !important;
        }

        /* 소분류 도입부 카드 */
        .intro-card {
            border-radius: 12px;
            padding: 18px 20px;
            font-size: 16px;
            font-weight: 700;
            line-height: 1.6;
            color: #3A2E1D;
            border: 1px solid rgba(120,90,50,0.18);
            margin: 10px 0 16px;
        }

        /* 결과 편지 카드 */
        .letter {
            position: relative;
            border-radius: 14px;
            padding: 22px 24px 20px;
            box-shadow:
                0 1px 1px rgba(80,60,30,0.12),
                0 6px 16px rgba(80,60,30,0.16);
            animation: letterIn 0.5s ease;
        }
        @keyframes letterIn {
            from { opacity: 0; transform: translateY(10px) scale(0.98); }
            to   { opacity: 1; transform: translateY(0) scale(1); }
        }

        .letter-top { display:flex; align-items:center; gap:14px; margin-bottom: 14px; }

        .card-thumb {
            width: 92px;
            border-radius: 8px;
            border: 3px solid #fff;
            outline: 1.5px solid rgba(120,90,50,0.35);
            box-shadow: 0 4px 12px rgba(0,0,0,0.28);
            animation: cardFlip 0.6s ease;
        }
        @keyframes cardFlip {
            from { transform: rotateY(90deg) scale(0.9); opacity: 0; }
            to   { transform: rotateY(0deg) scale(1); opacity: 1; }
        }

        .card-name-kr {
            font-family: 'Gamja Flower', cursive;
            font-size: 22px;
            color: #4A3B22;
        }
        .card-name-en { font-size: 14px; color: #A5926E; margin-top: 2px; }

        .letter-intro {
            font-size: 16px;
            color: #6B5B44;
            background: rgba(120,90,50,0.06);
            border-radius: 8px;
            padding: 8px 12px;
            margin-bottom: 14px;
        }

        .letter-body {
            font-family: 'Nanum Pen Script', cursive;
            font-size: 24px;
            font-weight: normal;
            line-height: 1.7;
            color: #3A2E1D;
        }
        .letter-body .emphasis {
            /* 고정폭 SVG 대신 네이티브 underline을 써서, 감싼 텍스트(=진짜 임팩트 문장) 길이에
               맞춰 형광펜 줄이 정확히 따라가도록 한다. 줄바꿈된 경우에도 각 줄마다 자연스럽게 그어진다. */
            text-decoration-line: underline;
            text-decoration-color: rgba(88, 196, 83, 0.55);
            text-decoration-thickness: 0.32em;
            text-decoration-skip-ink: none;
            text-underline-offset: -0.06em;
        }

        .moment-block {
            margin: 14px 0 4px;
            padding: 12px 14px;
            border-radius: 10px;
            background: rgba(120, 90, 50, 0.07);
            border-left: 3px solid rgba(88, 196, 83, 0.55);
            font-size: 19px;
            line-height: 1.7;
        }
        .moment-icon {
            margin-right: 4px;
        }

        .tarot-cta {
            margin-top: 18px;
        }
        .tarot-cta-lead {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Malgun Gothic", sans-serif;
            font-size: 18px;
            font-weight: 700;
            color: #6B5B44;
            text-align: center;
            margin-bottom: 10px;
        }
        .tarot-cta-grid {
            display: flex;
            gap: 10px;
        }
        .st-key-tarot_page_root_6n36s5 [data-testid="stMarkdownContainer"] a.tarot-cta-card,
        .st-key-tarot_page_root_6n36s5 [data-testid="stMarkdownContainer"] a.tarot-cta-card:link,
        .st-key-tarot_page_root_6n36s5 [data-testid="stMarkdownContainer"] a.tarot-cta-card:visited {
            flex: 1;
            display: block;
            text-decoration: none !important;
            color: inherit !important;
            border-radius: 14px;
            padding: 16px 14px;
            position: relative;
            transition: transform 0.15s ease;
        }
        .tarot-cta-card.primary {
            background: linear-gradient(135deg, #efe4ff, #f7f0ff);
            border: 1.5px solid rgba(139, 92, 246, 0.35);
        }
        .tarot-cta-card.secondary {
            background: linear-gradient(135deg, #fff6da, #fffaf0);
            border: 1.5px solid rgba(200, 160, 40, 0.35);
        }
        .tarot-cta-badge {
            position: absolute;
            top: -9px;
            right: 12px;
            background: #8B5CF6;
            color: #fff;
            font-size: 11px;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 999px;
        }
        .tarot-cta-icon { font-size: 26px; }
        .tarot-cta-title {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Malgun Gothic", sans-serif;
            font-size: 21px;
            font-weight: 900;
            color: #3A2E1D;
            margin-top: 4px;
        }
        .tarot-cta-desc {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Malgun Gothic", sans-serif;
            font-size: 14.5px;
            font-weight: 600;
            color: #6B5B44;
            margin-top: 4px;
            line-height: 1.45;
        }

        /* 실제 셔플을 발생시키는 버튼은 화면에는 숨기고, 스와이프 컴포넌트가 대신 클릭한다 */
        .st-key-shuffle_btn { display: none !important; }
        </style>
        """)
    # 마크다운 파서가 <style> 내부의 빈 줄에서 HTML 블록을 끊고 이후 내용을
    # 일반 문단(텍스트)으로 다시 파싱하는 문제가 있어, 빈 줄을 전부 제거해서
    # <style> 태그가 끊기지 않고 끝까지 raw HTML로 유지되게 한다.
    css = "\n".join(line for line in css.splitlines() if line.strip())
    st.markdown(css, unsafe_allow_html=True)


def _today_str() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def remaining_draws_today(guest_id: str) -> int:
    """세션 상태를 건드리지 않고, 이 guest_id가 오늘 몇 회 더 뽑을 수 있는지만 조회.

    메인화면의 타로 카드가 실제로 타로 페이지에 들어가기 전에 미리 "오늘은 다
    봤어요" 안내를 보여주기 위해 쓴다 — session_state를 쓰는 _draws_remaining()과
    달리 순수 조회 함수라 메인화면·타로 페이지 어디서 불러도 서로 상태를 오염시키지
    않는다.
    """
    from marketing_db import get_guest_tarot_draw_count, init_marketing_tables

    init_marketing_tables()
    used = get_guest_tarot_draw_count(guest_id, _today_str())
    return max(0, MAX_DAILY_DRAWS - used)


def _draws_remaining() -> int:
    """오늘(KST) 남은 뽑기 횟수. 날짜가 바뀌면 자동으로 초기화된다.

    session_state만으로 세면 앱을 완전히 껐다가 다시 켤 때(새 세션 시작) 값이
    사라져서 하루 제한이 무의미해지는 문제가 있었다. 예전엔 쿠키에 오늘 뽑은
    횟수를 저장해뒀는데, 안드로이드 웹뷰가 화면 전환마다 새로 생성되는 구조상
    쿠키가 디스크에 저장되기 전에 유실되곤 해서 "재접속하면 계속 뽑을 수 있는"
    문제로 이어졌다. 지금은 guest_id(자동구매 내역과 동일한 식별자)에 묶어
    DB(guest_tarot_draws)에 저장하므로 그 타이밍 문제 자체가 없다.
    """
    today = _today_str()
    if st.session_state.get("tarot_daily_date") != today:
        st.session_state["tarot_daily_date"] = today
        from marketing_db import get_guest_tarot_draw_count, init_marketing_tables

        init_marketing_tables()
        guest_id = get_or_create_guest_id()
        restored = get_guest_tarot_draw_count(guest_id, today)
        st.session_state["tarot_daily_count"] = max(0, min(MAX_DAILY_DRAWS, restored))
    return MAX_DAILY_DRAWS - st.session_state["tarot_daily_count"]


def _register_draw():
    """실제 카드가 결정되는 시점(셔플)에 한 번 호출해 오늘의 뽑기 횟수를 소진한다."""
    from marketing_db import init_marketing_tables, register_guest_tarot_draw

    _draws_remaining()  # 날짜 롤오버 보장
    init_marketing_tables()
    guest_id = get_or_create_guest_id()
    new_count = register_guest_tarot_draw(guest_id, _today_str())
    st.session_state["tarot_daily_count"] = max(st.session_state["tarot_daily_count"] + 1, new_count)


def _reset():
    for k in ("tarot_stage", "tarot_category", "tarot_subcategory", "tarot_card_key"):
        st.session_state.pop(k, None)


def _render_extra_draw_gate():
    """오늘 무료 뽑기(1회)를 다 쓴 상태 — 적립금 결제로 추가 1회를 열어준다."""
    st.info("오늘 무료 뽑기를 이미 사용했어요. 적립금으로 한 번 더 뽑을 수 있어요.")

    if st.button("✨ 50P로 한 번 더 뽑기", type="primary", use_container_width=True, key="tarot_extra_draw_btn"):
        from wallet_ui import ensure_member_or_banner

        if ensure_member_or_banner(
            resume="open_tarot_dialog",
            reason="타로 추가 뽑기를 위해 간편인증이 필요합니다.",
        ):
            st.session_state["open_tarot_dialog"] = True
            st.rerun()

    if st.session_state.get("open_tarot_dialog"):
        from wallet_ui import points_notice_dialog

        def _tarot_dialog_close(confirmed: bool) -> None:
            st.session_state["open_tarot_dialog"] = False
            if confirmed:
                from auth_kakao import current_member_id
                from wallet_db import TAROT_EXTRA_DRAW_COST, deduct_points

                mid = current_member_id()
                if mid:
                    import uuid

                    ref = f"tarot:{mid}:{uuid.uuid4().hex[:10]}"
                    deduct_points(mid, TAROT_EXTRA_DRAW_COST, "tarot:extra_draw", ref)
            # 테스트 기간이라 취소를 눌러도 추가 뽑기를 그대로 열어준다.
            st.session_state["tarot_paid_extra_unlocked"] = True

        points_notice_dialog("tarot", on_close=_tarot_dialog_close)

    if st.button("처음으로", use_container_width=True, key="tarot_extra_gate_home"):
        _reset()
        st.rerun()


# ────────────────────────────────────────────────
# 메인 렌더 함수
# ────────────────────────────────────────────────

def render():
    _inject_base_css()
    st.session_state.setdefault("tarot_stage", "category")

    # guest_id가 URL 쿼리 파라미터(?gid=...) 없이(=브라우저 직접 접속) 처음
    # 발급된 경우에만, 다음 방문에서도 이어지도록 쿠키에 남겨둔다. 네이티브
    # 앱 경로에서는 gid가 항상 쿼리로 들어오므로 이 동기화가 필요 없다.
    if not st.session_state.get("_guest_id_confirmed"):
        components.html(guest_id_cookie_sync_html(get_or_create_guest_id()), height=0)

    # 예전엔 st.markdown으로 <div class="tarot-wrap">를 열고 별도의 st.markdown 호출로
    # 닫았는데, Streamlit은 각 st.markdown 호출을 독립된 조각으로 렌더링해서 실제로는
    # 감싸지지 않고 빈 div만 남았다 — 그 안을 겨냥한 CSS가 전혀 안 먹히고 있었다.
    # st.container(key=...)를 쓰면 진짜로 그 안의 위젯들을 감싸는 DOM이 생긴다.
    with st.container(key="tarot_page_root_6n36s5"):
        stage = st.session_state["tarot_stage"]

        # 예전엔 카테고리→소분류를 다 고른 "뽑기" 단계에서야 오늘 한도 소진을
        # 알려줬다 — 이미 카드를 고른(card_key 있음) 결과 화면(stage=="result")이
        # 아닌 이상, 카테고리 선택 단계부터 바로 안내해서 헛걸음하지 않게 한다.
        if (
            stage != "result"
            and st.session_state.get("tarot_card_key") is None
            and _draws_remaining() <= 0
            and not st.session_state.get("tarot_paid_extra_unlocked")
        ):
            _render_extra_draw_gate()
            return

        if stage == "category":
            _render_category_select()
        elif stage == "subcategory":
            _render_subcategory_select()
        elif stage == "draw":
            _render_draw_stage()
        elif stage == "result":
            _render_result()


def _render_category_select():
    st.markdown("##### 지금, 마음이 어디에 머물러 있나요")
    cats = list(SUBCATEGORIES.keys())
    with st.container(key="tarot_cat_grid_6n36s5"):
        cols = st.columns(2)
        for i, cat in enumerate(cats):
            with cols[i % 2]:
                icon = CATEGORY_ICON.get(cat, "✦")
                if st.button(f"{icon}  {cat}", key=f"cat_{i}", use_container_width=True):
                    st.session_state["tarot_category"] = cat
                    st.session_state["tarot_stage"] = "subcategory"
                    st.rerun()


def _render_subcategory_select():
    cat = st.session_state["tarot_category"]
    subs = list(SUBCATEGORIES[cat].keys())

    if st.button("‹ 뒤로", key="back_to_cat"):
        st.session_state["tarot_stage"] = "category"
        st.rerun()

    st.markdown(f"##### {CATEGORY_ICON.get(cat,'✦')}  {cat}")
    with st.container(key="tarot_sub_list_6n36s5"):
        for i, sub in enumerate(subs):
            if st.button(sub, key=f"sub_{i}", use_container_width=True):
                st.session_state["tarot_subcategory"] = sub
                st.session_state["tarot_stage"] = "draw"
                st.rerun()


def _draw_card():
    """SPREADS[ACTIVE_SPREAD]에 정의된 장수만큼 78장 중 무작위로 뽑는다 (현재 "single"은 1장)."""
    num_cards = SPREADS[ACTIVE_SPREAD]["num_cards"]
    key = random.sample(list(CARDS.keys()), num_cards)[0]
    return key, CARDS[key]


def _render_draw_stage():
    """소분류 도입부 표시 → [카드 섞기]로 서버에서 카드 확정 → 인터랙티브 뒤집기."""
    cat = st.session_state["tarot_category"]
    sub = st.session_state["tarot_subcategory"]
    intro_text = SUBCATEGORIES[cat][sub]
    bg = CATEGORY_THEME.get(cat, "#FBF5E7")

    if st.button("‹ 뒤로", key="back_to_sub"):
        st.session_state.pop("tarot_card_key", None)
        st.session_state["tarot_stage"] = "subcategory"
        st.rerun()

    st.markdown(
        f'<div class="intro-card" style="background:{bg};">{intro_text}</div>',
        unsafe_allow_html=True,
    )

    card_key = st.session_state.get("tarot_card_key")

    if card_key is None:
        # 한도 소진 여부는 render()에서 이 단계까지 오기 전에 이미 걸러진다.
        remaining = _draws_remaining()
        st.caption(f"오늘 남은 뽑기: {remaining}회")
        _render_shuffle_deck()
        if st.button("⟲", key="shuffle_btn"):
            key, _card = _draw_card()
            st.session_state["tarot_card_key"] = key
            if st.session_state.pop("tarot_paid_extra_unlocked", False):
                # 유료로 연 추가 1회 — 오늘 무료 한도 카운터는 그대로 두고(이미 소진),
                # 이번 건은 결제로 이미 처리됐으니 별도 등록 없이 언락 플래그만 소모한다.
                pass
            else:
                _register_draw()
            st.rerun()
        return

    # 카드는 이미 서버에서 확정된 상태 — 뒤집기는 컴포넌트 안에서 순수 JS로 처리
    _render_flip_component(card_key)

    if st.button("해석 보기 →", key="reveal_result_btn", use_container_width=True):
        st.session_state["tarot_stage"] = "result"
        st.rerun()


def _render_shuffle_deck():
    """카드를 낙엽처럼 흩어놓고, 손가락으로 실제로 저어야(드래그 이동량 누적) 섞이는
    인터랙션. 충분히 저으면 카드들이 다시 모이는 연출 후, 숨겨진 shuffle_btn 클릭으로
    서버에서 실제 카드를 확정한다."""
    back_b64 = _img_b64(str(IMAGE_DIR / "card_back.svg"))
    num_cards = 16
    cards_html = "".join(
        f'<div class="scard" style="--ox:{random.uniform(-108, 108):.1f}px; '
        f'--oy:{random.uniform(-50, 50):.1f}px; '
        f'--rot0:{random.uniform(-32, 32):.1f}deg; z-index:{i};"></div>'
        for i in range(num_cards)
    )

    html = f"""
    <div class="wrap">
      <style>
        html, body {{ margin:0; padding:0; background:transparent; overflow:hidden; }}
        .wrap {{ font-family:'Gaegu', sans-serif; text-align:center; padding-top:4px; }}
        .hint {{ color:#8a7a5e; font-size:14px; font-weight:700; margin-bottom:8px; }}
        .progress-track {{
            width:200px; height:5px; margin:0 auto 10px; border-radius:999px;
            background:rgba(120,90,50,0.15); overflow:hidden;
        }}
        .progress-fill {{
            height:100%; width:0%; border-radius:999px;
            background:linear-gradient(90deg,#b389e0,#f9c74f);
            transition:width 0.15s ease-out;
        }}
        .pile {{
            position:relative; width:100%; max-width:340px; height:210px;
            margin:0 auto; touch-action:none; cursor:grab; user-select:none;
        }}
        .pile.pressed {{ cursor:grabbing; }}
        .scard {{
            position:absolute; left:50%; top:50%;
            width:50px; height:78px; margin:-39px 0 0 -25px;
            border-radius:6px;
            background-image:url('data:image/svg+xml;base64,{back_b64}');
            background-size:cover;
            box-shadow:0 3px 8px rgba(0,0,0,0.35);
            transform: translate(var(--ox),var(--oy)) rotate(var(--rot0));
            transition: transform 0.28s cubic-bezier(.22,.85,.32,1.15);
            will-change: transform;
        }}
        .pile.gathering .scard {{
            transition: transform 0.55s cubic-bezier(.4,0,.2,1);
            transform: translate(0,0) rotate(var(--rot0));
        }}
      </style>
      <div class="hint" id="hint">🌀 카드를 손가락으로 천천히 저어보세요</div>
      <div class="progress-track"><div class="progress-fill" id="fill"></div></div>
      <div class="pile" id="pile">{cards_html}</div>
      <script>
      (function() {{
        const pile = document.getElementById('pile');
        const hint = document.getElementById('hint');
        const fill = document.getElementById('fill');
        const cards = Array.from(document.querySelectorAll('.scard'));
        const THRESHOLD = 900;
        let pressed = false, done = false, hinted = false;
        let lastX = 0, lastY = 0, total = 0;

        function cssNum(el, prop) {{
            return parseFloat(getComputedStyle(el).getPropertyValue(prop)) || 0;
        }}

        function pointFromEvent(e) {{
            const rect = pile.getBoundingClientRect();
            return {{ x: e.clientX - rect.left - rect.width / 2, y: e.clientY - rect.top - rect.height / 2 }};
        }}

        function stirAt(x, y) {{
            cards.forEach(function(c) {{
                const cx = cssNum(c, '--ox'), cy = cssNum(c, '--oy');
                const dx = cx - x, dy = cy - y;
                const dist = Math.sqrt(dx * dx + dy * dy) || 1;
                if (dist >= 70) return;
                const push = (70 - dist) / 70;
                const nx = cx + (dx / dist) * push * 22 + (Math.random() * 6 - 3);
                const ny = cy + (dy / dist) * push * 22 + (Math.random() * 6 - 3);
                c.style.setProperty('--ox', Math.max(-118, Math.min(118, nx)).toFixed(1) + 'px');
                c.style.setProperty('--oy', Math.max(-58, Math.min(58, ny)).toFixed(1) + 'px');
                const rot = cssNum(c, '--rot0') + (Math.random() * 10 - 5);
                c.style.setProperty('--rot0', Math.max(-45, Math.min(45, rot)).toFixed(1) + 'deg');
            }});
        }}

        function updateProgress() {{
            const pct = Math.max(0, Math.min(1, total / THRESHOLD));
            fill.style.width = (pct * 100) + '%';
            if (pct > 0.65 && !hinted) {{
                hinted = true;
                hint.textContent = '조금만 더 저어주세요…';
            }}
        }}

        function finish() {{
            if (done) return;
            done = true;
            hint.textContent = '카드가 잘 섞였어요 ✨';
            fill.style.width = '100%';
            pile.classList.add('gathering');
            setTimeout(function() {{
                const btn = window.parent.document.querySelector('.st-key-shuffle_btn button')
                    || Array.from(window.parent.document.querySelectorAll('button'))
                        .find(function(b) {{ return b.textContent.trim() === '⟲'; }});
                if (btn) btn.click();
            }}, 620);
        }}

        pile.addEventListener('pointerdown', function(e) {{
            if (done) return;
            pressed = true;
            pile.classList.add('pressed');
            const p = pointFromEvent(e);
            lastX = p.x; lastY = p.y;
            stirAt(p.x, p.y);
        }});
        pile.addEventListener('pointermove', function(e) {{
            if (!pressed || done) return;
            const p = pointFromEvent(e);
            const dx = p.x - lastX, dy = p.y - lastY;
            const moved = Math.sqrt(dx * dx + dy * dy);
            if (moved > 2) {{
                total += moved;
                lastX = p.x; lastY = p.y;
                stirAt(p.x, p.y);
                updateProgress();
                if (total >= THRESHOLD) finish();
            }}
        }});
        pile.addEventListener('pointerup', function() {{
            pressed = false;
            pile.classList.remove('pressed');
        }});
        pile.addEventListener('pointercancel', function() {{
            pressed = false;
            pile.classList.remove('pressed');
        }});
      }})();
      </script>
    </div>
    """

    components.html(html, height=270, scrolling=False)


def _render_flip_component(card_key: str):
    card = CARDS[card_key]
    img_path = IMAGE_DIR / card["image"].split("/")[-1]
    front_b64 = _img_b64(str(img_path)) if img_path.exists() else ""
    back_b64 = _img_b64(str(IMAGE_DIR / "card_back.svg"))
    name_kr = card["name_kr"] or card["name_en"]

    payload = json.dumps({
        "front": f"data:image/jpeg;base64,{front_b64}",
        "nameKr": name_kr,
        "nameEn": card["name_en"],
    })

    n = len(MAJOR_KEYS)
    spread_deg = 100  # 부채꼴 전체 각도
    start_deg = -spread_deg / 2
    step_deg = spread_deg / (n - 1)
    slots_html = "".join(
        f'<div class="tcard" style="--rot:{start_deg + i * step_deg:.2f}deg; z-index:{i};" data-idx="{i}"></div>'
        for i in range(n)
    )

    html = f"""
    <div class="wrap">
      <style>
        html, body {{ margin:0; padding:0; background:transparent; overflow:hidden; }}
        .wrap {{ font-family: 'Gaegu', sans-serif; text-align:center; }}
        .hint {{ color:#8a7a5e; font-size:14px; font-weight:700; margin:2px 0 10px; }}
        .grid {{
            position:relative; height:160px; margin:4px auto 0;
            width:100%; max-width:520px; perspective:800px;
        }}
        .tcard {{
            position:absolute; left:50%; top:0; margin-left:-20px;
            width:40px; height:66px; border-radius:5px; cursor:pointer;
            background-image:url('data:image/svg+xml;base64,{back_b64}');
            background-size:cover; box-shadow:0 2px 6px rgba(0,0,0,0.35);
            transform-origin:50% var(--originY,220px);
            transform:rotate(var(--rot,0deg));
            transition:transform 0.4s cubic-bezier(.22,.85,.32,1.2), box-shadow 0.2s ease;
            transform-style:preserve-3d;
        }}
        .tcard:hover {{ transform:rotate(var(--rot,0deg)) translateY(-8px); box-shadow:0 6px 12px rgba(0,0,0,0.4); z-index:50 !important; }}
        .tcard.flipped {{ transform:rotate(var(--rot,0deg)) translateY(-8px) rotateY(180deg); box-shadow:0 4px 14px rgba(0,0,0,0.45); z-index:60 !important; }}
        .tcard.dim {{ opacity:0.35; pointer-events:none; }}
        .reveal {{
            margin-top:14px; display:none; flex-direction:column; align-items:center;
            animation:pop 0.4s ease;
        }}
        .reveal.show {{ display:flex; }}
        @keyframes pop {{ from {{opacity:0; transform:scale(0.9);}} to {{opacity:1; transform:scale(1);}} }}
        .reveal img {{ width:110px; border-radius:8px; border:3px solid #fff;
            outline:1.5px solid rgba(120,90,50,0.35); box-shadow:0 4px 12px rgba(0,0,0,0.28); }}
        .reveal .kr {{ font-size:20px; font-weight:700; color:#4A3B22; margin-top:8px; }}
        .reveal .en {{ font-size:14px; color:#A5926E; }}
      </style>

      <div class="hint">펼쳐진 카드 중 마음이 가는 한 장을 눌러보세요</div>
      <div class="grid" id="grid">{slots_html}</div>
      <div class="reveal" id="reveal">
        <img id="revealImg" src="" alt="">
        <div class="kr" id="revealKr"></div>
        <div class="en" id="revealEn"></div>
      </div>

      <script>
        const CARD = {payload};
        let revealed = false;

        function layoutFan() {{
            const grid = document.getElementById('grid');
            const w = grid.clientWidth || window.innerWidth;
            const maxAngleRad = ({spread_deg / 2} * Math.PI) / 180;
            const radius = Math.max(130, Math.min(240, w * 0.52));
            const dip = radius * (1 - Math.cos(maxAngleRad));
            document.querySelectorAll('.tcard').forEach(function(c) {{
                c.style.setProperty('--originY', radius + 'px');
            }});
            grid.style.height = Math.ceil(dip + 74) + 'px';
        }}
        layoutFan();
        window.addEventListener('resize', layoutFan);

        document.getElementById('grid').addEventListener('click', function(e) {{
            const el = e.target.closest('.tcard');
            if (!el || revealed) return;
            revealed = true;
            el.classList.add('flipped');
            document.querySelectorAll('.tcard').forEach(function(c) {{
                if (c !== el) c.classList.add('dim');
            }});
            setTimeout(function() {{
                document.getElementById('revealImg').src = CARD.front;
                document.getElementById('revealKr').textContent = CARD.nameKr;
                document.getElementById('revealEn').textContent = CARD.nameEn;
                document.getElementById('reveal').classList.add('show');
            }}, 320);
        }});
      </script>
    </div>
    """

    components.html(html, height=420, scrolling=False)


def _split_moment(moment: str) -> tuple[str, str]:
    """moment 필드는 '감각 초대 문장. 의미(임팩트) 문장.' 2문장 구조로 작성돼 있다.
    뒤쪽 문장이 진짜 강조할 내용이라, 그 부분만 emphasis로 감싸기 위해 나눈다."""
    if ". " in moment:
        lead, impact = moment.split(". ", 1)
        return lead + ".", impact
    return moment, ""


def _render_result():
    cat = st.session_state["tarot_category"]
    sub = st.session_state["tarot_subcategory"]
    card_key = st.session_state["tarot_card_key"]
    card = CARDS[card_key]
    intro_text = SUBCATEGORIES[cat][sub]
    bg = CATEGORY_THEME.get(cat, "#FBF5E7")

    img_path = IMAGE_DIR / card["image"].split("/")[-1]
    img_b64 = _img_b64(str(img_path)) if img_path.exists() else ""

    name_kr = card["name_kr"] or card["name_en"]
    moment_lead, moment_impact = _split_moment(card.get("moment", ""))
    moment_html = (
        f'<span class="moment-icon">🌿</span>{moment_lead} '
        f'<span class="emphasis">{moment_impact}</span>'
        if moment_impact else f'<span class="moment-icon">🌿</span>{moment_lead}'
    )

    st.markdown(
        textwrap.dedent(f"""
        <div class="letter" style="background:{bg};">
            <div class="intro-card" style="background:rgba(120,90,50,0.05);">
                {intro_text}
            </div>
            <div class="letter-top">
                <img class="card-thumb" src="data:image/jpeg;base64,{img_b64}">
                <div>
                    <div class="card-name-kr">{name_kr}</div>
                    <div class="card-name-en">{card['name_en']}</div>
                </div>
            </div>
            <div class="letter-intro">{card['intro']}</div>
            <div class="letter-body">
                {card['state']}<br>{card['comfort']}<br>{card['acceptance']}
            </div>
            <div class="moment-block">{moment_html}</div>
            <div class="letter-body">{card['hope']}</div>
        </div>
        <div class="tarot-cta">
            <div class="tarot-cta-lead">오늘 마음에 담은 카드, 번호에도 그 기운을 실어볼까요</div>
            <div class="tarot-cta-grid">
                <a class="tarot-cta-card primary" href="?page=auto" target="_self">
                    <span class="tarot-cta-badge">지금 이 흐름대로</span>
                    <div class="tarot-cta-icon">💎</div>
                    <div class="tarot-cta-title">자동구매</div>
                    <div class="tarot-cta-desc">고민 없이, 오늘의 조합을<br>바로 받아보세요</div>
                </a>
                <a class="tarot-cta-card secondary" href="?page=thunder&fresh=1" target="_self">
                    <div class="tarot-cta-icon">⚡</div>
                    <div class="tarot-cta-title">번개조합</div>
                    <div class="tarot-cta-desc">전문가 분석 기반으로<br>번호를 직접 골라보세요</div>
                </a>
            </div>
        </div>
        """),
        unsafe_allow_html=True,
    )

    remaining = _draws_remaining()
    extra_unlocked = st.session_state.get("tarot_paid_extra_unlocked", False)
    if remaining <= 0 and not extra_unlocked:
        _render_extra_draw_gate()
        return

    col1, col2 = st.columns(2)
    with col1:
        label = "🔄 한 번 더 뽑기" if extra_unlocked else f"🔄 다시 뽑기 ({remaining}회 남음)"
        if st.button(label, use_container_width=True):
            st.session_state.pop("tarot_card_key", None)
            st.session_state["tarot_stage"] = "draw"
            st.rerun()
    with col2:
        if st.button("처음으로", use_container_width=True):
            _reset()
            st.rerun()


# 단독 실행 테스트용 (streamlit run tarot_page.py)
if __name__ == "__main__":
    st.set_page_config(page_title="오늘의 타로 한 장", page_icon="🔮")
    render()
