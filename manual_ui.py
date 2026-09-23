"""사용자 사용설명서 — 메인화면 "📖 사용설명서" 버튼으로 여는 화면별 안내 초안.

⚠️ 초안 상태(2026-09-21): 이 파일은 아직 어느 화면에도 연결하지 않았다.
   컨펌 후 user_page.py 메인 화면에서 아래 두 줄만 호출하면 게시된다.
       from manual_ui import maybe_open_manual, render_manual_trigger_button
       render_manual_trigger_button()   # render_wallet_bar(...) 바로 다음 줄
       maybe_open_manual()              # 같은 블록 마지막

설계 원칙(이 프로젝트의 기존 규칙을 따른다):
  · **수치를 하드코딩하지 않는다** — 적립금은 legal_notices.PRICING(단일 출처)에서
    읽어 문구에 넣는다. 값이 바뀌어도 이 파일을 고칠 필요가 없다.
  · **게이트 판정을 렌더 도중 rerun으로 처리하지 않는다** — 설명서 버튼은
    st.button(on_click=콜백)으로 열림 플래그만 세우고, 다이얼로그는 그 다음 렌더에서
    열린다(login_gate/내정보와 같은 안전 패턴 — with 블록 안 rerun은 고아 DOM을 만든다).
  · 화면 이동 링크는 넣지 않는다(다이얼로그 안에서 실제 네비게이션이 일어나면
    다이얼로그 상태가 어긋난다). 필요하면 2차에서 검토.

문구의 근거(코드/문서 대조):
  · 자동구매 판매시간: sales_window.is_sales_window_open() — 화 09:00~토 19:55 (KST)
  · 번개조합: 2026-09-20 판매시간대 제한 해제(sales_window.py 독스트링)
  · 구매복권검증: 2026-09-14 제한 해제 / 가격은 선택수×2×10P(안티액땜_프로세스.md 2번)
  · 타로: 하루 1회 무료(guest_tarot_draws), 추가뽑기 유료, 진행 5단계(타로_프로세스.md)
  · 고급필터: 431개 규칙(1차381+2차48+4차2), 구독형·첫 구독 무료, PC 권장(admin_filter 안내)
  · 통계센터: 탭 3개(전문가 지표/출현 빈도/패턴 분석) — user_page.py stats 화면
  · 고객불만/개선요구사항: 메인화면 하단 접힌 항목 + 2,000자 제한(코드 그대로)
"""

from __future__ import annotations

import html

import streamlit as st

from legal_notices import PRICING

DRAFT_LABEL = "초안 v1 · 2026-09-21"

MANUAL_OPEN_FLAG = "manual_open"


def _esc(value) -> str:
    """HTML에 문구를 넣기 전에 이스케이프한다.

    설명서 문구는 컨펌 후에도 계속 사람이 고치는 텍스트라(예: "1~5위 & 그룹",
    괄호 속 부등호 등) `<`·`&`·따옴표가 들어올 수 있다. 그대로 붙이면 태그가
    주입되거나 레이아웃이 깨진다 — 검증(scratch/verify_manual_ui.py M8)에서
    실제로 잡혀 이 함수를 넣었다."""
    return html.escape(str(value))


