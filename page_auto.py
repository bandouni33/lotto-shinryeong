"""자동조합 상세 페이지 (K-595)."""

import base64
import importlib
import os
from datetime import datetime, time
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
SUBSCRIPTION_WEEKDAYS = ["화", "수", "목"]
QUANTITY_OPTIONS = [5, 10, 15, 20]
# 테스트 기간 기본: 구매 확정 시 인증 건너뜀. 출시 시 AUTO_PURCHASE_SKIP_AUTH=0
AUTO_PURCHASE_SKIP_AUTH = os.environ.get("AUTO_PURCHASE_SKIP_AUTH", "1").strip().lower() in (
    "1",
    "true",
    "yes",
)
ADMIN_COMBO_SAVE_FILE = "saved_combinations.csv"

AUTO_DEPLOY_WINDOW_BANNER = (
    "배포 가능 시간이 아닙니다. "
    "매주 화요일 09:00부터 토요일 19:55까지만 구매(배포)할 수 있습니다."
)


def _is_auto_deploy_window_open(now: datetime | None = None) -> bool:
    """KST — 화 09:00 ~ 토 19:55 (그 외 배포 불가)."""
    now = now or datetime.now(ZoneInfo("Asia/Seoul"))
    weekday = now.weekday()  # 월=0 … 일=6
    clock = now.time()
    if weekday in (6, 0):  # 일, 월
        return False
    if weekday == 1:  # 화
        return clock >= time(9, 0)
    if weekday == 5:  # 토
        return clock <= time(19, 55)
    return weekday in (2, 3, 4)  # 수, 목, 금


