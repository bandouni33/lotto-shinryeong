"""guest_generated_combos 기반 "저장내역" 카드 UI.

번개조합, 안티조합/액땜조합 등 "그 자리에서 생성한 조합을 저장하고 추첨 후
당첨 여부를 마킹해 보여주는" 화면이 여러 개 생길 예정이라, 카드 디자인(자동구매
구매내역과 동일한 형식)과 저장/조회/블링크 연출을 여기 한 곳에서만 관리하고
각 페이지는 이 모듈을 그대로 가져다 쓴다.
"""

import streamlit as st

RANK_LABELS = {1: "1등", 2: "2등", 3: "3등", 4: "4등", 5: "5등"}


def history_css(container_key: str) -> str:
    """container_key는 render_history_section에 준 key와 같아야 블링크 연출이 맞는
    컨테이너에만 걸린다. 카드 자체(.auto-purchase-banner 계열)는 자동구매
    구매내역(page_auto.py)과 완전히 동일한 정의를 그대로 옮겨왔다."""
    return f"""
    <style>
    .st-key-{container_key} div[data-testid="stExpander"] summary p {{
        font-size: 16px !important;
        font-weight: 800 !important;
        color: #ffffff !important;
        position: relative !important;
        z-index: 5 !important;
    }}
    .auto-purchase-banner {{
        margin: 14px 0 18px;
        padding: 16px 14px 14px;
        border-radius: 16px;
        border: 1px solid rgba(206, 147, 216, 0.55);
        background: linear-gradient(155deg, rgba(74, 20, 140, 0.92) 0%, rgba(26, 34, 56, 0.96) 55%, rgba(18, 24, 43, 0.98) 100%);
        box-shadow: 0 8px 28px rgba(0, 0, 0, 0.45), 0 0 0 1px rgba(179, 157, 219, 0.18), inset 0 1px 0 rgba(255, 255, 255, 0.08);
    }}
    .auto-banner-title {{
        color: #f3e5f5;
        font-weight: 800;
        font-size: 16px;
        line-height: 1.35;
        margin-bottom: 12px;
    }}
    .auto-banner-combos {{
        display: flex;
        flex-direction: column;
        gap: 8px;
    }}
    .auto-banner-combo {{
        display: flex;
        align-items: center;
        gap: 8px;
        width: fit-content;
        max-width: 100%;
        padding: 8px 12px;
        border-radius: 12px;
        background: rgba(0, 0, 0, 0.22);
        border: 1px solid rgba(179, 157, 219, 0.22);
    }}
    .auto-banner-ball-row {{
        display: flex;
        flex-wrap: nowrap;
        gap: 10px;
    }}
    .auto-banner-ball {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 24px;
        height: 24px;
        padding: 0 2px;
        color: #f1e9ff;
        font-weight: 800;
        font-size: 15px;
        font-variant-numeric: tabular-nums;
    }}
    .combo-history-rank-badge {{
        display: inline-block;
        flex-shrink: 0;
        padding: 3px 9px;
        border-radius: 999px;
        background: linear-gradient(145deg, #ffd54f, #ffb800);
        color: #4a2f00;
        font-weight: 900;
        font-size: 11px;
        white-space: nowrap;
    }}
    .auto-banner-ball-hit {{
        border-radius: 50%;
        border: 2px solid #FFD600;
        color: #FFD600;
    }}
    .auto-banner-ball-bonus {{
        border-radius: 50%;
        border: 2px solid #B0BEC5;
        color: #B0BEC5;
    }}
    .auto-banner-legend {{
        margin: 6px 0 0;
        color: #cfd8dc;
        font-size: 11px;
        font-weight: 600;
    }}
    @keyframes comboHistoryBlink {{
        0%, 100% {{
            box-shadow: 0 0 0 0 rgba(255, 184, 0, 0);
            background: #ffffff !important;
        }}
        50% {{
            box-shadow: 0 0 0 5px rgba(255, 184, 0, 0.9), 0 0 22px rgba(255, 152, 0, 0.55);
            background: #fff8e1 !important;
        }}
    }}
    @keyframes comboHistoryCardPulse {{
        0%, 100% {{
            transform: scale(1);
            border-color: rgba(255, 152, 0, 0.35) !important;
        }}
        50% {{
            transform: scale(1.015);
            border-color: rgba(255, 152, 0, 0.9) !important;
            box-shadow: 0 0 24px rgba(255, 184, 0, 0.4) !important;
        }}
    }}
    .st-key-{container_key}:has(.combo-history-just-saved-marker) div[data-testid="stExpander"] {{
        animation: comboHistoryCardPulse 0.95s ease-in-out 7 !important;
        border: 2px solid rgba(255, 152, 0, 0.75) !important;
    }}
    .st-key-{container_key}:has(.combo-history-just-saved-marker) div[data-testid="stExpander"] > details > summary {{
        animation: comboHistoryBlink 0.95s ease-in-out 7 !important;
        font-weight: 900 !important;
    }}
    .combo-history-just-saved-marker {{
        display: none !important;
        height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
    }}
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


def batch_card_html(batch: dict, *, label_prefix: str = "") -> str:
    """구매내역(_purchase_banner_html)과 동일한 카드 형식 — 순수 숫자 볼 + 당첨번호
    일치 시 테두리 동그라미. label_prefix가 있으면 "{label_prefix} · N회차"로 표시한다
    (한 화면에 여러 소스가 섞여 쌓일 수 있는 경우 구분용, 없으면 회차만 표시)."""
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
        combo_rows += (
            f'<div class="auto-banner-combo"><div class="auto-banner-ball-row">{balls}</div>{rank_badge}</div>'
        )

    legend = '<p class="auto-banner-legend">🟡 당첨번호 일치 · ⚪ 보너스 번호 일치</p>' if win_set else ""
    title = f"{label_prefix} · {draw_round}회차" if label_prefix else f"{draw_round}회차"

    return (
        '<div class="auto-purchase-banner">'
        f'<div class="auto-banner-title">{title}</div>'
        f'<div class="auto-banner-combos">{combo_rows}</div>'
        f"{legend}"
        "</div>"
    )


def render_history_section(
    *,
    container_key: str,
    guest_id: str,
    sources: list[str],
    blink_flag_key: str,
    title: str = "저장내역",
    empty_caption: str = "아직 저장한 조합이 없습니다.",
    limit_per_source: int = 10,
    label_for_source: dict[str, str] | None = None,
) -> None:
    """저장내역 익스팬더 전체(당첨마킹 동기화 + 블링크 연출 + 카드 목록)를 렌더링한다.

    sources가 여러 개면(예: 안티조합+액땜조합) 하나의 목록으로 합쳐 최신순으로 보여주고,
    label_for_source로 각 소스의 표시 이름을 지정하면 카드 제목에 "{이름} · N회차"로
    구분해 표시한다(소스가 하나뿐이고 label_for_source도 없으면 회차만 표시)."""
    try:
        from lotto_stats import sync_generated_combo_win_ranks

        sync_generated_combo_win_ranks()
    except Exception:
        pass

    from marketing_db import init_marketing_tables, list_guest_generated_combos

    init_marketing_tables()
    st.markdown(history_css(container_key), unsafe_allow_html=True)

    blink = bool(st.session_state.pop(blink_flag_key, False))
    with st.container(key=container_key):
        if blink:
            st.markdown(
                '<div class="combo-history-just-saved-marker" aria-hidden="true"></div>',
                unsafe_allow_html=True,
            )
        with st.expander(title, expanded=blink):
            batches = []
            for source in sources:
                for batch in list_guest_generated_combos(guest_id, source=source, limit=limit_per_source):
                    batch["_source"] = source
                    batches.append(batch)
            batches.sort(key=lambda b: b.get("created_at") or "", reverse=True)
            batches = batches[:limit_per_source]

            if not batches:
                st.caption(empty_caption)
            else:
                for batch in batches:
                    label_prefix = (label_for_source or {}).get(batch.get("_source"), "")
                    st.markdown(
                        batch_card_html(batch, label_prefix=label_prefix),
                        unsafe_allow_html=True,
                    )
