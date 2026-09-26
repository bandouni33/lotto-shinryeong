"""로또 볼(번호 원형) 색·글자색의 **단일 기준점** (2026-09-26).

왜 필요한가: 같은 번호→색 규칙이 메인(`user_page.py:580 get_ball_color`,
`:804 get_ball_style`), 번개조합(`page_thunder.py`), 죽은 `frontend/components/lotto_balls.py`
에 각각 복사돼 있었다. 게다가 글자색이 `color:white`로 고정이라 **노란 볼(1~10)에 흰 글씨**
(대비 약 1.9~2.6)가 되어 잘 안 보였다 — 사용자 신고("밝은 도형에 밝은 글씨").

규칙 — `tests/test_ball_style.py`가 강제한다
  1. 번호→채우기/글자색은 이 파일에만 있다. 화면은 ball_html/ball_fill/orbit_ball_css만 쓴다.
  2. 글자색은 항상 채우기(그라디언트의 가장 밝은/어두운 끝 포함)와 대비 4.5 이상이 되도록
     자동 선택된다 — 손으로 색을 박지 않는다.
  3. 번호는 1~45 이외 값이 들어와도 예외 없이 기본 그룹으로 처리한다(경계 전수 테스트).
"""

from __future__ import annotations

# 공식(동행복권) 구간 색 — 이 표가 채우기 색의 정본이다.
BALL_BASE_COLOR: tuple[tuple[int, int, str], ...] = (
    (45, 41, "#b0d840"),  # 41~45 초록
    (40, 31, "#aaaaaa"),  # 31~40 회색
    (30, 21, "#ff7272"),  # 21~30 빨강
    (20, 11, "#69c8f2"),  # 11~20 파랑
    (10, 1, "#fbc400"),   # 1~10 노랑
)
FALLBACK_COLOR = "#aaaaaa"

# 그라디언트 밝기 단계 후보 — 이 순서대로 시도해 "고른 글자색이 4.5 이상"이 되는
# 첫 단계를 쓴다(숫자를 손으로 튜닝하지 않기 위한 장치).
_BLEND_LADDER = (0.38, 0.30, 0.22, 0.12, 0.0)
_TEXT_CANDIDATES = ("#111111", "#FFFFFF")
_MIN_CONTRAST = 4.5


def ball_color(number: int) -> str:
    """번호 구간의 기준 색(공식 팔레트)."""
    try:
        value = int(number)
    except (TypeError, ValueError):
        return FALLBACK_COLOR
    for high, low, color in BALL_BASE_COLOR:
        if low <= value <= high:
            return color
    return FALLBACK_COLOR


def _rgb(hex_color: str) -> tuple[int, int, int]:
    text = hex_color.lstrip("#")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, int(round(c)))) for c in rgb))


def _blend(base: str, other: tuple[int, int, int], ratio: float) -> str:
    r, g, b = _rgb(base)
    return _hex((
        r + (other[0] - r) * ratio,
        g + (other[1] - g) * ratio,
        b + (other[2] - b) * ratio,
    ))


def _luminance(rgb: tuple[int, int, int]) -> float:
    def channel(value: int) -> float:
        v = value / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG 명도 대비 — 글자색을 고르고 검증하는 데 쓴다."""
    l1, l2 = _luminance(_rgb(fg)), _luminance(_rgb(bg))
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)


def ball_stops(number: int) -> tuple[str, str, str]:
    """(밝은 끝, 기준색, 어두운 끝) — 볼 그라디언트의 세 정지점.

    가장 밝은 끝과 어두운 끝 양쪽에서 글자 대비가 4.5 이상이 되는 첫 밝기 단계를
    고른다(즉 그라디언트 어느 부분 위에 글자가 놓여도 읽힌다)."""
    base = ball_color(number)
    best = None
    for ratio in _BLEND_LADDER:
        light = _blend(base, (255, 255, 255), ratio)
        dark = _blend(base, (0, 0, 0), ratio)
        text = _best_text_color((light, base, dark))
        worst = min(contrast_ratio(text, stop) for stop in (light, base, dark))
        if worst >= _MIN_CONTRAST:
            return light, base, dark
        if best is None or worst > best[0]:
            best = (worst, light, base, dark)
    assert best is not None
    return best[1], best[2], best[3]


def _best_text_color(stops: tuple[str, ...]) -> str:
    scored = [
        (min(contrast_ratio(candidate, stop) for stop in stops), candidate)
        for candidate in _TEXT_CANDIDATES
    ]
    scored.sort(reverse=True)
    return scored[0][1]


def ball_text_color(number: int) -> str:
    """이 볼 위에 올릴 글자색 — 채우기에서 자동으로 유도한다(손으로 박지 않는다)."""
    return _best_text_color(ball_stops(number))


def ball_fill(number: int) -> str:
    """CSS `background` 값(원형 볼 채우기)."""
    light, base, dark = ball_stops(number)
    return f"radial-gradient(circle at 35% 35%, {light}, {base}, {dark})"


def ball_html(number: int, *, size: int = 26, font_size: int = 12, margin_right: int = 4) -> str:
    """메인/번호판에서 쓰는 볼 한 개의 HTML(글자색 자동)."""
    label = f"{int(number):02d}" if str(number).isdigit() else str(number)
    return (
        f'<div style="background:{ball_fill(number)}; width:{size}px; height:{size}px; '
        f"border-radius:50%; display:flex; align-items:center; justify-content:center; "
        f"color:{ball_text_color(number)}; font-weight:900; font-size:{font_size}px; "
        f"flex-shrink:0; margin-right:{margin_right}px; "
        'box-shadow: 2px 3px 5px rgba(0,0,0,0.5), inset -3px -3px 5px rgba(0,0,0,0.4), '
        'inset 2px 2px 4px rgba(255,255,255,0.6); text-shadow: 1px 1px 2px rgba(0,0,0,0.35);">'
        f"{label}</div>"
    )


def orbit_ball_css(index: int, number: int, *, angle_step: int = 30, size: int = 30, font_size: int = 15) -> str:
    """메인 상단 '회전 볼' 오버레이 한 개의 CSS — 채우기·글자색·크기까지 여기서 만든다."""
    angle = index * angle_step
    return f"""
        .orbit-ball-{index} {{
            position: absolute; width: {size}px; height: {size}px; border-radius: 50%;
            background: {ball_fill(number)};
            display: flex; align-items: center; justify-content: center;
            color: {ball_text_color(number)}; font-weight: 900; font-size: {font_size}px;
            text-shadow: 1px 1px 2px rgba(0,0,0,0.35);
            box-shadow: 2px 3px 5px rgba(0,0,0,0.6), inset 2px 2px 4px rgba(255,255,255,0.4);
            top: 50%; left: 50%;
            margin-top: -{size // 2}px; margin-left: -{size // 2}px;
            animation: orbit{index} 10s linear infinite;
        }}
"""
