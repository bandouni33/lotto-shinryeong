"""사용설명서 다이얼로그의 개인정보 비수집 고지 (2026-09-26 사용자 지시).

문구·위치·색 조건을 전부 불변식으로 잡는다:
  P1. 다이얼로그를 실제로 열면(진입점 렌더) 문구가 **실제로 출력에 나온다**.
  P2. 위치는 제목("📖 사용설명서") 바로 아래·차례(첫 항목 타로점) 위 — 즉 차례
      블록보다 먼저 렌더된다(순서 불변식).
  P3. "도형 없이 텍스트만" — 배경·테두리·아이콘이 없다.
  P4. 색은 흰 배경에서 읽히는 진한 남색(#1f2650) + 굵게, 그리고 금색(#ffd479)이
      아니다 — 다이얼로그 본문이 흰 배경이라 금색이면 안 보인다(원래 안 보였던 원인).

pytest 없이도 돌도록 표준 assert + __main__ 러너를 둔다(이 프로젝트 규칙).
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TIMEOUT_SEC = 60
NOTICE = "번호 생성, 보관 등 앱 이용의 어떠한 개인정보도 수집하지 않습니다."
BADGE = "ln-manual-privacy"

# 실제 진입점(app.py)이 아니라 다이얼로그 자체를 여는 경로 — 이 다이얼로그는
# 메인화면 버튼 콜백이 플래그를 세우면 다음 렌더에서 열린다(maybe_open_manual).
_APP = r"""
import streamlit as st
import manual_ui

