"""번개조합 "생일/행운수 관리" 이동을 진짜 <a href> 링크로 바꿔 달았는지 확인하는 테스트.

배경(2026-09-19): 이 이동만 st.query_params["page"]="birthday" + st.rerun()으로
"브라우저 새로고침 없이"(History API 갱신 + 같은 문서 rerun) 페이지를 갈아끼우고
있었고, 무거운 번호판 iframe/최상위 문서 스크립트를 들고 있는 번개조합 화면에서만
"반전·화면 2개"가 재현됐다. 다른 내부이동과 같은 진짜 <a href>로 바꿔서 클릭 시
브라우저가 문서를 완전히 새로 만들게 한다.

불변식:
  L1. 번개조합 화면이 예외 없이 렌더된다.
  L2. 렌더된 마크다운에 생일/행운수 링크가 존재하고, 그 href가
      ?page=birthday&gid=<현재 gid> 로 정확히 만들어진다(내부이동 규칙).
  L3. 그 href에는 th_save(결과저장 자동이동) 파라미터가 섞여 있지 않다 —
      결과저장 스크립트와 겹치지 않는다.
  L4. 예전 위젯(버튼 key th_nav_bday_6n36s5)은 사라졌다(같은 기능이 두 개로
      남아 두 번 그려지는 일이 없다).
  L5. 링크만 바꿔서 다른 요소(조합시작 버튼·게임 수 선택·저장내역 버튼·결과저장
      안전망 링크)는 그대로 살아 있다.
  L6. 결과저장 자동이동용 폴링 스크립트/안전망 링크(#th_save_real_link)가 여전히
      페이지에 있다(이번 변경으로 손대지 않았음을 고정).

한계: AppTest는 <a href>를 "클릭"해서 브라우저 이동을 일으킬 수 없다(위젯이 아니라
마크다운 HTML이다). 그래서 "클릭하면 실제로 ?page=birthday&gid=... 로 간다"는
부분은 브라우저가 그대로 따라갈 href를 실제 렌더 출력에서 꺼내 검증한다.

pytest 없이도 돌도록 표준 assert + __main__ 러너를 함께 둔다.
"""

from __future__ import annotations

import os
import sys
import urllib.parse
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
ENTRY = str(ROOT / "app.py")
TIMEOUT_SEC = 60

OLD_BUTTON_KEY = "th_nav_bday_6n36s5"
LINK_TEXT = "생일/행운수 관리"
SAVE_FALLBACK_ID = "th_save_real_link"


def _thunder_app(gid: str) -> AppTest:
    at = AppTest.from_file(ENTRY, default_timeout=TIMEOUT_SEC)
    at.query_params["page"] = "thunder"
    at.query_params["gid"] = gid
    at.run()
    return at


def _birthday_href(at: AppTest) -> str | None:
    """생일/행운수 링크의 href를 실제 렌더 출력(마크다운 값)에서 꺼낸다."""
    for m in at.markdown:
        value = m.value or ""
        if LINK_TEXT not in value:
            continue
        marker = 'href="'
        start = value.find(marker)
        if start == -1:
            continue
        start += len(marker)
        end = value.find('"', start)
        if end == -1:
            continue
        return value[start:end]
    return None


def test_birthday_nav_is_a_real_link_with_expected_href() -> None:
    """L1~L3 — 실제 진입점에서 링크가 렌더되고, href가 내부이동 규칙대로 만들어진다."""
    gid = "link" + os.urandom(6).hex()
    at = _thunder_app(gid)
    assert len(at.exception) == 0, f"thunder page raised: {at.exception}"

    href = _birthday_href(at)
    assert href is not None, (
        f"생일/행운수 링크를 렌더 출력에서 찾지 못했다 (markdown {len(at.markdown)}개)"
    )

    query = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
    assert query.get("page") == ["birthday"], f"page 파라미터가 birthday가 아니다: {href!r}"
    assert query.get("gid") == [gid], (
        f"gid가 현재 게스트 식별자로 실리지 않았다: 기대 {gid!r}, 실제 {query.get('gid')!r} ({href!r})"
    )
    assert "th_save" not in query, f"결과저장 파라미터가 링크에 섞여 있다: {href!r}"


def test_old_widget_is_gone_and_others_survive() -> None:
    """L4~L5 — 예전 버튼은 사라지고, 나머지 요소는 그대로다."""
    gid = "surv" + os.urandom(6).hex()
    at = _thunder_app(gid)
    assert len(at.exception) == 0, f"thunder page raised: {at.exception}"

    keys = [b.key for b in at.button]
    assert OLD_BUTTON_KEY not in keys, (
        f"예전 생일/행운수 버튼이 아직 남아 있다(같은 이동이 두 개): {keys}"
    )
    for expected in ("th_generate_btn", "th_history_zone_6n36s5_open_btn"):
        assert expected in keys, f"기대한 버튼이 사라졌다: {expected} (실제 {keys})"
    assert "th_game_count_select" in [s.key for s in at.selectbox], "게임 수 선택이 사라졌다"


def test_save_auto_navigation_path_is_untouched() -> None:
    """L6 — 결과저장 자동이동 안전망 링크가 그대로 살아 있다(겹침 방지용 고정)."""
    gid = "save" + os.urandom(6).hex()
    at = _thunder_app(gid)
    assert len(at.exception) == 0, f"thunder page raised: {at.exception}"
    assert any(SAVE_FALLBACK_ID in (m.value or "") for m in at.markdown), (
        "결과저장 안전망 링크(#th_save_real_link)가 사라졌다 — 결과저장 경로가 깨진다"
    )


def _main() -> int:
    tests = [
        test_birthday_nav_is_a_real_link_with_expected_href,
        test_old_widget_is_gone_and_others_survive,
        test_save_auto_navigation_path_is_untouched,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"ERROR {t.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"PASS {t.__name__}")
        sys.stdout.flush()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