# ── 본문 문구 (컨펌 대상) ────────────────────────────────────────────────────
def manual_sections() -> list[dict]:
    """화면별 안내 7건. 값은 가능한 한 원본(PRICING 등)에서 계산해 넣는다."""
    auto_unit = PRICING["auto_per_unit"]
    thunder_unit = PRICING["thunder_per_game"]
    hedge_unit = PRICING["hedge_per_combo"]
    tarot_cost = PRICING["tarot_extra_draw"]

    return [
        {
            "no": "01",
            "icon": "🔮",
            "title": "타로점",
            "badge": "하루 1회 무료 · 시간 제한 없음",
            "summary": "마음이 지칠 때, 지금 마음을 카드 한 장으로 짚어보는 콘텐츠",
            "steps": [
                "지금 마음이 머무는 곳을 큰 분류에서 고릅니다",
                "세부 상황을 고릅니다",
                "화면을 손가락으로 저어 카드를 섞습니다",
                "부채꼴로 펼쳐진 카드 중 한 장을 고릅니다",
                "카드 해석과 위로 문구를 확인합니다",
            ],
            "price": f"하루 1회 무료 · 추가 뽑기 1회 {tarot_cost:,}P",
            "notes": [
                "카드가 확정되는 순간 오늘의 무료 1회가 소모됩니다.",
                "해석을 본 뒤에는 화면 아래 [자동조합으로] · [번개조합으로] 버튼으로 "
                "마음이 가는 쪽으로 바로 이어갈 수 있습니다.",
                "이용하려면 로그인이 필요합니다.",
            ],
        },
        {
            "no": "02",
            "icon": "💎",
            "title": "자동조합",
            "badge": "배포 화 09:00 ~ 토 19:55 (KST)",
            "summary": "다음 회차 배포용 조합에서 내 몫을 자동으로 배정받는 방식",
            "steps": [
                "조합 수량을 고릅니다 (5개 / 10개)",
                "조합시작을 누릅니다",
                "저장내역에서 배정된 번호를 확인합니다",
            ],
            "price": f"5개 조합 {auto_unit * 5:,}P · 10개 조합 {auto_unit * 10:,}P (1개당 {auto_unit:,}P)",
            "notes": [
                "배포 시간: 매주 화요일 09:00부터 토요일 19:55까지만 배정됩니다. "
                "일·월요일 전체와 화요일 09:00 이전, 토요일 19:55 이후에는 이용할 수 없습니다.",
                "다음 회차 조합은 일요일 오후 2시대에 자동 생성됩니다. 생성이 끝나기 전에는 "
                "‘다음회차 조합생성이 완료된 후 이용’ 안내가 뜹니다.",
                "5개를 선택할 때마다 1~5위 그룹에서 각 1개씩 배정됩니다(10개면 각 2개씩).",
                "조합을 받으면 자동 저장되고, 추첨 후 적중 여부가 자동으로 표시됩니다. "
                "저장 내역은 최근 2회차까지만 보관됩니다.",
            ],
        },
        {
            "no": "03",
            "icon": "⚡",
            "title": "번개조합",
            "badge": "배포 시간 제한 없음 (요일·시간 무관)",
            "summary": "고정수·삭제수·행운수를 정해 그 조건으로 한 번에 여러 게임을 뽑는 방식",
            "steps": [
                "게임 수를 고릅니다 (5 / 10)",
                "꼭 넣을 번호(고정수)와 뺄 번호(삭제수)를 고릅니다",
                "행운수를 쓰려면 [행운수] 탭에서 생일을 등록합니다",
                "조합시작을 누르면 결과가 하나씩 차례로 표시됩니다",
                "결과가 모두 나오면 자동 저장됩니다",
            ],
            "price": f"5개 조합 {thunder_unit * 5:,}P · 10개 조합 {thunder_unit * 10:,}P (1게임당 {thunder_unit:,}P)",
            "notes": [
                "배포 시간: 요일·시간과 무관하게 언제든 이용할 수 있습니다(제한 해제).",
                "배포용 저장본에 조건과 맞는 조합이 있으면 우선 배정하고, 부족한 만큼만 새로 만듭니다.",
                "번호가 저장되지 않은 채 화면을 떠나면 10분 뒤 자동으로 환불됩니다.",
                "이용하려면 로그인이 필요합니다.",
            ],
        },
        {
            "no": "04",
            "icon": "🛡️",
            "title": "번호 검증 (전체·개별리셋)",
            "badge": "배포 시간 제한 없음",
            "summary": "내가 가진 번호를 넣으면, 그 번호와 반대 조건의 조합을 만들어 주는 방식",
            "steps": [
                "QR스캔(앱 카메라) 또는 직접입력으로 번호를 넣습니다",
                "만들 개수를 고릅니다",
                "조합시작을 누릅니다",
                "결과를 확인합니다 (자동 저장)",
            ],
            "price": (
                f"전체리셋 5개 {5 * hedge_unit:,}P + 개별리셋 5개 {5 * hedge_unit:,}P "
                f"(1개당 {hedge_unit:,}P, 10개 합계 {10 * hedge_unit:,}P)"
            ),
            "notes": [
                "배포 시간: 요일·시간과 무관하게 언제든 이용할 수 있습니다(제한 해제).",
                "조합이 목표 개수를 채우지 못하면 적립금이 차감되지 않습니다.",
                "저장내역에는 전체리셋이 위, 개별리셋이 아래로 표시됩니다.",
                "이용하려면 로그인이 필요합니다.",
            ],
        },
        {
            "no": "05",
            "icon": "👑",
            "title": "고급필터",
            "badge": "구독형 · PC 환경 권장",
            "summary": "검증된 필터 규칙으로 조합을 걸러 전문가용 후보를 보는 화면",
            "steps": [
                "로그인 후 구독을 시작합니다 (첫 구독 1회 무료)",
                "적용할 필터 규칙을 확인합니다",
                "조합을 추출해 후보를 확인합니다",
            ],
            "price": (
                f"월 {PRICING['advanced_monthly']:,}P · 3개월권 "
                f"{PRICING['advanced_3month']:,}P (첫 구독 1회 무료)"
            ),
            "notes": [
                "화면이 넓은 PC 환경에 맞춰 설계되어, 모바일에서는 일부만 보입니다. "
                "전체 패턴을 한눈에 보려면 PC에서 이용해 주세요.",
                "구독이 끝나면 잠기며, 다시 구독하면 이어서 쓸 수 있습니다.",
            ],
        },
        {
            "no": "06",
            "icon": "📊",
            "title": "통계센터",
            "badge": "상시 이용",
            "summary": "최신 회차 요약과 번호별 흐름을 세 개의 탭으로 보는 화면",
            "steps": [
                "🧠 전문가 지표 — 최신 회차 요약(합계·AC·이월수 등)",
                "🔥 출현 빈도 — 최근 100회 기준 뜨거운 수 / 차가운 수",
                "🎯 패턴 분석 — 번호 흐름과 조합 패턴",
            ],
            "price": "무료",
            "notes": [
                "통계는 참고용이며 당첨을 보장하지 않습니다.",
                "회차 데이터가 갱신되면 자동으로 최신 내용이 반영됩니다.",
            ],
        },
        {
            "no": "07",
            "icon": "💬",
            "title": "고객불만 / 개선요구사항",
            "badge": "상시 접수",
            "summary": "불편한 점과 원하는 기능을 운영자에게 바로 보내는 창구",
            "steps": [
                "메인화면 맨 아래 [고객불만 / 개선요구사항]을 눌러 펼칩니다",
                "의견을 적습니다 (2,000자까지)",
                "[저장]을 누르면 접수됩니다",
            ],
            "price": "무료",
            "notes": [
                "접수된 내용은 운영자 화면에서 처리상태(대기 · 처리중 · 완료)로 관리됩니다.",
                "로그인 상태면 회원 번호가 함께 기록되어 확인이 빨라집니다.",
            ],
        },
    ]


