"""pytest 진입점 — 모든 테스트에 DB 격리(운영 Turso 차단)를 자동 적용한다.

이 프로젝트의 테스트는 pytest 없이도 돌도록 단독 러너(__main__)를 갖고 있고,
실제로 venv312에는 pytest가 설치돼 있지도 않다 — 그래서 격리를 conftest에만
두면 pytest로 돌릴 때만 안전해진다. 격리 구현은 tests/_db_isolation.py 한 곳에만
있고, 이 fixture는 그걸 모든 테스트에 자동으로 걸어주는 얇은 껍데기다(테스트가
직접 isolated_db()를 쓰는 경우와 같은 코드를 타야 한쪽만 빠지는 일이 없다).

제외 대상: test_db_turso_pool.py — db_turso 내부(풀 라운드로빈·타임아웃 슬롯
재생성)를 가짜 클라이언트로 검증하는 파일이라 connect()를 임시 sqlite로 바꾸면
검증 대상 자체가 사라진다. 그 파일은 운영 DB에도 접근하지 않는다(모든 테스트가
_client_pool/_make_client를 가짜로 바꿔치기한다).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _path in (str(ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import _db_isolation  # noqa: E402

# 격리를 걸면 안 되는 파일(이유는 위 docstring).
NO_ISOLATION_FILES = {"test_db_turso_pool.py"}


@pytest.fixture(autouse=True)
def db_isolation(request):
    """테스트 하나마다 새 임시 sqlite DB로 격리한다(운영 Turso 출구를 db_turso에서 봉쇄)."""
    node_path = getattr(request.node, "path", None) or request.node.fspath
    if Path(str(node_path)).name in NO_ISOLATION_FILES:
        yield
        return
    with _db_isolation.isolated_db():
        yield
