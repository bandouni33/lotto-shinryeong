"""다이얼로그 열기·재개 기준점(dialog_registry) 계약 검증 — 2026-09-26.

왜 이 테스트가 필요한가: `af_show_subscribe`(고급필터 구독창)가 매핑 사슬에서
빠져 있어서 로그인을 마쳐도 창이 열리지 않았고, 반대로 호출부도 소비부도 없는
`af_show_step1_points`/`af_show_step2_points`가 죽은 분기로 남아 있었다. 같은
유형이 다시 생기지 않도록 이름·플래그·문서가 서로 어긋나면 실패시킨다.

  D1 화면 코드의 모든 resume 문자열이 레지스트리에 등록돼 있다
  D2 등록된 플래그는 실제로 어느 화면이 읽는다(consumer 존재)
  D3 재개 요청이 있는 항목은 그 호출부 파일에 이름이 실제로 있다
  D4 apply()가 모든 등록 항목에 대해 선언한 플래그·데이터를 세운다(전수)
  D5 루트 AGENTS.md의 재개 이름 목록이 레지스트리와 일치한다
  D6 제거된 죽은 이름이 코드에 되살아나지 않았다
  D7 user_scope의 로그아웃 정리 목록이 레지스트리에서 파생된다

pytest 없이 돌도록 표준 assert + __main__ 러너를 둔다.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _path in (str(ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import dialog_registry  # noqa: E402
import user_scope  # noqa: E402

SKIP_DIRS = {"venv312", "node_modules", ".git", "__pycache__", ".expo", "builds", "data", "scratch"}
AGENTS = ROOT / "AGENTS.md"


def _py_files() -> list[Path]:
    files: list[Path] = []
    for path in list(ROOT.glob("*.py")) + list(ROOT.glob("tarot/*.py")) + list(ROOT.glob("tests/*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if ".bak" in path.name or "_backup" in path.name:
            continue
        files.append(path)
    return files


def _resume_literals() -> dict[str, list[str]]:
    """코드에 직접 쓰인 resume="..." 문자열을 (이름 → 파일들)로 모은다."""
    found: dict[str, list[str]] = {}
    for path in _py_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg != "resume" or not isinstance(keyword.value, ast.Constant):
                    continue
                value = keyword.value.value
                if isinstance(value, str) and value:
                    found.setdefault(value, []).append(str(path.relative_to(ROOT)))
    return found


def test_D1_every_resume_literal_is_registered():
    registered = set(dialog_registry.names())
    unknown = {name: files for name, files in _resume_literals().items() if name not in registered}
    assert not unknown, f"레지스트리에 없는 resume 이름을 쓰고 있다: {unknown}"


def test_D2_every_registered_flag_has_a_consumer():
    missing: list[str] = []
    for name, target in dialog_registry.DIALOGS.items():
        consumer = target.consumer
        assert consumer, f"{name}: consumer가 지정되지 않았다(누가 이 창을 띄우는지 불명)"
        path = ROOT / consumer
        assert path.exists(), f"{name}: consumer 파일이 없다: {consumer}"
        body = path.read_text(encoding="utf-8", errors="replace")
        if target.flag not in body:
            missing.append(f"{name} → {consumer}에서 {target.flag!r}를 읽지 않는다")
    assert not missing, "; ".join(missing)


def test_D3_registered_resume_callers_actually_request_it():
    literals = _resume_literals()
    # 이름을 리터럴로 쓰지 않고 DIALOGS[...]로 참조하는 코드도 호출부로 인정한다.
    problems: list[str] = []
    for name, target in dialog_registry.DIALOGS.items():
        if not target.resume_caller:
            continue
        path = ROOT / target.resume_caller
        assert path.exists(), f"{name}: resume_caller 파일이 없다: {target.resume_caller}"
        body = path.read_text(encoding="utf-8", errors="replace")
        if name in literals.get(name, []) or name in body:
            continue
        problems.append(f"{name} → {target.resume_caller}에 재개 요청이 없다")
    assert not problems, "; ".join(problems)


def test_D4_apply_sets_declared_flag_and_data_for_every_entry():
    """로그인을 마친 직후의 상태 전이를 모든 등록 항목에 대해 전수 확인한다."""
    original = dialog_registry._session_state
    try:
        for name, target in dialog_registry.DIALOGS.items():
            state: dict = {}
            dialog_registry._session_state = lambda _s=state: _s  # type: ignore[assignment]
            payload = {key: f"value-{key}" for _, key in target.data}
            assert dialog_registry.apply(name, payload) is True, f"{name}: apply가 실패했다"
            assert state.get(target.flag) is True, f"{name}: 플래그 {target.flag!r}가 안 세워졌다"
            for session_key, data_key in target.data:
                assert state.get(session_key) == payload[data_key], (
                    f"{name}: {session_key!r}에 {data_key!r} 값이 안 옮겨졌다"
                )
            # 알 수 없는 이름은 아무 것도 건드리지 않는다(묵은 resume 사고 방지).
            untouched: dict = {}
            dialog_registry._session_state = lambda _s=untouched: _s  # type: ignore[assignment]
            assert dialog_registry.apply("존재하지_않는_이름", payload) is False
            assert untouched == {}, "등록되지 않은 이름인데 상태가 바뀌었다"
            dialog_registry._session_state = lambda _s=state: _s  # type: ignore[assignment]
    finally:
        dialog_registry._session_state = original


def test_D5_agents_md_lists_the_same_resume_names():
    assert AGENTS.exists(), "루트 AGENTS.md가 없다 — 기준점 문서가 있어야 한다"
    body = AGENTS.read_text(encoding="utf-8")
    missing = [name for name in dialog_registry.names() if name not in body]
    assert not missing, f"AGENTS.md에 빠진 재개 이름: {missing}"


def test_D6_removed_dead_names_stay_removed():
    # 리터럴로 쓰면 이 테스트 자신이 걸리므로 조각으로 만든다.
    dead = ["af_show_" + "step1_points", "af_show_" + "step2_points"]
    # 예외 둘: 기준점 파일(dialog_registry)은 "무엇을 왜 제거했는지" 이력을 적어두고,
    # 이 테스트 파일은 금지 목록을 담는다 — 둘 다 코드에서 쓰는 게 아니다.
    allowed = {"dialog_registry.py", "tests/test_dialog_registry.py"}
    offenders: list[str] = []
    for path in _py_files():
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if rel in allowed:
            continue
        body = path.read_text(encoding="utf-8", errors="replace")
        for name in dead:
            if name in body:
                offenders.append(f"{rel}: {name}")
    assert not offenders, f"제거한 죽은 재개 이름이 남아 있다: {offenders}"


def test_D7_logout_keys_are_derived_from_registry():
    routed = user_scope._LOGOUT_EXACT_KEYS
    for key in dialog_registry.logout_keys():
        assert key in routed, f"로그아웃 정리 목록에 {key!r}가 빠졌다(다이얼로그 플래그 누락)"


def test_D8_insufficient_balance_dialog_has_exactly_one_render_site():
    """적립금 부족/충전창은 **한 곳에서만** 띄운다(2026-09-26 규격).

    화면이 자기 분기 안에서 대신 띄우면, 창을 열어둔 플래그를 닫기 콜백이 먼저
    내려버려 창이 아예 안 뜨는 사고가 화면마다 다르게 난다(타로 실기기 신고).
    호출(`open_insufficient_balance_dialog`)은 화면에서 해도 되지만, 띄우는 자리는
    wallet_ui.render_wallet_bar 한 곳뿐이어야 한다."""
    import re

    offenders: list[str] = []
    for path in sorted(list(ROOT.glob("*.py")) + list(ROOT.glob("tarot/*.py"))):
        if path.name == "wallet_ui.py":
            continue
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"^\s*insufficient_balance_dialog\(\)", text, re.M):
            line = text[: match.start()].count("\n") + 1
            offenders.append(f"{path.name}:{line}")
    assert offenders == [], (
        "적립금 부족/충전창을 화면에서 직접 띄우고 있다 - 공통 자리(wallet_ui.render_wallet_bar)만 "
        f"쓰도록 통일할 것: {offenders}"
    )

    wallet_ui_src = (ROOT / "wallet_ui.py").read_text(encoding="utf-8")
    call_sites = re.findall(
        r"^\s*insufficient_balance_dialog\(\)\s*$", wallet_ui_src, re.M
    )
    assert len(call_sites) == 1, (
        "wallet_ui 안에서 부족/충전창을 띄우는 자리가 정확히 하나여야 한다: "
        f"{len(call_sites)}곳"
    )


def test_D9_every_notice_screen_flag_is_registered_as_trigger():
    """적립금 안내창을 여는 네 화면의 플래그는 모두 points_notice_trigger로 등록된다.

    빠진 화면은 X로 닫아도 플래그가 남아 창이 곧바로 다시 뜨고(X 먹통), 자동구매만
    정상인 것처럼 보인다(2026-09-26 실기기 신고 - 타로가 빠져 있었다)."""
    import re

    trigger_flags = set(dialog_registry.points_notice_trigger_flags())
    missing: list[str] = []
    for rel in ("page_thunder.py", "page_hedge.py", "page_auto.py", "tarot/tarot_page.py"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        for match in re.finditer(r"points_notice_dialog\(\s*\"(\w+)\"", text):
            head = text[: match.start()]
            flags = re.findall(r'st\.session_state\.get\("([a-z_]+)"\)', head)
            assert flags, f"{rel}: 안내창을 열어둔 플래그를 찾지 못했다"
            if flags[-1] not in trigger_flags:
                missing.append(f"{rel}:{flags[-1]}")
    assert missing == [], (
        "적립금 안내창을 여는 화면인데 X닫기 플래그로 등록되지 않았다(창이 다시 떠서 X 먹통): "
        f"{missing}"
    )


def _main() -> int:
    tests = [
        test_D1_every_resume_literal_is_registered,
        test_D2_every_registered_flag_has_a_consumer,
        test_D3_registered_resume_callers_actually_request_it,
        test_D4_apply_sets_declared_flag_and_data_for_every_entry,
        test_D5_agents_md_lists_the_same_resume_names,
        test_D6_removed_dead_names_stay_removed,
        test_D7_logout_keys_are_derived_from_registry,
        test_D8_insufficient_balance_dialog_has_exactly_one_render_site,
        test_D9_every_notice_screen_flag_is_registered_as_trigger,
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
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