# ── 디자인 (메뉴얼 스타일) ───────────────────────────────────────────────────
def manual_css() -> str:
    return """
<style>
/* 사용설명서 — 앱 다크 팔레트(#12182b/#1c2645/#2a3a60) + 금색 괘선의 메뉴얼 톤.
   클래스 접두사를 ln-manual-로 고정해 다른 화면 CSS와 충돌하지 않게 한다.

   2026-09-23(사용자 지시): 표지 카드(USER GUIDE/제목/버전칩)는 다이얼로그 자체 제목
   "📖 사용설명서"와 트리거 버튼 라벨이 이미 같은 말을 하고 있어 중복이라 삭제했다.
   차례의 번호(01~07)·이모지도 같은 이유로 뺐다. 요약 텍스트가 "뿌옇게" 보인다는
   지적은 색 대비가 낮았던 게 원인으로 보여(#8f9bb0, 11.5px) 더 밝은 색·큰 글자로
   올렸고, 혹시 겹쳐 보일 만한 레이어가 없도록 position/z-index를 명시했다. */
.ln-manual-toc {
    border: 1px solid #2a3a60;
    border-radius: 14px;
    padding: 4px 12px;
    background: #171f3d;
    margin-bottom: 14px;
    position: relative;
    z-index: 1;
}
.ln-manual-toc-row {
    padding: 9px 0;
    border-bottom: 1px dashed rgba(42, 58, 96, 0.85);
    text-align: left;
}
.ln-manual-toc-row:last-child { border-bottom: none; }
.ln-manual-toc-t {
    display: block;
    color: #f2f4fb;
    font-size: 13.5px;
    font-weight: 800;
    text-align: left;
}
.ln-manual-toc-s {
    display: block;
    color: #c7cee2;
    font-size: 12.5px;
    line-height: 1.55;
    margin-top: 3px;
    text-align: left;
    position: relative;
    z-index: 1;
}
.ln-manual-card {
    background: linear-gradient(150deg, #1c2645 0%, #141c33 100%);
    border: 1px solid #2a3a60;
    border-left: 3px solid #ffb300;
    border-radius: 14px;
    padding: 13px 14px 12px 14px;
    margin: 0 0 10px 0;
    box-shadow: 0 6px 16px rgba(0, 0, 0, 0.4);
}
.ln-manual-badges { margin-bottom: 8px; }
.ln-manual-badge {
    display: inline-block;
    background: rgba(255, 179, 0, 0.12);
    border: 1px solid rgba(255, 179, 0, 0.42);
    color: #ffd479;
    border-radius: 999px;
    padding: 2px 9px;
    font-size: 10.5px;
    font-weight: 800;
    margin: 0 6px 4px 0;
}
.ln-manual-h {
    color: #ffffff;
    font-size: 16.5px;
    font-weight: 900;
    letter-spacing: -0.2px;
    margin-bottom: 4px;
}
.ln-manual-lead { color: #b8c2d6; font-size: 12.5px; line-height: 1.55; margin-bottom: 10px; }
.ln-manual-label {
    color: #ffb300;
    font-size: 10.5px;
    font-weight: 800;
    letter-spacing: 1.4px;
    text-transform: uppercase;
    margin: 10px 0 5px 0;
}
.ln-manual-steps { margin: 0; padding: 0; list-style: none; }
.ln-manual-steps li {
    color: #dbe3ee;
    font-size: 12.5px;
    line-height: 1.5;
    margin-bottom: 5px;
    padding-left: 22px;
    position: relative;
}
.ln-manual-steps li::before {
    content: attr(data-n);
    position: absolute;
    left: 0; top: 0;
    width: 16px; height: 16px;
    border-radius: 50%;
    background: rgba(255, 179, 0, 0.16);
    border: 1px solid rgba(255, 179, 0, 0.5);
    color: #ffd479;
    font-size: 9.5px;
    font-weight: 900;
    display: flex;
    align-items: center;
    justify-content: center;
    line-height: 1;
}
.ln-manual-price {
    color: #ffeb3b;
    font-size: 12.5px;
    font-weight: 800;
    line-height: 1.5;
}
.ln-manual-notes { margin: 0; padding-left: 14px; }
.ln-manual-notes li { color: #93a0b5; font-size: 12px; line-height: 1.55; margin-bottom: 3px; }
.ln-manual-foot {
    color: #6f7c92;
    font-size: 11px;
    line-height: 1.5;
    border-top: 1px solid #2a3a60;
    padding-top: 9px;
    margin-top: 6px;
}
/* 2026-09-23(사용자 지시): (1) 차례 바로 아래 — 버튼만 나열돼 있어서 누르면 자세한
   설명이 나온다는 걸 이용자가 알기 어렵다는 피드백 대응 안내문구. (2) 항목 세부
   설명창 우측 상단 "닫기" — 뒤로가기로 앱이 종료되는 문제(네이티브 다음 빌드에서
   대응)와 별개로, 그 안에서 바로 접을 수 있는 버튼이 필요하다는 요청. 버튼 자체는
   st.button이라 key로 CSS를 건다(manual_dialog()의 exp_key + "_close" 조합).
   */
.ln-manual-hint {
    /* 2026-09-23(실기기 재확인): 안 보이던 진짜 원인은 레이어(z-index)가 아니라
       다이얼로그 자체 배경이 흰색이라는 것 — 위 .ln-manual-toc처럼 배경을
       직접 칠하고(카드와 같은 톤), 글자색은 이 파일에서 이미 쓰는 금색
       (.ln-manual-steps li::before와 동일한 #ffd479)으로 흰 배경이든
       어떤 배경이든 항상 읽히게 만든다 — 배경색을 추측하지 않아도 된다.*/
    color: #ffd479;
    font-size: 12.5px;
    font-weight: 800;
    text-align: left;
    margin: 0 2px 14px 2px;
    padding: 8px 12px;
    background: #171f3d;
    border: 1px solid #2a3a60;
    border-radius: 10px;
}
[class*="st-key-manual_exp_"][class*="_close"] button {
    background: rgba(28, 28, 56, 0.9) !important;
    color: #c7cee2 !important;
    font-size: 11px !important;
    font-weight: 700 !important;
    padding: 2px 10px !important;
    min-height: 0 !important;
    height: auto !important;
    border: 1px solid rgba(42, 58, 96, 0.9) !important;
    border-radius: 999px !important;
}
</style>
"""