def _get_icon_base64(file_path: str = "K-325.jpg") -> str:
    if os.path.exists(file_path):
        with open(file_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    return ""


def _spirit2_filter_svg(filter_id: str = "auto-spirit-ripple") -> str:
    return f"""
    <svg width="0" height="0" aria-hidden="true" style="position:absolute;overflow:hidden;">
      <filter id="{filter_id}" x="-14%" y="-14%" width="128%" height="128%" color-interpolation-filters="sRGB">
        <feTurbulence type="fractalNoise" baseFrequency="0.016 0.062" numOctaves="2" seed="7" result="noise">
          <animate attributeName="baseFrequency"
                   dur="10s"
                   values="0.016 0.062;0.026 0.085;0.016 0.062"
                   calcMode="spline"
                   keySplines="0.45 0 0.55 1;0.45 0 0.55 1"
                   keyTimes="0;0.5;1"
                   repeatCount="indefinite"/>
        </feTurbulence>
        <feDisplacementMap in="SourceGraphic" in2="noise" scale="6" xChannelSelector="R" yChannelSelector="G">
          <animate attributeName="scale"
                   dur="10s"
                   values="6;11;6"
                   calcMode="spline"
                   keySplines="0.45 0 0.55 1;0.45 0 0.55 1"
                   keyTimes="0;0.5;1"
                   repeatCount="indefinite"/>
        </feDisplacementMap>
      </filter>
    </svg>
    """


def _spirit2_iframe_doc(base64: str, filter_id: str = "auto-spirit-ripple-dsk") -> str:
    """PC 데스크톱 슬롯: iframe 내부 자체 완결 HTML."""
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{
    width: 100%;
    overflow: hidden;
    background: transparent;
}}
.auto-spirit2-wrap {{
    position: relative;
    width: 100%;
    overflow: hidden;
}}
.auto-spirit2-ripple {{
    position: relative;
    width: 100%;
}}
.auto-spirit2-img {{
    width: 100%;
    height: auto;
    display: block;
    border: none;
    object-fit: contain;
}}
.auto-spirit2-body-mask {{
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
    overflow: hidden;
    -webkit-mask-image: radial-gradient(
        ellipse 17% 16% at 47% 37%,
        transparent 0%,
        transparent 70%,
        rgba(0, 0, 0, 0.35) 82%,
        black 92%
    );
    mask-image: radial-gradient(
        ellipse 17% 16% at 47% 37%,
        transparent 0%,
        transparent 70%,
        rgba(0, 0, 0, 0.35) 82%,
        black 92%
    );
}}
.auto-spirit2-ripple-wave {{
    width: 100%;
    transform-origin: 50% 42%;
    animation: autoSpiritBodyWave 10s ease-in-out infinite;
    will-change: transform;
}}
.auto-spirit2-img-wave {{
    filter: url(#{filter_id});
    -webkit-filter: url(#{filter_id});
    will-change: filter, transform;
}}
@keyframes autoSpiritBodyWave {{
    0%, 100% {{
        transform: perspective(820px) rotateY(0deg) skewX(0deg) translateY(0);
    }}
    50% {{
        transform: perspective(820px) rotateY(1.6deg) skewX(-1.1deg) translateY(-3px);
    }}
}}
@media (prefers-reduced-motion: reduce) {{
    .auto-spirit2-ripple-wave {{ animation: none !important; }}
    .auto-spirit2-img-wave {{ filter: none !important; }}
    .auto-spirit2-body-mask {{ display: none !important; }}
}}
</style>
</head>
<body>
{_spirit2_filter_svg(filter_id)}
<div class="auto-spirit2-wrap">
  <div class="auto-spirit2-ripple">
    <img class="auto-spirit2-img auto-spirit2-img-base"
         src="data:image/jpeg;base64,{base64}"
         alt="로또신령2">
    <div class="auto-spirit2-body-mask" aria-hidden="true">
      <div class="auto-spirit2-ripple-wave">
        <img class="auto-spirit2-img auto-spirit2-img-wave"
             src="data:image/jpeg;base64,{base64}"
             alt="">
      </div>
    </div>
  </div>
</div>
<script>
(function() {{
  function reportHeight() {{
    var h = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight) + 2;
    window.parent.postMessage({{type: "streamlit:setFrameHeight", height: h}}, "*");
  }}
  reportHeight();
  window.addEventListener("load", reportHeight);
  if (window.ResizeObserver) {{
    new ResizeObserver(reportHeight).observe(document.body);
  }}
}})();
</script>
</body>
</html>"""


def _spirit2_image_block(base64: str, slot_class: str, filter_id: str) -> str:
    return f"""
    {_spirit2_filter_svg(filter_id)}
    <div class="{slot_class}">
      <div class="auto-spirit2-wrap">
        <div class="auto-spirit2-ripple">
          <img class="auto-spirit2-img auto-spirit2-img-base"
               src="data:image/jpeg;base64,{base64}"
               alt="로또신령2">
          <div class="auto-spirit2-body-mask" aria-hidden="true">
            <div class="auto-spirit2-ripple-wave">
              <img class="auto-spirit2-img auto-spirit2-img-wave"
                   style="filter:url(#{filter_id});-webkit-filter:url(#{filter_id});"
                   src="data:image/jpeg;base64,{base64}"
                   alt="">
            </div>
          </div>
        </div>
      </div>
    </div>
    """


def _marketing_db():
    """Streamlit 핫리로드 시 stale 모듈 캐시 방지."""
    import marketing_db as mdb

    if not hasattr(mdb, "get_draw_extraction_stats"):
        mdb = importlib.reload(mdb)
    return mdb


def _stats_to_dataframe(stats: list[dict], is_mock: bool) -> pd.DataFrame:
    rows = []
    for item in stats:
        rows.append(
            {
                "회차": item["draw_round"],
                "추출수량": item["total_count"],
                "1등": item["rank_1"],
                "2등": item["rank_2"],
                "3등": item["rank_3"],
                "4등": item["rank_4"],
                "5등": item["rank_5"],
            }
        )
    df = pd.DataFrame(rows)
    if is_mock:
        df.attrs["is_mock"] = True
    return df


def _sync_completed_draw_win_ranks() -> None:
    """메인 엑셀에 당첨번호가 있는 회차 — 추출 조합 등수 집계 반영."""
    try:
        from lotto_stats import sync_marketing_win_ranks_for_db_draws

        sync_marketing_win_ranks_for_db_draws()
    except Exception:
        pass


def _auto_target_draw_round() -> int:
    from auto_purchase_service import _next_draw_round

    return int(_next_draw_round())


def _rank_counts_from_upload_combos(
    combos: list[tuple[int, int, int, int, int, int]],
    draw_round: int,
) -> dict[int, int]:
    from lotto_stats import calc_lotto_win_rank, get_draw_result_by_round

    counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    result = get_draw_result_by_round(int(draw_round))
    if not result:
        return counts
    winning = result["numbers"]
    bonus = int(result["bonus"])
    for combo in combos:
        rank = calc_lotto_win_rank(combo, winning, bonus)
        if rank is not None:
            counts[int(rank)] += 1
    return counts


def _stats_from_admin_combo_upload(draw_round: int) -> dict | None:
    """운영자 대시보드 배포용 재업로드(saved_combinations.csv) → 해당 회차 통계."""
    if not os.path.exists(ADMIN_COMBO_SAVE_FILE):
        return None
    try:
        from marketing_db import parse_combination_rows_from_dataframe

        df = pd.read_csv(ADMIN_COMBO_SAVE_FILE)
        combos = parse_combination_rows_from_dataframe(df)
        if not combos:
            return None
        ranks = _rank_counts_from_upload_combos(combos, draw_round)
        return {
            "draw_round": int(draw_round),
            "total_count": len(combos),
            "rank_1": ranks[1],
            "rank_2": ranks[2],
            "rank_3": ranks[3],
            "rank_4": ranks[4],
            "rank_5": ranks[5],
        }
    except Exception:
        return None


def _merge_upload_stats_for_target_draw(stats: list[dict], draw_round: int) -> list[dict]:
    upload_item = _stats_from_admin_combo_upload(draw_round)
    if not upload_item:
        return stats
    merged = [item for item in stats if int(item["draw_round"]) != int(draw_round)]
    merged.append(upload_item)
    merged.sort(key=lambda x: int(x["draw_round"]), reverse=True)
    return merged


def _admin_combo_save_mtime() -> float:
    try:
        return os.path.getmtime(ADMIN_COMBO_SAVE_FILE)
    except OSError:
        return 0.0


def _load_stats_table() -> tuple[pd.DataFrame, bool]:
    mdb = _marketing_db()
    mdb.init_marketing_tables()
    mdb.ensure_marketing_pool_seeds()
    _sync_completed_draw_win_ranks()
    target_draw = _auto_target_draw_round()
    stats = mdb.get_draw_extraction_stats(limit=20)
    if stats:
        stats = _merge_upload_stats_for_target_draw(stats, target_draw)
        return _stats_to_dataframe(stats, False), False
    upload_only = _stats_from_admin_combo_upload(target_draw)
    if upload_only:
        return _stats_to_dataframe([upload_only], False), False
    return _stats_to_dataframe(mdb.get_mock_draw_extraction_stats(), True), True


@st.cache_data(ttl=120, show_spinner=False)
def _load_stats_table_cached(_admin_combo_csv_mtime: float) -> tuple[pd.DataFrame, bool]:
    return _load_stats_table()


def _load_pattern_count_from_n5() -> int | None:
    """관리자 3종필터(saved_filters.pkl) — 기본·절대·이격수 활성 규칙 합계."""
    import pickle

    path = "saved_filters.pkl"
    if not os.path.exists(path):
        return None
    try:
        from filter_sheet_validation import normalize_three_filter_data, validate_three_filter_sheets

        with open(path, "rb") as f:
            saved = normalize_three_filter_data(pickle.load(f))
        _, summary = validate_three_filter_sheets(saved)
        total = (
            int(summary.get("basic_rows", 0))
            + int(summary.get("absolute_rows", 0))
            + int(summary.get("interval_rows", 0))
        )
        return total if total > 0 else None
    except Exception:
        return None


def _pattern_applied_count() -> int:
    """3종 필터 규칙 합계 (없으면 0)."""
    count = _load_pattern_count_from_n5()
    return int(count) if count is not None else 0


def _ball_color(n: int) -> str:
    if 1 <= n <= 10:
        return "#f9a825"
    if 11 <= n <= 20:
        return "#1976d2"
    if 21 <= n <= 30:
        return "#e53935"
    if 31 <= n <= 40:
        return "#757575"
    return "#388e3c"


def _sms_schedule_label(purchase_method: str, sms_days: list[str] | str) -> str:
    days = sms_days
    if isinstance(days, str):
        days = [d.strip() for d in days.split(",") if d.strip()]
    if purchase_method == "월간구독" and days:
        return "문자 발송 예정: 매주 " + " · ".join(f"{d}요일" for d in days)
    return "문자 발송: 즉시 구매 (테스트 기간 — 화면 확인)"


def _purchase_banner_html(data: dict, *, compact: bool = False) -> str:
    allocated = data.get("allocated") or []
    draw_round = data.get("draw_round", "")
    combo_count = data.get("combo_count", len(allocated))
    cost = data.get("cost")
    purchase_method = data.get("purchase_method") or (
        "월간구독" if data.get("purchase_type") == "정기구독" else "즉시"
    )
    sms_days = data.get("sms_days") or []
    schedule = _sms_schedule_label(purchase_method, sms_days)
    cost_line = f"{int(cost):,}P 차감" if cost is not None else ""

    combo_rows = ""
    for idx, item in enumerate(allocated, start=1):
        combo = item.get("combo") or []
        balls = "".join(
            f'<span class="auto-banner-ball" style="background:{_ball_color(n)};">{n:02d}</span>'
            for n in combo
        )
        combo_rows += (
            f'<div class="auto-banner-combo">'
            f'<span class="auto-banner-combo-idx">{idx}</span>'
            f'<div class="auto-banner-ball-row">{balls}</div>'
            f"</div>"
        )

    if compact:
        grid_rows = ""
        for idx, item in enumerate(allocated[:5], start=1):
            combo = (item.get("combo") or [])[:6]
            balls = "".join(
                f'<span class="auto-banner-ball" style="background:{_ball_color(n)};">{n:02d}</span>'
                for n in combo
            )
            grid_rows += (
                f'<div class="auto-banner-combo">'
                f'<span class="auto-banner-combo-idx">{idx}</span>'
                f'<div class="auto-banner-ball-row">{balls}</div>'
                f"</div>"
            )
        return (
            '<div class="auto-purchase-banner auto-purchase-banner-compact auto-purchase-banner-history-grid">'
            f'<div class="auto-banner-combos">{grid_rows}</div>'
            "</div>"
        )

    notice = (
        ""
        if compact
        else (
            '<p class="auto-banner-notice">'
            "현재 테스트 기간으로 문자 발송 대신 화면에서 결과를 확인하실 수 있습니다."
            "</p>"
        )
    )

    oid = data.get("order_id")
    if compact:
        if oid is not None and int(oid) < 0:
            title = f"내역 #{abs(int(oid))}"
        else:
            title = f"주문 #{oid}"
    else:
        title = "구매 완료"
    meta_parts = [f"{combo_count}개 배정", schedule]
    if cost_line:
        meta_parts.append(cost_line)
    meta = " · ".join(meta_parts)
    compact_cls = " auto-purchase-banner-compact" if compact else ""

    return (
        f'<div class="auto-purchase-banner{compact_cls}">'
        f'<div class="auto-banner-head">'
        f'<span class="auto-banner-badge">✓</span>'
        f"<div>"
        f'<div class="auto-banner-title">{title} · {draw_round}회차</div>'
        f'<div class="auto-banner-meta">{meta}</div>'
        f"</div></div>"
        f'<div class="auto-banner-combos">{combo_rows}</div>'
        f"{notice}"
        f"</div>"
    )


def _purchase_history_entry(
    outcome: dict,
    purchase_method: str,
    sms_days: list[str] | None = None,
) -> dict:
    return {
        "draw_round": outcome["draw_round"],
        "combo_count": outcome["combo_count"],
        "cost": outcome["cost"],
        "allocated": outcome.get("allocated") or [],
        "purchase_method": purchase_method,
        "purchase_type": outcome.get("purchase_type"),
        "sms_days": outcome.get("sms_days") or sms_days or [],
        "order_id": outcome["order_id"],
    }


def _append_purchase_history(entry: dict) -> None:
    from user_scope import session_key

    hist_key = session_key("auto_purchase_history")
    history = list(st.session_state.get(hist_key) or [])
    order_id = entry.get("order_id")
    if order_id is not None:
        history = [item for item in history if item.get("order_id") != order_id]
    history.insert(0, entry)
    st.session_state[hist_key] = history[:20]


def _build_quick_purchase_entry(
    quantity: int,
    purchase_method: str,
    sms_days: list[str],
) -> dict:
    """테스트 기간 — DB 저장 조합(회차 풀)에서 무작위 순차 배정."""
    from auto_purchase_service import (
        NextDrawPoolNotReadyError,
        _next_draw_round,
        check_next_draw_pool_ready,
    )
    from marketing_db import (
        allocate_lotto_combinations_random_sequential,
        init_marketing_tables,
    )
    from wallet_db import calc_auto_cost

    pool = check_next_draw_pool_ready()
    if not pool["ok"]:
        raise NextDrawPoolNotReadyError(pool["draw_round"], pool["message"])

    init_marketing_tables()
    draw_round = _next_draw_round()
    from user_scope import session_key

    seq_key = session_key("auto_purchase_seq")
    seq = int(st.session_state.get(seq_key) or 0) + 1
    st.session_state[seq_key] = seq
    test_order_id = 9_000_000 + seq

    allocated = allocate_lotto_combinations_random_sequential(
        draw_round,
        int(quantity),
        test_order_id,
    )
    return {
        "draw_round": draw_round,
        "combo_count": int(quantity),
        "cost": calc_auto_cost(int(quantity)),
        "allocated": allocated,
        "purchase_method": purchase_method,
        "purchase_type": "정기구독" if purchase_method == "월간구독" else "일반구매",
        "sms_days": list(sms_days),
        "order_id": -seq,
    }


def _collect_purchase_history_items(member_id: int | None) -> list[dict]:
    """세션 + DB 구매 내역 (order_id 기준 중복 제거, 최신순)."""
    from user_scope import session_key

    items: list[dict] = []
    seen_order_ids: set[int] = set()

    for entry in st.session_state.get(session_key("auto_purchase_history")) or []:
        order_id = entry.get("order_id")
        if order_id is not None:
            if order_id in seen_order_ids:
                continue
            seen_order_ids.add(int(order_id))
        items.append(entry)

    if member_id:
        from marketing_db import get_combinations_by_auto_order_id, init_marketing_tables
        from wallet_db import calc_auto_cost, init_wallet_tables, list_completed_auto_orders

        init_wallet_tables()
        init_marketing_tables()
        for order in list_completed_auto_orders(member_id, limit=20):
            order_id = int(order["id"])
            if order_id in seen_order_ids:
                continue
            seen_order_ids.add(order_id)
            combos = get_combinations_by_auto_order_id(order_id)
            purchase_method = (
                "월간구독" if order.get("purchase_type") == "정기구독" else "즉시"
            )
            items.append(
                {
                    "order_id": order_id,
                    "draw_round": order.get("draw_round"),
                    "combo_count": order.get("combo_count") or len(combos),
                    "cost": calc_auto_cost(int(order.get("quantity") or 0)),
                    "allocated": combos,
                    "purchase_method": purchase_method,
                    "purchase_type": order.get("purchase_type"),
                    "sms_days": order.get("sms_days") or "",
                }
            )

    return items


def render():
    from user_scope import init_guest_scope

    init_guest_scope()
    from shared_ui_styles import auto_page_button_css

    st.markdown(auto_page_button_css(), unsafe_allow_html=True)
    st.markdown(
        """
    <style>
        .stApp { background-color: #12182b; color: white; }
        .block-container { padding: 10px !important; max-width: 600px; }
        section[data-testid="stSidebar"], header[data-testid="stHeader"] { display: none; }
        .auto-page-wrap { max-width: 600px; margin: 0 auto; }
        .auto-label-pill {
            display: inline-block;
            flex: 0 0 auto;
            background: linear-gradient(145deg, #e1bee7, #ce93d8);
            color: #4a148c;
            font-weight: 800;
            font-size: 14px;
            padding: 10px 18px;
            border-radius: 14px;
            box-shadow: 0 4px 14px rgba(206, 147, 216, 0.28), inset 0 1px 0 rgba(255,255,255,0.35);
            margin-bottom: 0;
            min-width: 92px;
            text-align: center;
        }
        .auto-section-row {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 8px;
            flex-wrap: nowrap;
        }
        .auto-options-wrap {
            flex: 0 1 auto;
            width: auto;
            max-width: 100%;
        }
        .st-key-auto_purchase_method_zone_6n36s5 > div[data-testid="stVerticalBlock"] {
            display: flex !important;
            flex-direction: column !important;
            align-items: stretch !important;
            gap: 0 !important;
            margin-bottom: 7px !important;
        }
        /* 구매방식·수신번호 하단 여백: 도형 높이 35px × 20% = 7px */
        .st-key-auto_phone_input_6n36s5 {
            margin-bottom: 7px !important;
        }
        .st-key-auto_purchase_method_zone_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] {
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            align-items: flex-start !important;
            justify-content: space-between !important;
            gap: 6px !important;
            width: 100% !important;
        }
        .st-key-auto_purchase_method_zone_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:nth-child(1) {
            flex: 0 0 auto !important;
            min-width: 0 !important;
            width: auto !important;
        }
        .st-key-auto_purchase_method_zone_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:nth-child(2) {
            flex: 0 0 auto !important;
            min-width: 0 !important;
            width: auto !important;
        }
        .st-key-auto_method_left_6n36s5 > div[data-testid="stVerticalBlock"] {
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: wrap !important;
            align-items: center !important;
            gap: 6px 8px !important;
        }
        .st-key-auto_purchase_method_zone_6n36s5 .auto-label-pill {
            margin: 0 !important;
            flex: 0 0 auto !important;
        }
        .st-key-auto_purchase_method_zone_6n36s5 .st-key-auto_purchase_method_6n36s5 {
            flex: 0 0 auto !important;
            margin: 0 !important;
        }
        .st-key-auto_purchase_method_zone_6n36s5 .st-key-auto_sms_days_6n36s5 {
            flex: 0 0 auto !important;
            margin: 0 !important;
            transition: opacity 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease !important;
        }
        .st-key-auto_purchase_method_zone_6n36s5.auto-sms-dim .st-key-auto_sms_days_6n36s5 {
            opacity: 0.28 !important;
            pointer-events: none !important;
            filter: saturate(0.55) !important;
            border-color: rgba(179, 157, 219, 0.22) !important;
            box-shadow: none !important;
        }
        .st-key-auto_purchase_method_zone_6n36s5.auto-sms-active .st-key-auto_sms_days_6n36s5 {
            opacity: 1 !important;
            pointer-events: auto !important;
            filter: none !important;
        }
        .st-key-auto_purchase_method_zone_6n36s5.auto-sms-dim .auto-sms-days-caption {
            color: rgba(179, 157, 219, 0.45) !important;
        }
        .auto-sms-days-caption {
            color: #b39ddb;
            font-size: 9px;
            font-weight: 700;
            margin: 0 !important;
            padding: 0 2px !important;
            letter-spacing: -0.03em;
            line-height: 1.1;
            white-space: normal !important;
            text-align: center !important;
        }
        .st-key-auto_sms_days_6n36s5 {
            display: block !important;
            width: 100% !important;
            max-width: 100% !important;
            padding: 4px 6px 4px 6px !important;
            margin: 0 !important;
            border: 1px solid rgba(179, 157, 219, 0.52) !important;
            border-radius: 10px !important;
            background: linear-gradient(165deg, rgba(255,255,255,0.08), rgba(255,255,255,0.02)) !important;
            box-shadow:
                0 2px 8px rgba(0,0,0,0.2),
                inset 0 1px 0 rgba(255,255,255,0.06) !important;
            box-sizing: border-box !important;
        }
        .st-key-auto_sms_days_6n36s5 > div[data-testid="stVerticalBlock"] {
            display: flex !important;
            flex-direction: column !important;
            gap: 2px !important;
            align-items: stretch !important;
        }
        .st-key-auto_sms_days_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] {
            width: auto !important;
            max-width: 100% !important;
            gap: 0.35rem !important;
            justify-content: flex-start !important;
            flex-wrap: nowrap !important;
        }
        .st-key-auto_sms_days_6n36s5 div[data-testid="stColumn"] {
            flex: 1 1 0 !important;
            width: auto !important;
            min-width: 0 !important;
            max-width: 33% !important;
        }
        .auto-table-title {
            display: inline-block;
            background: linear-gradient(145deg, #243052 0%, #1a2238 42%, #12182b 100%);
            color: #b8c2d6;
            font-weight: 800;
            font-size: 16px;
            padding: 10px 16px;
            border-radius: 14px;
            border: 1px solid rgba(100, 126, 170, 0.32);
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.06);
            margin: 8px 0 12px 0;
        }
        .auto-stats-head-row {
            display: flex;
            flex-direction: column;
            flex-wrap: nowrap;
            align-items: flex-start;
            justify-content: flex-start;
            gap: 7px;
            width: 100%;
            max-width: 100%;
            margin: 4px 0 10px 0;
            box-sizing: border-box;
        }
        .auto-stats-head-row .auto-table-title {
            flex: 0 0 auto;
            margin: 0 !important;
            white-space: nowrap;
            font-size: 14px;
            padding: 8px 12px;
        }
        .auto-stats-head-row .auto-pattern-applied-note {
            flex: 0 0 auto;
            width: 100%;
            min-width: 0;
            margin: 0 !important;
            text-align: left;
            color: #f1f5f9 !important;
            font-size: 13px !important;
            font-weight: 700 !important;
            line-height: 1.35 !important;
            white-space: normal;
        }
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] summary p {
            font-size: 16px !important;
            font-weight: 800 !important;
        }
        .auto-purchase-banner {
            margin: 14px 0 18px;
            padding: 16px 14px 14px;
            border-radius: 16px;
            border: 1px solid rgba(206, 147, 216, 0.55);
            background: linear-gradient(155deg, rgba(74, 20, 140, 0.92) 0%, rgba(26, 34, 56, 0.96) 55%, rgba(18, 24, 43, 0.98) 100%);
            box-shadow: 0 8px 28px rgba(0, 0, 0, 0.45), 0 0 0 1px rgba(179, 157, 219, 0.18), inset 0 1px 0 rgba(255, 255, 255, 0.08);
        }
        .auto-purchase-banner-compact {
            margin: 10px 0;
            padding: 12px;
        }
        /* K-979: 구매내역 — 6볼 × 5줄 그리드 전용 */
        .st-key-auto_purchase_history_zone_6n36s5 {
            overflow: visible !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"],
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] details {
            overflow: visible !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] {
            position: relative !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpanderDetails"] {
            overflow: visible !important;
            width: max-content !important;
            min-width: 168px !important;
            max-width: min(240px, calc(100vw - 20px)) !important;
            padding: 4px 2px !important;
            box-sizing: border-box !important;
            position: absolute !important;
            right: 0 !important;
            top: calc(100% + 4px) !important;
            z-index: 40 !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpanderDetails"] div[data-testid="stMarkdown"],
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpanderDetails"] div[data-testid="stMarkdown"] > div {
            width: fit-content !important;
            max-width: 100% !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5 .auto-purchase-banner-history-grid {
            margin: 0 !important;
            padding: 6px 8px 8px !important;
            width: fit-content !important;
            max-width: 100% !important;
            box-sizing: border-box !important;
            border-radius: 12px !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5 .auto-purchase-banner-history-grid .auto-banner-combos {
            display: flex !important;
            flex-direction: column !important;
            gap: 4px !important;
            margin: 0 !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5 .auto-purchase-banner-history-grid .auto-banner-combo {
            display: flex !important;
            flex-wrap: nowrap !important;
            align-items: center !important;
            padding: 3px 5px !important;
            gap: 5px !important;
            border-radius: 8px !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5 .auto-purchase-banner-history-grid .auto-banner-combo-idx {
            flex: 0 0 12px !important;
            width: 12px !important;
            min-width: 12px !important;
            font-size: 10px !important;
            line-height: 1 !important;
            text-align: center !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5 .auto-purchase-banner-history-grid .auto-banner-ball-row {
            display: flex !important;
            flex-wrap: nowrap !important;
            flex: 0 0 auto !important;
            gap: 3px !important;
            min-width: 0 !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5 .auto-purchase-banner-history-grid .auto-banner-ball {
            flex: 0 0 20px !important;
            width: 20px !important;
            height: 20px !important;
            min-width: 20px !important;
            max-width: 20px !important;
            font-size: 9px !important;
            padding: 0 !important;
        }
        .auto-next-draw-pool-banner {
            margin: 0 0 14px 0;
            padding: 14px 16px;
            border-radius: 12px;
            border: 1px solid rgba(255, 183, 77, 0.55);
            background: linear-gradient(155deg, rgba(62, 39, 7, 0.95) 0%, rgba(26, 34, 56, 0.98) 100%);
            color: #ffe082;
            font-size: 15px;
            font-weight: 800;
            line-height: 1.5;
            text-align: center;
        }
        .auto-banner-head {
            display: flex;
            align-items: flex-start;
            gap: 10px;
            margin-bottom: 12px;
        }
        .auto-banner-badge {
            flex: 0 0 auto;
            width: 28px;
            height: 28px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 900;
            font-size: 14px;
            color: #4a148c;
            background: linear-gradient(145deg, #e1bee7, #ce93d8);
            box-shadow: 0 2px 8px rgba(206, 147, 216, 0.35);
        }
        .auto-banner-title {
            color: #f3e5f5;
            font-weight: 800;
            font-size: 16px;
            line-height: 1.35;
        }
        .auto-banner-meta {
            color: #b39ddb;
            font-size: 12px;
            font-weight: 600;
            margin-top: 4px;
            line-height: 1.45;
        }
        .auto-banner-combos {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        .auto-banner-combo {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 10px;
            border-radius: 12px;
            background: rgba(0, 0, 0, 0.22);
            border: 1px solid rgba(179, 157, 219, 0.22);
        }
        .auto-banner-combo-idx {
            flex: 0 0 auto;
            width: 22px;
            color: #ce93d8;
            font-weight: 800;
            font-size: 13px;
            text-align: center;
        }
        .auto-banner-ball-row {
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
        }
        .auto-banner-ball {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 28px;
            height: 28px;
            padding: 0 4px;
            border-radius: 50%;
            color: #fff;
            font-weight: 800;
            font-size: 12px;
            text-shadow: 0 1px 2px rgba(0, 0, 0, 0.45);
            box-shadow: inset 0 1px 2px rgba(255, 255, 255, 0.35), 0 2px 4px rgba(0, 0, 0, 0.35);
        }
        .auto-banner-notice {
            margin: 12px 0 0;
            padding: 10px 12px;
            border-radius: 10px;
            background: rgba(255, 193, 7, 0.12);
            border: 1px solid rgba(255, 213, 79, 0.35);
            color: #ffe082;
            font-size: 12px;
            font-weight: 600;
            line-height: 1.5;
        }
        div[data-testid="stRadio"] label p {
            font-weight: 700 !important;
        }
        div[data-testid="stCheckbox"] label p {
            font-weight: 600 !important;
        }
        .st-key-auto_purchase_method_6n36s5,
        .st-key-auto_purchase_quantity_6n36s5 {
            width: auto !important;
            max-width: 100% !important;
        }
        .st-key-auto_purchase_method_6n36s5 input[type="radio"],
        .st-key-auto_purchase_quantity_6n36s5 input[type="radio"] {
            accent-color: #ce93d8 !important;
        }
        .st-key-auto_purchase_method_6n36s5 div[data-testid="stRadio"],
        .st-key-auto_purchase_quantity_6n36s5 div[data-testid="stRadio"] {
            width: auto !important;
        }
        .st-key-auto_purchase_method_6n36s5 div[data-testid="stRadio"] > div,
        .st-key-auto_purchase_quantity_6n36s5 div[data-testid="stRadio"] > div {
            flex-wrap: nowrap !important;
            gap: 0.85rem !important;
            align-items: flex-start !important;
            justify-content: flex-start !important;
            width: auto !important;
        }
        .st-key-auto_purchase_method_6n36s5 div[data-testid="stRadio"] label[data-baseweb="radio"],
        .st-key-auto_purchase_quantity_6n36s5 div[data-testid="stRadio"] label[data-baseweb="radio"] {
            display: inline-flex !important;
            flex-direction: column !important;
            align-items: center !important;
            justify-content: flex-start !important;
            gap: 5px !important;
            margin: 0 !important;
            padding: 4px 6px !important;
            min-width: 0 !important;
            background: transparent !important;
            border-radius: 10px !important;
            transition: background 0.15s ease !important;
        }
        .st-key-auto_purchase_method_6n36s5 div[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked),
        .st-key-auto_purchase_quantity_6n36s5 div[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) {
            background: linear-gradient(165deg, rgba(206, 147, 216, 0.18), rgba(171, 71, 188, 0.08)) !important;
            box-shadow: inset 0 0 0 1px rgba(206, 147, 216, 0.28) !important;
        }
        .st-key-auto_purchase_method_6n36s5 div[data-testid="stRadio"] label[data-baseweb="radio"] div[data-testid="stMarkdownContainer"],
        .st-key-auto_purchase_quantity_6n36s5 div[data-testid="stRadio"] label[data-baseweb="radio"] div[data-testid="stMarkdownContainer"] {
            order: -1 !important;
            margin: 0 !important;
            padding: 0 !important;
            z-index: 2 !important;
            position: relative !important;
        }
        .st-key-auto_purchase_method_6n36s5 div[data-testid="stRadio"] label[data-baseweb="radio"] div[data-testid="stMarkdownContainer"] p,
        .st-key-auto_purchase_quantity_6n36s5 div[data-testid="stRadio"] label[data-baseweb="radio"] div[data-testid="stMarkdownContainer"] p {
            color: #ffffff !important;
            font-weight: 700 !important;
            margin: 0 !important;
            white-space: nowrap !important;
        }
        .st-key-auto_purchase_quantity_6n36s5 div[data-testid="stRadio"] label[data-baseweb="radio"] div[data-testid="stMarkdownContainer"] p {
            font-size: 13px !important;
        }
        .st-key-auto_purchase_method_6n36s5 div[data-testid="stRadio"] label[data-baseweb="radio"] > div:first-of-type,
        .st-key-auto_purchase_quantity_6n36s5 div[data-testid="stRadio"] label[data-baseweb="radio"] > div:first-of-type {
            order: 1 !important;
            width: 22px !important;
            height: 22px !important;
            min-width: 22px !important;
            min-height: 22px !important;
            border-radius: 50% !important;
            border: 2px solid rgba(206, 147, 216, 0.72) !important;
            background: radial-gradient(circle at 32% 28%, rgba(255,255,255,0.16), rgba(18, 24, 43, 0.88)) !important;
            flex-shrink: 0 !important;
            box-shadow:
                inset 0 2px 5px rgba(0,0,0,0.38),
                0 0 0 1px rgba(255,255,255,0.06) !important;
            transition: box-shadow 0.18s ease, border-color 0.18s ease !important;
        }
        .st-key-auto_purchase_method_6n36s5 div[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) > div:first-of-type,
        .st-key-auto_purchase_quantity_6n36s5 div[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) > div:first-of-type {
            border-color: #e1bee7 !important;
            box-shadow:
                0 0 14px rgba(206, 147, 216, 0.55),
                0 0 0 2px rgba(206, 147, 216, 0.22),
                inset 0 1px 3px rgba(0,0,0,0.28) !important;
        }
        .st-key-auto_purchase_method_6n36s5 div[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) > div:first-of-type > div,
        .st-key-auto_purchase_quantity_6n36s5 div[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) > div:first-of-type > div {
            width: 10px !important;
            height: 10px !important;
            min-width: 10px !important;
            min-height: 10px !important;
            border-radius: 50% !important;
            background: radial-gradient(circle at 35% 30%, #f8efff, #ba68c8 58%, #8e24aa 100%) !important;
            background-color: #ce93d8 !important;
            box-shadow: 0 0 10px rgba(206, 147, 216, 0.85) !important;
        }
        .st-key-auto_sms_days_6n36s5 input[type="checkbox"] {
            accent-color: #ce93d8 !important;
        }
        .st-key-auto_sms_days_6n36s5 div[data-testid="stColumn"] {
            overflow: visible !important;
        }
        .st-key-auto_sms_days_6n36s5 div[data-testid="stCheckbox"] {
            overflow: visible !important;
            margin: 0 !important;
        }
        .st-key-auto_sms_days_6n36s5 div[data-testid="stCheckbox"] label,
        .st-key-auto_sms_days_6n36s5 div[data-testid="stCheckbox"] [data-baseweb="checkbox"] {
            display: inline-flex !important;
            flex-direction: row !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 3px !important;
            margin: 0 !important;
            padding: 0 !important;
            width: auto !important;
            min-height: 0 !important;
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
            overflow: visible !important;
        }
        .st-key-auto_sms_days_6n36s5 div[data-testid="stCheckbox"] [data-testid="stWidgetLabel"] {
            order: 1 !important;
            position: relative !important;
            z-index: 30 !important;
            margin: 0 !important;
            padding: 0 !important;
            width: auto !important;
            text-align: center !important;
            overflow: visible !important;
        }
        .st-key-auto_sms_days_6n36s5 div[data-testid="stCheckbox"] [data-testid="stWidgetLabel"] p,
        .st-key-auto_sms_days_6n36s5 div[data-testid="stCheckbox"] label p {
            color: #ffffff !important;
            font-weight: 700 !important;
            margin: 0 !important;
            padding: 0 !important;
            white-space: nowrap !important;
            font-size: 12px !important;
            line-height: 1 !important;
            text-align: center !important;
            opacity: 1 !important;
            visibility: visible !important;
            display: block !important;
            position: relative !important;
            z-index: 30 !important;
            text-shadow: 0 1px 3px rgba(0, 0, 0, 0.85) !important;
        }
        .st-key-auto_sms_days_6n36s5 div[data-testid="stCheckbox"] [data-baseweb="checkbox"] > span:first-of-type {
            order: 0 !important;
            flex-shrink: 0 !important;
            width: 18px !important;
            height: 18px !important;
            min-width: 18px !important;
            min-height: 18px !important;
            margin: 0 !important;
            border: 2px solid rgba(206, 147, 216, 0.72) !important;
            border-radius: 6px !important;
            background: radial-gradient(circle at 32% 28%, rgba(255,255,255,0.14), rgba(18, 24, 43, 0.88)) !important;
            background-image: none !important;
            box-shadow:
                inset 0 2px 5px rgba(0,0,0,0.34),
                0 0 0 1px rgba(255,255,255,0.06) !important;
            position: relative !important;
            z-index: 1 !important;
        }
        .st-key-auto_sms_days_6n36s5 div[data-testid="stCheckbox"] [data-baseweb="checkbox"]:has(input:checked) > span:first-of-type {
            background: radial-gradient(circle at 35% 30%, #f3e5f5, #ba68c8 55%, #8e24aa 100%) !important;
            background-color: #ce93d8 !important;
            border-color: #e1bee7 !important;
            box-shadow:
                0 0 12px rgba(206, 147, 216, 0.55),
                inset 0 1px 2px rgba(255,255,255,0.25) !important;
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' fill='none'%3E%3Cpath d='M3.5 8.2 L6.8 11.5 L12.5 4.5' stroke='%234a148c' stroke-width='1.45' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E") !important;
            background-repeat: no-repeat !important;
            background-position: center !important;
            background-size: 10px 10px !important;
        }
        .st-key-auto_form_lower_6n36s5 {
            margin-top: 2px !important;
            padding-top: 0 !important;
        }
        .st-key-auto_form_lower_6n36s5 > div[data-testid="stVerticalBlock"] {
            gap: 0.35rem !important;
        }
        .st-key-auto_form_lower_6n36s5 div[data-testid="stTextInput"],
        .st-key-auto_form_lower_6n36s5 div[data-testid="stButton"],
        .st-key-auto_form_lower_6n36s5 div[data-testid="stExpander"] {
            margin-bottom: 0 !important;
        }
        .st-key-auto_page_columns_6n36s5 > div[data-testid="stVerticalBlock"] {
            gap: 0.25rem !important;
        }
        .st-key-auto_page_columns_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] {
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            align-items: flex-start !important;
            gap: 6px !important;
        }
        .st-key-auto_page_columns_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
            align-self: flex-start !important;
            height: auto !important;
            min-height: 0 !important;
        }
        .st-key-auto_page_columns_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] {
            height: auto !important;
            min-height: 0 !important;
            justify-content: flex-start !important;
        }
        .st-key-auto_stats_section_6n36s5 {
            margin-top: 0 !important;
            padding-top: 0 !important;
            width: 100% !important;
            max-width: 600px !important;
            box-sizing: border-box !important;
        }
        .st-key-auto_page_columns_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:nth-child(1) .st-key-auto_stats_section_6n36s5 {
            width: calc(100% / 0.55) !important;
            max-width: min(600px, calc(100vw - 20px)) !important;
        }
        .st-key-auto_stats_section_6n36s5 div[data-testid="stMarkdown"] {
            width: 100% !important;
            max-width: 100% !important;
        }
        .st-key-auto_stats_section_6n36s5 div[data-testid="stMarkdown"] > div {
            width: 100% !important;
            max-width: 100% !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5 {
            margin-bottom: 0 !important;
            padding-bottom: 0 !important;
        }
        .st-key-auto_page_columns_6n36s5 {
            margin-bottom: 0 !important;
            padding-bottom: 0 !important;
        }
        .st-key-auto_page_columns_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:nth-child(1) {
            flex: 1 1 55% !important;
            width: 55% !important;
            min-width: 0 !important;
            max-width: 55% !important;
        }
        .st-key-auto_page_columns_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:nth-child(2) {
            flex: 1 1 42% !important;
            width: 42% !important;
            min-width: 0 !important;
            max-width: 42% !important;
        }
        .auto-spirit2-slot-mobile {
            display: none !important;
        }
        .st-key-auto_spirit_below_confirm_6n36s5 {
            width: 100% !important;
            max-width: 100% !important;
            display: flex !important;
            flex-direction: column !important;
            align-items: center !important;
            justify-content: center !important;
            text-align: center !important;
            margin: 10px auto 0 !important;
            margin-bottom: 0 !important;
            padding: 0 !important;
            box-sizing: border-box !important;
        }
        .st-key-auto_spirit_below_confirm_6n36s5 > div[data-testid="stVerticalBlock"] {
            gap: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        .st-key-auto_spirit_below_confirm_6n36s5 .auto-spirit2-slot-right {
            display: block !important;
            visibility: visible !important;
            width: 100% !important;
            max-width: min(360px, calc(100vw - 24px)) !important;
            height: auto !important;
            min-height: 0 !important;
            overflow: visible !important;
            margin: 0 auto !important;
            padding: 0 !important;
        }
        .st-key-auto_spirit_below_confirm_6n36s5 .auto-spirit2-wrap,
        .st-key-auto_spirit_below_confirm_6n36s5 .auto-spirit2-ripple {
            width: 100% !important;
            max-width: min(360px, calc(100vw - 24px)) !important;
            height: auto !important;
        }
        .st-key-auto_spirit_below_confirm_6n36s5 .auto-spirit2-img-base {
            width: 100% !important;
            height: auto !important;
            display: block !important;
            object-fit: contain !important;
            aspect-ratio: auto !important;
        }
        .st-key-auto_spirit_below_confirm_6n36s5 [data-testid="stElementContainer"]:has([data-testid="stMarkdown"]) {
            width: 100% !important;
            max-width: min(360px, calc(100vw - 24px)) !important;
            margin: 0 auto !important;
            height: auto !important;
            flex: 0 0 auto !important;
        }
        .st-key-auto_form_lower_6n36s5 .st-key-auto_stats_section_6n36s5 {
            margin-top: 0 !important;
            padding-top: 0 !important;
        }
        .st-key-auto_form_lower_6n36s5 .st-key-auto_spirit_below_confirm_6n36s5 + div[data-testid="stElementContainer"]:has(.st-key-auto_stats_section_6n36s5),
        .st-key-auto_form_lower_6n36s5 .st-key-auto_spirit_below_confirm_6n36s5 ~ .st-key-auto_stats_section_6n36s5 {
            margin-top: 0 !important;
            padding-top: 0 !important;
        }
        .st-key-auto_spirit_below_confirm_6n36s5 [data-testid="stMarkdown"],
        .st-key-auto_spirit_below_confirm_6n36s5 [data-testid="stMarkdown"] > div {
            width: 100% !important;
            max-width: 100% !important;
            display: flex !important;
            justify-content: center !important;
        }
        .st-key-auto_visual_col_6n36s5 {
            display: none !important;
            height: 0 !important;
            min-height: 0 !important;
            overflow: hidden !important;
            visibility: hidden !important;
            pointer-events: none !important;
        }
        .auto-spirit2-slot-right {
            display: block;
            width: 100%;
            margin: 0;
            padding: 0;
        }
        .auto-spirit2-slot-right .auto-spirit2-img {
            width: 100%;
            max-width: 100%;
            border-radius: 10px;
        }
        .auto-spirit2-slot-desktop {
            display: block;
            width: 100%;
        }
        @media (max-width: 768px) {
            .auto-section-row {
                flex-wrap: nowrap;
                align-items: center;
                margin-bottom: 10px !important;
            }
            .st-key-auto_purchase_method_zone_6n36s5 > div[data-testid="stVerticalBlock"] {
                margin-bottom: 7px !important;
            }
            .st-key-auto_purchase_method_zone_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] {
                flex-direction: row !important;
                flex-wrap: nowrap !important;
                align-items: flex-start !important;
                gap: 4px !important;
            }
            .st-key-auto_method_left_6n36s5 > div[data-testid="stVerticalBlock"] {
                flex-direction: row !important;
                flex-wrap: wrap !important;
                align-items: center !important;
                gap: 4px 6px !important;
            }
            .st-key-auto_purchase_method_zone_6n36s5 .st-key-auto_sms_days_6n36s5 {
                flex: 1 1 0 !important;
                width: auto !important;
                max-width: none !important;
                margin-top: 0 !important;
                padding: 3px 5px 3px 5px !important;
            }
            .auto-sms-days-caption {
                font-size: 8px !important;
                line-height: 1.15 !important;
                text-align: center !important;
            }
            .st-key-auto_sms_days_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] {
                flex-direction: row !important;
                flex-wrap: nowrap !important;
                justify-content: space-between !important;
                gap: 2px !important;
                width: 100% !important;
            }
            .st-key-auto_sms_days_6n36s5 div[data-testid="stColumn"] {
                flex: 0 0 auto !important;
                min-width: 0 !important;
                width: auto !important;
            }
            .st-key-auto_sms_days_6n36s5 div[data-testid="stCheckbox"] [data-baseweb="checkbox"] > span:first-of-type {
                width: 18px !important;
                height: 18px !important;
                min-width: 18px !important;
                min-height: 18px !important;
            }
            .st-key-auto_spirit_below_confirm_6n36s5 {
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                width: 100% !important;
                margin-top: 10px !important;
                margin-bottom: 0 !important;
            }
            .st-key-auto_spirit_below_confirm_6n36s5 > div[data-testid="stVerticalBlock"] {
                gap: 0 !important;
            }
            .st-key-auto_spirit_below_confirm_6n36s5 > div[data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"]:has([data-testid="stCustomComponentV1"]) {
                display: none !important;
                height: 0 !important;
                min-height: 0 !important;
                max-height: 0 !important;
                margin: 0 !important;
                padding: 0 !important;
                overflow: hidden !important;
            }
            .st-key-auto_spirit_below_confirm_6n36s5 iframe {
                display: none !important;
                height: 0 !important;
                min-height: 0 !important;
                visibility: hidden !important;
            }
            .st-key-auto_spirit_below_confirm_6n36s5 [data-testid="stCustomComponentV1"],
            .st-key-auto_spirit_below_confirm_6n36s5 [data-testid="stCustomComponentV1"] > div,
            .st-key-auto_spirit_below_confirm_6n36s5 [data-testid="stCustomComponentV1"] iframe {
                display: none !important;
                height: 0 !important;
                min-height: 0 !important;
                max-height: 0 !important;
                margin: 0 !important;
                padding: 0 !important;
                overflow: hidden !important;
                visibility: hidden !important;
                pointer-events: none !important;
            }
            .st-key-auto_page_columns_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:nth-child(2) {
                display: none !important;
                width: 0 !important;
                max-width: 0 !important;
                flex: 0 0 0 !important;
                overflow: hidden !important;
                visibility: hidden !important;
                pointer-events: none !important;
            }
            .st-key-auto_page_columns_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] {
                position: relative !important;
                align-items: flex-start !important;
                display: block !important;
                min-height: 0 !important;
                height: auto !important;
            }
            .st-key-auto_page_columns_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:nth-child(1) {
                position: relative !important;
                z-index: 2 !important;
            }
            .st-key-auto_page_columns_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:nth-child(1) {
                padding-right: 0 !important;
                width: 100% !important;
                max-width: 100% !important;
                flex: 1 1 100% !important;
            }
            .st-key-auto_page_columns_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:nth-child(1) .st-key-auto_stats_section_6n36s5 {
                width: 100% !important;
                max-width: 100% !important;
            }
            .auto-stats-head-row .auto-table-title {
                font-size: 12px !important;
                padding: 7px 10px !important;
            }
            .auto-stats-head-row .auto-pattern-applied-note {
                font-size: 11px !important;
            }
            .auto-spirit2-slot-right {
                display: block !important;
                visibility: visible !important;
            }
            .st-key-auto_spirit_below_confirm_6n36s5 .auto-spirit2-slot-right {
                display: block !important;
                visibility: visible !important;
                height: auto !important;
                /* 작은 화면에서 화면 높이를 다 잡아먹지 않도록 폭 상한을 더 촘촘히 —
                   base/wave 두 레이어 모두 이 컨테이너의 width:100%를 따라가므로
                   여기서만 줄이면 두 레이어가 항상 같은 크기로 정렬 유지됨 */
                max-width: min(230px, 62vw) !important;
            }
            .auto-spirit2-slot-right .auto-spirit2-ripple-wave {
                animation: autoSpiritBodyWave 10s ease-in-out infinite !important;
            }
            .auto-spirit2-slot-right .auto-spirit2-img-wave {
                filter: url(#auto-spirit-ripple-mob) !important;
                -webkit-filter: url(#auto-spirit-ripple-mob) !important;
            }
            .auto-label-pill {
                font-size: 12px !important;
                padding: 6px 10px !important;
            }
            .st-key-auto_purchase_method_6n36s5 div[data-testid="stRadio"] > div,
            .st-key-auto_purchase_quantity_6n36s5 div[data-testid="stRadio"] > div {
                gap: 0.4rem !important;
            }
        }
        @media (min-width: 769px) {
            .st-key-auto_purchase_method_zone_6n36s5 > div[data-testid="stVerticalBlock"] {
                flex-wrap: nowrap !important;
            }
            .auto-spirit2-slot-right {
                display: none !important;
                visibility: hidden !important;
                height: 0 !important;
                overflow: hidden !important;
            }
            .st-key-auto_spirit_below_confirm_6n36s5 .auto-spirit2-slot-right {
                display: block !important;
                visibility: visible !important;
                height: auto !important;
                overflow: visible !important;
                max-width: min(360px, calc(100vw - 24px)) !important;
            }
            .auto-spirit2-slot-mobile {
                display: none !important;
                visibility: hidden !important;
                height: 0 !important;
                overflow: hidden !important;
                pointer-events: none !important;
            }
            .auto-spirit2-slot-desktop {
                display: block !important;
                visibility: visible !important;
                position: relative !important;
                width: 100% !important;
            }
            .auto-spirit2-slot-desktop .auto-spirit2-ripple-wave {
                animation: autoSpiritBodyWave 10s ease-in-out infinite !important;
                animation-play-state: running !important;
            }
            .auto-spirit2-slot-desktop .auto-spirit2-img-wave {
                filter: url(#auto-spirit-ripple-dsk) !important;
                -webkit-filter: url(#auto-spirit-ripple-dsk) !important;
            }
            .st-key-auto_spirit_below_confirm_6n36s5 {
                display: flex !important;
                flex-direction: column !important;
                align-items: center !important;
                justify-content: center !important;
                width: 100% !important;
                margin: 12px auto 0 !important;
                margin-bottom: 0 !important;
            }
            .st-key-auto_spirit_below_confirm_6n36s5 > div[data-testid="stVerticalBlock"] {
                gap: 0 !important;
            }
            .st-key-auto_spirit_below_confirm_6n36s5 [data-testid="stCustomComponentV1"],
            .st-key-auto_spirit_below_confirm_6n36s5 [data-testid="stCustomComponentV1"] > div,
            .st-key-auto_spirit_below_confirm_6n36s5 [data-testid="stCustomComponentV1"] iframe {
                display: block !important;
                visibility: visible !important;
                pointer-events: auto !important;
                width: 100% !important;
                max-width: 360px !important;
                height: 560px !important;
                min-height: 560px !important;
                max-height: none !important;
                margin-left: auto !important;
                margin-right: auto !important;
            }
            .st-key-auto_spirit_below_confirm_6n36s5 [data-testid="stElementContainer"]:has([data-testid="stCustomComponentV1"]) {
                height: auto !important;
                min-height: 0 !important;
                max-height: none !important;
                margin: 0 !important;
                padding: 0 !important;
                overflow: visible !important;
            }
            div[data-testid="stVerticalBlock"]:has(.st-key-auto_spirit_below_confirm_6n36s5) {
                overflow: visible !important;
            }
            .st-key-auto_purchase_history_zone_6n36s5 .auto-purchase-banner-history-grid .auto-banner-combo {
                flex-wrap: nowrap !important;
                padding: 3px 5px !important;
                gap: 5px !important;
            }
            .st-key-auto_purchase_history_zone_6n36s5 .auto-purchase-banner-history-grid .auto-banner-ball-row {
                flex-wrap: nowrap !important;
                gap: 3px !important;
            }
            .st-key-auto_purchase_history_zone_6n36s5 .auto-purchase-banner-history-grid .auto-banner-ball {
                width: 20px !important;
                height: 20px !important;
                min-width: 20px !important;
                font-size: 9px !important;
            }
            .st-key-auto_purchase_history_zone_6n36s5 .auto-purchase-banner-history-grid {
                width: fit-content !important;
                max-width: 100% !important;
                box-sizing: border-box !important;
            }
            .st-key-auto_page_columns_6n36s5 div[data-testid="stColumn"]:has(.st-key-auto_purchase_history_zone_6n36s5) {
                overflow: visible !important;
            }
            .st-key-auto_purchase_history_zone_6n36s5 {
                width: auto !important;
                max-width: none !important;
            }
            .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"],
            .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] details,
            .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] > div {
                width: auto !important;
                max-width: none !important;
                overflow: visible !important;
            }
        }
        div[data-testid="stTextInput"] input {
            background: linear-gradient(165deg, rgba(255,255,255,0.12), rgba(255,255,255,0.06)) !important;
            color: #f3e5f5 !important;
            border: 1px solid rgba(179, 157, 219, 0.42) !important;
            border-radius: 12px !important;
            box-shadow: inset 0 2px 6px rgba(0,0,0,0.28) !important;
        }
        .st-key-auto_phone_input_6n36s5 div[data-testid="stTextInput"] input {
            background: #ffffff !important;
            color: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
            caret-color: #000000 !important;
            border: 1px solid rgba(179, 157, 219, 0.55) !important;
            box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.12) !important;
        }
        .st-key-auto_phone_input_6n36s5 div[data-testid="stTextInput"] input::placeholder {
            color: #757575 !important;
            -webkit-text-fill-color: #757575 !important;
            opacity: 1 !important;
        }
        div[data-testid="stTextInput"] label p {
            color: #d1c4e9 !important;
            font-weight: 700 !important;
        }
        div[data-testid="stExpander"] {
            border: 1px solid rgba(179, 157, 219, 0.28) !important;
            border-radius: 12px !important;
            background: rgba(255,255,255,0.03) !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] summary,
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] summary p,
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] summary span,
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] summary svg {
            color: #000000 !important;
            fill: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] > details > summary {
            background: #ffffff !important;
            border-radius: 12px !important;
        }
        @keyframes autoHistoryBlink {
            0%, 100% {
                box-shadow: 0 0 0 0 rgba(206, 147, 216, 0);
                background: #ffffff !important;
            }
            50% {
                box-shadow: 0 0 0 5px rgba(206, 147, 216, 0.95), 0 0 22px rgba(186, 104, 200, 0.65);
                background: #f3e5f5 !important;
            }
        }
        @keyframes autoHistoryCardPulse {
            0%, 100% {
                transform: scale(1);
                border-color: rgba(171, 71, 188, 0.35) !important;
            }
            50% {
                transform: scale(1.015);
                border-color: rgba(171, 71, 188, 0.95) !important;
                box-shadow: 0 0 24px rgba(186, 104, 200, 0.45) !important;
            }
        }
        @keyframes autoHistoryChevronBounce {
            0%, 100% { transform: translateY(0); }
            40% { transform: translateY(3px); }
            60% { transform: translateY(-2px); }
        }
        .st-key-auto_purchase_history_zone_6n36s5:has(.auto-history-just-saved-marker) div[data-testid="stExpander"] {
            animation: autoHistoryCardPulse 0.95s ease-in-out 7 !important;
            border: 2px solid rgba(171, 71, 188, 0.75) !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5:has(.auto-history-just-saved-marker) div[data-testid="stExpander"] > details > summary {
            animation: autoHistoryBlink 0.95s ease-in-out 7 !important;
            font-weight: 900 !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5:has(.auto-history-just-saved-marker) div[data-testid="stExpander"] summary svg {
            animation: autoHistoryChevronBounce 0.95s ease-in-out 7 !important;
        }
        .auto-history-just-saved-marker {
            display: none !important;
            height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        .auto-stats-table-wrap {
            width: 100%;
            max-width: 100%;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
        }
        .auto-stats-table {
            width: 100%;
            min-width: 100%;
            table-layout: fixed;
            border-collapse: collapse;
            margin-top: 4px;
        }
        .auto-stats-table thead tr th {
            background-color: #90caf9 !important;
            color: #0d47a1 !important;
            font-weight: 800 !important;
            text-align: center !important;
            padding: 10px 4px !important;
            border: 1px solid #64b5f6 !important;
            font-size: 13px !important;
            word-break: keep-all;
        }
        .auto-stats-table tbody tr td {
            text-align: center !important;
            background-color: #ffffff !important;
            color: #1a1a1a !important;
            padding: 10px 4px !important;
            border: 1px solid #cfd8dc !important;
            font-size: 13px !important;
        }
        .auto-stats-table th:nth-child(1),
        .auto-stats-table td:nth-child(1) { width: 14%; }
        .auto-stats-table th:nth-child(2),
        .auto-stats-table td:nth-child(2) { width: 18%; }
        .auto-stats-table th:nth-child(n+3),
        .auto-stats-table td:nth-child(n+3) { width: 13.6%; }
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
        .auto-spirit2-wrap {
            position: relative;
            display: flex;
            align-items: flex-start;
            justify-content: center;
            width: 100%;
            padding: 0;
            margin: 0;
            overflow: hidden;
        }
        .auto-spirit2-ripple {
            position: relative;
            width: 100%;
        }
        .auto-spirit2-img {
            width: 100%;
            max-width: none;
            height: auto;
            display: block;
            border: none !important;
            outline: none !important;
            border-radius: 0;
            object-fit: contain;
            box-shadow: none !important;
        }
        .auto-spirit2-img-base {
            filter: none !important;
        }
        .auto-spirit2-body-mask {
            position: absolute;
            inset: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            overflow: hidden;
            /* 얼굴·목(중앙 상단)만 고정 — 나무·산·몸통 등 배경·주변은 물결 */
            -webkit-mask-image: radial-gradient(
                ellipse 17% 16% at 47% 37%,
                transparent 0%,
                transparent 70%,
                rgba(0, 0, 0, 0.35) 82%,
                black 92%
            );
            mask-image: radial-gradient(
                ellipse 17% 16% at 47% 37%,
                transparent 0%,
                transparent 70%,
                rgba(0, 0, 0, 0.35) 82%,
                black 92%
            );
        }
        .auto-spirit2-ripple-wave {
            width: 100%;
            transform-origin: 50% 42%;
            animation: autoSpiritBodyWave 10s ease-in-out infinite;
            animation-play-state: running;
            will-change: transform;
        }
        .auto-spirit2-img-wave {
            will-change: filter, transform;
        }
        .auto-spirit2-slot-desktop .auto-spirit2-wrap,
        .auto-spirit2-slot-mobile .auto-spirit2-wrap {
            transform: translateZ(0);
            backface-visibility: hidden;
        }
        @keyframes autoSpiritBodyWave {
            0%, 100% {
                transform: perspective(820px) rotateY(0deg) skewX(0deg) translateY(0);
            }
            50% {
                transform: perspective(820px) rotateY(1.6deg) skewX(-1.1deg) translateY(-3px);
            }
        }
        @media (prefers-reduced-motion: reduce) {
            .auto-spirit2-ripple-wave {
                animation: none !important;
            }
            .auto-spirit2-img-wave {
                filter: none !important;
            }
            .auto-spirit2-body-mask {
                display: none !important;
            }
        }
        /* 구매수량·전화번호·구매확정·구매내역 — 조합시작: 106×35px, r12, px10 */
        .auto-section-row .auto-label-pill,
        .st-key-auto_phone_input_6n36s5 div[data-testid="stTextInput"] input,
        .st-key-auto_purchase_confirm_6n36s5 div[data-testid="stButton"] > button,
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] > details > summary {
            box-sizing: border-box !important;
            width: 106px !important;
            min-width: 106px !important;
            max-width: 106px !important;
            height: 35px !important;
            min-height: 35px !important;
            max-height: 35px !important;
            padding: 0 10px !important;
            border-radius: 12px !important;
            border: none !important;
            font-family: "Noto Sans KR", sans-serif !important;
            font-weight: 900 !important;
            font-size: 15px !important;
            line-height: 1.25 !important;
            -webkit-font-smoothing: antialiased !important;
            text-rendering: optimizeLegibility !important;
            transform: translateZ(0);
            position: relative !important;
            z-index: 12 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }
        /* 구매 방식 select — 구매확정/구매내역과 동일 106×35로 통일 */
        .st-key-auto_purchase_method_6n36s5 div[data-testid="stSelectbox"],
        .st-key-auto_purchase_method_6n36s5 div[data-testid="stSelectbox"] > div,
        .st-key-auto_purchase_method_6n36s5 div[data-baseweb="select"] > div {
            box-sizing: border-box !important;
            width: 106px !important;
            min-width: 106px !important;
            max-width: 106px !important;
            height: 35px !important;
            min-height: 35px !important;
            max-height: 35px !important;
            padding: 0 10px !important;
            border-radius: 12px !important;
            border: none !important;
            font-family: "Noto Sans KR", sans-serif !important;
            font-weight: 900 !important;
            font-size: 15px !important;
            line-height: 1.25 !important;
            -webkit-font-smoothing: antialiased !important;
            text-rendering: optimizeLegibility !important;
            transform: translateZ(0);
            position: relative !important;
            z-index: 12 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }
        .st-key-auto_phone_input_6n36s5 {
            margin-bottom: 7px !important;
        }
        .st-key-auto_phone_input_6n36s5 div[data-testid="stTextInput"] {
            width: 159px !important;
            min-width: 159px !important;
            max-width: 159px !important;
        }
        .st-key-auto_phone_input_6n36s5 div[data-testid="stTextInput"] input {
            width: 100% !important;
            min-width: 0 !important;
            max-width: 100% !important;
        }
        .st-key-auto_purchase_confirm_6n36s5 div[data-testid="stButton"] {
            width: 106px !important;
            min-width: 106px !important;
            max-width: 106px !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] {
            width: 106px !important;
            min-width: 106px !important;
            max-width: 106px !important;
        }
        .st-key-auto_purchase_method_6n36s5 div[data-testid="stSelectbox"] {
            width: 106px !important;
            min-width: 106px !important;
            max-width: 106px !important;
            margin: 0 !important;
        }
        .st-key-auto_purchase_method_6n36s5 div[data-testid="stSelectbox"] label {
            display: none !important;
        }
        .st-key-auto_purchase_method_6n36s5 div[data-baseweb="select"] {
            width: 100% !important;
            background: transparent !important;
        }
        .st-key-auto_purchase_method_6n36s5 div[data-baseweb="select"] > div {
            width: 100% !important;
            min-width: 0 !important;
            max-width: 100% !important;
            padding: 0 8px 0 10px !important;
            background: linear-gradient(180deg, #22d3ee 0%, #06B6D4 55%, #0891b2 100%) !important;
            color: #FFFFFF !important;
            box-shadow:
                0 4px 0 #0e7490,
                0 7px 14px rgba(6, 182, 212, 0.4),
                inset 0 1px 0 rgba(255, 255, 255, 0.3) !important;
            border: none !important;
            cursor: pointer !important;
        }
        .st-key-auto_purchase_method_6n36s5 div[data-baseweb="select"] span,
        .st-key-auto_purchase_method_6n36s5 div[data-baseweb="select"] svg {
            color: #FFFFFF !important;
            fill: #FFFFFF !important;
        }
        .st-key-auto_purchase_method_6n36s5 div[data-baseweb="select"] span {
            font-weight: 900 !important;
            font-size: 15px !important;
            line-height: 1.25 !important;
        }
        /* 닫힌 버튼에는 선택값 대신 「구매방식」 표시 */
        .st-key-auto_purchase_method_6n36s5 div[data-baseweb="select"] > div > div:first-of-type {
            flex: 0 0 0 !important;
            width: 0 !important;
            min-width: 0 !important;
            max-width: 0 !important;
            overflow: hidden !important;
            opacity: 0 !important;
            pointer-events: none !important;
        }
        .st-key-auto_purchase_method_6n36s5 div[data-baseweb="select"] > div::before {
            content: "구매방식" !important;
            flex: 1 1 auto !important;
            text-align: center !important;
            font-family: "Noto Sans KR", sans-serif !important;
            font-weight: 900 !important;
            font-size: 15px !important;
            line-height: 1.25 !important;
            color: #FFFFFF !important;
            -webkit-text-fill-color: #FFFFFF !important;
        }
        /* 구매 수량 select — 구매확정/구매내역과 동일 106×35로 통일 */
        .st-key-auto_purchase_quantity_6n36s5 div[data-testid="stSelectbox"],
        .st-key-auto_purchase_quantity_6n36s5 div[data-testid="stSelectbox"] > div,
        .st-key-auto_purchase_quantity_6n36s5 div[data-baseweb="select"] > div {
            box-sizing: border-box !important;
            width: 106px !important;
            min-width: 106px !important;
            max-width: 106px !important;
            height: 35px !important;
            min-height: 35px !important;
            max-height: 35px !important;
            padding: 0 10px !important;
            border-radius: 12px !important;
            border: none !important;
            font-family: "Noto Sans KR", sans-serif !important;
            font-weight: 900 !important;
            font-size: 15px !important;
            line-height: 1.25 !important;
            -webkit-font-smoothing: antialiased !important;
            text-rendering: optimizeLegibility !important;
            transform: translateZ(0);
            position: relative !important;
            z-index: 12 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }
        .st-key-auto_purchase_quantity_6n36s5 div[data-testid="stSelectbox"] {
            width: 106px !important;
            min-width: 106px !important;
            max-width: 106px !important;
            margin: 0 !important;
        }
        .st-key-auto_purchase_quantity_6n36s5 div[data-testid="stSelectbox"] label {
            display: none !important;
        }
        .st-key-auto_purchase_quantity_6n36s5 div[data-baseweb="select"] {
            width: 100% !important;
            background: transparent !important;
        }
        .st-key-auto_purchase_quantity_6n36s5 div[data-baseweb="select"] > div {
            width: 100% !important;
            min-width: 0 !important;
            max-width: 100% !important;
            padding: 0 8px 0 10px !important;
            background: linear-gradient(180deg, #22d3ee 0%, #06B6D4 55%, #0891b2 100%) !important;
            color: #FFFFFF !important;
            box-shadow:
                0 4px 0 #0e7490,
                0 7px 14px rgba(6, 182, 212, 0.4),
                inset 0 1px 0 rgba(255, 255, 255, 0.3) !important;
            border: none !important;
            cursor: pointer !important;
        }
        .st-key-auto_purchase_quantity_6n36s5 div[data-baseweb="select"] span,
        .st-key-auto_purchase_quantity_6n36s5 div[data-baseweb="select"] svg {
            color: #FFFFFF !important;
            fill: #FFFFFF !important;
        }
        .st-key-auto_purchase_quantity_6n36s5 div[data-baseweb="select"] span {
            font-weight: 900 !important;
            font-size: 15px !important;
            line-height: 1.25 !important;
        }
        .st-key-auto_purchase_quantity_6n36s5 div[data-baseweb="select"] > div > div:first-of-type {
            flex: 0 0 0 !important;
            width: 0 !important;
            min-width: 0 !important;
            max-width: 0 !important;
            overflow: hidden !important;
            opacity: 0 !important;
            pointer-events: none !important;
        }
        .st-key-auto_purchase_quantity_6n36s5 div[data-baseweb="select"] > div::before {
            content: "구매 수량" !important;
            flex: 1 1 auto !important;
            text-align: center !important;
            font-family: "Noto Sans KR", sans-serif !important;
            font-weight: 900 !important;
            font-size: 15px !important;
            line-height: 1.25 !important;
            color: #FFFFFF !important;
            -webkit-text-fill-color: #FFFFFF !important;
        }
        .auto-section-row .auto-label-pill {
            margin: 0 !important;
            background: linear-gradient(180deg, #22d3ee 0%, #06B6D4 55%, #0891b2 100%) !important;
            color: #FFFFFF !important;
            box-shadow:
                0 4px 0 #0e7490,
                0 7px 14px rgba(6, 182, 212, 0.4),
                inset 0 1px 0 rgba(255, 255, 255, 0.3) !important;
        }
        .st-key-auto_phone_input_6n36s5 div[data-testid="stTextInput"] input {
            background: linear-gradient(180deg, #ffffff 0%, #e2e8f0 100%) !important;
            color: #0F172A !important;
            -webkit-text-fill-color: #0F172A !important;
            caret-color: #0F172A !important;
            width: 100% !important;
            min-width: 0 !important;
            max-width: 100% !important;
            box-shadow:
                0 4px 0 #0e7490,
                0 7px 14px rgba(6, 182, 212, 0.4),
                inset 0 1px 0 rgba(255, 255, 255, 0.3) !important;
        }
        .st-key-auto_purchase_confirm_6n36s5 div[data-testid="stButton"] > button {
            width: 106px !important;
            min-width: 106px !important;
            max-width: 106px !important;
            background: linear-gradient(180deg, #22d3ee 0%, #06B6D4 55%, #0891b2 100%) !important;
            color: #FFFFFF !important;
            box-shadow:
                0 4px 0 #0e7490,
                0 7px 14px rgba(6, 182, 212, 0.4),
                inset 0 1px 0 rgba(255, 255, 255, 0.3) !important;
            transition: transform 0.12s ease, box-shadow 0.12s ease !important;
        }
        .st-key-auto_purchase_confirm_6n36s5 div[data-testid="stButton"] > button:hover {
            box-shadow:
                0 5px 0 #0e7490,
                0 9px 18px rgba(6, 182, 212, 0.45),
                inset 0 1px 0 rgba(255, 255, 255, 0.35) !important;
        }
        .st-key-auto_purchase_confirm_6n36s5 div[data-testid="stButton"] > button:active {
            transform: scale(0.97) !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] > details > summary {
            background: linear-gradient(180deg, #22d3ee 0%, #06B6D4 55%, #0891b2 100%) !important;
            color: #FFFFFF !important;
            box-shadow:
                0 4px 0 #0e7490,
                0 7px 14px rgba(6, 182, 212, 0.4),
                inset 0 1px 0 rgba(255, 255, 255, 0.3) !important;
            transition: transform 0.12s ease, box-shadow 0.12s ease !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] > details > summary:active {
            transform: scale(0.97) !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] summary p,
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] summary span {
            color: #FFFFFF !important;
            -webkit-text-fill-color: #FFFFFF !important;
            font-size: 15px !important;
            font-weight: 900 !important;
            position: relative !important;
            z-index: 13 !important;
            margin: 0 !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] summary svg {
            display: none !important;
        }
    </style>
        """,
        unsafe_allow_html=True,
    )

    icon_base64 = _get_icon_base64()
    col_back, _ = st.columns([3, 7])
    with col_back:
        icon_html = (
            f'<img class="auto-back-main-icon" src="data:image/jpeg;base64,{icon_base64}" alt="로또신령">'
            if icon_base64
            else "🏠"
        )
        st.markdown(
            f'<a href="?" target="_self" class="auto-back-main-btn">{icon_html}<span>메인으로</span></a>',
            unsafe_allow_html=True,
        )

    st.markdown('<div class="auto-page-wrap">', unsafe_allow_html=True)

    spirit2_base64 = _get_icon_base64("로또신령2.jpg")

    with st.container(key="auto_page_columns_6n36s5"):
        col_form, col_visual = st.columns([0.55, 0.45], gap="small")

        with col_form:
            # ── 1. 구매 방식 + 구매 수량 (나란히) + 월간구독 요일 ──
            with st.container(key="auto_purchase_method_zone_6n36s5"):
                col_method, col_qty = st.columns(2, gap="small")
                with col_method:
                    with st.container(key="auto_method_left_6n36s5"):
                        purchase_method = st.selectbox(
                            "구매 방식",
                            ["즉시", "월간구독"],
                            label_visibility="collapsed",
                            key="auto_purchase_method_6n36s5",
                        )
                    is_monthly = purchase_method == "월간구독"
                    selected_days = []
                    if is_monthly:
                        with st.container(key="auto_sms_days_6n36s5"):
                            day_cols = st.columns(len(SUBSCRIPTION_WEEKDAYS), gap="small")
                            for idx, day in enumerate(SUBSCRIPTION_WEEKDAYS):
                                with day_cols[idx]:
                                    if st.checkbox(
                                        day,
                                        key=f"auto_sms_day_{day}_6n36s5",
                                    ):
                                        selected_days.append(day)
                        st.markdown(
                            """
                            <style>
                            .st-key-auto_purchase_method_zone_6n36s5 .st-key-auto_sms_days_6n36s5 {
                                margin-top: 6px !important;
                                width: 106px !important;
                                max-width: 106px !important;
                            }
                            </style>
                            """,
                            unsafe_allow_html=True,
                        )
                with col_qty:
                    with st.container(key="auto_quantity_zone_6n36s5"):
                        quantity_label = st.selectbox(
                            "구매 수량",
                            ["5개", "10개"],
                            label_visibility="collapsed",
                            key="auto_purchase_quantity_6n36s5",
                        )
            st.session_state["auto_sms_days"] = selected_days if is_monthly else []
            selected_quantity = int(str(quantity_label).replace("개", ""))

            with st.container(key="auto_form_lower_6n36s5"):
                # ── 3. 구매 안내 Expander ──
                with st.expander("⚠️ 구매 안\u200b내 및 유의사항 (필독)"):
                    st.markdown(
                        """
• **수신 번호 확인:** 본 서비스는 회원정보에 등록된 연락처로 문자가 발송됩니다. 발송 전 번호를 반드시 확인해 주세요.

• **자동 결제 안내:** 월간구독은 신청일 기준 30일마다 자동 결제되며, 마이페이지에서 언제든지 해지하실 수 있습니다.

• **환불 규정:** 로또 번호 추출 및 SMS 발송 서비스가 시작된 이후에는 디지털 콘텐츠 특성상 중도 청약철회 및 환불이 불가능합니다.

• **당첨 면책 조항:** 본 조합 서비스는 당첨을 100% 보장하지 않으며, 실제 로또 결과에 대한 어떠한 법적 책임도 지지 않습니다.
                        """
                    )

                phone = st.text_input(
                    "수신 번호 (문자 발송용)",
                    placeholder="01012345678",
                    key="auto_phone_input_6n36s5",
                )

                from auto_purchase_service import (
                    NEXT_DRAW_POOL_BANNER,
                    NextDrawPoolNotReadyError,
                    check_next_draw_pool_ready,
                )

                next_pool = check_next_draw_pool_ready()
                if not next_pool["ok"]:
                    st.markdown(
                        f'<div class="auto-next-draw-pool-banner">{NEXT_DRAW_POOL_BANNER}</div>',
                        unsafe_allow_html=True,
                    )

                confirm_history_row = st.container(key="auto_confirm_history_row_6n36s5")
                with confirm_history_row:
                    col_confirm, col_history = st.columns(2, gap="small")
                with col_confirm:
                    if st.button(
                        "구매 확정",
                        type="primary",
                        use_container_width=True,
                        key="auto_purchase_confirm_6n36s5",
                    ):
                        if not _is_auto_deploy_window_open():
                            st.markdown(
                                f'<div class="auto-next-draw-pool-banner">{AUTO_DEPLOY_WINDOW_BANNER}</div>',
                                unsafe_allow_html=True,
                            )
                        elif not next_pool["ok"]:
                            st.error(NEXT_DRAW_POOL_BANNER)
                        elif AUTO_PURCHASE_SKIP_AUTH:
                            from marketing_db import InsufficientCombinationsError

                            try:
                                entry = _build_quick_purchase_entry(
                                    selected_quantity,
                                    purchase_method,
                                    st.session_state.get("auto_sms_days", []),
                                )
                            except NextDrawPoolNotReadyError:
                                st.error(NEXT_DRAW_POOL_BANNER)
                            except InsufficientCombinationsError as exc:
                                st.error(
                                    f"{exc.draw_round}회차 저장 조합이 부족합니다. "
                                    f"(요청 {exc.requested}개 / 가용 {exc.available}개)"
                                )
                            else:
                                _append_purchase_history(entry)
                                st.session_state["auto_history_blink"] = True
                                st.rerun()
                        else:
                            from wallet_ui import ensure_member_or_banner

                            if ensure_member_or_banner(
                                resume="auto_show_points",
                                reason="구매 확정을 위해 간편인증이 필요합니다.",
                            ):
                                st.session_state["auto_show_points"] = True

                with col_history:
                    history_blink = bool(st.session_state.pop("auto_history_blink", False))
                    history_expander_label = "구매내역"
                    with st.container(key="auto_purchase_history_zone_6n36s5"):
                        if history_blink:
                            st.markdown(
                                '<div class="auto-history-just-saved-marker" aria-hidden="true"></div>',
                                unsafe_allow_html=True,
                            )
                        with st.expander(
                            history_expander_label,
                            expanded=history_blink,
                        ):
                            from auth_providers import current_member_id

                            mid = current_member_id()
                            history_items = _collect_purchase_history_items(mid)
                            if not history_items:
                                st.caption(
                                    "아직 구매 내역이 없습니다. 구매 확정 후 이곳에 저장됩니다."
                                )
                            else:
                                for item in history_items:
                                    st.markdown(
                                        _purchase_banner_html(item, compact=True),
                                        unsafe_allow_html=True,
                                    )

                with st.container(key="auto_spirit_below_confirm_6n36s5"):
                    if spirit2_base64:
                        st.markdown(
                            _spirit2_image_block(
                                spirit2_base64,
                                "auto-spirit2-slot-right",
                                "auto-spirit-ripple-mob",
                            ),
                            unsafe_allow_html=True,
                        )

                # ── 4. 회차별 당첨번호 배출 표 (아이콘 바로 아래) ──
                stats_df, is_mock = _load_stats_table_cached(_admin_combo_save_mtime())
                if not stats_df.empty:
                    stats_df = stats_df[~stats_df["회차"].isin([1233, 1])]
                with st.container(key="auto_stats_section_6n36s5"):
                    pattern_count = _pattern_applied_count()
                    st.markdown(
                        f"""
                        <div class="auto-stats-head-row">
                            <div class="auto-table-title">회차별 당\u200b첨번호 배출</div>
                            <div class="auto-pattern-applied-note">당 회차 필터링에 {pattern_count:,}개의 패턴이 적용되었습니다</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    if is_mock:
                        st.caption("현재 DB에 등록된 회차 데이터가 없어 테스트용 샘플을 표시합니다.")
                    table_html = stats_df.to_html(index=False, border=0, classes="auto-stats-table")
                    st.markdown(
                        f'<div class="auto-stats-table-wrap">{table_html}</div>',
                        unsafe_allow_html=True,
                    )

                if not AUTO_PURCHASE_SKIP_AUTH and st.session_state.get("auto_show_points"):
                    from wallet_ui import points_notice_dialog
                    from auth_providers import current_member_id
                    from auto_purchase_service import process_auto_purchase

                    result = points_notice_dialog("auto", quantity=selected_quantity)
                    if result == "confirm":
                        st.session_state["auto_show_points"] = False
                        if not _is_auto_deploy_window_open():
                            st.markdown(
                                f'<div class="auto-next-draw-pool-banner">{AUTO_DEPLOY_WINDOW_BANNER}</div>',
                                unsafe_allow_html=True,
                            )
                        elif not phone.strip():
                            st.error("수신 번호를 입력해 주세요.")
                        else:
                            mid = current_member_id()
                            if mid:
                                outcome = process_auto_purchase(
                                    mid,
                                    selected_quantity,
                                    purchase_method,
                                    phone,
                                    st.session_state.get("auto_sms_days", []),
                                )
                                if outcome.get("ok"):
                                    entry = _purchase_history_entry(
                                        outcome,
                                        purchase_method,
                                        st.session_state.get("auto_sms_days", []),
                                    )
                                    _append_purchase_history(entry)
                                    st.session_state["auto_history_blink"] = True
                                    st.rerun()
                                elif outcome.get("error") == "insufficient_balance":
                                    st.error("적립금이 부족합니다.")
                                elif outcome.get("error") == "next_draw_pool_missing":
                                    st.error(outcome.get("message") or NEXT_DRAW_POOL_BANNER)
                                else:
                                    st.error("구매 처리에 실패했습니다.")
                    elif result == "cancel":
                        st.session_state["auto_show_points"] = False

        with col_visual:
            pass

    # ── 최종 레이아웃 강제 오버라이드 ──
    # Streamlit이 stVerticalBlock/stHorizontalBlock 사이에 stLayoutWrapper를 끼워 넣는
    # 버전으로 올라가면서, 위쪽에 있는 동일 내용의 CSS가 소스 순서상 밀려 적용되지 않는
    # 문제가 있었다. 페이지 렌더링 맨 마지막에 한 번 더(동일 규칙을) 주입해서
    # 캐스케이드 순서상 항상 이기도록 한다.
    st.markdown(
        """
        <style>
        .st-key-auto_purchase_method_zone_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] {
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            align-items: flex-start !important;
            gap: 6px !important;
            width: 100% !important;
        }
        .st-key-auto_purchase_method_zone_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
            flex: 0 0 auto !important;
            width: auto !important;
            min-width: 0 !important;
        }
        .st-key-auto_purchase_method_zone_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] * {
            flex-shrink: 0 !important;
        }
        .st-key-auto_page_columns_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] {
            display: flex !important;
        }
        /* 왼쪽 쏠림 없이 양 끝으로 균형 배치 */
        .st-key-auto_purchase_method_zone_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] {
            justify-content: space-between !important;
        }
        .st-key-auto_confirm_history_row_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] {
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            justify-content: space-between !important;
            align-items: center !important;
            width: 100% !important;
        }
        .st-key-auto_confirm_history_row_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:nth-child(1) {
            flex: 0 0 auto !important;
            width: 106px !important;
            max-width: 106px !important;
            min-width: 0 !important;
        }
        .st-key-auto_confirm_history_row_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:nth-child(2) {
            flex: 0 0 auto !important;
            width: 106px !important;
            max-width: 106px !important;
            min-width: 0 !important;
        }
        .st-key-auto_purchase_confirm_6n36s5 div[data-testid="stButton"],
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] {
            width: 106px !important;
            min-width: 106px !important;
            max-width: 106px !important;
        }
        /* 캐릭터 이미지는 항상 "구매내역" 팝업(z-index:40) 뒤에 있도록 낮은 z-index 고정 */
        .st-key-auto_spirit_below_confirm_6n36s5 {
            position: relative !important;
            z-index: 1 !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5 {
            position: relative !important;
            z-index: 41 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("</div>", unsafe_allow_html=True)
