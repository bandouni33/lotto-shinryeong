"""번개조합 생성 규칙(2026-10-12 사용자 지시) — page_thunder.py 에서 실제 JS 함수를 뽑아 Node 로 돌린다.

  R1 고정수 전부 포함·삭제수 없음 (풀 조합·직접 생성 모두)
  R2 메인 핵심수 1~2개 반드시 포함
  R3 기준값패턴: 최대 200번 시도 → 못 찾으면 최다 만족(시도 상한 상수 200)
  R4 행운수 지정 시 게임마다 1~2개 반드시 포함 (예전 0~3개 무작위)
  R5 첫 게임은 1.5초 뒤, 이후 2초 간격 (연출 시작과 동시에 채워지지 않게)
  R6 풀 조합은 위 규칙과 패턴 전부 만족일 때만 사용
실행: python tests/test_thunder_gen_rules.py   (node 없으면 R1·R2·R4·R6 동작 검사는 건너뜀)
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = (ROOT / "page_thunder.py").read_text(encoding="utf-8")
FUNCS = ["pickLuckyCount", "countIn", "luckyActive", "adminActive", "meetsUserRules",
         "weightedPickWithoutReplacement", "longestConsecutiveRun", "maxDecadeCount",
         "maxLastDigitCount", "violatesNaturalFilter", "fillRandomSlots", "scoreComboPattern",
         "tryPoolMatch", "buildOneGame"]


def _extract(name: str) -> str:
    i = SRC.index(f"function {name}(")
    j = SRC.index("{{", i)
    depth, k = 0, j
    while True:
        if SRC.startswith("{{", k):
            depth += 1; k += 2; continue
        if SRC.startswith("}}", k):
            depth -= 1; k += 2
            if depth == 0:
                break
            continue
        k += 1
    return SRC[i:k].replace("{{", "{").replace("}}", "}")


def test_static():
    assert "const THUNDER_FIRST_GAME_DELAY_MS = 1500;" in SRC
    assert "const THUNDER_PATTERN_MAX_TRIES = 200;" in SRC
    assert "THUNDER_FIRST_GAME_DELAY_MS + g * 2000" in SRC
    assert "const maxRetries = THUNDER_PATTERN_MAX_TRIES;" in SRC
    assert "if (r < 0.30) return 0;" not in SRC


JS_DRIVER = r"""
let selectedFixed, selectedDelete, luckyNumbers, poolCombos;
const numberWeights = {}; for (let i = 1; i <= 45; i++) numberWeights[i] = 1 + (i % 7);
const thunderFilter = {thresholds: {max_consecutive_run: 4, max_decade_count: 4, max_last_digit_count: 3, max_retries: 100}};
const THUNDER_PATTERN_MAX_TRIES = 200;
let ADMIN_LUCKY_NUMBERS = [3, 11, 19, 27, 35, 43];
let patternRules = [{targets: [1,3,5,7,9,11,13,15,17,19,21,23,25,27,29,31,33,35,37,39,41,43,45], min: 2, max: 4}];
__FUNCS__
const cases = __CASES__;
const out = [];
for (const c of cases) {
  selectedFixed = new Set(c.fixed); selectedDelete = new Set(c.deleted); luckyNumbers = new Set(c.lucky);
  ADMIN_LUCKY_NUMBERS = c.admin;
  const available = []; for (let i = 1; i <= 45; i++) if (!selectedDelete.has(i)) available.push(i);
  poolCombos = c.pool.map(x => x.slice());
  for (let t = 0; t < c.n; t++) {
    const pm = tryPoolMatch();
    const g = pm || buildOneGame(available).game;
    out.push({name: c.name, game: g, fromPool: !!pm});
  }
}
console.log(JSON.stringify(out));
"""


def test_behaviour():
    node = shutil.which("node")
    if not node:
        print("node 없음 — 동작 검사 건너뜀")
        return
    pool = [[1, 2, 3, 4, 5, 6], [3, 8, 14, 21, 30, 40], [2, 11, 20, 26, 33, 44], [7, 9, 13, 22, 31, 42]]
    cases = [
        {"name": "기본", "fixed": [], "deleted": [], "lucky": [], "admin": [3, 11, 19, 27, 35, 43], "pool": pool, "n": 300},
        {"name": "행운수", "fixed": [], "deleted": [], "lucky": [5, 16, 28, 33, 41], "admin": [3, 11, 19, 27, 35, 43], "pool": pool, "n": 300},
        {"name": "고정삭제행운", "fixed": [10, 20], "deleted": [1, 2, 3, 4, 11, 30], "lucky": [5, 16, 28],
         "admin": [3, 11, 19, 27, 35, 43], "pool": pool, "n": 300},
        {"name": "핵심수가행운수", "fixed": [], "deleted": [], "lucky": [19, 27], "admin": [3, 11, 19, 27, 35, 43], "pool": pool, "n": 300},
        {"name": "핵심수없음", "fixed": [8], "deleted": [], "lucky": [], "admin": [], "pool": pool, "n": 100},
    ]
    js = JS_DRIVER.replace("__FUNCS__", "\n".join(_extract(f) for f in FUNCS)).replace("__CASES__", json.dumps(cases))
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(js)
    res = subprocess.run([node, f.name], capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    rows = json.loads(res.stdout)
    byname = {c["name"]: c for c in cases}
    for r in rows:
        c, g = byname[r["name"]], r["game"]
        assert len(g) == 6 and len(set(g)) == 6, r
        assert all(x in g for x in c["fixed"]), r                       # R1
        assert not any(x in c["deleted"] for x in g), r                 # R1
        if c["admin"]:
            ac = sum(1 for x in g if x in c["admin"])
            assert 1 <= ac <= 2, r                                      # R2
        if c["lucky"]:
            lc = sum(1 for x in g if x in c["lucky"])
            assert 1 <= lc <= 2, r                                      # R4
        if r["fromPool"]:                                               # R6
            assert sum(1 for x in g if x % 2) in (2, 3, 4), r
    print(f"동작 검사 {len(rows)}게임 통과")


if __name__ == "__main__":
    test_static()
    test_behaviour()
    print("OK")