def manual_hint_html() -> str:
    """차례 바로 아래에 두는 한 줄 안내 — 아래 항목 버튼을 눌러야 자세한 설명이
    펼쳐진다는 걸 이용자가 알 수 있게 한다(2026-09-23 사용자 지시)."""
    return '<div class="ln-manual-hint">세부사항은 아래 버튼을 클릭해보세요</div>'


def manual_overview_html() -> str:
    """차례 — 표지 카드는 다이얼로그 제목("📖 사용설명서")과 중복이라 뺐다(사용자 지시)."""
    rows = "".join(
        f'<div class="ln-manual-toc-row">'
        f'<span class="ln-manual-toc-t">{_esc(s["title"])}</span>'
        f'<span class="ln-manual-toc-s">{_esc(s["summary"])}</span>'
        f"</div>"
        for s in manual_sections()
    )
    return f'<div class="ln-manual-toc">{rows}</div>'


def manual_section_html(section: dict) -> str:
    """항목 1건 — 배지 / 한 줄 요약 / 사용 순서 / 적립금 / 알아두세요."""
    steps = "".join(
        f'<li data-n="{i}" >{_esc(text)}</li>' for i, text in enumerate(section["steps"], start=1)
    )
    notes = "".join(f"<li>{_esc(n)}</li>" for n in section["notes"])
    return (
        '<div class="ln-manual-card">'
        f'<div class="ln-manual-badges"><span class="ln-manual-badge">{_esc(section["badge"])}</span></div>'
        f'<div class="ln-manual-h">{_esc(section["title"])}</div>'
        f'<div class="ln-manual-lead">{_esc(section["summary"])}</div>'
        '<div class="ln-manual-label">이렇게 사용하세요</div>'
        f'<ul class="ln-manual-steps">{steps}</ul>'
        '<div class="ln-manual-label">적립금</div>'
        f'<div class="ln-manual-price">{_esc(section["price"])}</div>'
        '<div class="ln-manual-label">알아두세요</div>'
        f'<ul class="ln-manual-notes">{notes}</ul>'
        "</div>"
    )


