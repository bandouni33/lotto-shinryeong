"""자동조합 상세 페이지 (K-595)."""

import base64
import importlib
import os

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
SUBSCRIPTION_WEEKDAYS = ["화", "수", "목"]
QUANTITY_OPTIONS = [5, 10, 15, 20]


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
                   dur="11s"
                   values="0.016 0.062;0.026 0.085;0.013 0.048;0.021 0.078;0.016 0.062"
                   repeatCount="indefinite"/>
        </feTurbulence>
        <feDisplacementMap in="SourceGraphic" in2="noise" scale="6" xChannelSelector="R" yChannelSelector="G">
          <animate attributeName="scale"
                   dur="9s"
                   values="6;11;7;12;6"
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
        ellipse 30% 24% at 50% 25%,
        transparent 0%,
        transparent 70%,
        rgba(0, 0, 0, 0.35) 82%,
        black 92%
    );
    mask-image: radial-gradient(
        ellipse 30% 24% at 50% 25%,
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
        transform: perspective(820px) rotateY(-1.4deg) skewX(0.75deg) translateY(0);
    }}
    25% {{
        transform: perspective(820px) rotateY(1.6deg) skewX(-1.1deg) translateY(-3px);
    }}
    50% {{
        transform: perspective(820px) rotateY(-0.9deg) skewX(1.3deg) translateY(2px);
    }}
    75% {{
        transform: perspective(820px) rotateY(1.2deg) skewX(-0.65deg) translateY(-2px);
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


def _load_stats_table() -> tuple[pd.DataFrame, bool]:
    mdb = _marketing_db()
    mdb.init_marketing_tables()
    stats = mdb.get_draw_extraction_stats(limit=20)
    if stats:
        return _stats_to_dataframe(stats, False), False
    return _stats_to_dataframe(mdb.get_mock_draw_extraction_stats(), True), True


def render():
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
            margin-bottom: 18px;
            flex-wrap: nowrap;
        }
        .auto-options-wrap {
            flex: 0 1 auto;
            width: auto;
            max-width: 100%;
        }
        .st-key-auto_purchase_method_zone_6n36s5 > div[data-testid="stVerticalBlock"] {
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: wrap !important;
            align-items: center !important;
            gap: 10px 12px !important;
            margin-bottom: 18px !important;
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
            font-size: 11px;
            font-weight: 700;
            margin: 0 0 6px 0;
            letter-spacing: -0.02em;
            line-height: 1.25;
            white-space: nowrap;
        }
        .st-key-auto_sms_days_6n36s5 {
            display: inline-block !important;
            width: fit-content !important;
            max-width: 100% !important;
            padding: 8px 12px 6px 12px !important;
            margin: 0 !important;
            border: 1px solid rgba(179, 157, 219, 0.52) !important;
            border-radius: 14px !important;
            background: linear-gradient(165deg, rgba(255,255,255,0.08), rgba(255,255,255,0.02)) !important;
            box-shadow:
                0 4px 16px rgba(0,0,0,0.24),
                inset 0 1px 0 rgba(255,255,255,0.08),
                0 0 0 1px rgba(206, 147, 216, 0.12) !important;
        }
        .st-key-auto_sms_days_6n36s5 div[data-testid="stHorizontalBlock"] {
            width: auto !important;
            max-width: 100% !important;
            gap: 0.95rem !important;
            justify-content: center !important;
            flex-wrap: nowrap !important;
        }
        .st-key-auto_sms_days_6n36s5 div[data-testid="column"] {
            flex: 0 0 auto !important;
            width: auto !important;
            min-width: 0 !important;
        }
        .auto-table-title {
            display: inline-block;
            background: linear-gradient(145deg, #243052 0%, #1a2238 42%, #12182b 100%);
            color: #b8c2d6;
            font-weight: 800;
            font-size: 14px;
            padding: 10px 16px;
            border-radius: 14px;
            border: 1px solid rgba(100, 126, 170, 0.32);
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.06);
            margin: 8px 0 12px 0;
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
        .st-key-auto_sms_days_6n36s5 div[data-testid="column"] {
            overflow: visible !important;
        }
        .st-key-auto_sms_days_6n36s5 div[data-testid="stCheckbox"] {
            overflow: visible !important;
            margin: 0 !important;
        }
        .st-key-auto_sms_days_6n36s5 div[data-testid="stCheckbox"] label,
        .st-key-auto_sms_days_6n36s5 div[data-testid="stCheckbox"] [data-baseweb="checkbox"] {
            display: inline-flex !important;
            flex-direction: column !important;
            align-items: center !important;
            justify-content: flex-start !important;
            gap: 5px !important;
            margin: 0 !important;
            padding: 0 !important;
            width: 100% !important;
            min-height: 0 !important;
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
            overflow: visible !important;
        }
        .st-key-auto_sms_days_6n36s5 div[data-testid="stCheckbox"] [data-testid="stWidgetLabel"] {
            order: -1 !important;
            position: relative !important;
            z-index: 30 !important;
            margin: 0 !important;
            padding: 0 !important;
            width: 100% !important;
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
            font-size: 14px !important;
            line-height: 1.2 !important;
            text-align: center !important;
            opacity: 1 !important;
            visibility: visible !important;
            display: block !important;
            position: relative !important;
            z-index: 30 !important;
            text-shadow: 0 1px 3px rgba(0, 0, 0, 0.85) !important;
        }
        .st-key-auto_sms_days_6n36s5 div[data-testid="stCheckbox"] [data-baseweb="checkbox"] > span:first-of-type {
            order: 1 !important;
            flex-shrink: 0 !important;
            width: 22px !important;
            height: 22px !important;
            min-width: 22px !important;
            min-height: 22px !important;
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
            background-size: 12px 12px !important;
        }
        div[data-testid="stTextInput"] input {
            background: linear-gradient(165deg, rgba(255,255,255,0.12), rgba(255,255,255,0.06)) !important;
            color: #f3e5f5 !important;
            border: 1px solid rgba(179, 157, 219, 0.42) !important;
            border-radius: 12px !important;
            box-shadow: inset 0 2px 6px rgba(0,0,0,0.28) !important;
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
        .auto-spirit2-slot-mobile {
            display: none;
            width: 100%;
            margin: 14px 0 6px 0;
        }
        .auto-spirit2-slot-desktop {
            display: block;
            width: 100%;
        }
        @media (max-width: 768px) {
            .auto-section-row {
                flex-wrap: nowrap;
                align-items: center;
            }
            .st-key-auto_page_columns_6n36s5 div[data-testid="stHorizontalBlock"] {
                flex-direction: column !important;
                gap: 0 !important;
            }
            .st-key-auto_page_columns_6n36s5 div[data-testid="column"] {
                width: 100% !important;
                min-width: 100% !important;
                flex: 1 1 100% !important;
            }
            .auto-spirit2-slot-mobile {
                display: block !important;
                visibility: visible !important;
                position: relative !important;
                width: 100% !important;
            }
            .auto-spirit2-slot-mobile .auto-spirit2-ripple-wave {
                animation: autoSpiritBodyWave 10s ease-in-out infinite !important;
                animation-play-state: running !important;
            }
            .auto-spirit2-slot-mobile .auto-spirit2-img-wave {
                filter: url(#auto-spirit-ripple-mob) !important;
                -webkit-filter: url(#auto-spirit-ripple-mob) !important;
            }
            .auto-spirit2-slot-desktop,
            .st-key-auto_visual_col_6n36s5 {
                display: none !important;
                visibility: hidden !important;
                height: 0 !important;
                min-height: 0 !important;
                overflow: hidden !important;
                margin: 0 !important;
                padding: 0 !important;
                position: absolute !important;
                left: -9999px !important;
                width: 0 !important;
                content-visibility: hidden !important;
                pointer-events: none !important;
            }
            .auto-spirit2-slot-desktop .auto-spirit2-ripple-wave,
            .auto-spirit2-slot-desktop .auto-spirit2-img-wave {
                animation: none !important;
                animation-play-state: paused !important;
                filter: none !important;
                -webkit-filter: none !important;
            }
            .st-key-auto_purchase_method_zone_6n36s5 > div[data-testid="stVerticalBlock"] {
                flex-wrap: wrap !important;
                align-items: flex-start !important;
                gap: 8px 10px !important;
                overflow: visible !important;
            }
            .st-key-auto_purchase_method_zone_6n36s5 .st-key-auto_purchase_method_6n36s5 {
                flex: 0 0 auto !important;
            }
            .st-key-auto_purchase_method_zone_6n36s5 .st-key-auto_sms_days_6n36s5 {
                flex: 1 1 100% !important;
                width: 100% !important;
                max-width: 100% !important;
                margin-top: 2px !important;
                overflow: visible !important;
                padding: 10px 12px 8px 12px !important;
                box-sizing: border-box !important;
            }
            .auto-sms-days-caption {
                font-size: 11px !important;
                white-space: normal !important;
                max-width: none !important;
                text-align: center !important;
            }
            .st-key-auto_sms_days_6n36s5 div[data-testid="stHorizontalBlock"] {
                flex-wrap: nowrap !important;
                justify-content: space-evenly !important;
                gap: 0.5rem !important;
                width: 100% !important;
            }
            .st-key-auto_sms_days_6n36s5 div[data-testid="column"] {
                flex: 1 1 0 !important;
                min-width: 58px !important;
                max-width: none !important;
                overflow: visible !important;
            }
            .st-key-auto_sms_days_6n36s5 div[data-testid="stCheckbox"] [data-baseweb="checkbox"] > span:first-of-type {
                width: 24px !important;
                height: 24px !important;
                min-width: 24px !important;
                min-height: 24px !important;
            }
            .st-key-auto_purchase_method_6n36s5 div[data-testid="stRadio"] > div,
            .st-key-auto_purchase_quantity_6n36s5 div[data-testid="stRadio"] > div {
                gap: 0.65rem !important;
            }
        }
        @media (min-width: 769px) {
            .st-key-auto_purchase_method_zone_6n36s5 > div[data-testid="stVerticalBlock"] {
                flex-wrap: nowrap !important;
            }
            .auto-spirit2-slot-mobile {
                display: none !important;
                visibility: hidden !important;
                height: 0 !important;
                overflow: hidden !important;
                margin: 0 !important;
                padding: 0 !important;
                pointer-events: none !important;
                position: absolute !important;
                left: -9999px !important;
                width: 0 !important;
                content-visibility: hidden !important;
            }
            .auto-spirit2-slot-mobile .auto-spirit2-ripple-wave,
            .auto-spirit2-slot-mobile .auto-spirit2-img-wave {
                animation: none !important;
                animation-play-state: paused !important;
                filter: none !important;
                -webkit-filter: none !important;
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
            .st-key-auto_visual_col_6n36s5 {
                display: block !important;
                visibility: visible !important;
                height: auto !important;
                overflow: visible !important;
            }
            div[data-testid="stVerticalBlock"]:has(.auto-spirit2-slot-desktop) {
                overflow: visible !important;
            }
        }
        .auto-stats-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 4px;
        }
        .auto-stats-table thead tr th {
            background-color: #90caf9 !important;
            color: #0d47a1 !important;
            font-weight: 800 !important;
            text-align: center !important;
            padding: 10px 6px !important;
            border: 1px solid #64b5f6 !important;
        }
        .auto-stats-table tbody tr td {
            text-align: center !important;
            background-color: #ffffff !important;
            color: #1a1a1a !important;
            padding: 10px 6px !important;
            border: 1px solid #cfd8dc !important;
        }
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
                ellipse 30% 24% at 50% 25%,
                transparent 0%,
                transparent 70%,
                rgba(0, 0, 0, 0.35) 82%,
                black 92%
            );
            mask-image: radial-gradient(
                ellipse 30% 24% at 50% 25%,
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
                transform: perspective(820px) rotateY(-1.4deg) skewX(0.75deg) translateY(0);
            }
            25% {
                transform: perspective(820px) rotateY(1.6deg) skewX(-1.1deg) translateY(-3px);
            }
            50% {
                transform: perspective(820px) rotateY(-0.9deg) skewX(1.3deg) translateY(2px);
            }
            75% {
                transform: perspective(820px) rotateY(1.2deg) skewX(-0.65deg) translateY(-2px);
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
        col_form, col_visual = st.columns([0.92, 1.08], gap="small")

        with col_form:
            # ── 1. 구매 방식 + 월간구독 요일 (한 줄 배치) ──
            with st.container(key="auto_purchase_method_zone_6n36s5"):
                st.markdown('<div class="auto-label-pill">구매 방식</div>', unsafe_allow_html=True)
                purchase_method = st.radio(
                    "구매 방식 선택",
                    ["즉시", "월간구독"],
                    horizontal=True,
                    label_visibility="collapsed",
                    key="auto_purchase_method_6n36s5",
                )
                is_monthly = purchase_method == "월간구독"
                with st.container(key="auto_sms_days_6n36s5"):
                    st.markdown(
                        '<p class="auto-sms-days-caption">문자전송 희망요일 (복수 선택 가능)</p>',
                        unsafe_allow_html=True,
                    )
                    day_cols = st.columns(len(SUBSCRIPTION_WEEKDAYS))
                    selected_days = []
                    for idx, day in enumerate(SUBSCRIPTION_WEEKDAYS):
                        with day_cols[idx]:
                            if st.checkbox(
                                day,
                                key=f"auto_sms_day_{day}_6n36s5",
                                disabled=not is_monthly,
                            ):
                                selected_days.append(day)
            st.session_state["auto_sms_days"] = selected_days if is_monthly else []
            st.markdown(
                f"""
                <style>
                .st-key-auto_purchase_method_zone_6n36s5 .st-key-auto_sms_days_6n36s5 {{
                    opacity: {'1' if is_monthly else '0.28'} !important;
                    pointer-events: {'auto' if is_monthly else 'none'} !important;
                    filter: {'none' if is_monthly else 'saturate(0.55)'} !important;
                    border-color: {'rgba(179, 157, 219, 0.52)' if is_monthly else 'rgba(179, 157, 219, 0.22)'} !important;
                    box-shadow: {'0 4px 16px rgba(0,0,0,0.24), inset 0 1px 0 rgba(255,255,255,0.08), 0 0 0 1px rgba(206, 147, 216, 0.12)' if is_monthly else 'none'} !important;
                }}
                .st-key-auto_purchase_method_zone_6n36s5 .auto-sms-days-caption {{
                    color: {'#b39ddb' if is_monthly else 'rgba(179, 157, 219, 0.45)'} !important;
                }}
                </style>
                """,
                unsafe_allow_html=True,
            )

            # ── 2. 구매 수량 ──
            st.markdown(
                """
            <div class="auto-section-row">
                <div class="auto-label-pill">구매 수량</div>
                <div class="auto-options-wrap">
            """,
                unsafe_allow_html=True,
            )
            quantity_label = st.radio(
                "구매 수량 선택",
                [f"{n}개" for n in QUANTITY_OPTIONS],
                horizontal=True,
                label_visibility="collapsed",
                key="auto_purchase_quantity_6n36s5",
            )
            selected_quantity = int(str(quantity_label).replace("개", ""))
            st.markdown("</div></div>", unsafe_allow_html=True)

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

            # ── 수신 번호 ──
            phone = st.text_input(
                "수신 번호 (문자 발송용)",
                placeholder="01012345678",
                key="auto_phone_input_6n36s5",
            )

            if st.button("구매 확정", type="primary", use_container_width=True, key="auto_purchase_confirm_6n36s5"):
                from wallet_ui import ensure_member_or_banner

                if ensure_member_or_banner(
                    resume="auto_show_points",
                    reason="구매 확정을 위해 간편인증이 필요합니다.",
                ):
                    st.session_state["auto_show_points"] = True

            if st.session_state.get("auto_show_points"):
                from wallet_ui import points_notice_dialog
                from auth_providers import current_member_id
                from auto_purchase_service import process_auto_purchase

                result = points_notice_dialog("auto", quantity=selected_quantity)
                if result == "confirm":
                    st.session_state["auto_show_points"] = False
                    mid = current_member_id()
                    if not phone.strip():
                        st.error("수신 번호를 입력해 주세요.")
                    elif mid:
                        outcome = process_auto_purchase(
                            mid,
                            selected_quantity,
                            purchase_method,
                            phone,
                            st.session_state.get("auto_sms_days", []),
                        )
                        if outcome.get("ok"):
                            st.success(
                                f"회차 {outcome['draw_round']} · 추출 {outcome['combo_count']}개 · "
                                f"SMS 발송 · {outcome['cost']:,}P 차감 완료"
                            )
                        elif outcome.get("error") == "insufficient_balance":
                            st.error("적립금이 부족합니다.")
                        else:
                            st.error("구매 처리에 실패했습니다.")
                elif result == "cancel":
                    st.session_state["auto_show_points"] = False

            if spirit2_base64:
                st.markdown(
                    _spirit2_image_block(
                        spirit2_base64,
                        "auto-spirit2-slot-mobile",
                        "auto-spirit-ripple-mob",
                    ),
                    unsafe_allow_html=True,
                )

        with col_visual:
            with st.container(key="auto_visual_col_6n36s5"):
                if spirit2_base64:
                    components.html(
                        _spirit2_iframe_doc(spirit2_base64),
                        height=560,
                        scrolling=False,
                    )

    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    # ── 4. 회차별 당첨번호 배출 표 ──
    stats_df, is_mock = _load_stats_table()
    if not stats_df.empty:
        stats_df = stats_df[~stats_df["회차"].isin([1233, 1])]
    st.markdown(
        '<div class="auto-table-title">회차별 당\u200b첨번호 배출</div>',
        unsafe_allow_html=True,
    )
    if is_mock:
        st.caption("현재 DB에 등록된 회차 데이터가 없어 테스트용 샘플을 표시합니다.")

    table_html = stats_df.to_html(index=False, border=0, classes="auto-stats-table")
    st.markdown(table_html, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)
