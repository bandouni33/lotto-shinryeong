"""@st.cache_data 인자명이 밑줄로 시작해 캐시가 무효화되지 않던 나머지 함수들.

Streamlit은 밑줄로 시작하는 인자를 캐시 키 해시에서 제외한다 — mtime·DB 캐시 키를
"무효화용 인자"로 받아둔 함수들은 그 값을 통째로 무시한 채, 데이터가 바뀌어도
프로세스를 재시작하기 전까지 옛 값을 계속 돌려줬다(메인화면 '다음회차'가 안 바뀌던
원인과 같은 뿌리).

막는 방법 두 갈래:
  1) CacheDataParamNameInvariantTests — 프로젝트 소스를 AST로 훑어 "캐시 함수의 인자
     이름에 밑줄 금지"를 강제한다. admin_dashboard.py처럼 import만으로 페이지 본문이
     실행되는 모듈도 안전하게 검사되고, 앞으로 추가되는 함수에도 자동 적용된다.
  2) SameRootCacheFallthroughTests — 실제 동작 확인: 데이터(또는 캐시 키)가 바뀐 뒤
     다시 호출하면 새 값이 나와야 한다(호출 사이에 캐시를 비우지 않는 것이 검증 지점).

실행: venv312\\Scripts\\python.exe -m unittest discover -s tests -p "test_cache_key_underscore_fixes.py" -v
"""

