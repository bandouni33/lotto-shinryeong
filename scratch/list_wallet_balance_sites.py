"""읽기 전용 — 지갑 잔액을 조회하는 지점을 코드에서 기계적으로 뽑는다.

눈으로 훑으면 빠뜨리므로 AST로 함수 경계를 잡아 "어느 함수의 몇 번째 줄에서
무엇을 조회하는지"를 전부 나열한다. 코드는 전혀 바꾸지 않는다.

  A) wallet_db.get_balance() 호출 — 잔액을 읽는 유일한 정상 경로
  B) 'FROM wallets'가 들어간 SQL 문자열 — 테이블을 직접 치는 곳
     (balance 말고 toss_customer_key 같은 다른 컬럼도 여기 걸린다)

실행: venv312\\Scripts\\python.exe scratch\\list_wallet_balance_sites.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = [
    "wallet_ui.py", "user_page.py", "app.py", "page_auto.py", "page_thunder.py",
    "page_hedge.py", "combo_history_ui.py", "auto_purchase_service.py",
    "tarot/tarot_page.py", "google_play_pg.py", "toss_pg.py", "wallet_db.py",
]
BALANCE_CALLS = {"get_balance"}
WALLET_SQL_TOKENS = ("FROM wallets", "INTO wallets", "UPDATE wallets")


def enclosing(tree: ast.AST, lineno: int) -> str:
    """그 줄을 감싸는 가장 안쪽 함수 이름(없으면 module)."""
    best: ast.FunctionDef | None = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        end = node.end_lineno or node.lineno
        if node.lineno <= lineno <= end and (best is None or node.lineno > best.lineno):
            best = node
    return best.name if best else "(module)"


def scanned(path: str) -> tuple[int, int]:
    text = (ROOT / path).read_text(encoding="utf-8")
    tree = ast.parse(text)

    calls: list[tuple[int, str, str]] = []
    sqls: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else (
                func.attr if isinstance(func, ast.Attribute) else None)
            if name in BALANCE_CALLS:
                calls.append((node.lineno, enclosing(tree, node.lineno), name))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            flat = " ".join(node.value.split())
            if any(tok in flat for tok in WALLET_SQL_TOKENS):
                what = flat[:70]
                sqls.append((node.lineno, enclosing(tree, node.lineno), what))

    if calls or sqls:
        print(f"\n=== {path} ===")
        for lineno, func, name in sorted(calls):
            print(f"  {path}:{lineno:<5} {func}()  ->  {name}()")
        for lineno, func, what in sorted(sqls):
            print(f"  {path}:{lineno:<5} {func}()  SQL: {what}")
    return len(calls), len(sqls)


def main() -> int:
    total_calls = total_sqls = 0
    print("A) get_balance() 호출  /  B) wallets 테이블을 직접 치는 SQL")
    for path in FILES:
        if not (ROOT / path).exists():
            print(f"\n=== {path} === (파일 없음)")
            continue
        calls, sqls = scanned(path)
        total_calls += calls
        total_sqls += sqls
    print(f"\nget_balance() 호출 총 {total_calls}곳, wallets SQL 총 {total_sqls}곳")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
