"""1·2등 배출 이벤트 배너 — 메인화면에서 회차당 1회 뜨는 축하 모달 (2026-10-04 확정 설계).

이 파일이 이벤트 배너의 **단일 기준점**이다(트리거·1회 노출·닫기 처리·문구).
  · 트리거 : marketing_db.get_latest_win_event_round()
             = 가장 최근에 확정된 회차가 1·2등 히트일 때만. 1244회차부터 노출한다
               (marketing_db.WIN_EVENT_BANNER_MIN_ROUND — 이미 지난 히트라 지금 뜨면 어색).
  · 1회    : **닫을 때** marketing_db.mark_win_event_banner_closed(guest_id, 회차)로 기록
             (guest_update_notice의 "win_event:{회차}" 키 — 업데이트 안내 배너와 같은 방식).
             렌더 시점에 기록하지 않으므로, 떴지만 못 보고 지나간 경우 다음에 다시 뜬다.
  · 닫기    : [다시 보지 않기] [확인] 두 버튼 + 우상단 X 까지 전부 "봤음"으로 기록한다.
             X는 서버가 관측할 수 없으므로 관찰 스크립트가 닫힘을 감지해 숨김 버튼을
             클릭해 준다(이 저장소가 이미 쓰는 JS→st.button 브리지 방식).
  · 문구    : B안(수치 근거형) 고정 — "필터 통과 조합 기준"을 명시해 실제 판매 당첨으로
             오인되지 않게 한다(구름님 확정).

화면(user_page.py)은 main 렌더에서 maybe_show_win_event_banner()만 호출한다.
시각 스타일은 아래 STYLES에서 고르며, 샘플 HTML도 같은 함수로 만들어 화면과 100% 동일하다.
"""

from __future__ import annotations

import html as _html

import streamlit as st

import dialog_registry

# ── 확정 문구 (B안) ────────────────────────────────────────────────────────
# 2026-10-04 재확정(구름님): **배출 등수만 간략 표기 · 조합수량 뺄 것 · 미사여구 넣지 말 것.**
BANNER_TITLE = "🏆 {draw_round}회차 결과 — {rank_label}"
BANNER_HEAD = "필터 통과 조합 기준"
BANNER_RANKS = "{hit_list}"
BTN_NEVER = "다시 보지 않기"
BTN_OK = "확인"

CLOSED_BTN_KEY = "win_event_banner_closed_btn"
NEVER_BTN_KEY = "win_event_banner_never"
OK_BTN_KEY = "win_event_banner_ok"
DIALOG_NAME = "win_event_banner"

# 시각 스타일 — 샘플(1~4) 중 구름님이 고른 번호. 2026-10-04 확정: **샘플 2(네온)**.
CHOSEN_STYLE = 2

# 등수는 1~3등까지만 간단 표기한다(4·5등은 메인 표에서 본다).
HIT_LABELS = ("1등", "2등", "3등")


def _rank_label(info: dict) -> str:
    """제목에 들어가는 배출 등수 — 실제로 나온 등수만 적는다(미사여구 없이)."""
    rank_1 = int(info.get("rank_1") or 0)
    rank_2 = int(info.get("rank_2") or 0)
    if rank_1 > 0 and rank_2 > 0:
        return "1·2등 배출"
    if rank_1 > 0:
        return "1등 배출"
    return "2등 배출"


def _hit_list(info: dict) -> str:
    """등수 한 줄 — **나온 등수만** 짧게(0개인 등수는 빼고, 조합수량·군말 없이).

    예: "2등 1개 · 3등 18개"
    """
    parts = [
        f"{label} {int(info.get(f'rank_{i}') or 0)}개"
        for i, label in enumerate(HIT_LABELS, start=1)
        if int(info.get(f"rank_{i}") or 0) > 0
    ]
    return " · ".join(parts)


CONFETTI_COLORS = ("#4ff0ff", "#ff5cf0", "#8a5cff", "#ffd66b", "#7cff9b")