def manual_footer_html() -> str:
    return (
        '<div class="ln-manual-foot">'
        "적립금·이용 시간은 앱과 같은 기준에서 자동으로 표시됩니다. "
        "문의는 메인화면 맨 아래 [고객불만 / 개선요구사항]으로 남겨 주세요."
        "</div>"
    )


# ── 화면 연결부 ─────────────────────────────────────────────────────────────
def _close_manual_section(exp_key: str) -> None:
    """항목 세부설명창 우측 상단 "닫기" 버튼 콜백 — 그 항목 하나만 접는다.

    st.expander(key=..., on_change="rerun")로 열어야 expanded 상태를
    st.session_state[key]로 읽고 쓸 수 있다(Streamlit 공식 동작) — 콜백은
    그 값을 False로 세팅만 하고, 실제 접힘은 다음 렌더에서 반영된다(이
    프로젝트의 기존 안전 패턴과 동일하게 콜백 안에서 st.rerun()을 직접
    부르지 않는다).
    """
    st.session_state[exp_key] = False


def _render_manual_close_row(exp_key: str) -> None:
    """항목 카드 맨 위, 우측에 작은 "닫기" 버튼을 놓는다(2026-09-23 사용자 지시)."""
    _, right = st.columns([5, 1])
    with right:
        st.button(
            "닫기",
            key=f"{exp_key}_close",
            on_click=_close_manual_section,
            args=(exp_key,),
        )


