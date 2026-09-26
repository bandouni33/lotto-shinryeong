"""볼(번호 원형) 색·글자색 기준점(ball_style.py) 계약 검증 — 2026-09-26.

배경: 같은 번호→색 규칙이 메인·번개조합·죽은 frontend에 복사돼 있었고, 글자색이
흰색 고정이라 노란 볼(1~10)에서 대비가 2.0 수준이었다(사용자 신고). 채우기와 글자색을
한 곳(ball_style)으로 모으고, 글자색은 항상 대비로 자동 선택되게 바꾼 것의 계약.

  B1 번호 1~45 전수: 글자색은 흑/백 중 하나이고, 그라디언트의 밝은 끝·기준·어두운 끝
     세 지점 모두에서 대비 4.5 이상이다
  B2 경계·비정상 입력: 10/11/20/21/30/31/40/41 같은 경계와 범위 밖(0, 46, 999, 문자열)이
     예외 없이 결정적으로 처리된다
  B3 그룹 일관성: 같은 구간은 같은 채우기, 구간끼리는 서로 다르다
  B4 사본 금지: 살아있는 화면 파일에 볼 색 표(함수·리터럴)가 남아 있지 않다
  B5 렌더 문자열: 볼 HTML에 채우기와 '대비가 확보된' 글자색이 함께 들어간다
  B6 조립: 실제 진입점(메인) 렌더 출력에 새 볼 마크업이 나온다

pytest 없이 돌도록 표준 assert + __main__ 러너를 둔다.
"""

from __future__ import annotations