def _particles_html(style_id: int, count: int) -> str:
    """폭죽(색종이) — 2026-10-04 지시: "폭죽 내려오는 모습" 추가.

    색을 여러 개 섞고, 떨어지는 애니메이션을 무한 반복(아래 CSS)으로 둔다 — 창이 닫히면
    이 모듈 자체가 사라져 자연히 멈춘다. 지연(--d)을 입자마다 어긋나게 줘서 줄줄이 떨어진다.
    """
    if count <= 0:
        return ""
    spans = "".join(
        f'<span class="wev-p" style="--i:{i}; --x:{4 + (i * 7) % 92}%; '
        f'--d:{round((i * 0.19) % 2.6, 2)}s; --r:{(i * 47) % 360}deg; '
        f'--c:{CONFETTI_COLORS[i % len(CONFETTI_COLORS)]}"></span>'
        for i in range(count)
    )
    return f'<div class="wev-particles" aria-hidden="true">{spans}</div>'


# ── 스타일 정의 ────────────────────────────────────────────────────────────
# 1 금색 클래식(그라데이션 테두리) · 2 네온(시안/보라) · 3 미니멀 골드 라인(정적)
# 4 축제(컬러 그라데이션 + 입자 최대)
STYLES: dict[int, dict[str, object]] = {
    1: {
        "name": "금색 클래식",
        "desc": "금색 그라데이션 테두리 + 은은한 발광, 반짝임 1회, 금색 입자 10개",
        "border": "linear-gradient(135deg, #ffd66b 0%, #b8860b 45%, #ffe9a8 100%)",
        "bg": "radial-gradient(120% 130% at 50% -20%, #2a2416 0%, #14121a 55%, #0d0d12 100%)",
        "accent": "#ffd66b",
        "title_color": "#ffe9a8",
        "glow": "0 0 0 1px rgba(255,214,107,.25), 0 18px 48px rgba(0,0,0,.6)",
        "shine": True,
        "particles": 10,
        "pulse": False,
    },
    2: {
        "name": "네온",
        "desc": "시안-보라 네온 테두리 + 강한 발광, 빛 사선 계속 지나감, 폭죽 내려옴",
        "border": "linear-gradient(135deg, #4ff0ff 0%, #8a5cff 50%, #ff5cf0 100%)",
        "bg": "radial-gradient(120% 130% at 50% -20%, #102033 0%, #0b1020 55%, #07070f 100%)",
        "accent": "#4ff0ff",
        "title_color": "#c8f9ff",
        "glow": "0 0 28px rgba(79,240,255,.45), 0 0 60px rgba(138,92,255,.35)",
        "shine": True,
        "particles": 14,
        "pulse": True,
    },
    3: {
        "name": "미니멀 금선",
        "desc": "얇은 금색 라인 + 차분한 등장만(반짝임·입자 없음) — 가장 조용한 버전",
        "border": "linear-gradient(135deg, #d9b25a 0%, #8a6b1f 100%)",
        "bg": "linear-gradient(180deg, #16161c 0%, #101014 100%)",
        "accent": "#d9b25a",
        "title_color": "#f0e2bd",
        "glow": "0 12px 32px rgba(0,0,0,.55)",
        "shine": False,
        "particles": 0,
        "pulse": False,
    },
    4: {
        "name": "축제",
        "desc": "컬러풀 그라데이션 테두리 + 입자 14개 + 반짝임 — 가장 화려한 버전",
        "border": "linear-gradient(135deg, #ff4d6d 0%, #ffb703 35%, #4cc9f0 70%, #b5179e 100%)",
        "bg": "radial-gradient(130% 130% at 50% -30%, #33143a 0%, #1a1024 55%, #0d0a12 100%)",
        "accent": "#ffb703",
        "title_color": "#ffe3a3",
        "glow": "0 0 0 1px rgba(255,183,3,.28), 0 20px 52px rgba(0,0,0,.62)",
        "shine": True,
        "particles": 14,
        "pulse": False,
    },
}


