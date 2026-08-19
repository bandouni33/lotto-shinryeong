"""앱 공통 버튼 스타일 (고급필터 admin_filter.py 톤과 통일)."""

from __future__ import annotations

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