import ast
import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _path in (str(ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import pandas as pd  # noqa: E402

import _db_isolation  # noqa: E402
import draw_results_db  # noqa: E402
import lotto_stats  # noqa: E402
import page_auto  # noqa: E402

# 훑지 않을 디렉터리(가상환경·빌드 산출물·숨김 폴더는 프로젝트 소스가 아니다).
SKIP_DIRS = {"venv312", "__pycache__", "node_modules", "builds", "data"}
CACHE_DECORATORS = {"cache_data", "cache_resource"}


def _iter_source_files():
    for path in ROOT.rglob("*.py"):
        parts = path.relative_to(ROOT).parts
        if any(part.startswith(".") for part in parts):
            continue  # .git/.astra/.expo 등
        if set(parts) & SKIP_DIRS:
            continue
        yield path


def _decorator_name(node: ast.AST) -> str:
    target = node.func if isinstance(node, ast.Call) else node
    parts: list[str] = []
    while isinstance(target, ast.Attribute):
        parts.append(target.attr)
        target = target.value
    if isinstance(target, ast.Name):
        parts.append(target.id)
    return ".".join(reversed(parts))


def _table_rounds(df: pd.DataFrame) -> set[int]:
    return {int(r) for r in df["회차"]}


class CacheDataParamNameInvariantTests(unittest.TestCase):
    def test_no_cache_function_param_starts_with_underscore(self):
        """캐시 함수의 인자 이름에 밑줄이 있으면 그 인자는 캐시 키에서 빠진다."""
        offenders: list[str] = []
        checked = 0

        for path in _iter_source_files():
            # utf-8-sig: db_turso.py 등 일부 파일이 BOM으로 시작한다(파이썬 import는
            # BOM을 떼어내지만 ast.parse는 그대로 넘기면 SyntaxError를 낸다).
            tree = ast.parse(
                path.read_text(encoding="utf-8-sig"), filename=str(path)
            )
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                decorated = any(
                    _decorator_name(d).split(".")[-1] in CACHE_DECORATORS
                    for d in node.decorator_list
                )
                if not decorated:
                    continue
                checked += 1
                args = node.args
                params = (
                    list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
                )
                for arg in params:
                    if arg.arg in ("self", "cls"):
                        continue
                    if arg.arg.startswith("_"):
                        offenders.append(
                            f"{path.relative_to(ROOT)}:{node.lineno} {node.name}({arg.arg})"
                        )

        self.assertGreaterEqual(
            checked, 5, f"검사한 캐시 함수가 {checked}개뿐이다 — 훑기 로직이 깨졌을 수 있다"
        )
        self.assertEqual(
            offenders,
            [],
            "밑줄 인자는 캐시 키에서 제외돼 무효화가 무력화된다: " + ", ".join(offenders),
        )


class SameRootCacheFallthroughTests(unittest.TestCase):
    def setUp(self):
        self._iso = _db_isolation.isolated_db()
        self._iso.__enter__()
        self.addCleanup(self._iso.__exit__, None, None, None)
        draw_results_db.init_draw_results_table()
        # 화면·가중치 경로가 xlsb 폴백(파일 없음)으로 가지 않도록 실제 회차 한 건을 넣어둔다.
        draw_results_db.upsert_draw_result(1241, [3, 8, 19, 27, 35, 44], 21)

        for cached in (
            lotto_stats._auto_sync_latest_draw_cached,
            lotto_stats._load_lotto_data_db_cached,
            lotto_stats._load_lotto_data_cached,
            lotto_stats._number_weights_cached,
            page_auto._load_stats_table_cached,
            page_auto._winning_numbers_for_draw_cached,
        ):
            cached.clear()

        # 렌더/조회가 외부(동행복권) 응답에 의존하지 않게 막는다.
        original_sync = draw_results_db.sync_latest_from_dhlottery
        draw_results_db.sync_latest_from_dhlottery = lambda: None
        self.addCleanup(
            setattr, draw_results_db, "sync_latest_from_dhlottery", original_sync
        )

    def test_xlsb_fallback_loader_follows_file_mtime(self):
        """lotto_stats._load_lotto_data_cached — 파일(mtime)이 바뀌면 다시 파싱한다."""
        frames = [pd.DataFrame([["A"]] * 8), pd.DataFrame([["B"]] * 8)]
        state = {"calls": 0}

        def fake_read_excel(path, engine=None, header=None):
            state["calls"] += 1
            return frames[0] if state["calls"] == 1 else frames[1]

        original = lotto_stats.pd.read_excel
        lotto_stats.pd.read_excel = fake_read_excel
        self.addCleanup(setattr, lotto_stats.pd, "read_excel", original)

        first = lotto_stats._load_lotto_data_cached("dummy.xlsb", 111.0)
        second = lotto_stats._load_lotto_data_cached("dummy.xlsb", 222.0)

        self.assertEqual(first.iloc[0, 0], "A")
        self.assertEqual(
            second.iloc[0, 0], "B", "mtime이 바뀌었는데 옛 파싱 결과를 그대로 돌려줬다"
        )

    def test_number_weights_follow_new_draw(self):
        """lotto_stats._number_weights_cached — DB에 회차가 늘면 가중치도 다시 계산된다."""
        draw_results_db.upsert_draw_result(2000, [1, 2, 3, 4, 5, 6], 7)
        self.assertEqual(lotto_stats.get_number_weights()[1], 1)

        draw_results_db.upsert_draw_result(2001, [1, 2, 3, 4, 5, 6], 8)
        self.assertEqual(
            lotto_stats.get_number_weights()[1],
            2,
            "새 회차가 가중치에 반영되지 않았다(조합 추첨 근거가 옛 데이터에 고정)",
        )

    def test_stats_table_distinguishes_cache_keys(self):
        """page_auto._load_stats_table_cached — 캐시 키가 달라지면 표를 다시 만든다."""
        import marketing_db as mdb

        mdb.init_marketing_tables()
        first, _ = page_auto._load_stats_table_cached((1.0, 2.0))
        self.assertNotIn(1243, _table_rounds(first))

        mdb.bulk_insert_lotto_combinations(1243, [(1, 2, 3, 4, 5, 6)])
        second, _ = page_auto._load_stats_table_cached((3.0, 4.0))
        self.assertIn(
            1243,
            _table_rounds(second),
            "캐시 키가 달라졌는데 옛 표를 그대로 돌려줬다",
        )

    def test_winning_numbers_distinguish_cache_keys(self):
        """page_auto._winning_numbers_for_draw_cached — 같은 회차라도 키가 다르면 새로 조회한다."""
        state = {"calls": 0}

        def fake_get_draw_result(draw_round, filepath=None):
            state["calls"] += 1
            numbers = (
                [1, 2, 3, 4, 5, 6] if state["calls"] == 1 else [10, 11, 12, 13, 14, 15]
            )
            return {"draw_no": int(draw_round), "numbers": numbers, "bonus": 7}

        original = lotto_stats.get_draw_result_by_round
        lotto_stats.get_draw_result_by_round = fake_get_draw_result
        self.addCleanup(setattr, lotto_stats, "get_draw_result_by_round", original)

        first = page_auto._winning_numbers_for_draw_cached(1242, ("k1",))
        second = page_auto._winning_numbers_for_draw_cached(1242, ("k2",))

        self.assertEqual(first[0], {1, 2, 3, 4, 5, 6})
        self.assertEqual(
            second[0],
            {10, 11, 12, 13, 14, 15},
            "같은 회차를 다른 캐시 키로 조회했는데 옛 값을 그대로 돌려줬다",
        )


if __name__ == "__main__":
    unittest.main()
