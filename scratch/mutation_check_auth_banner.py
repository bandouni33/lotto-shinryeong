"""변조 검사 — tests/test_auth_banner_js_target.py가 "옛 코드"에서 실제로
실패하는지 확인한다. 새 코드에서만 통과하는 테스트는 아무것도 잠그지 않는다.

wallet_ui.py에서 각 함수 구간만 잠시 옛/틀린 형태로 되돌려 테스트를 돌리고,
성공·실패와 무관하게 원본 바이트를 되돌린다.

주의 1: 변조는 반드시 대상 함수 구간 안에서만 한다 — 파일 전체에서 첫 일치를
바꾸면 다른 함수를 건드려 검사가 무의미해진다.
주의 2: 변조본이 변조하려는 불변식 말고 다른 것도 깨면, 무엇을 잡았는지
알 수 없다. 변조본이 파이썬으로 읽히는지는 매번 확인한다.

실행: venv312\\Scripts\\python.exe scratch\\mutation_check_auth_banner.py
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "wallet_ui.py"
TEST = ROOT / "tests" / "test_auth_banner_js_target.py"

CLEANUP = "_cleanup_stale_auth_banner_dom"
KAKAO = "_force_kakao_link_same_tab"

# (설명, 함수, 정규식, 틀린 형태) — 각각이 새 코드의 불변식 하나(혹은 둘)를 깬다.
MUTATIONS = [
    ("T1 깨기 (정리 함수가 최상위 문서 조회)", CLEANUP,
     r"var doc = window\.parent\.document;", "var doc = window.top.document;"),
    ("T2 깨기 (대상 셀렉터 3종 -> 래퍼 1종)", CLEANUP,
     r"doc\.querySelectorAll\([^)]*\)", "doc.querySelectorAll('.st-key-auth_banner_wrap')"),
    ("T4 깨기 (정리 함수 catch 비움)", CLEANUP,
     r"try \{\s*console\.error\('\[auth_banner\][^}]*\} catch \(e2\) \{\}", ""),
    ("K1/F1 깨기 (카카오 함수가 최상위 문서 조회)", KAKAO,
     r"var doc = window\.parent\.document;", "var doc = window.top.document;"),
    ("K4 깨기 (관찰 대상만 다른 문서로 남김)", KAKAO,
     r"obs\.observe\(doc\.body", "obs.observe(document.body"),
    ("K3 깨기 (카카오 함수 catch 비움)", KAKAO,
     r"try \{\s*console\.error\('\[kakao_link\][^}]*\} catch \(e2\) \{\}", ""),
]


def function_span(text: str, name: str) -> tuple[int, int]:
    """(시작줄, 끝줄) 1-based — ast로 함수 경계를 잡는다."""
    for node in ast.parse(text).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            assert node.end_lineno is not None
            return node.lineno, node.end_lineno
    raise AssertionError(f"{name} 함수를 찾을 수 없다")


def mutate(normalized: str, func: str, pattern: str, replacement: str) -> str:
    start, end = function_span(normalized, func)
    lines = normalized.split("\n")
    body = "\n".join(lines[start - 1:end])
    mutated, count = re.subn(pattern, replacement, body, count=1)
    assert count == 1, f"{func} 안에서 패턴을 못 찾았다: {pattern!r}"
    assert mutated != body, "치환이 아무것도 바꾸지 않았다"
    return "\n".join(lines[:start - 1] + mutated.split("\n") + lines[end:])


def main() -> int:
    original = TARGET.read_bytes()
    normalized = original.decode("utf-8").replace("\r\n", "\n")

    results = []
    try:
        for label, func, pattern, replacement in MUTATIONS:
            stacked = mutate(normalized, func, pattern, replacement)
            compile(stacked, str(TARGET), "exec")  # 문법이 깨진 채 돌리지 않는다
            TARGET.write_bytes(stacked.encode("utf-8"))
            proc = subprocess.run(
                [sys.executable, "-X", "utf8", str(TEST)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            fails = [ln.split(":", 1)[0] for ln in proc.stdout.splitlines()
                     if ln.startswith("FAIL")]
            results.append((label, proc.returncode, fails))
            TARGET.write_bytes(original)  # 다음 변조를 위해 즉시 원복
    finally:
        TARGET.write_bytes(original)

    ok = True
    for label, rc, fails in results:
        caught = ", ".join(f.replace("FAIL test_", "") for f in fails) or "(없음)"
        print(f"[{label}]\n  종료코드={rc}  잡은 테스트: {caught}")
        if rc == 0:
            ok = False
            print("  -> 통과해버렸다: 이 변조를 테스트가 못 잡는다")

    restored = TARGET.read_bytes() == original
    print(f"\n원본 바이트 복원 = {restored}")
    print(f"변조 검사 결과 = {'OK (모든 변조를 테스트가 잡음)' if ok and restored else 'NG'}")
    return 0 if (ok and restored) else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
