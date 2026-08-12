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


def _spirit2_image_block(base64: str, slot_class: str) -> str:
    """정적 원형 크롭 이미지 (물결 애니메이션은 추후 원형 비율에 맞게 재조정해서 복원 예정)."""
    return f"""
    <div class="{slot_class}">
      <div class="auto-spirit2-wrap">
        <div class="auto-spirit2-ripple">
          <img class="auto-spirit2-img auto-spirit2-img-base"
               src="data:image/jpeg;base64,{base64}"
               alt="로또신령2">
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


def _admin_combo_save_mtime() -> float:
    try:
        return os.path.getmtime(ADMIN_COMBO_SAVE_FILE)
    except OSError:
        return 0.0


def _load_stats_table() -> tuple[pd.DataFrame, bool]:
    """실제 DB(lotto_combinations)에 저장된 회차만 표시 — 로컬 재업로드 파일은 미리보기일 뿐
    실제 추출 결과가 아니므로 반영하지 않는다."""
    mdb = _marketing_db()
    mdb.init_marketing_tables()
    mdb.ensure_marketing_pool_seeds()
    _sync_completed_draw_win_ranks()
    stats = mdb.get_draw_extraction_stats(limit=20)
    if stats:
        return _stats_to_dataframe(stats, False), False
    return _stats_to_dataframe(mdb.get_mock_draw_extraction_stats(), True), True


@st.cache_data(ttl=120, show_spinner=False)
def _load_stats_table_cached(_admin_combo_csv_mtime: float) -> tuple[pd.DataFrame, bool]:
    return _load_stats_table()


def _saved_filters_mtime() -> float:
    try:
        return os.path.getmtime("saved_filters.pkl")
    except OSError:
        return 0.0


@st.cache_data(ttl=120, show_spinner=False)
def _load_pattern_count_from_n5(_saved_filters_pkl_mtime: float) -> int | None:
    """관리자 3종필터(saved_filters.pkl) — 기본·절대·이격수 활성 규칙 합계.

    이 파일이 350KB 정도라 매 렌더마다(버튼 클릭 하나하나마다) unpickle +
    검증을 다시 하면 약 1.9초가 걸렸다 — _load_stats_table_cached와 동일하게
    파일 mtime을 키로 캐싱해서, 파일이 실제로 바뀌었을 때만 다시 계산한다.
    """
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
    count = _load_pattern_count_from_n5(_saved_filters_mtime())
    return int(count) if count is not None else 0


@st.cache_data(show_spinner=False)
def _winning_numbers_for_draw_cached(draw_round: int, _mtime: float) -> tuple[set[int], int | None]:
    try:
        from lotto_stats import get_draw_result_by_round

        result = get_draw_result_by_round(int(draw_round))
    except Exception:
        return set(), None
    if not result:
        return set(), None
    return set(int(n) for n in result.get("numbers", [])), result.get("bonus")


def _winning_numbers_for_draw(draw_round) -> tuple[set[int], int | None]:
    """해당 회차 당첨번호가 확정돼 있으면 반환 — 구매내역에서 저장된 번호와
    자동으로 대조해 맞은 번호에 동그라미를 표시하기 위함. 아직 추첨 전이면
    빈 집합을 반환한다(그래도 화면이 자연스럽게 "미확정" 상태로 보인다).

    구매내역엔 회차별로 여러 건이 쌓일 수 있어서, 캐싱 없이는 같은 회차를
    항목 수만큼(내부적으로 매번 엑셀 데이터프레임을 훑으며) 반복 조회하게 된다
    — load_lotto_data 자체는 이미 파일 mtime 기준으로 캐싱돼 있지만, 그 안에서
    회차를 찾는 순회 자체는 캐싱되지 않았었다. mtime을 키에 포함해 admin이 파일을
    갱신하면 바로 무효화되면서도, 평소엔 회차당 한 번만 계산하도록 캐싱한다."""
    from lotto_stats import _xlsb_mtime, lotto_data_path

    path = lotto_data_path()
    return _winning_numbers_for_draw_cached(int(draw_round), _xlsb_mtime(path))


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

    # 당첨번호가 확정된 회차면, 저장해둔 숫자를 일일이 눈으로 대조하지 않아도
    # 되도록 맞은 번호에 자동으로 동그라미(테두리 강조)를 표시한다.
    win_set, bonus_number = _winning_numbers_for_draw(draw_round) if draw_round != "" else (set(), None)

    def _ball_span(n: int) -> str:
        # 색칠된 볼 대신 순수 숫자 텍스트로 표시 — 당첨번호 대조 시 선명하게 보이도록.
        # 맞은 번호만 테두리(동그라미)로 표시한다(배경색 없이 숫자 자체는 그대로 텍스트).
        if n in win_set:
            hit_cls = " auto-banner-ball-hit"
        elif bonus_number is not None and n == int(bonus_number):
            hit_cls = " auto-banner-ball-bonus"
        else:
            hit_cls = ""
        return f'<span class="auto-banner-ball{hit_cls}">{n:02d}</span>'

    combo_rows = ""
    for item in allocated:
        combo = item.get("combo") or []
        balls = "".join(_ball_span(n) for n in combo)
        combo_rows += f'<div class="auto-banner-combo"><div class="auto-banner-ball-row">{balls}</div></div>'

    if compact:
        grid_rows = ""
        for item in allocated[:5]:
            combo = (item.get("combo") or [])[:6]
            balls = "".join(_ball_span(n) for n in combo)
            grid_rows += f'<div class="auto-banner-combo"><div class="auto-banner-ball-row">{balls}</div></div>'
        compact_legend = (
            '<p class="auto-banner-legend">🟡 당첨번호 일치</p>' if win_set else ""
        )
        return (
            '<div class="auto-purchase-banner auto-purchase-banner-compact auto-purchase-banner-history-grid">'
            f'<div class="auto-banner-combos">{grid_rows}</div>'
            f"{compact_legend}"
            "</div>"
        )

    notice_extra = (
        '<p class="auto-banner-legend">🟡 당첨번호 일치 · ⚪ 보너스 번호 일치</p>' if win_set else ""
    )
    notice = (
        ""
        if compact
        else (
            '<p class="auto-banner-notice">'
            "현재 테스트 기간으로 문자 발송 대신 화면에서 결과를 확인하실 수 있습니다."
            "</p>"
            f"{notice_extra}"
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


MAX_HISTORY_ROUNDS = 2  # 구매내역에는 최근 이 회차 수만큼만 남긴다


def _limit_to_recent_rounds(items: list[dict], max_rounds: int = MAX_HISTORY_ROUNDS) -> list[dict]:
    """최근 N개 회차분만 남기고 그보다 오래된 회차는 잘라낸다.

    items는 이미 최신순으로 정렬돼 있다고 가정한다. 무한정 쌓이는 걸 막아서
    사용자가 오래된 내역까지 뒤적이며 헷갈리는 일도 없애고, 저장 공간도 아낀다.
    """
    seen_rounds: list = []
    result = []
    for item in items:
        dr = item.get("draw_round")
        if dr not in seen_rounds:
            if len(seen_rounds) >= max_rounds:
                continue
            seen_rounds.append(dr)
        result.append(item)
    return result


def _append_purchase_history(entry: dict) -> None:
    from user_scope import session_key

    hist_key = session_key("auto_purchase_history")
    history = list(st.session_state.get(hist_key) or [])
    order_id = entry.get("order_id")
    if order_id is not None:
        history = [item for item in history if item.get("order_id") != order_id]
    history.insert(0, entry)
    st.session_state[hist_key] = _limit_to_recent_rounds(history)


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
    """세션 + DB 구매 내역 (order_id 기준 중복 제거, 최신순, 최근 2개 회차만)."""
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
        db_orders = [
            order
            for order in list_completed_auto_orders(member_id, limit=20)
            if int(order["id"]) not in seen_order_ids
        ]
        # 어차피 최근 2개 회차분만 남길 거라, 그 안에 들지 못할 주문의 조합까지
        # DB에서 미리 조회할 필요는 없다 — 대상 회차를 먼저 정하고, 그 안에 드는
        # 주문에 대해서만 get_combinations_by_auto_order_id를 호출한다.
        candidate_rounds = [item.get("draw_round") for item in items]
        candidate_rounds += [order.get("draw_round") for order in db_orders]
        kept_rounds: list = []
        for dr in candidate_rounds:
            if dr not in kept_rounds:
                if len(kept_rounds) >= MAX_HISTORY_ROUNDS:
                    continue
                kept_rounds.append(dr)

        for order in db_orders:
            if order.get("draw_round") not in kept_rounds:
                continue
            order_id = int(order["id"])
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

    return _limit_to_recent_rounds(items)


def render():
    from user_scope import init_guest_scope

    init_guest_scope()

    st.markdown(
        """
    <style>
        .stApp { background-color: #12182b; color: white; }
        html, body, #root, .stApp, [data-testid="stAppViewContainer"],
        [data-testid="stAppViewContainer"] > section.main {
            overflow-x: hidden !important;
            overflow-y: auto !important;
            height: auto !important;
            min-height: 100% !important;
            max-height: none !important;
        }
        section.main > div.block-container {
            overflow: visible !important;
            height: auto !important;
            max-height: none !important;
        }
        .block-container { padding: 10px !important; padding-bottom: 96px !important; max-width: 600px; }
        section[data-testid="stSidebar"], header[data-testid="stHeader"] { display: none; }
        .st-key-auto_page_wrap_6n36s5 {
            width: 100% !important;
            max-width: 600px !important;
            margin: 0 auto !important;
            overflow: visible !important;
            /* 캐릭터 이미지 영역과 그 위 버튼/드롭다운 행이 공통으로 참조하는 단일 폭 기준.
               이미지 모양(사각형→원형 등)이 바뀌어도 여기 값만 조정하면 버튼 위치가 자동으로
               같이 따라오고, 이미지 내부 스타일만 바뀌는 경우엔 버튼은 전혀 영향받지 않는다. */
            --auto-visual-col-width: min(360px, calc(100vw - 24px));
        }
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
            z-index: auto !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"],
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] details {
            overflow: visible !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] {
            position: relative !important;
            z-index: 40 !important;
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
        .st-key-auto_purchase_history_zone_6n36s5 .auto-purchase-banner-history-grid .auto-banner-ball-row {
            display: flex !important;
            flex-wrap: nowrap !important;
            flex: 0 0 auto !important;
            gap: 6px !important;
            min-width: 0 !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5 .auto-purchase-banner-history-grid .auto-banner-ball {
            flex: 0 0 auto !important;
            width: auto !important;
            min-width: 16px !important;
            height: auto !important;
            font-size: 11px !important;
            padding: 0 !important;
        }
        @keyframes autoToastFade {
            0% { opacity: 0; transform: translate(-50%, -6px); }
            8% { opacity: 1; transform: translate(-50%, 0); }
            85% { opacity: 1; transform: translate(-50%, 0); }
            100% { opacity: 0; transform: translate(-50%, -6px); }
        }
        .auto-next-draw-pool-banner {
            position: absolute;
            top: calc(100% + 10px);
            left: 50%;
            z-index: 45;
            width: max-content;
            max-width: min(90vw, 380px);
            margin: 0;
            padding: 13px 20px;
            border-radius: 14px;
            border: 1px solid rgba(255, 193, 7, 0.4);
            background: rgba(24, 17, 9, 0.88);
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
            color: #ffe082;
            font-size: 14px;
            font-weight: 700;
            line-height: 1.5;
            text-align: center;
            pointer-events: none;
            animation: autoToastFade 4s ease forwards;
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
        .auto-history-round-head {
            margin: 14px 0 6px;
            padding-bottom: 4px;
            color: #ce93d8;
            font-weight: 800;
            font-size: 13px;
            border-bottom: 1px solid rgba(206, 147, 216, 0.3);
        }
        .auto-history-round-head:first-child {
            margin-top: 2px;
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
        .auto-banner-ball-row {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }
        /* 색칠된 볼 대신 순수 숫자 텍스트 — 당첨번호와 대조할 때 눈에 더 선명하게
           들어오도록 배경/그림자를 뺐다. */
        .auto-banner-ball {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 22px;
            height: 22px;
            padding: 0 2px;
            color: #f1e9ff;
            font-weight: 800;
            font-size: 13px;
            font-variant-numeric: tabular-nums;
        }
        /* 당첨번호가 확정되면 맞은 번호만 동그라미(테두리)로 감싸서, 일일이 손으로
           대조하지 않아도 한눈에 보이게 한다 — 실제 종이 로또에 펜으로 동그라미
           치는 느낌으로, 배경을 채우지 않고 테두리만 그린다. */
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
        .auto-banner-legend {
            margin: 6px 0 0;
            color: #cfd8dc;
            font-size: 11px;
            font-weight: 600;
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
            overflow: visible !important;
        }
        .st-key-auto_form_lower_6n36s5 > div[data-testid="stVerticalBlock"] {
            gap: 0.35rem !important;
            overflow: visible !important;
        }
        .st-key-auto_confirm_history_row_6n36s5,
        .st-key-auto_confirm_history_row_6n36s5 > div[data-testid="stVerticalBlock"],
        .st-key-auto_confirm_history_row_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] {
            overflow: visible !important;
            height: auto !important;
            min-height: 0 !important;
            max-height: none !important;
        }
        .st-key-auto_confirm_history_row_6n36s5 {
            position: relative !important;
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
            overflow: visible !important;
            position: relative !important;
            z-index: 2 !important;
        }
        .st-key-auto_page_columns_6n36s5 > div[data-testid="stVerticalBlock"] {
            overflow: visible !important;
        }
        .st-key-auto_page_wrap_6n36s5 .st-key-auto_stats_section_6n36s5 {
            width: 100% !important;
            max-width: min(600px, calc(100vw - 20px)) !important;
            margin: 10px auto 0 !important;
            clear: both !important;
        }
        .st-key-auto_page_wrap_6n36s5 .st-key-auto_spirit_below_confirm_6n36s5 {
            width: 100% !important;
            max-width: min(600px, calc(100vw - 20px)) !important;
            margin: 8px auto 0 !important;
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
        .st-key-auto_page_columns_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] {
            display: block !important;
        }
        .st-key-auto_page_columns_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:nth-child(1) {
            flex: none !important;
            width: 100% !important;
            min-width: 0 !important;
            max-width: 100% !important;
        }
        .st-key-auto_page_columns_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:nth-child(2) {
            display: none !important;
            flex: 0 0 0 !important;
            width: 0 !important;
            max-width: 0 !important;
            overflow: hidden !important;
            visibility: hidden !important;
            pointer-events: none !important;
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
            max-width: var(--auto-visual-col-width) !important;
            height: auto !important;
            min-height: 0 !important;
            overflow: visible !important;
            margin: 0 auto !important;
            padding: 0 !important;
        }
        .st-key-auto_spirit_below_confirm_6n36s5 .auto-spirit2-wrap,
        .st-key-auto_spirit_below_confirm_6n36s5 .auto-spirit2-ripple {
            width: 100% !important;
            max-width: var(--auto-visual-col-width) !important;
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
            max-width: var(--auto-visual-col-width) !important;
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
        .auto-spirit2-slot-right .auto-spirit2-img,
        .st-key-auto_spirit_below_confirm_6n36s5 .auto-spirit2-slot-right .auto-spirit2-img-base {
            width: 100% !important;
            max-width: 100% !important;
            height: 100% !important;
            object-fit: cover !important;
            border-radius: 50% !important;
            border: 2px solid rgba(34, 211, 238, 0.45) !important;
            box-shadow:
                0 6px 16px rgba(6, 182, 212, 0.35),
                inset 0 1px 0 rgba(255, 255, 255, 0.15) !important;
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
                max-width: var(--auto-visual-col-width) !important;
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
                gap: 5px !important;
            }
            .st-key-auto_purchase_history_zone_6n36s5 .auto-purchase-banner-history-grid .auto-banner-ball {
                width: auto !important;
                height: auto !important;
                min-width: 14px !important;
                font-size: 10px !important;
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
            font-size: 15px !important;
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
            aspect-ratio: 1 / 1;
            overflow: hidden;
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
        /* 닫힌 select — 선택값(즉시/월간구독) 표시, 로컬·Cloud DOM 차이 없도록 ::before 미사용 */
        .st-key-auto_purchase_method_6n36s5 div[data-baseweb="select"] > div > div:first-of-type {
            flex: 1 1 auto !important;
            min-width: 0 !important;
            max-width: 100% !important;
            overflow: hidden !important;
            justify-content: center !important;
        }
        .st-key-auto_purchase_method_6n36s5 div[data-baseweb="select"] span {
            display: block !important;
            max-width: 100% !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            white-space: nowrap !important;
            text-align: center !important;
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
            flex: 1 1 auto !important;
            min-width: 0 !important;
            max-width: 100% !important;
            overflow: hidden !important;
            justify-content: center !important;
        }
        .st-key-auto_purchase_quantity_6n36s5 div[data-baseweb="select"] span {
            display: block !important;
            max-width: 100% !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            white-space: nowrap !important;
            text-align: center !important;
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
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] summary svg,
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] summary img,
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] summary > *:not(p):not(span) {
            display: none !important;
            width: 0 !important;
            visibility: hidden !important;
        }
        /* 화살표 아이콘 자체는 숨겨지지만, 그걸 감싼 wrapper span이 flex:0 0 auto로
           너비를 그대로 차지해서 옆 텍스트("구매내역")가 남은 공간 0px로 밀리는 문제가
           있었다 — wrapper span 자체를 구조적으로 찾아 같이 접는다. */
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] summary span:has(> [data-testid="stIconMaterial"]) {
            display: none !important;
            width: 0 !important;
            flex: 0 0 0 !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] summary {
            list-style: none !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] summary::-webkit-details-marker,
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] summary::marker {
            display: none !important;
            content: "" !important;
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

    spirit2_base64 = _get_icon_base64("로또신령2.jpg")

    with st.container(key="auto_page_wrap_6n36s5"):
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
                    with st.container(key="auto_guide_expander_zone_6n36s5"):
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
                                        # 여러 회차 구매가 섞여 쌓일 수 있는데, 예전엔 조합
                                        # 숫자만 보여주고 몇 회차 것인지 표시가 없어서 어떤
                                        # 조합이 어느 회차인지, 왜 동그라미가 없는지(미추첨
                                        # 인지 낙첨인지) 헷갈릴 수 있었다 — 회차별로 묶어서
                                        # 머리글을 붙인다.
                                        grouped_history: dict = {}
                                        for item in history_items:
                                            grouped_history.setdefault(item.get("draw_round"), []).append(item)
                                        for draw_round, items in grouped_history.items():
                                            st.markdown(
                                                f'<div class="auto-history-round-head">{draw_round}회차</div>',
                                                unsafe_allow_html=True,
                                            )
                                            for item in items:
                                                st.markdown(
                                                    _purchase_banner_html(item, compact=True),
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

        # ── 신령 이미지 + 회차별 당첨번호 배출 (2열 밖·전체 너비) ──
        with st.container(key="auto_spirit_below_confirm_6n36s5"):
            if spirit2_base64:
                st.markdown(
                    _spirit2_image_block(
                        spirit2_base64,
                        "auto-spirit2-slot-right",
                    ),
                    unsafe_allow_html=True,
                )

        stats_df, is_mock = _load_stats_table_cached(_admin_combo_save_mtime())
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
            display: block !important;
        }
        .st-key-auto_page_wrap_6n36s5 .st-key-auto_stats_section_6n36s5,
        .st-key-auto_page_wrap_6n36s5 .st-key-auto_stats_section_6n36s5 > div[data-testid="stVerticalBlock"],
        .st-key-auto_page_wrap_6n36s5 .st-key-auto_stats_section_6n36s5 [data-testid="stMarkdown"],
        .st-key-auto_page_wrap_6n36s5 .st-key-auto_stats_section_6n36s5 .auto-stats-table-wrap {
            display: block !important;
            visibility: visible !important;
            opacity: 1 !important;
            height: auto !important;
            min-height: 0 !important;
            max-height: none !important;
            overflow: visible !important;
            position: relative !important;
            z-index: 1 !important;
        }
        /* 구매방식·수량 / 구매확정·구매내역 — 아래 캐릭터 이미지와 같은 폭 기준(360px 중앙정렬)
           컨테이너 안에서, 두 항목을 하나의 짝으로 묶어 항상 가운데(캐릭터 아이콘과 같은 축)에
           배치한다. 예전엔 위쪽 줄은 20%/80%, 아래 줄은 30%/70% 지점으로 서로 다르게 벌려놔서
           두 줄이 서로 다른 폭으로 벌어져 보였다 — 두 줄 모두 같은 방식(중앙 정렬 + 고정 간격)으로
           통일해서 좌우 균형이 맞도록 한다. */
        .st-key-auto_purchase_method_zone_6n36s5 {
            width: 100% !important;
            max-width: var(--auto-visual-col-width) !important;
            margin: 0 auto !important;
        }
        .st-key-auto_purchase_method_zone_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] {
            justify-content: center !important;
            align-items: center !important;
            gap: 14px !important;
            box-sizing: border-box !important;
        }
        .st-key-auto_confirm_history_row_6n36s5 {
            width: 100% !important;
            max-width: var(--auto-visual-col-width) !important;
            margin: 0 auto !important;
        }
        .st-key-auto_confirm_history_row_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] {
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            justify-content: center !important;
            align-items: center !important;
            gap: 14px !important;
            width: 100% !important;
            max-width: 100% !important;
            height: auto !important;
            min-height: 0 !important;
            box-sizing: border-box !important;
        }
        .st-key-auto_confirm_history_row_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:nth-child(1),
        .st-key-auto_confirm_history_row_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:nth-child(2) {
            flex: 0 0 auto !important;
            width: auto !important;
            max-width: none !important;
            min-width: 0 !important;
            height: auto !important;
        }
        .st-key-auto_purchase_confirm_6n36s5 div[data-testid="stButton"],
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] {
            width: 106px !important;
            min-width: 106px !important;
            max-width: 106px !important;
        }
        /* ⚠️ 구매 안내 expander — 내용 크기만큼만 폭을 줄이고 가로 중앙 정렬 */
        .st-key-auto_guide_expander_zone_6n36s5 {
            width: 100% !important;
            display: flex !important;
            justify-content: center !important;
        }
        .st-key-auto_guide_expander_zone_6n36s5 div[data-testid="stExpander"] {
            width: auto !important;
            max-width: max-content !important;
        }
        .st-key-auto_guide_expander_zone_6n36s5 div[data-testid="stExpander"] > details {
            width: auto !important;
        }
        .st-key-auto_guide_expander_zone_6n36s5 div[data-testid="stExpander"] > details > summary {
            width: auto !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 8px !important;
            padding: 10px 18px !important;
            white-space: nowrap !important;
        }
        .st-key-auto_guide_expander_zone_6n36s5 div[data-testid="stExpander"] summary svg {
            flex: 0 0 auto !important;
            margin: 0 !important;
        }
        .st-key-auto_guide_expander_zone_6n36s5 div[data-testid="stExpander"] summary p,
        .st-key-auto_guide_expander_zone_6n36s5 div[data-testid="stExpander"] summary span {
            margin: 0 !important;
            white-space: nowrap !important;
        }
        /* 캐릭터 이미지는 항상 "구매내역" 팝업(z-index:40) 뒤에 있도록 낮은 z-index 고정 */
        .st-key-auto_spirit_below_confirm_6n36s5 {
            position: relative !important;
            z-index: 1 !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] {
            position: relative !important;
            z-index: 40 !important;
        }
        html, body, .stApp, [data-testid="stAppViewContainer"], section.main {
            overflow-y: auto !important;
            max-height: none !important;
        }
        /* 구매방식·구매수량·구매확정·구매내역 — 공통 사이즈 조정 (높이 -10%, 폰트 한 단계 확대) */
        .st-key-auto_purchase_method_6n36s5 div[data-testid="stSelectbox"],
        .st-key-auto_purchase_method_6n36s5 div[data-testid="stSelectbox"] > div,
        .st-key-auto_purchase_method_6n36s5 div[data-baseweb="select"] > div,
        .st-key-auto_purchase_quantity_6n36s5 div[data-testid="stSelectbox"],
        .st-key-auto_purchase_quantity_6n36s5 div[data-testid="stSelectbox"] > div,
        .st-key-auto_purchase_quantity_6n36s5 div[data-baseweb="select"] > div,
        .st-key-auto_purchase_confirm_6n36s5 div[data-testid="stButton"] > button,
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] > details > summary {
            height: 32px !important;
            min-height: 32px !important;
            max-height: 32px !important;
            font-size: 16px !important;
        }
        .st-key-auto_purchase_method_6n36s5 div[data-baseweb="select"] span,
        .st-key-auto_purchase_quantity_6n36s5 div[data-baseweb="select"] span {
            font-size: 16px !important;
        }
        /* 구매방식·구매수량 — 현재 Streamlit 버전은 BaseWeb select 대신
           React Aria ComboBox(input[type="text"] + div[role="group"])를 쓰므로
           위 data-baseweb 규칙이 매치되지 않는다. 실제 DOM 기준으로 재적용. */
        .st-key-auto_purchase_method_6n36s5 div[role="group"],
        .st-key-auto_purchase_quantity_6n36s5 div[role="group"] {
            height: 32px !important;
            min-height: 32px !important;
            max-height: 32px !important;
        }
        .st-key-auto_purchase_method_6n36s5 input[type="text"],
        .st-key-auto_purchase_quantity_6n36s5 input[type="text"] {
            font-size: 16px !important;
        }
        /* input[type=text]가 브라우저 기본 폭(약 211px)을 그대로 차지해서 화살표 버튼이
           박스 밖으로 밀려나 overflow:hidden에 잘려 안 보이던 문제 — input은 남는 공간만
           차지하고 버튼은 자기 크기만큼만 차지하도록 flex 배분을 명시. */
        .st-key-auto_purchase_method_6n36s5 input[type="text"],
        .st-key-auto_purchase_quantity_6n36s5 input[type="text"] {
            flex: 1 1 auto !important;
            width: 0 !important;
            min-width: 0 !important;
        }
        .st-key-auto_purchase_method_6n36s5 div[role="group"] button,
        .st-key-auto_purchase_quantity_6n36s5 div[role="group"] button {
            flex: 0 0 auto !important;
        }
        /* 즉시/월간·5개/10개 — 클릭 가능한 선택 요소로 보이도록 테두리·그림자·hover 반응 추가 */
        .st-key-auto_purchase_method_6n36s5 div[role="group"],
        .st-key-auto_purchase_quantity_6n36s5 div[role="group"] {
            box-sizing: border-box !important;
            overflow: visible !important;
            border: 2px solid #6C3CE0 !important;
            box-shadow: 0 2px 6px rgba(108, 60, 224, 0.35) !important;
            cursor: pointer !important;
            transition: box-shadow 0.15s ease, border-color 0.15s ease !important;
        }
        .st-key-auto_purchase_method_6n36s5 div[role="group"]:hover,
        .st-key-auto_purchase_quantity_6n36s5 div[role="group"]:hover,
        .st-key-auto_purchase_method_6n36s5 div[role="group"]:focus-within,
        .st-key-auto_purchase_quantity_6n36s5 div[role="group"]:focus-within {
            border-color: #8B5CF6 !important;
            box-shadow: 0 3px 10px rgba(108, 60, 224, 0.55) !important;
        }
        .st-key-auto_purchase_method_6n36s5 div[role="group"] button svg,
        .st-key-auto_purchase_quantity_6n36s5 div[role="group"] button svg {
            width: 1.6rem !important;
            height: 1.6rem !important;
            color: #6C3CE0 !important;
            fill: #6C3CE0 !important;
        }
        /* 구매확정·구매내역 버튼 — 106px → 7%↓(98.58) → 4%↑(102.52) → 3%↑(105.6px) */
        .st-key-auto_purchase_confirm_6n36s5 div[data-testid="stButton"],
        .st-key-auto_purchase_confirm_6n36s5 div[data-testid="stButton"] > button,
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"],
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] > details > summary {
            width: 105.6px !important;
            min-width: 105.6px !important;
            max-width: 105.6px !important;
        }
        .st-key-auto_purchase_confirm_6n36s5 div[data-testid="stButton"] > button {
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            text-align: center !important;
        }
        .st-key-auto_purchase_confirm_6n36s5 div[data-testid="stButton"] > button p,
        .st-key-auto_purchase_confirm_6n36s5 div[data-testid="stButton"] > button span,
        .st-key-auto_purchase_confirm_6n36s5 div[data-testid="stButton"] > button div {
            width: 100% !important;
            text-align: center !important;
            margin: 0 auto !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] > details > summary {
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            text-align: center !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] > details > summary p,
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] > details > summary span {
            width: 100% !important;
            text-align: center !important;
            margin: 0 auto !important;
        }
        /* 화살표는 Material Symbols 아이콘 폰트로 렌더링된다. 번들 코드를 더 파보니
           "icon"/"type" prop이 있는 특수 expander(체크·에러·스피너)만 data-testid를
           "stExpanderIcon*"로 오버라이드하고, 우리처럼 그런 prop이 없는 일반 expander는
           기본 아이콘 컴포넌트를 타서 기본 testid인 "stIconMaterial" 그대로 남는다 —
           그래서 stExpanderIcon만 노렸던 지난 시도가 안 먹혔다. 둘 다 잡는다. */
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] summary [data-testid="stExpanderIcon"],
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] summary [data-testid="stIconMaterial"] {
            display: none !important;
            width: 0 !important;
            height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            gap: 0 !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] > details > summary {
            gap: 0 !important;
            justify-content: center !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] > details > summary > span,
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] > details > summary > p {
            width: 100% !important;
            text-align: center !important;
            margin: 0 auto !important;
            flex: 1 1 auto !important;
        }
        /* 구매확정·구매내역 — 버튼/summary 자체에 font-size·weight를 줘도 안쪽 <p>가
           Streamlit 기본 스타일(구매확정 p는 weight 400, 구매내역 p는 weight 900으로
           서로 달랐다)을 그대로 써서 두 버튼 글씨체가 달라 보였다 — 실제로 텍스트를
           그리는 p/span에 직접 같은 값을 지정해야 반영된다. font-family까지 명시해서
           혹시 모를 폴백 폰트 차이도 없앤다. */
        .st-key-auto_purchase_confirm_6n36s5 div[data-testid="stButton"] > button,
        .st-key-auto_purchase_confirm_6n36s5 div[data-testid="stButton"] > button p,
        .st-key-auto_purchase_confirm_6n36s5 div[data-testid="stButton"] > button span,
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] > details > summary,
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] summary p,
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] summary span {
            font-family: "Source Sans", sans-serif !important;
            font-size: 17px !important;
            font-weight: 700 !important;
        }
        /* 구매내역 쪽 p는 폭이 텍스트 크기만큼만 좁게 잡혀서(68px) 106px 버튼 안에서
           살짝 왼쪽으로 치우쳐 보이거나(데스크톱), 모바일 폭에서는 아예 0px로 접혀
           안 보이는 문제까지 있었다 — flex-grow 하나에만 기대지 않고, 감싸는 모든
           단계(outer span → text-wrap div → stMarkdownContainer → p)를 전부
           display:block + width:100%로 강제해서 어떤 화면 폭에서도 안정적으로
           구매확정 쪽과 동일하게 꽉 채워 중앙정렬되게 한다. */
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] summary > span,
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] summary > span > div,
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] summary [data-testid="stMarkdownContainer"] {
            display: block !important;
            width: 100% !important;
            flex: 1 1 auto !important;
            min-width: 0 !important;
        }
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] summary p,
        .st-key-auto_purchase_history_zone_6n36s5 div[data-testid="stExpander"] summary span {
            display: block !important;
            width: 100% !important;
            margin: 0 auto !important;
            text-align: center !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
