"""guest_generated_combos 기반 "저장내역" 카드 UI.

번개조합, 안티조합/액땜조합 등 "그 자리에서 생성한 조합을 저장하고 추첨 후
당첨 여부를 마킹해 보여주는" 화면이 여러 개 생길 예정이라, 카드 디자인(자동구매
구매내역과 동일한 형식)과 저장/조회/블링크 연출을 여기 한 곳에서만 관리하고
각 페이지는 이 모듈을 그대로 가져다 쓴다.

2026-08-27: 자동구매 "구매내역"이 겪었던 것과 같은 문제(테두리·박스 장식,
position:absolute 팝오버, 좁은 열 안에서 펼치다 번호가 잘리는 버그)를 여기도
그대로 겪을 이유가 없어, 자동구매가 최종적으로 정착한 방식을 그대로 옮겨왔다 —
박스 없이 순수 숫자만, 트리거는 진짜 st.button, 펼침은 화면 중앙 팝업이 아니라
버튼 바로 밑 전체 폭 인라인 패널.
"""

import streamlit as st

RANK_LABELS = {1: "1등", 2: "2등", 3: "3등", 4: "4등", 5: "5등"}

# 2026-08-27: 자동구매 "구매내역"(page_auto.py)은 회차 기준으로 최근 2개
# 회차분만 표시하는데, 여기(번개조합/안티·액땜조합 "저장내역")는 회차와
# 무관하게 "최근 저장 10건"만 보여주고 있어 세 화면의 표시 기준이 서로 달랐다
# — 세 곳 모두 "최근 2개 회차만 보인다"로 통일한다.
MAX_HISTORY_ROUNDS = 2


def _limit_to_recent_rounds(batches: list[dict], max_rounds: int = MAX_HISTORY_ROUNDS) -> list[dict]:
    """최근 N개 회차분만 남기고 그보다 오래된 회차는 잘라낸다.

    batches는 이미 최신순(created_at desc)으로 정렬돼 있다고 가정한다.
    page_auto.py의 동일 이름 함수와 로직을 그대로 맞춰, 세 화면의 "구매/저장
    내역"이 항상 같은 회차 범위를 보여주게 한다.
    """
    seen_rounds: list = []
    result = []
    for batch in batches:
        dr = batch.get("draw_round")
        if dr not in seen_rounds:
            if len(seen_rounds) >= max_rounds:
                continue
            seen_rounds.append(dr)
        result.append(batch)
    return result


@st.cache_data(ttl=3600, show_spinner=False)
def _sync_generated_combo_win_ranks_cached() -> None:
    """"저장내역"을 열 때마다(위젯 하나만 건드려도 Streamlit이 스크립트 전체를
    재실행) 당첨 대기 중인 모든 회차의 생성조합을 매번 다시 훑어 win_rank를
    갱신하고 있었다 — 캐싱이 없어 Turso 쓰기 한도(월 1,000만 행)를 순식간에
    소진시킨 진짜 원인이었다(2026-08-23, 실제 사용량으로 역산해 확인: 회차당
    수천 건 × 반복 호출 ≈ 실제 초과분과 거의 일치). 이미 처리된 회차까지
    매번 전체 UPDATE를 다시 날리는 구조라 캐시 시간이 짧으면 여전히 많이
    쌓인다 — 로또 추첨은 주 1회뿐이라 1시간 캐시로도 실질적 지연은 없다."""
    from lotto_stats import sync_generated_combo_win_ranks

    sync_generated_combo_win_ranks()


def history_css(container_key: str = "") -> str:
    """카드 자체(.auto-banner-ball 등)는 자동구매 구매내역(page_auto.py)과 완전히
    동일한 정의를 그대로 옮겨왔다 — 두 화면이 항상 같은 사이즈·서체로 유지보수되게.

    container_key는 이제 CSS 스코프에 쓰이지 않는다(트리거가 expander가 아니라
    진짜 st.button이라 별도 스코프가 필요 없어졌다) — 기존 호출부(page_hedge.py의
    미리보기 CSS 주입)와의 호환을 위해 인자만 남겨두고 무시한다."""
    return """
    <style>
    .auto-purchase-banner-plain {
        margin: 10px 0;
    }
    .auto-history-round-head {
        margin: 14px 0 6px;
        color: #ce93d8;
        font-weight: 800;
        font-size: 13px;
    }
    .auto-history-round-head:first-child {
        margin-top: 2px;
    }
    .auto-banner-combos {
        display: flex;
        flex-direction: column;
        gap: 10px;
    }
    .auto-banner-ball-row {
        display: flex;
        flex-wrap: nowrap;
        align-items: center;
        justify-content: center;
        gap: 8px;
    }
    .auto-banner-ball {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 20px;
        color: #ffffff;
        font-weight: 800;
        font-size: 15px;
        font-variant-numeric: tabular-nums;
    }
    .auto-banner-ball-hit {
        border-radius: 50%;
        border: 2px solid #FFD600;
        color: #FFD600;
    }
    .auto-banner-ball-bonus {
        border-radius: 50%;
        border: 2px solid #B0BEC5;
        color: #B0BEC5;
    }
    .combo-history-rank-badge {
        display: inline-block;
        flex-shrink: 0;
        margin-left: 6px;
        padding: 2px 8px;
        border-radius: 999px;
        background: linear-gradient(145deg, #ffd54f, #ffb800);
        color: #4a2f00;
        font-weight: 900;
        font-size: 11px;
        white-space: nowrap;
    }
    </style>
    """