@st.dialog("📖 사용설명서", width="large")
def manual_dialog() -> None:
    """표지 → 목차 → 안내문구 → 7개 항목(접힘, 각각 우측상단 닫기) → 각주."""
    st.markdown(manual_css(), unsafe_allow_html=True)
    st.markdown(manual_overview_html(), unsafe_allow_html=True)
    st.markdown(manual_hint_html(), unsafe_allow_html=True)
    for idx, section in enumerate(manual_sections()):
        exp_key = f"manual_exp_{idx}"
        with st.expander(section["title"], key=exp_key, on_change="rerun"):
            _render_manual_close_row(exp_key)
            st.markdown(manual_section_html(section), unsafe_allow_html=True)
    st.markdown(manual_footer_html(), unsafe_allow_html=True)


def _open_manual() -> None:
    """버튼 콜백 — 렌더 도중 rerun 없이 플래그만 세운다(프로젝트 안전 패턴)."""
    st.session_state[MANUAL_OPEN_FLAG] = True


def maybe_open_manual() -> None:
    """플래그가 세워진 렌더에서 다이얼로그를 연다. 메인 화면에서 1회 호출."""
    if st.session_state.pop(MANUAL_OPEN_FLAG, False):
        manual_dialog()


def render_manual_trigger_button() -> None:
    """메인화면 "내정보" 버튼 아래에 간격을 두고 붙는 안내 버튼(고정 위치).

    내정보 버튼이 우측 상단(right:12px, top:8px, z-index:999) 고정이라, 같은 폭/스타일로
    48px 아래(top:56px)에 둔다. 2026-09-22(사용자 지시): 원래 top:44px(36px 간격)이었는데
    "내정보"와 너무 붙어 보인다는 실기기 피드백으로 12px 더 내렸다. 로그인 배너가 떠 있을 때
    이 버튼과 겹칠 수 있는지는 컨펌 시 확인 필요.
    """
    st.markdown(
        """
<style>
.st-key-manual_trigger_wrap {
    position: fixed !important;
    right: 12px !important;
    top: 56px !important;
    z-index: 999 !important;
    width: auto !important;
}
.st-key-manual_trigger_wrap div[data-testid="stButton"] > button {
    background: rgba(28, 28, 56, 0.9) !important;
    color: #ffd479 !important;
    font-weight: 700 !important;
    font-size: 11px !important;
    border: 1px solid rgba(255, 179, 0, 0.45) !important;
    border-radius: 999px !important;
    padding: 4px 12px !important;
    min-height: 0 !important;
    height: auto !important;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4) !important;
}
</style>
        """,
        unsafe_allow_html=True,
    )
    with st.container(key="manual_trigger_wrap"):
        st.button(
            "📖 사용설명서",
            key="manual_trigger_btn",
            use_container_width=True,
            on_click=_open_manual,
        )