def style_css(style_id: int) -> str:
    """스타일 하나의 CSS — 화면(st.dialog)과 샘플 HTML이 이 함수를 함께 쓴다(이중 구현 방지)."""
    style = STYLES[int(style_id)]
    pulse = (
        "@keyframes wevPulse { 0%,100%{filter:brightness(1)} 50%{filter:brightness(1.35)} }"
        ".wev-card{animation: wevIn .38s cubic-bezier(.2,.8,.3,1.15) both, wevPulse 2.6s ease-in-out .5s 2;}"
        if style["pulse"]
        else ""
    )
    shine = (
        """
@keyframes wevShine {
  0%   { transform: translateX(-190%) rotate(18deg) scaleY(1.15); opacity: 0; }
  6%   { opacity: 1; }
  88%  { opacity: 1; }
  100% { transform: translateX(230%) rotate(18deg) scaleY(1.15); opacity: 0; }
}
/* 2026-10-04 지시: 모바일에서 사선이 잘 안 보인다 → 더 밝게/넓게 + 창이 닫힐 때까지 계속.
   또 한 번 지시: 중간에서 사라진다 → 카드 **오른쪽 끝을 지나서** 퇴장하도록 범위 확대
   (-190% → 230%). 불투명도는 88%까지 유지하고 마지막에만 0으로 줄인다. */
.wev-shine { animation: wevShine 3.4s cubic-bezier(.4,0,.6,1) .3s infinite; }
"""
        if style["shine"]
        else ".wev-shine{display:none;}"
    )
    return f"""
@keyframes wevIn {{
  from {{ opacity: 0; transform: translateY(10px) scale(.92); }}
  to   {{ opacity: 1; transform: translateY(0) scale(1); }}
}}
@keyframes wevFall {{
  0%   {{ opacity: 0; transform: translateY(-18px) rotate(0deg) scale(.65); }}
  12%  {{ opacity: 1; }}
  100% {{ opacity: 0; transform: translateY(300px) rotate(var(--r)) scale(1); }}
}}
@keyframes wevTwinkle {{
  0%,100% {{ opacity: .25; }} 50% {{ opacity: 1; }}
}}
{pulse}
{shine}
.wev-wrap {{
  position: relative;
  padding: 2px;
  border-radius: 16px;
  background: {style['border']};
  box-shadow: {style['glow']};
  animation: wevIn .38s cubic-bezier(.2,.8,.3,1.15) both;
  overflow: hidden;
}}
.wev-card {{
  position: relative;
  border-radius: 14px;
  padding: 12px 14px 10px;
  background: {style['bg']};
  text-align: center;
  color: #f2f2f6;
  overflow: hidden;
}}
.wev-shine {{
  position: absolute; top: -70%; left: -20%; width: 70%; height: 260%;
  background: linear-gradient(90deg,
      rgba(255,255,255,0) 0%,
      rgba(255,255,255,.38) 38%,
      rgba(255,255,255,.98) 50%,
      rgba(255,255,255,.38) 62%,
      rgba(255,255,255,0) 100%);
  filter: blur(1px);
  mix-blend-mode: screen;
  will-change: transform, opacity;
  pointer-events: none;
}}
.wev-particles {{ position: absolute; inset: 0; pointer-events: none; overflow: hidden; }}
.wev-p {{
  position: absolute; top: -6px; left: var(--x);
  width: 7px; height: 11px; border-radius: 2px;
  background: var(--c);
  opacity: 0;
  animation: wevFall 2.6s linear var(--d) infinite, wevTwinkle 1.3s ease-in-out var(--d) infinite;
}}
@keyframes wevSamplePulse {{ 0%,100% {{ opacity: .55; }} 50% {{ opacity: 1; }} }}
.wev-sample {{
  font-size: 12px; font-weight: 800; letter-spacing: 1px;
  color: #ffffff; background: rgba(255,255,255,.12);
  border: 1px solid rgba(255,255,255,.18);
  border-radius: 6px; padding: 2px 8px;
  display: inline-block; margin-bottom: 10px;
  animation: wevSamplePulse 1.6s ease-in-out infinite;
}}
.wev-badges, .wev-badge {{ /* 등수 뱃지는 2026-10-04 확정으로 제거(등수는 문구 한 줄로만) */ display: none !important; }}
.wev-title {{
  font-size: 17px; font-weight: 900; letter-spacing: -0.6px;
  color: {style['title_color']};
  margin: 0 0 5px;
}}
.wev-head {{ font-size: 12px; color: #c8c8d2; margin-bottom: 6px; }}
.wev-head b {{ color: #ffffff; }}
.wev-ranks {{
  font-size: 14.5px; font-weight: 800; letter-spacing: -0.4px;
  color: #ffffff; line-height: 1.35;
}}
.wev-note {{ margin-top: 10px; font-size: 11.5px; color: #9a9aa6; line-height: 1.5; }}
.wev-sample {{
"""


