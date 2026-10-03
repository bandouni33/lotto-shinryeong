"""인증 배너 JS가 조작하는 "문서" 불변식 검증 — 2026-10-03.

배경(배포본 실측으로 확정): 배너의 JS 수정 함수들이 `window.top.document`를
조회했는데, 실사용자 주소(lotto-shinryeong.streamlit.app)에서는 앱이 Streamlit
Cloud 껍데기 문서 안의 iframe(/~/+)에서 돈다. 그 최상위 문서에는 앱 DOM
(.st-key-*)이 아예 없으므로 이 함수들은 셀렉터 0건으로 **조용히 무동작**했고,
둘 다 try/catch로 감싸여 있어 오류도 남지 않았다. 앱이 곧 최상위인 개발 중에는
top과 parent가 같은 문서라 정상으로 보였다 — 그래서 이 버그가 오래 숨았다.

  window.parent는 앱이 최상위든 껍데기 안이든 항상 "앱 문서"를 가리킨다.
  window.top은 앱이 프레임 안에 들어가는 순간 딴 문서가 된다.

그래서 여기서 고정하는 것은 "어느 문서를 조작하는가"와 "실패를 삼키지 않는가"다.

  T1 정리 함수가 window.parent.document를 쓴다 (window.top이 아니라)
  T2 대상 셀렉터가 실제로 유효한 선택자 목록으로 합쳐지고 세 컨테이너를 덮는다
  T3 그 세 키가 렌더 코드에 실재한다 (셀렉터가 헛돌지 않는다)
  T4 catch가 더 이상 빈 블록이 아니다 — 실패를 console.error로 남긴다
  T5 호출 조건은 그대로다 (보류된 ㉠을 실수로 켜지 않게 잠금)
  T6 주입 방식(components.html + height=0)이 유지된다

pytest 없이 돌도록 표준 assert + __main__ 러너를 둔다(AGENTS §3 테스트 실행 환경).
실행: venv312\\Scripts\\python.exe tests\\test_auth_banner_js_target.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SOURCE = (ROOT / "wallet_ui.py").read_text(encoding="utf-8")

CLEANUP_NAME = "_cleanup_stale_auth_banner_dom"
BANNER_KEYS = ("auth_banner_wrap", "auth_banner_box", "auth_banner_close_x")


def _function_source(name: str) -> str:
    """모듈 최상단 함수 하나의 소스를 그대로 떼어낸다.

    정규식으로 `def name`부터 다음 `def`까지 자르면 함수 안에 문자열로 들어있는
    `def`나 들여쓰기 변화에 속을 수 있어, AST로 노드 경계를 잡는다.
    """
    tree = ast.parse(SOURCE)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            segment = ast.get_source_segment(SOURCE, node)
            assert segment, f"{name} 소스를 못 떼어냈다"
            return segment
    raise AssertionError(f"{name} 함수 정의를 wallet_ui.py에서 찾을 수 없다")


CLEANUP = _function_source(CLEANUP_NAME)
RENDER = _function_source("render_auth_banner")


def _strip_python_docstring(name: str, func_source: str) -> str:
    """함수 독스트링 본문을 소스에서 뺀다(AST로 그 노드만 정확히 찾아 제거)."""
    tree = ast.parse(SOURCE)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            head = node.body[0] if node.body else None
            if (isinstance(head, ast.Expr) and isinstance(head.value, ast.Constant)
                    and isinstance(head.value.value, str)):
                return func_source.replace(head.value.value, "")
    return func_source


def _executable_only(name: str, func_source: str) -> str:
    """실행되는 줄만 남긴다 — 독스트링과 줄 전체 주석(//)을 뺀다.

    이 테스트가 막으려는 것은 "실행되는 JS가 최상위 문서를 조회하는 것"이지
    "그 버그를 설명하는 산문이 최상위 문서를 언급하는 것"이 아니다. 산문까지
    금지하면 설명을 지우게 되고, 그러면 다음 사람이 테스트를 약화시킨다.
    줄 전체가 주석인 줄만 지운다(문자열 안의 // 를 잘못 지우지 않기 위해).
    """
    text = _strip_python_docstring(name, func_source)
    keep = [line for line in text.splitlines() if not line.strip().startswith("//")]
    return "\n".join(keep)


CLEANUP_CODE = _executable_only(CLEANUP_NAME, CLEANUP)


def _selector_argument(func_source: str) -> str:
    """`querySelectorAll(<여기>)`의 인자를 JS 문자열 결합 규칙대로 이어붙인다.

    셀렉터는 소스에서 여러 조각으로 나뉘어 있으므로, 조각을 그냥 세는 것이
    아니라 실제로 합쳐서 하나의 선택자 목록이 되는지 봐야 한다 — 조각 하나에
    쉼표나 공백이 빠지면 브라우저에서 조용히 0건이 된다.
    """
    marker = "querySelectorAll("
    assert marker in func_source, f"querySelectorAll 호출이 없다: {func_source[:80]!r}"
    body = func_source.split(marker, 1)[1]
    end = body.index(")")
    argument = body[:end]
    pieces = [piece for piece in _single_quoted(argument)]
    assert pieces, f"셀렉터 문자열 리터럴을 못 찾았다: {argument!r}"
    return "".join(pieces)


def _single_quoted(text: str) -> list[str]:
    out, buf, inside = [], [], False
    for char in text:
        if char == "'":
            if inside:
                out.append("".join(buf))
                buf = []
            inside = not inside
        elif inside:
            buf.append(char)
    assert not inside, f"닫히지 않은 문자열 리터럴: {text!r}"
    return out


# ── T1 어느 문서를 조작하는가 ────────────────────────────────
def test_T1_cleanup_targets_the_parent_document_not_the_top():
    assert "window.parent.document" in CLEANUP_CODE, (
        "정리 함수가 부모 문서를 조회하지 않는다 — 실사용자 주소에서는 앱 DOM이 "
        "부모 문서에만 있다"
    )
    assert "window.top" not in CLEANUP_CODE, (
        "정리 함수의 실행 코드에 window.top이 남아 있다 — 앱이 Streamlit Cloud "
        "껍데기 안 iframe에서 돌면 window.top은 앱 문서가 아니라 딴 문서라 "
        "조용히 무동작한다"
    )


def test_T1b_stripping_left_the_real_payload_intact():
    # T1이 "아무것도 안 남아서 통과"하는 거짓 통과가 되지 않게, 주입되는 JS가
    # 살아 있는지 같이 본다.
    assert "components.html" in CLEANUP_CODE, "제거가 과해 주입 코드까지 지워졌다"
    assert "querySelectorAll" in CLEANUP_CODE, "제거가 과해 셀렉터까지 지워졌다"
    assert "forEach" in CLEANUP_CODE
    assert len(CLEANUP_CODE.strip().splitlines()) > 8, "남은 코드가 너무 적다"


# ── T2 대상 셀렉터 ──────────────────────────────────────────
def test_T2_selector_is_one_valid_list_covering_all_three_containers():
    selector = _selector_argument(CLEANUP)
    parts = [part.strip() for part in selector.split(",")]
    assert "" not in parts, f"빈 셀렉터 조각이 있다(결합 오류): {selector!r}"
    assert len(parts) == len(BANNER_KEYS), (
        f"대상 셀렉터가 {len(parts)}개다 — 정리할 컨테이너는 {len(BANNER_KEYS)}개다: "
        f"{selector!r}"
    )
    for key in BANNER_KEYS:
        assert f".st-key-{key}" in parts, f"{key}가 대상 셀렉터에 없다: {selector!r}"


# ── T3 셀렉터가 헛돌지 않는가 ─────────────────────────────────
def test_T3_target_keys_still_exist_in_the_render_code():
    # 지우려는 키가 렌더 코드에서 사라지면, 셀렉터는 영원히 0건을 찾는다.
    for key in BANNER_KEYS:
        assert f'st.container(key="{key}")' in SOURCE, (
            f'{key} 컨테이너가 렌더 코드에 없다 — 셀렉터가 헛돈다'
        )
    # 닫기(×)의 실제 버튼 키도 함께 확인한다(컨테이너만 남고 버튼이 바뀌면 잔재 형태가 달라진다).
    assert 'st.button("✕", key="auth_banner_close_x_btn")' in SOURCE


# ── T4 실패를 삼키지 않는가 ──────────────────────────────────
def test_T4_cleanup_reports_failure_instead_of_swallowing_it():
    assert "catch (e) {}" not in CLEANUP, (
        "catch가 여전히 빈 블록이다 — 실패가 조용히 삼켜져 이 버그처럼 오래 숨는다"
    )
    assert "console.error" in CLEANUP, "실패를 아무 데도 남기지 않는다"
    tail = CLEANUP.split("} catch (e) {", 1)
    assert len(tail) == 2, "catch (e) 블록 형태가 바뀌었다"
    catch_body = tail[1]
    assert "console.error" in catch_body, "catch 블록 밖에서만 로그를 남긴다"
    # 로그 자체가 던지면(console이 없는 컨텍스트 등) catch 안에서 예외가 새어
    # 나가 이 함수가 "절대 던지지 않는다"는 성질이 깨진다 — 다시 감싸야 한다.
    assert "try {" in catch_body, "console.error를 감싸지 않아 로그 실패가 예외로 샌다"


# ── T5 호출 조건 동결 ────────────────────────────────────────
def test_T5_call_site_is_still_only_the_deferred_guard():
    # ㉠(호출 조건 확대)은 사용자 지시로 보류됐다 — 지금 호출부는 "닫은 직후 1번"
    # 한 곳뿐이어야 한다. 여기서 세지 않으면 나중에 조용히 늘어난다.
    assert RENDER.count(f"{CLEANUP_NAME}()") == 1, (
        f"{CLEANUP_NAME} 호출부가 1곳이 아니다 — 보류된 호출 조건 변경이 섞였다"
    )
    assert "AUTH_BANNER_JUST_DISMISSED" in RENDER
    guard = RENDER.split("AUTH_BANNER_JUST_DISMISSED", 1)[1].split("return", 1)[0]
    assert f"{CLEANUP_NAME}()" in guard, (
        "정리 함수가 JUST_DISMISSED 가드 밖에서 불린다 — 매 렌더마다 iframe이 주입된다"
    )


# ── T6 주입 방식 유지 ────────────────────────────────────────
def test_T6_injection_mechanism_is_unchanged():
    assert "components.html(" in CLEANUP, "components.html 주입이 아니다"
    assert "height=0" in CLEANUP, "높이 0이 아니면 배너 자리에 빈 iframe이 남는다"
    assert "<script>" in CLEANUP and "</script>" in CLEANUP


def _main() -> int:
    import os

    tests = [
        test_T1_cleanup_targets_the_parent_document_not_the_top,
        test_T1b_stripping_left_the_real_payload_intact,
        test_T2_selector_is_one_valid_list_covering_all_three_containers,
        test_T3_target_keys_still_exist_in_the_render_code,
        test_T4_cleanup_reports_failure_instead_of_swallowing_it,
        test_T5_call_site_is_still_only_the_deferred_guard,
        test_T6_injection_mechanism_is_unchanged,
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