def winning_numbers_for_draw(draw_round) -> tuple[set[int], int | None]:
    """당첨번호가 확정된 회차면 (당첨번호 집합, 보너스번호)를 반환 — 맞은 번호에
    동그라미를 칠 수 있도록. 아직 추첨 전이면 빈 집합을 반환한다."""
    try:
        from lotto_stats import get_draw_result_by_round

        result = get_draw_result_by_round(int(draw_round))
    except Exception:
        return set(), None
    if not result:
        return set(), None
    return set(int(n) for n in result.get("numbers", [])), result.get("bonus")


def batch_card_html(batch: dict) -> str:
    """구매내역(_purchase_banner_html)과 완전히 동일한 카드 형식 — 순수 숫자 볼 +
    당첨번호 일치 시 테두리 동그라미. 회차/소스 제목은 호출부(render_history_section)가
    회차별로 묶어 별도 줄(auto-history-round-head)로 그리므로 여기서는 조합 숫자만
    그린다."""
    draw_round = batch.get("draw_round", "")
    win_set, bonus_number = winning_numbers_for_draw(draw_round) if draw_round != "" else (set(), None)

    def _ball_span(n: int) -> str:
        n = int(n)
        if n in win_set:
            hit_cls = " auto-banner-ball-hit"
        elif bonus_number is not None and n == int(bonus_number):
            hit_cls = " auto-banner-ball-bonus"
        else:
            hit_cls = ""
        return f'<span class="auto-banner-ball{hit_cls}">{n:02d}</span>'

    combos = batch.get("combos") or []
    combo_rows = ""
    for item in combos:
        combo = item.get("combo") or []
        balls = "".join(_ball_span(n) for n in combo)
        rank = item.get("win_rank")
        rank_badge = (
            f'<span class="combo-history-rank-badge">{RANK_LABELS[rank]}</span>'
            if rank in RANK_LABELS
            else ""
        )
        combo_rows += f'<div class="auto-banner-ball-row">{balls}{rank_badge}</div>'

    return f'<div class="auto-purchase-banner-plain"><div class="auto-banner-combos">{combo_rows}</div></div>'


def render_history_section(
    *,
    container_key: str,
    guest_id: str,
    sources: list[str],
    blink_flag_key: str,
    title: str = "저장내역",
    empty_caption: str = "아직 저장한 조합이 없습니다.",
    limit_per_source: int = 30,
    label_for_source: dict[str, str] | None = None,
) -> None:
    """"저장내역" 전체(당첨마킹 동기화 + 버튼 트리거 + 인라인 패널)를 렌더링한다.

    sources가 여러 개면(예: 안티조합+액땜조합) 하나의 목록으로 합쳐 최신순으로 보여주고,
    label_for_source로 각 소스의 표시 이름을 지정하면 회차 머리글에 "{이름} · N회차"로
    구분해 표시한다(소스가 하나뿐이고 label_for_source도 없으면 회차만 표시).

    자동구매 "구매내역"과 동일한 방식 — 진짜 st.button으로 열고 닫으며, 펼침 내용은
    버튼 바로 밑에 전체 폭 인라인 패널로 그린다(팝업이나 좁은 열 안 펼침이 아님).

    limit_per_source는 최종 표시 개수가 아니라 소스별 DB 조회 상한이다 — 실제
    화면에 남는 범위는 언제나 _limit_to_recent_rounds가 정하는 "최근
    MAX_HISTORY_ROUNDS개 회차"이며, 10건보다 더 자주 저장한 회차가 있어도
    빠짐없이 그 회차 안에 들어오도록 여유 있게(기존 10 → 30) 조회한다.
    """
    try:
        _sync_generated_combo_win_ranks_cached()
    except Exception:
        pass

    from marketing_db import init_marketing_tables, list_guest_generated_combos

    init_marketing_tables()
    st.markdown(history_css(), unsafe_allow_html=True)

    panel_open_key = f"{blink_flag_key}_panel_open"
    if bool(st.session_state.pop(blink_flag_key, False)):
        st.session_state[panel_open_key] = True

    with st.container(key=container_key):
        if st.button(title, type="primary", use_container_width=True, key=f"{container_key}_open_btn"):
            st.session_state[panel_open_key] = not st.session_state.get(panel_open_key, False)

    if st.session_state.get(panel_open_key, False):
        with st.container(key=f"{container_key}_panel"):
            batches = []
            for source in sources:
                for batch in list_guest_generated_combos(guest_id, source=source, limit=limit_per_source):
                    batch["_source"] = source
                    batches.append(batch)
            batches.sort(key=lambda b: b.get("created_at") or "", reverse=True)
            batches = _limit_to_recent_rounds(batches)

            if not batches:
                st.caption(empty_caption)
            else:
                for batch in batches:
                    label_prefix = (label_for_source or {}).get(batch.get("_source"), "")
                    draw_round = batch.get("draw_round", "")
                    heading = f"{label_prefix} · {draw_round}회차" if label_prefix else f"{draw_round}회차"
                    st.markdown(
                        f'<div class="auto-history-round-head">{heading}</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(batch_card_html(batch), unsafe_allow_html=True)
