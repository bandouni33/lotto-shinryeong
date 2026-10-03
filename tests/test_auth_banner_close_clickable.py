"""인증 배너의 닫기(×)를 누를 수 있는가 — 2026-10-03 운영 실측으로 잠근다.

배포본 실측(430x932): 메인 화면의 "📖 사용설명서" 버튼은
manual_ui.render_manual_trigger_button()이 `.st-key-manual_trigger_wrap` 으로
position:fixed; top:56px; z-index:999 에 고정한다. 좁은 폭에서는 그 버튼이
배너의 × 와 같은 좌표에 겹치고(사용설명서 300~418 × 56~88 / × 368~390 × 57~79),
z-index 999 > 100 이라 이긴다. 그래서 × 자리를 누르면 클릭이 사용설명서로 가고
배너는 닫히지 않았다 — 배너 z-index 를 100 -> 1000 으로 올려 × 가 그 픽셀을
가져가게 했다(999 에서는 아직 사용설명서가 가져감, 1000 부터 × 가 가져감: 실측).

여기서 잠그는 것은 "배너가 그 플로팅 버튼보다 위에 있어야 한다"는 관계다.
숫자 하나만 박아두면 상대쪽(manual_ui)이 바뀌어도 안 깨지므로, 두 파일에서
값을 각각 읽어 비교한다.

  Z1 배너 z-index 가 사용설명서 버튼 z-index 보다 크다 (관계가 핵심)
  Z2 배너 규칙이 specificity(div[data-testid=...])와 !important 를 유지한다
  Z3 배너는 여전히 position:sticky + top:0 이다 (수정이 그걸 뭉개지 않았다)
  Z4 배너 폭(max-width 325px)이 그대로다 (수정이 레이아웃을 안 건드렸다)
  Z5 상대쪽(manual_ui) 전제가 그대로인지도 확인해 바뀌면 사람이 다시 보게 한다
  Z6 불변식 자체가 옛 값을 잡는지 — 합성 입력으로 자기검증한다

pytest 없이 돌도록 표준 assert + __main__ 러너를 둔다(AGENTS §3).
실행: venv312\\Scripts\\python.exe tests\\test_auth_banner_close_clickable.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WALLET = (ROOT / "wallet_ui.py").read_text(encoding="utf-8")
MANUAL = (ROOT / "manual_ui.py").read_text(encoding="utf-8")

BANNER_SEL = 'div[data-testid="stVerticalBlock"].st-key-auth_banner_wrap'
MANUAL_SEL = ".st-key-manual_trigger_wrap"


def _rule_body(source: str, selector: str) -> str:
    """CSS 규칙 하나의 본문({ } 안)을 떼어낸다 — 선언 하나만 보고 판정하지 않기 위해."""
    idx = source.find(selector)
    assert idx >= 0, f"{selector} 규칙을 찾을 수 없다"
    start = source.find("{", idx)
    assert start >= 0, f"{selector} 뒤에 중괄호가 없다"
    depth, i = 0, start
    while i < len(source):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
        i += 1
    raise AssertionError(f"{selector} 규칙이 닫히지 않았다")


def _z_index(body: str) -> int:
    m = re.search(r"z-index\s*:\s*(\d+)\s*!important", body)
    assert m, f"z-index !important 선언이 없다: {body[:120]}"
    return int(m.group(1))


def banner_beats_manual(wallet_src: str, manual_src: str) -> bool:
    """관계 판정을 순수 함수로 빼둔다 — Z6이 옛 값으로 자기검증할 수 있게."""
    return _z_index(_rule_body(wallet_src, BANNER_SEL)) > \
        _z_index(_rule_body(manual_src, MANUAL_SEL))


BANNER_BODY = _rule_body(WALLET, BANNER_SEL)
MANUAL_BODY = _rule_body(MANUAL, MANUAL_SEL)


# ── Z1 관계 ─────────────────────────────────────────────────
def test_Z1_banner_z_index_beats_the_pinned_manual_button():
    banner_z = _z_index(BANNER_BODY)
    manual_z = _z_index(MANUAL_BODY)
    assert banner_z > manual_z, (
        f"배너 z-index({banner_z})가 사용설명서 버튼 z-index({manual_z}) 이하다 — "
        "폰 폭에서 사용설명서가 × 를 덮어 배너를 닫을 수 없다(2026-10-03 실측)"
    )


# ── Z2 선택자·강제 ───────────────────────────────────────────
def test_Z2_banner_rule_keeps_specificity_and_important():
    assert 'div[data-testid="stVerticalBlock"].st-key-auth_banner_wrap' in WALLET, (
        "클래스 단일 선택자로 돌아가면 Streamlit 자체 stVerticalBlock 규칙에 진다"
    )
    assert re.search(r"z-index\s*:\s*\d+\s*!important", BANNER_BODY), (
        "z-index 에 !important 가 없다 — Streamlit 기본 규칙에 질 수 있다"
    )


# ── Z3 배너 동작 유지 ────────────────────────────────────────
def test_Z3_banner_is_still_sticky_at_top():
    assert "position: sticky !important" in BANNER_BODY, (
        "배너가 sticky 가 아니게 됐다 — 상단 고정 동작이 바뀐다"
    )
    assert re.search(r"top:\s*0\s*!important", BANNER_BODY), (
        "배너 top:0 이 사라졌다"
    )


# ── Z4 레이아웃 무변화 ───────────────────────────────────────
def test_Z4_banner_width_is_unchanged():
    # 운영 실측에서 100·999·1000 모두 배너 rect 가 53,54~378,146 으로 같았다 —
    # z-index 만 바꾸는 수정이며 폭/여백을 건드리지 않았음을 잠근다.
    assert "max-width: 325px !important" in BANNER_BODY, (
        "배너 폭이 바뀌었다 — 이번 수정은 z-index 만 건드려야 한다"
    )
    assert "margin: 10px auto 12px auto !important" in BANNER_BODY


# ── Z5 상대쪽 전제 ───────────────────────────────────────────
def test_Z5_manual_button_is_still_pinned_over_the_banner():
    # 이 전제가 바뀌면(예: 겹치지 않게 옮겨짐) 위 관계의 근거도 바뀐다 —
    # 그때는 사람이 다시 재고 이 테스트를 갱신해야 한다.
    assert "position: fixed !important" in MANUAL_BODY, (
        "사용설명서 버튼이 더 이상 fixed 가 아니다"
    )
    m = re.search(r"top:\s*(\d+)px\s*!important", MANUAL_BODY)
    assert m, "사용설명서 버튼의 top 이 없다"
    assert int(m.group(1)) == 56, (
        f"사용설명서 버튼 top 이 {m.group(1)}px 로 바뀌었다 — 배너의 × 와 겹치는지 "
        "다시 실측하고 이 테스트를 갱신할 것"
    )
    assert re.search(r"right:\s*12px\s*!important", MANUAL_BODY)


# ── Z6 불변식 자기검증 ───────────────────────────────────────
def test_Z6_invariant_catches_the_old_value():
    # 옛 값(배너 100)으로 만든 합성 입력에서 관계가 깨져야 한다 —
    # 그러지 않으면 이 테스트는 아무것도 잠그지 못하는 것이다.
    old_wallet = WALLET.replace("z-index: 1000 !important;",
                                "z-index: 100 !important;")
    assert old_wallet != WALLET, "배너 z-index 선언을 못 찾았다(치환 실패)"
    assert not banner_beats_manual(old_wallet, MANUAL), (
        "옛 값(100)인데도 통과한다 — 이 테스트가 관계를 잠그지 못한다"
    )
    # 상대쪽을 배너보다 낮춘 경우(예: 50)도 통과해야 한다.
    lowered = MANUAL.replace("z-index: 999 !important;", "z-index: 50 !important;")
    assert lowered != MANUAL
    assert banner_beats_manual(WALLET, lowered)


def _main() -> int:
    import os

    tests = [
        test_Z1_banner_z_index_beats_the_pinned_manual_button,
        test_Z2_banner_rule_keeps_specificity_and_important,
        test_Z3_banner_is_still_sticky_at_top,
        test_Z4_banner_width_is_unchanged,
        test_Z5_manual_button_is_still_pinned_over_the_banner,
        test_Z6_invariant_catches_the_old_value,
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
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