def card_html(info: dict, style_id: int | None = None, *, sample_label: str = "") -> str:
    """배너 카드 한 장(HTML) — 화면과 샘플이 같은 함수를 쓴다."""
    style_id = CHOSEN_STYLE if style_id is None else int(style_id)
    style = STYLES[style_id]
    label = (
        f'<div class="wev-sample">{_html.escape(sample_label)}</div>' if sample_label else ""
    )
    title = BANNER_TITLE.format(draw_round=int(info["draw_round"]), rank_label=_rank_label(info))
    head = BANNER_HEAD
    ranks = BANNER_RANKS.format(hit_list=_hit_list(info))
    return f"""
<style>{style_css(style_id)}</style>
<div class="wev-wrap">
  <div class="wev-card">
    <div class="wev-shine"></div>
    {_particles_html(style_id, int(style["particles"]))}
    {label}
    <div class="wev-title">{_html.escape(title)}</div>
    <div class="wev-head">{_html.escape(head)}</div>
    <div class="wev-ranks">{_html.escape(ranks)}</div>
  </div>
</div>
"""


@st.dialog("🎉 이벤트 알림")
def _banner_dialog(info: dict) -> None:
    """축하 모달 — 버튼 동선은 기존 안내창(points_notice_dialog)과 같은 2열 구조."""
    import streamlit.components.v1 as components

    # 2026-10-04 실기기 신고 대응: 카드를 st.markdown HTML로 그리면 환경에 따라 태그가
    # 글자로 노출됐다(신고 내용: <div class="wev-title">... 가 그대로 보임). 이 앱이
    # 업데이트 안내 토스트·번개조합 번호판에서 써 오는 components.html(iframe)로 바꿔
    # CSS·애니메이션을 브라우저 기본 동작으로 100% 적용되게 한다.
    components.html(card_iframe_html(info), height=CARD_IFRAME_HEIGHT, scrolling=False)
    c1, c2 = st.columns(2)
    with c1:
        if st.button(BTN_NEVER, use_container_width=True, key=NEVER_BTN_KEY):
            _close_banner(int(info["draw_round"]))
    with c2:
        if st.button(BTN_OK, type="primary", use_container_width=True, key=OK_BTN_KEY):
            _close_banner(int(info["draw_round"]))


CARD_IFRAME_HEIGHT = 120  # 초기값(폴백) — 실제 높이는 아래 리포트 스크립트가 내용에 맞춰 줄인다


def card_iframe_html(info: dict, style_id: int | None = None) -> str:
    """카드 하나를 독립 HTML 문서로 감싼다 — components.html(iframe)로 그리기 위한 것.

    왜 st.markdown이 아니라 iframe인가(2026-10-04 실기기 신고): 실제 앱에서 카드가
    HTML로 그려지지 않고 태그가 글자로 보였다. Streamlit markdown의 HTML 처리에
    의존하지 않고 iframe 안에서 그리면 CSS·애니메이션이 그대로 동작한다.
    배경은 투명(transparent) — 창 배경을 해치지 않게.

    높이는 고정하지 않는다(2026-10-04 신고: 창이 너무 크고 빈 공간이 많다) —
    이 저장소의 신령 이미지 블록과 같은 방식으로 내용 높이를 부모에게 알려
    프레임을 내용에 맞춰 줄인다.
    """
    body = card_html(info, style_id)
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<style>
  html, body {{ margin: 0; padding: 0; background: transparent; }}
  body {{ font-family: "Malgun Gothic", "Apple SD Gothic Neo", sans-serif; }}