import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _path in (str(ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import ball_style  # noqa: E402

LIVE_SCREEN_FILES = (
    "user_page.py",
    "page_thunder.py",
    "page_auto.py",
    "page_hedge.py",
    "tarot/tarot_page.py",
    "admin_filter.py",
)
# 볼 전용 패턴 — 같은 색이 다른 용도(예: user_page의 .highlight 노란 글씨)로도
# 쓰이므로 색 하나만으로 막지 않고, 볼 코드에서만 나오는 형태를 막는다.
BALL_ONLY_PATTERNS = (
    "#fbc400",              # 공식 팔레트(볼 전용)
    "#69c8f2",
    "#ff7272",
    "#b0d840",
    "radial-gradient(circle at 35% 35%, #ffeb3b",   # 예전 노란 볼 그라디언트
    "radial-gradient(circle at 35% 35%, #4fc3f7",   # 예전 파란 볼
    "radial-gradient(circle at 35% 35%, #81c784",   # 예전 초록 볼
    "def get_ball_style",
    "def get_ball_color",
)


def test_B1_every_number_meets_contrast_on_all_stops():
    worst = None
    for number in range(1, 46):
        text = ball_style.ball_text_color(number)
        assert text in ("#111111", "#FFFFFF"), f"{number}: 흑/백이 아닌 글자색 {text}"
        for stop in ball_style.ball_stops(number):
            ratio = ball_style.contrast_ratio(text, stop)
            assert ratio >= 4.5, f"{number}: {text} on {stop} 대비 {ratio:.2f} < 4.5"
            if worst is None or ratio < worst[0]:
                worst = (ratio, number, stop, text)
    assert worst is not None
    print(f"    (lowest contrast {worst[0]:.2f} at number {worst[1]}: {worst[3]} on {worst[2]})")


def test_B2_boundaries_and_hostile_input():
    groups = {
        1: ball_style.ball_color(1),
        10: ball_style.ball_color(1),
        11: ball_style.ball_color(11),
        20: ball_style.ball_color(11),
        21: ball_style.ball_color(21),
        30: ball_style.ball_color(21),
        31: ball_style.ball_color(31),
        40: ball_style.ball_color(31),
        41: ball_style.ball_color(41),
        45: ball_style.ball_color(41),
    }
    for number, expected in groups.items():
        assert ball_style.ball_color(number) == expected, f"{number}: 구간 색이 다르다"
        assert ball_style.ball_stops(number) and ball_style.ball_text_color(number)

    for hostile in (0, -1, 46, 999, None, "abc"):
        assert ball_style.ball_color(hostile) == ball_style.FALLBACK_COLOR, (
            f"{hostile!r}: 범위 밖 값은 기본색으로 처리해야 한다"
        )
        # 예외 없이 그라디언트·글자색이 나와야 한다(화면이 죽지 않는다).
        assert "radial-gradient" in ball_style.ball_fill(hostile)
        assert ball_style.contrast_ratio(
            ball_style.ball_text_color(hostile), ball_style.ball_color(hostile)
        ) >= 4.5

    # 정수로 해석되는 값은 그 정수의 구간을 따른다(결정적·예외 없음).
    assert ball_style.ball_color("7") == ball_style.ball_color(7)
    assert ball_style.ball_color(3.7) == ball_style.ball_color(3)


def test_B3_groups_are_internally_consistent_and_distinct():
    by_group = [
        {ball_style.ball_color(n) for n in range(1, 11)},
        {ball_style.ball_color(n) for n in range(11, 21)},
        {ball_style.ball_color(n) for n in range(21, 31)},
        {ball_style.ball_color(n) for n in range(31, 41)},
        {ball_style.ball_color(n) for n in range(41, 46)},
    ]
    for index, colors in enumerate(by_group):
        assert len(colors) == 1, f"{index}번째 구간 안에서 색이 갈렸다: {colors}"
    flat = [next(iter(c)) for c in by_group]
    assert len(set(flat)) == len(flat), f"구간 색이 중복됐다: {flat}"


def test_B4_no_ball_palette_copies_in_live_screens():
    offenders: list[str] = []
    for rel in LIVE_SCREEN_FILES:
        path = ROOT / rel
        body = path.read_text(encoding="utf-8", errors="replace")
        for pattern in BALL_ONLY_PATTERNS:
            if pattern in body:
                offenders.append(f"{rel}: 볼 색 사본({pattern})이 남아 있다 — ball_style만 쓸 것")
    assert not offenders, "; ".join(offenders)


def test_B5_ball_html_carries_fill_and_contrast_text():
    html = ball_style.ball_html(1, size=26, font_size=12)
    assert "radial-gradient(circle at 35% 35%" in html, "채우기 그라디언트가 없다"
    assert f"color:{ball_style.ball_text_color(1)}" in html, "글자색이 채우기에서 유도되지 않았다"
    assert "color:white" not in html.lower(), "글자색이 흰색 고정이다"
    assert ">01<" in html, "두 자리 번호 표기가 아니다"
    # 노란 볼은 흰 글씨가 물리적으로 불가능(대비 1.4) → 어두운 글자여야 한다.
    assert ball_style.ball_text_color(1) == "#111111", "노란 볼 글자색이 어둡지 않다"


def test_B6_main_page_render_uses_new_ball_markup():
    from streamlit.testing.v1 import AppTest

    import _db_isolation

    with _db_isolation.isolated_db():
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
        at.query_params["page"] = "main"
        at.query_params["gid"] = "ballstylecheck"
        at.run()
        assert not at.exception, f"메인 렌더 예외: {at.exception}"
        rendered = "\n".join(m.value or "" for m in at.markdown)
        assert "radial-gradient(circle at 35% 35%" in rendered, "화면에 볼 채우기가 안 나왔다"
        assert "color:#111111" in rendered or "color:#FFFFFF" in rendered, (
            "화면에 대비가 확보된 볼 글자색이 안 나왔다"
        )


def _main() -> int:
    import os

    tests = [
        test_B1_every_number_meets_contrast_on_all_stops,
        test_B2_boundaries_and_hostile_input,
        test_B3_groups_are_internally_consistent_and_distinct,
        test_B4_no_ball_palette_copies_in_live_screens,
        test_B5_ball_html_carries_fill_and_contrast_text,
        test_B6_main_page_render_uses_new_ball_markup,
    ]
    failed = 0
    for test in tests:
        try:
            test()
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001 — 러너이므로 무엇이든 보고하고 계속
            failed += 1
            print(f"ERROR {test.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
        sys.stdout.flush()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
