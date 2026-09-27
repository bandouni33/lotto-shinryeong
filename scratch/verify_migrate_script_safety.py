# -*- coding: utf-8 -*-
"""migrate_filter_rules_to_db.py 커밋 전 안전 검사 (2026-09-27 사용자 지시 2항목).

  ① 실제 필터 규칙 값(숫자 배열 등)이 파일에 하드코딩돼 있지 않을 것
  ② Turso 접속정보(URL·AUTH_TOKEN)가 코드에 문자열로 박혀 있지 않고
     os.environ/.env 로 읽는 구조일 것

눈으로 보는 대신 소스를 AST로 파싱해 검사한다(주석·docstring의 산문에 걸려
거짓 경보가 나지 않게). 저장소는 **Public**이라 이 둘은 실제 유출 경로다.

실행: venv312\\Scripts\\python.exe -X utf8 scratch\\verify_migrate_script_safety.py
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "migrate_filter_rules_to_db.py"

# ① 규칙 스키마 토큰 — 규칙 값이 들어 있으면 반드시 등장한다
RULE_TOKENS = ('"is_auto"', "'is_auto'", '"targets"', "'targets'",
               '"min"', "'min'", '"max"', "'max'")
# ② 자격증명 흔적
CRED_PATTERNS = [
    ("turso 호스트", re.compile(r"[a-z0-9-]+\.turso\.io")),
    ("libsql 스킴", re.compile(r"libsql://")),
    ("JWT", re.compile(r"eyJ[A-Za-z0-9_-]{10,}")),
    ("Authorization 헤더", re.compile(r"Bearer\s+[A-Za-z0-9._-]{10,}")),
    ("토큰 대입 리터럴", re.compile(r"(AUTH_TOKEN|TOKEN|PASSWORD|SECRET)\s*=\s*['\"][^'\"]{8,}['\"]")),
    ("윈도우 절대경로", re.compile(r"[A-Za-z]:\\\\?Users")),
]
TOKENISH = re.compile(r"^[A-Za-z0-9+/=_.:-]{40,}$")   # 공백 없는 긴 토큰/URL 모양


def main() -> int:
    src = TARGET.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fails: list[str] = []
    checks = 0

    print("=" * 92)
    print(f"검사 대상: {TARGET.name} ({len(src):,}바이트, {src.count(chr(10)) + 1}줄)")

    # ── ① 숫자 리터럴: 규칙 값이면 수십~수백 개의 숫자가 나온다
    numbers = [n.value for n in ast.walk(tree)
               if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))
               and not isinstance(n.value, bool)]
    print(f"\n① 숫자 리터럴 {len(numbers)}개: {sorted(set(numbers))}")
    checks += 1
    bad_numbers = [n for n in numbers if abs(n) > 10]
    if bad_numbers:
        fails.append(f"①-1 규칙처럼 보이는 큰 숫자 리터럴: {sorted(set(bad_numbers))}")

    containers = [c for c in ast.walk(tree)
                  if isinstance(c, (ast.List, ast.Tuple, ast.Set))
                  and sum(1 for e in c.elts if isinstance(e, ast.Constant)
                          and isinstance(e.value, (int, float))) >= 2]
    checks += 1
    if containers:
        fails.append(f"①-2 파일 안에 숫자 목록 리터럴 {len(containers)}개(규칙 배열 의심)")

    tokens = [t for t in RULE_TOKENS if t in src]
    print(f"① 규칙 스키마 토큰(is_auto/targets/min/max): {tokens or '없음'}")
    checks += 1
    if tokens:
        fails.append(f"①-3 규칙 스키마 토큰 발견: {tokens}")

    # 규칙은 **파일 경로로만** 언급돼야 한다
    refs = [ln.strip() for ln in src.splitlines() if "combo_filter_rules_stage" in ln]
    print("① 규칙 파일 언급(경로여야 함):")
    for r in refs:
        print(f"    {r}")
    checks += 1
    if not all(("os.path.join" in r) or r.startswith("#") or r.startswith("_") or '"' in r
               for r in refs):
        fails.append("①-4 규칙 파일 언급 방식이 예상과 다름")

    # ── ② 자격증명
    print("\n② 자격증명 흔적 검사")
    for label, pat in CRED_PATTERNS:
        m = pat.search(src)
        checks += 1
        if m:
            fails.append(f"②-1 {label} 패턴 발견: {m.group(0)[:20]}…")
            print(f"    !! {label}: 발견")
        else:
            print(f"    OK {label}: 없음")

    # 긴 토큰 모양의 문자열 상수(공백 없는 40자 이상) — docstring 산문은 공백/줄바꿈이 있어 제외됨
    suspicious = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for piece in node.value.split():
                if TOKENISH.match(piece):
                    suspicious.append(piece[:24] + "…")
    checks += 1
    print(f"    긴 토큰 모양 문자열 상수: {suspicious or '없음'}")
    if suspicious:
        fails.append(f"②-2 토큰 모양 문자열 상수 {len(suspicious)}개")

    # 자격증명은 환경변수로만 읽어야 한다
    ev = [n for n in ast.walk(tree)
          if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
          and n.func.attr == "getenv" and n.args
          and isinstance(n.args[0], ast.Constant)]
    ev_names = sorted({n.args[0].value for n in ev})
    print(f"    os.getenv() 로 읽는 이름: {ev_names}")
    checks += 1
    for need in ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN"):
        if need not in ev_names:
            fails.append(f"②-3 {need}를 os.getenv로 읽지 않음(하드코딩 의심)")
    checks += 1
    if "env_loader.load_dotenv_file()" not in src:
        fails.append("②-4 .env 로더 호출 없음")

    # ── ③ 값 자체를 출력하지 않는지(로그 유출)
    checks += 1
    leaked = [ln.strip() for ln in src.splitlines()
              if re.search(r"print\([^)]*getenv\(", ln)]
    if leaked:
        fails.append(f"③ 자격증명 값을 출력하는 줄 {len(leaked)}개: {leaked[0][:60]}")

    print("\n" + "=" * 92)
    print(f"검사 {checks}개 · 실패 {len(fails)}개")
    for f in fails:
        print(f"  FAIL {f}")
    print("판정: " + ("커밋 가능 (두 항목 모두 통과)" if not fails else "!! 커밋 보류 — 위 실패 항목 먼저 처리"))
    return 1 if fails else 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    raise SystemExit(code)