</style></head>
<body>{body}
<script>
(function () {{
  function report() {{
    var h = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight) + 1;
    window.parent.postMessage({{type: "streamlit:setFrameHeight", height: h}}, "*");
  }}
  report();
  window.addEventListener("load", report);
  if (window.ResizeObserver) {{ new ResizeObserver(report).observe(document.body); }}
}})();
</script>
</body></html>"""


def _close_banner(draw_round: int) -> None:
    """닫기 처리 — 서버 기록 + 이번 세션 플래그 + 즉시 닫기(재렌더)."""
    from marketing_db import init_marketing_tables, mark_win_event_banner_closed
    from user_scope import get_or_create_guest_id

    init_marketing_tables()
    try:
        mark_win_event_banner_closed(get_or_create_guest_id(), draw_round)
    except Exception:
        # 기록 실패로 창이 안 닫히면 더 나쁘다 — 세션 플래그만으로라도 닫고 넘어간다.
        pass
    st.session_state[dialog_registry.flag_key(DIALOG_NAME)] = True
    st.rerun()


def _render_close_bridge(draw_round: int) -> None:
    """X(우상단)로 닫아도 기록되게 하는 다리 — 숨김 버튼 + 닫힘 감시 스크립트.

    숨김 버튼은 **다이얼로그 밖**(main 영역)에 둔다 — 안에 두면 창이 닫히는 순간
    DOM에서 함께 사라져 클릭할 대상이 없어진다.
    """
    st.markdown(
        """
        <style>
        .st-key-win_event_banner_closed_btn { display: none !important; }

        /* 이 이벤트 창 전용 규칙 (2026-10-04 지시) — components.html iframe을 품은
           다이얼로그에만 적용하도록 :has()로 좁혔다(다른 안내창에는 영향 없음).
             ① 제목 가운데 정렬  ② 버튼 두 개를 한 줄로  ③ 여백(빈 공간) 최소 */
        div[data-testid="stDialog"]:has(iframe[title="st.components.v1.html"]) > div {{ padding: 6px 10px 4px !important; }}
        div[data-testid="stDialog"]:has(iframe[title="st.components.v1.html"]) h2 {{
            text-align: center !important;
            width: 100% !important;
        }}
        div[data-testid="stDialog"]:has(iframe[title="st.components.v1.html"]) > div > div:first-child {{
            justify-content: center !important;
        }}
        div[data-testid="stDialog"]:has(iframe[title="st.components.v1.html"]) [data-testid="stHorizontalBlock"] {{
            flex-wrap: nowrap !important;
            gap: 8px !important;
        }}
        div[data-testid="stDialog"]:has(iframe[title="st.components.v1.html"]) [data-testid="stHorizontalBlock"] > div {{
            width: auto !important;
            min-width: 0 !important;
        }}
        div[data-testid="stDialog"]:has(iframe[title="st.components.v1.html"]) [data-testid="stElementContainer"]:has(iframe) {{
            margin-bottom: 2px !important;
        }}
        div[data-testid="stDialog"]:has(iframe[title="st.components.v1.html"]) button p {{
            font-size: 13px !important;
            white-space: nowrap !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    if st.button("closed-marker", key=CLOSED_BTN_KEY):
        _close_banner(draw_round)

    import streamlit.components.v1 as components

    components.html(
        """
        <script>
        (function () {
            const doc = window.parent.document;
            const SEL = '.st-key-win_event_banner_closed_btn button';
            const DIALOG = 'div[data-testid="stDialog"]';
            let sawDialog = false;
            let fired = false;
            const timer = window.setInterval(function () {
                if (fired) { window.clearInterval(timer); return; }
                if (doc.querySelector(DIALOG)) { sawDialog = true; return; }
                if (!sawDialog) { return; }        // 아직 창이 뜬 적이 없다
                const btn = doc.querySelector(SEL); // 창이 사라졌다 = X 또는 버튼으로 닫힘
                if (!btn) { return; }
                fired = true;
                btn.click();
                window.clearInterval(timer);
            }, 500);
        })();
        </script>
        """,
        height=0,
    )


def maybe_show_win_event_banner() -> None:
    """메인화면 렌더에서 호출 — 조건이 맞으면 이벤트 배너를 띄운다.

    조건: ① 가장 최근 확정 회차가 1·2등 히트(**1244회차부터** — 그 미만은 대상 아님)
          ② 이번 세션에서 아직 닫지 않았고
          ③ 이 guest_id로 그 회차를 아직 닫은 적이 없을 때
    """
    if st.session_state.get(dialog_registry.flag_key(DIALOG_NAME)):
        return

    from marketing_db import (
        get_latest_win_event_round,
        init_marketing_tables,
        was_win_event_banner_closed,
    )
    from user_scope import get_or_create_guest_id

    try:
        init_marketing_tables()
        info = get_latest_win_event_round()
        if not info:
            return
        if was_win_event_banner_closed(get_or_create_guest_id(), int(info["draw_round"])):
            return
    except Exception:
        # 조회 실패로 화면이 죽으면 안 된다 — 배너는 부가 기능이다.
        return

    _render_close_bridge(int(info["draw_round"]))
    _banner_dialog(info)


def sample_html(style_id: int, info: dict) -> str:
    """샘플 파일 생성용 — 같은 카드/문구를 단독 HTML로 렌더(번호 라벨 포함).

    구름님이 직접 열어보고 번호로 고를 수 있게, 파일 안에 "샘플 N"을 큼지막하게 넣는다.
    """
    style = STYLES[int(style_id)]
    label = f"샘플 {style_id}"
    card = card_html(info, style_id, sample_label="")
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{label} — 1·2등 배출 배너</title>
<style>
  html, body {{ margin: 0; padding: 0; background: #0b0b10; color: #f2f2f6;
    font-family: "Malgun Gothic", "Apple SD Gothic Neo", sans-serif; }}
  .sample-page {{ max-width: 420px; margin: 0 auto; padding: 22px 16px 40px; }}
  .sample-no {{ font-size: 44px; font-weight: 900; letter-spacing: -2px;
    color: #ffffff; text-align: center; margin: 6px 0 4px; }}
  .sample-desc {{ text-align: center; font-size: 12.5px; color: #9a9aa6; margin-bottom: 18px; }}
  .sample-btns {{ display: flex; gap: 10px; margin-top: 14px; }}
  .sample-btn {{ flex: 1; height: 42px; border-radius: 10px; font-size: 14px; font-weight: 800;
    border: 1px solid #3a3a46; background: #1b1b22; color: #e8e8ee; }}
  .sample-btn.primary {{ background: linear-gradient(180deg, #2f6df6, #2456c8); border-color: #2f6df6; color: #fff; }}
  .sample-foot {{ margin-top: 18px; font-size: 11.5px; color: #7c7c88; line-height: 1.6; }}
</style></head>
<body>
  <div class="sample-page">
    <div class="sample-no">{label}</div>
    <div class="sample-desc">{style['name']} — {style['desc']}</div>
    {card}
    <div class="sample-btns">
      <button class="sample-btn" type="button">{BTN_NEVER}</button>
      <button class="sample-btn primary" type="button">{BTN_OK}</button>
    </div>
    <div class="sample-foot">
      · 문구는 확정 문구 그대로입니다 — 배출 등수만 간략 표기, 조합수량·군말 없음.<br>
      · 버튼은 실제 모달과 같은 자리·같은 규격입니다(이 샘플 파일에서는 동작하지 않습니다).<br>
      · 애니메이션은 페이지를 열 때 1회 재생됩니다 — 다시 보려면 새로고침하세요.
    </div>
  </div>
</body></html>
"""
