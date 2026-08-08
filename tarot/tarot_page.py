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
import random
import textwrap
from pathlib import Path

import streamlit as st

from tarot_data import SUBCATEGORIES, CARDS

BASE_DIR = Path(__file__).parent
IMAGE_DIR = BASE_DIR / "images"

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
        <link href="https://fonts.googleapis.com/css2?family=Gaegu:wght@400;700&family=Gamja+Flower&display=swap" rel="stylesheet">
        <style>
        .tarot-wrap * { box-sizing: border-box; }
        .tarot-wrap { font-family: 'Gaegu', sans-serif; }

        /* 카테고리 그리드 */
        .cat-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-top: 6px;
        }

        /* 소분류 도입부 카드 */
        .intro-card {
            border-radius: 12px;
            padding: 18px 20px;
            font-size: 19px;
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
            font-size: 21px;
            color: #4A3B22;
        }
        .card-name-en { font-size: 13px; color: #A5926E; margin-top: 2px; }

        .letter-intro {
            font-size: 15px;
            color: #6B5B44;
            background: rgba(120,90,50,0.06);
            border-radius: 8px;
            padding: 8px 12px;
            margin-bottom: 14px;
        }

        .letter-body {
            font-size: 21px;
            font-weight: 700;
            line-height: 1.6;
            color: #3A2E1D;
        }
        .letter-body .hope {
            display: block;
            margin-top: 8px;
            color: #7A3B2E;
            background: linear-gradient(to top, rgba(212,165,116,0.4) 45%, transparent 45%);
            padding: 0 2px;
        }
        </style>
        """)
    # 마크다운 파서가 <style> 내부의 빈 줄에서 HTML 블록을 끊고 이후 내용을
    # 일반 문단(텍스트)으로 다시 파싱하는 문제가 있어, 빈 줄을 전부 제거해서
    # <style> 태그가 끊기지 않고 끝까지 raw HTML로 유지되게 한다.
    css = "\n".join(line for line in css.splitlines() if line.strip())
    st.markdown(css, unsafe_allow_html=True)


def _reset():
    for k in ("tarot_stage", "tarot_category", "tarot_subcategory", "tarot_card_key"):
        st.session_state.pop(k, None)


# ────────────────────────────────────────────────
# 메인 렌더 함수
# ────────────────────────────────────────────────

def render():
    _inject_base_css()
    st.session_state.setdefault("tarot_stage", "category")

    st.markdown('<div class="tarot-wrap">', unsafe_allow_html=True)

    stage = st.session_state["tarot_stage"]

    if stage == "category":
        _render_category_select()
    elif stage == "subcategory":
        _render_subcategory_select()
    elif stage == "result":
        _render_result()

    st.markdown('</div>', unsafe_allow_html=True)


def _render_category_select():
    st.markdown("##### 지금, 마음이 어디에 머물러 있나요")
    cats = list(SUBCATEGORIES.keys())
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
    for i, sub in enumerate(subs):
        if st.button(sub, key=f"sub_{i}", use_container_width=True):
            st.session_state["tarot_subcategory"] = sub
            key, _card = _draw_card()
            st.session_state["tarot_card_key"] = key
            st.session_state["tarot_stage"] = "result"
            st.rerun()


def _draw_card():
    """78장 중 완전 무작위 1장 (카테고리와 무관)"""
    key = random.choice(list(CARDS.keys()))
    return key, CARDS[key]


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
                <span class="hope">{card['hope']}</span>
            </div>
        </div>
        """),
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 다시 뽑기", use_container_width=True):
            key, _c = _draw_card()
            st.session_state["tarot_card_key"] = key
            st.rerun()
    with col2:
        if st.button("처음으로", use_container_width=True):
            _reset()
            st.rerun()


# 단독 실행 테스트용 (streamlit run tarot_page.py)
if __name__ == "__main__":
    st.set_page_config(page_title="오늘의 타로 한 장", page_icon="🔮")
    render()