st.session_state[manual_ui.MANUAL_OPEN_FLAG] = True
manual_ui.maybe_open_manual()
"""


def _blocks(at: AppTest) -> list[str]:
    return [m.value or "" for m in at.markdown]


def _render_dialog() -> tuple[AppTest, list[str]]:
    at = AppTest.from_string(_APP, default_timeout=TIMEOUT_SEC)
    at.run()
    assert not at.exception, f"사용설명서 다이얼로그 렌더 예외: {at.exception}"
    return at, _blocks(at)


def test_P1_notice_is_actually_rendered_with_its_class():
    _, blocks = _render_dialog()
    hits = [b for b in blocks if NOTICE in b]
    assert hits, (
        "다이얼로그를 열었는데 개인정보 비수집 문구가 출력에 없다: "
        f"{[b[:40] for b in blocks[:6]]}"
    )
    assert any(BADGE in b for b in hits), (
        f"문구는 나오는데 전용 클래스({BADGE})가 안 붙었다 - CSS가 안 먹는다: {hits[0][:120]!r}"
    )
    print(f"  (문구 렌더 OK - 클래스 {BADGE})")


def test_P2_notice_comes_before_the_toc():
    _, blocks = _render_dialog()
    notice_i = [i for i, b in enumerate(blocks) if NOTICE in b]
    # 주의: "ln-manual-toc" 문자열은 <style> 블록(CSS 선택자)에도 들어있다 - 그걸
    # 차례로 오인하면 순서 판정이 뒤집힌다. 요소로 찍는다.
    toc_i = [i for i, b in enumerate(blocks) if '<div class="ln-manual-toc">' in b]
    assert notice_i, "문구가 렌더되지 않았다"
    assert toc_i, "차례(목차) 블록이 렌더되지 않았다 - 다이얼로그 구조가 바뀌었나?"
    assert notice_i[0] < toc_i[0], (
        f"문구가 차례보다 아래에 있다(위치 불변식 위반): 문구 {notice_i[0]} vs 차례 {toc_i[0]}"
    )
    print(f"  (문구 {notice_i[0]}번째 < 차례 {toc_i[0]}번째)")


def test_P3_P4_plain_text_readable_on_a_white_dialog():
    import manual_ui

    css = manual_ui.manual_css()
    rule = css.split(f".{BADGE}", 1)[1].split("}", 1)[0]
    assert "#1f2650" in rule, f"글자색이 진한 남색이 아니다(흰 배경에서 안 읽힘): {rule!r}"
    assert "#ffd479" not in rule, f"금색이 남아 있다 - 흰 배경에서 안 보인다: {rule!r}"
    assert "font-weight: 900" in rule, f"굵게 표시되지 않는다: {rule!r}"

    for banned in ("background", "border", "border-radius"):
        assert banned not in rule, f"'도형 없이 텍스트만' 위반 - {banned}가 있다: {rule!r}"

    # 아이콘·이모지 없이 문구만(요청: "도형없이 ... 텍스트만")
    html = manual_ui.manual_privacy_notice_html()
    assert re.fullmatch(rf'<div class="{BADGE}">[^<>]+</div>', html.strip()), (
        f"문구 블록에 텍스트 말고 다른 요소가 섞여 있다: {html!r}"
    )
    assert not _has_icon_or_invisible(html), f"아이콘/이모지가 들어갔다: {html!r}"
    print("  (진한 남색 #1f2650 · 굵게 · 배경/테두리/아이콘 없음)")


def _has_icon_or_invisible(text: str) -> bool:
    """아이콘·이모지·미표시 문자 판정.

    한글이 ord > 0x2500이라 단순 상한 비교로는 안 된다 — 그림문자 구역과, 이
    프로젝트가 실제로 사고를 견었던 제로폭 계열만 골라 검사한다."""
    for ch in text:
        cp = ord(ch)
        if 0x1F000 <= cp <= 0x1FAFF:  # 이모지·그림문자
            return True
        if 0x2600 <= cp <= 0x27BF:  # 기타 기호·딩벳
            return True
        if cp in (0x200B, 0x200C, 0x200D, 0xFE0F):
            return True
    return False


def test_P5_entry_point_manual_button_shows_the_notice():
    """조립 검증 — 사용자가 실제로 여는 길: app.py 메인화면의 "사용설명서" 버튼을
    눌렀을 때 그 다이얼로그 안에 문구가 들어 있는가(위 P1~P4는 다이얼로그 자체만
    열어 본 것이라, 버튼→플래그→다이얼로그 배선은 여기서 처음 본다)."""
    entry = str(ROOT / "app.py")
    at = AppTest.from_file(entry, default_timeout=TIMEOUT_SEC)
    at.query_params["page"] = "main"
    at.query_params["gid"] = "manualnotice01"
    at.query_params["native"] = "1"
    at.session_state["_guest_id"] = "manualnotice01"
    at.run()
    assert not at.exception, f"메인화면 렌더 예외: {at.exception}"

    keys = [b.key for b in at.button]
    assert "manual_trigger_btn" in keys, f"메인화면에 사용설명서 버튼이 없다: {keys}"
    for button in at.button:
        if button.key == "manual_trigger_btn":
            at = button.click().run()
            break
    assert not at.exception, f"사용설명서 열기에서 예외: {at.exception}"

    blocks = _blocks(at)
    assert any(NOTICE in b for b in blocks), (
        "진입점에서 사용설명서를 열었는데 문구가 실제 출력에 없다: "
        f"{[b[:40] for b in blocks[:8]]}"
    )
    print("  (진입점 메인 → 사용설명서 버튼 → 문구 확인)")


def _main() -> int:
    tests = [
        test_P1_notice_is_actually_rendered_with_its_class,
        test_P2_notice_comes_before_the_toc,
        test_P3_P4_plain_text_readable_on_a_white_dialog,
        test_P5_entry_point_manual_button_shows_the_notice,
    ]
    failed = 0
    for test in tests:
        try:
            test()
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"ERROR {test.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
        sys.stdout.flush()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.stdout.flush()
    # db_turso 등이 import 시점에 만드는 비데몬 스레드 때문에 프로세스가 스스로
    # 끝나지 않는다(다른 테스트 파일과 같은 현상) — 결과를 다 낸 뒤 즉시 종료한다.
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
