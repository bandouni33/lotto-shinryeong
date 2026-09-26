"""타로 상세페이지 실기기 신고 4건 재현 (2026-09-26, 사용자 제보).

신고 내용(모바일 실기기)
  ① 적립금 이용안내창 우측상단 X가 먹통 — 자동구매창에서는 X가 먹힌다(통일성 문제)
  ② '확인 후 진행'을 누르면 충전창이 안 뜨고 '50P로 한 번 더 뽑기' 화면으로 회귀
  ③ 같은 화면의 '처음으로' 버튼 먹통
  ④ 그 과정에서 '점검 중' 안내 화면(페이지 렌더 예외)이 보임

이 파일은 그 4건을 실제 화면 렌더(AppTest)로 **재현**해 사실로 고정한다 — 통과를
전제로 쓴 테스트가 아니라, 지금 실기기에서 보이는 현상을 코드 레벨에서 확인하는
재현 테스트다(고치면 통과로 바뀐다). DB는 _db_isolation.isolated_db()로만 만진다.
"""

from __future__ import annotations

import sys
import urllib.parse
import uuid
from pathlib import Path

from streamlit.testing.v1 import AppTest

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _path in (str(ROOT), str(TESTS_DIR), str(ROOT / "tarot")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import _db_isolation  # noqa: E402
import wallet_db as wdb  # noqa: E402

PROBE = str(TESTS_DIR / "_tarot_gate_probe.py")
TIMEOUT_SEC = 60


def _member_zero_balance(handle: str) -> int:
    """잔액 0인 회원 — '적립금 부족 → 충전창' 경로를 타게 하려면 필요하다."""
    wdb.init_wallet_tables()
    mid, _new = wdb.get_or_create_member("kakao", handle)
    mid = int(mid)
    balance = int(wdb.get_balance(mid) or 0)
    if balance > 0:
        wdb.deduct_points(mid, balance, "test:zero", f"test:zero:{mid}:{uuid.uuid4().hex[:8]}")
    return mid


def _render_gate(mid: int, gid: str = "tarotgidentry") -> AppTest:
    """오늘 무료 뽑기를 다 쓴 상태로 타로 화면을 그린다(**실제 진입점 app.py 경유**).

    화면 함수를 직접 부르지 않는 이유: 적립금 부족/충전창을 띄우는 자리는 모든
    화면 공통 구역(user_page.py → wallet_ui.render_wallet_bar)이라, 페이지 함수를
    직접 부르면 그 자리가 아예 실행되지 않아 실제 동작과 달라진다."""
    import tarot_page

    at = AppTest.from_file(ENTRY, default_timeout=TIMEOUT_SEC)
    at.query_params["page"] = "tarot"
    at.query_params["gid"] = gid
    at.query_params["native"] = "1"
    at.session_state["member_id"] = mid
    at.session_state["_guest_id"] = gid
    at.session_state["tarot_daily_date"] = tarot_page._today_str()
    at.session_state["tarot_daily_count"] = tarot_page.MAX_DAILY_DRAWS
    at.run()
    return at


def _keys(at: AppTest) -> list[str]:
    return [b.key for b in at.button]


def _click(at: AppTest, key: str) -> AppTest:
    for button in at.button:
        if button.key == key:
            return button.click().run()
    raise AssertionError(f"버튼을 찾지 못했다: {key} (있던 키: {_keys(at)})")


def _body(at: AppTest) -> str:
    return "\n".join((m.value or "") for m in at.markdown)


SUBMIT_SCREENS = (
    "page_thunder.py",
    "page_hedge.py",
    "page_auto.py",
    "tarot/tarot_page.py",
)


def _notice_flags_from_source() -> list[tuple[str, str]]:
    """네 화면이 적립금 안내창을 열 때 쓰는 (파일, 플래그) 전부 — **소스에서 파생**한다.

    화면을 손으로 찍어 검사하면 나머지 한 곳이 또 어긋나므로(실제 사고),
    각 화면의 `points_notice_dialog(` 호출 바로 앞에서 그 창을 열어둔 플래그를
    찾아낸다 — 화면을 새로 추가해도 이 검사에 자동으로 들어온다.
    (QR 스캐너 트리거같이 적립금 안내창이 아닌 플래그는 여기 안 잡힌다.)"""
    import re

    found: list[tuple[str, str]] = []
    for rel in SUBMIT_SCREENS:
        text = (ROOT / rel).read_text(encoding="utf-8")
        for match in re.finditer(r"points_notice_dialog\(\s*\"(\w+)\"", text):
            head = text[: match.start()]
            flags = re.findall(r'st\.session_state\.get\("([a-z_]+)"\)', head)
            assert flags, f"{rel}: 안내창을 열어둔 플래그를 찾지 못했다"
            found.append((rel, flags[-1]))
    return found


def _assert_flags_are_registered(owners: list[tuple[str, str]]) -> None:
    """파생한 플래그가 기준점(dialog_registry)에 실제로 등록돼 있는지 —
    등록 밖 플래그를 쓰면 X닫기·로그아웃 정리에서 조용히 빠진다."""
    import dialog_registry

    registered = {spec.flag for spec in dialog_registry.DIALOGS.values()}
    unknown = sorted({flag for _rel, flag in owners} - registered)
    assert unknown == [], f"기준점에 등록되지 않은 안내창 플래그: {unknown}"


def test_T1_dismiss_closes_the_notice_on_every_screen():
    """① 통일성(전수): X로 닫으면 네 화면의 적립금 안내창이 **모두** 닫혀야 한다.

    하나라도 남으면 그 화면에서는 다음 렌더에 안내창이 다시 떠서 X가 먹통으로
    보인다 — 자동구매가 정상이라고 통일된 것이 아니다."""
    with _db_isolation.isolated_db():
        owners = _notice_flags_from_source()
        _assert_flags_are_registered(owners)
        assert len(owners) >= 4, f"검사 대상 화면이 4개 미만이다: {owners}"
        flags = [flag for _rel, flag in owners]

        at = AppTest.from_file(PROBE, default_timeout=TIMEOUT_SEC)
        at.query_params["probe"] = "dismiss"
        at.query_params["flags"] = ",".join(flags)
        at.run()
        assert not at.exception, f"프로브 렌더 예외: {at.exception}"

        survivors = list(at.session_state["probe_survivors"])
        assert at.session_state["probe_auto_flag"] is False, (
            "기준 동작(자동구매)부터 어긋났다 - 검사 자체가 무의미해진다"
        )
        assert survivors == [], (
            "X로 닫아도 안내창 플래그가 남는 화면이 있다 - 그 화면은 창이 곧바로 "
            f"다시 떠서 X가 먹통으로 보인다: {survivors} (대상: {owners})"
        )


def test_T2_confirm_without_balance_opens_charge_dialog():
    """② 잔액 부족으로 '확인 후 진행'하면 그 자리에서 통합 충전창이 떠야 한다."""
    with _db_isolation.isolated_db():
        mid = _member_zero_balance("tarot_t2")
        at = _render_gate(mid)
        assert "tarot_extra_draw_btn" in _keys(at), f"추가뽑기 버튼이 없다: {_keys(at)}"

        at = _click(at, "tarot_extra_draw_btn")
        assert "pn_confirm_tarot" in _keys(at), (
            f"적립금 안내창이 안 떴다(게이트 -> 안내창 배선): {_keys(at)}"
        )

        at = _click(at, "pn_confirm_tarot")
        assert "점검 중" not in _body(at), (
            f"확인 후 페이지가 예외로 '점검 중' 화면이 됐다: {at.exception}"
        )
        assert not at.exception, f"확인 후 페이지 예외: {at.exception}"
        assert "insufficient_balance_close" in _keys(at), (
            "적립금 부족/충전창이 안 떴다 - 50P 화면으로 회귀: " f"{_keys(at)}"
        )


def test_T3_gate_uses_the_shared_main_link_and_has_no_dead_button():
    """③ 이동 버튼은 규격: 이 화면도 다른 화면과 같은 공통 "메인 이동" 링크 하나만 쓴다.

    예전에는 st.button("처음으로")가 따로 있었는데, 오늘 뽑기를 다 쓴 상태에서는 이
    화면이 곷 "처음"이라 눌러도 같은 게이트가 다시 떠서 먹통으로 보였다."""
    with _db_isolation.isolated_db():
        mid = _member_zero_balance("tarot_t3")
        gid = "tarotgidt3"
        at = _render_gate(mid, gid=gid)
        keys = _keys(at)
        assert "tarot_extra_draw_btn" in keys, f"추가뽑기 게이트가 아니다: {keys}"
        assert "tarot_extra_gate_home" not in keys, (
            "게이트에 화면 전용 '처음으로' 버튼이 남아 있다 - 공통 메인 이동 링크 규격 위반"
        )
        body = _body(at)
        assert 'class="brand-home-link"' in body, (
            "게이트 화면에 공통 메인 이동 링크(shared_ui_styles 아이콘 링크)가 없다"
        )
        href = (
            body.split('class="brand-home-link"', 1)[0]
            .rsplit('href="', 1)[1]
            .split('"', 1)[0]
        )
        query = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        assert query.get("page") == ["main"], f"메인 링크의 page가 main이 아니다: {href!r}"
        assert query.get("native") == ["1"], f"메인 링크에서 native=1이 유실됐다: {href!r}"
        assert query.get("gid") == [gid], f"메인 링크에서 gid가 유실됐다: {gid!r} -> {href!r}"


ENTRY = str(ROOT / "app.py")


def test_T4_entry_point_renders_tarot_page():
    """조립 검증: 사용자가 실제로 여는 진입점(app.py)의 타로 라우트를 그대로 렌더해,
    기대 요소(카테고리 선택 또는 게이트)가 실제 출력에 나오는지 본다.

    app.py는 페이지 예외를 잡아 '점검 중' 화면으로 바꾸므로, 예외 목록만 보면 안 되고
    그려진 내용까지 확인해야 한다(안티·액땜 진입점 테스트와 같은 판정 방식)."""
    with _db_isolation.isolated_db():
        wdb.init_wallet_tables()
        mid, _new = wdb.get_or_create_member("kakao", "tarot_entry")
        at = AppTest.from_file(ENTRY, default_timeout=TIMEOUT_SEC)
        at.query_params["page"] = "tarot"
        at.query_params["gid"] = "entrytarot01"
        at.query_params["native"] = "1"
        at.session_state["member_id"] = int(mid)
        at.session_state["_guest_id"] = "entrytarot01"
        at.run()

        assert not at.exception, f"진입점 타로 렌더 예외: {at.exception}"
        assert "점검 중" not in _body(at), "진입점이 예외로 '점검 중' 화면을 대신 보여줬다"
        keys = _keys(at)
        assert any(k.startswith("cat_") for k in keys) or "tarot_extra_draw_btn" in keys, (
            f"타로 페이지의 기대 요소가 실려 나가지 않았다: {keys}"
        )
        print(f"  (진입점 page=tarot 렌더 OK - 버튼 {keys[:6]})")


def _main() -> int:
    tests = [
        test_T1_dismiss_closes_the_notice_on_every_screen,
        test_T2_confirm_without_balance_opens_charge_dialog,
        test_T3_gate_uses_the_shared_main_link_and_has_no_dead_button,
        test_T4_entry_point_renders_tarot_page,
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
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
