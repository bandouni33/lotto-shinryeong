"""앱 공통 버튼 스타일 (고급필터 admin_filter.py 톤과 통일)."""

from __future__ import annotations

import base64
import os
from functools import lru_cache

# ── "메인으로" 상세페이지 공통 네비게이션 버튼 ──
# 예전엔 페이지마다 이름(홈/메인/메인으로)과 모양(순수 st.button, 흰색 알약,
# 검은 알약+아이콘 등)이 제각각이었다 — 자동구매/고급필터/통계센터가 이미 쓰던
# "검은 알약 + 금테 원형 아이콘 + 메인으로" 스타일로 전체 통일한다.
_MAIN_NAV_BTN_CSS = """
<style>
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
"""


@lru_cache(maxsize=4)
def _main_nav_icon_base64(file_path: str = "K-325.jpg") -> str:
    if os.path.exists(file_path):
        with open(file_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    return ""


def main_nav_button_css() -> str:
    return _MAIN_NAV_BTN_CSS


def main_nav_button_html(href: str = "?") -> str:
    """모든 상세페이지 공통 "메인으로" 버튼 HTML — 검은 알약 + 금테 원형 아이콘."""
    icon_base64 = _main_nav_icon_base64()
    icon_html = (
        f'<img class="auto-back-main-icon" src="data:image/jpeg;base64,{icon_base64}" alt="로또신령">'
        if icon_base64
        else "🏠"
    )
    return f'<a href="{href}" target="_self" class="auto-back-main-btn">{icon_html}<span>메인으로</span></a>'


# ── 가벼운 "로또신령" 로고 링크 (2026-08-28) ──
# 위 "메인으로" 알약 버튼을 화면 공간 낭비라고 지우고 나니, 네이티브 앱
# 바깥(브라우저로 직접 이 URL을 열었을 때)에는 메인으로 돌아갈 길이 아예
# 없어져 버렸다 — 네이티브 앱은 자체 툴바에 "← 메인" 버튼이 있어서 문제
# 없지만, 브라우저에는 그게 없다. 자리를 거의 안 차지하는 작은 로고
# 텍스트를 대신 두고, 그걸 누르면 메인으로 가게 한다(웹사이트 로고 클릭하면
# 홈으로 가는 것과 같은 흔한 패턴).
_BRAND_HOME_LINK_CSS = """
<style>
.brand-home-link {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: #d8c48a !important;
    font-weight: 800 !important;
    font-size: 13px !important;
    letter-spacing: 0.02em;
    text-decoration: none !important;
    padding: 4px 2px;
    margin-bottom: 6px;
}
.brand-home-link:hover {
    color: #ffe9b3 !important;
}
.brand-home-link-icon {
    width: 18px;
    height: 18px;
    border-radius: 50%;
    object-fit: cover;
    border: 1px solid #ffb300;
    flex-shrink: 0;
}
</style>
"""


def brand_home_link_css() -> str:
    return _BRAND_HOME_LINK_CSS


def brand_home_link_html(href: str = "?") -> str:
    """작은 "로또신령" 로고 링크 — 클릭하면 메인으로. main_nav_button_html보다
    훨씬 작아서 화면을 거의 안 차지한다."""
    icon_base64 = _main_nav_icon_base64()
    icon_html = (
        f'<img class="brand-home-link-icon" src="data:image/jpeg;base64,{icon_base64}" alt="로또신령">'
        if icon_base64
        else "🔮"
    )
    return f'<a href="{href}" target="_self" class="brand-home-link">{icon_html}<span>로또신령</span></a>'


# ── Primary (간편인증 · 구매 확정 등) ──
_PRIMARY_GRADIENT = """
    background: linear-gradient(135deg, #6366F1 0%, #8B5CF6 45%, #A855F7 100%) !important;
    color: #FFFFFF !important;
    font-weight: 800 !important;
    border: 1px solid rgba(167, 139, 250, 0.5) !important;
    border-radius: 12px !important;
    box-shadow:
        0 0 24px rgba(139, 92, 246, 0.45),
        0 4px 16px rgba(99, 102, 241, 0.35),
        inset 0 1px 0 rgba(255, 255, 255, 0.2) !important;
    transition: transform 0.15s ease, box-shadow 0.15s ease !important;
"""

_PRIMARY_HOVER = """
    transform: translateY(-1px) !important;
    box-shadow:
        0 0 32px rgba(139, 92, 246, 0.55),
        0 6px 20px rgba(99, 102, 241, 0.4),
        inset 0 1px 0 rgba(255, 255, 255, 0.25) !important;
"""

# ── Secondary (테스트 로그인 · 로그아웃 · 충전 등) ──
_SECONDARY_GRADIENT = """
    background: linear-gradient(145deg, #1c1c38, #141428) !important;
    color: #E2E8F0 !important;
    font-weight: 700 !important;
    border: 1px solid rgba(100, 116, 139, 0.4) !important;
    border-radius: 10px !important;
    box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.35) !important;
    transition: transform 0.15s ease, border-color 0.15s ease !important;
"""

_SECONDARY_HOVER = """
    border-color: rgba(139, 92, 246, 0.45) !important;
    transform: translateY(-1px) !important;
"""


def _key_selectors(keys: list[str], suffix: str = "") -> str:
    return ",\n".join(f".st-key-{k} div[data-testid=\"stButton\"] > button{suffix}" for k in keys)


def wallet_bar_button_css() -> str:
    """내정보 다이얼로그 안 충전·로그아웃 버튼 + 화면 우하단 고정 "내정보" 트리거."""
    secondary_keys = [
        "wallet_logout_btn",
        "zp_logout_btn",
        "wallet_charge_btn",
    ]
    s_sel = _key_selectors(secondary_keys)
    s_hover = _key_selectors(secondary_keys, ":hover")
    return f"""
<style>
{s_sel} {{
    {_SECONDARY_GRADIENT}
    font-size: 13px !important;
    padding: 0.5rem 0.75rem !important;
    min-height: 42px !important;
}}
{s_hover} {{
    {_SECONDARY_HOVER}
}}
/* 예전엔 모든 화면 맨 위에 적립금/ID/로그아웃 줄이 항상 떠 있었는데, 화면을
   옮길 때마다 반복 노출돼 거슬린다는 요청으로 작은 버튼 뒤로 숨겼다(탭하면
   dialog로 뜸). 메인 화면에만 필요하다는 요청이라 render_wallet_bar가 메인
   에서만 이 버튼을 그리고, 위치도 우상단 구석으로 옮김(다른 상세페이지에서
   빈 공간을 만들던 원인이라 아예 안 그리는 쪽으로 없앴다 — 여기 위치값은
   메인 화면에서만 적용됨). */
.st-key-my_info_trigger_wrap {{
    position: fixed !important;
    right: 12px !important;
    top: 8px !important;
    z-index: 999 !important;
    width: auto !important;
}}
.st-key-my_info_trigger_wrap div[data-testid="stButton"] > button {{
    background: rgba(28, 28, 56, 0.9) !important;
    color: #CBD5E1 !important;
    font-weight: 700 !important;
    font-size: 11px !important;
    border: 1px solid rgba(100, 116, 139, 0.4) !important;
    border-radius: 999px !important;
    padding: 4px 12px !important;
    min-height: 0 !important;
    height: auto !important;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4) !important;
}}
</style>
"""


def auto_page_button_css() -> str:
    """자동조합 상세 — 구매 확정 primary."""
    sel = '.st-key-auto_purchase_confirm_6n36s5 div[data-testid="stButton"] > button'
    return f"""
<style>
{sel} {{
    {_PRIMARY_GRADIENT}
    font-size: 18px !important;
    padding: 0.65rem 1rem !important;
    min-height: 48px !important;
    width: 100% !important;
}}
{sel}:hover {{
    {_PRIMARY_HOVER}
}}
</style>
"""
