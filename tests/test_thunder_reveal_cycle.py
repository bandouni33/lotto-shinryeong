"""번개조합 조합 생성 연출 — 5종 순환 + 다섯 변형 모두 6초 통일 (2026-10-18 사용자 지시).

배경: 이 화면은 renderGame() 에서 연출 v1(기본)/v2(심해 오라)/v3(균열) 3종을
localStorage(게스트별 키 `thunder_reveal_cycle_<guest>`)로 방문자마다 돌려가며 보여줬다.
요청: v4(번개 낙뢰)·v5(오색 상운)를 더하고 `% 3 + 1` → `% 5 + 1`, 그리고 화면마다
길이가 달랐던 연출(v2 약 3~4초, v3 5.5초)을 전부 6000ms 로 맞춘다. 기존 키·값(1~3)은
그대로 유효해야 한다(이미 1~3 이 저장된 브라우저가 1번으로 되돌아가면 안 된다).

불변식:
  R1. 연출 길이·종류의 기준점은 page_thunder.THUNDER_REVEAL_ANIM_MS(6000)·
      THUNDER_REVEAL_VARIANTS(5) 하나이고, JS 상수와 v1 잔광 CSS 가 같은 값을 쓴다.
  R2. renderGame 이 v1~v5 다섯 경로를 모두 알고, 다섯 경로 모두 결과 줄을 제자리에서 교체한다
      (insertResultRow — 빈 자리 순서 계약은 tests/test_thunder_placeholder_order.py 가 본다).
  R3. (동작, Node) 소스에서 실제로 뽑은 renderGameV2~V5 를 가상 타이머 위에서 돌려, 각 변형의
      마지막 애니메이션이 정확히 REVEAL_ANIM_MS 에 끝나고 그보다 오래 가는 것이 없다.
  R4. (동작, Node) consumeRevealVersion 이 1→2→3→4→5→1 로 돌고, 저장값이 깨졌으면 1,
      예전에 저장된 1~3 은 그대로 이어서 쓴다. localStorage 키 이름은 바뀌지 않는다.

pytest 없이도 돌도록 unittest 로 썼다: venv312\\Scripts\\python.exe tests\\test_thunder_reveal_cycle.py
node 가 없으면 R3·R4 만 건너뛰고 그 사실을 출력한다.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

THUNDER = ROOT / "page_thunder.py"
INSERT_CALL = "insertResultRow(document.getElementById('resultArea'), row);"


def _source() -> str:
    return THUNDER.read_text(encoding="utf-8")


def _py_constant(name: str) -> int:
    match = re.search(rf"^{name} = (\d+)\s*$", _source(), re.M)
    assert match, f"{name} 상수를 찾지 못했다(기준점이 사라졌다)"
    return int(match.group(1))


def _js_function(name: str) -> str:
    """소스(f-string)에서 함수 하나를 떼어내 실행 가능한 JS 로 만든다.

    손으로 옮겨 적지 않는 이유: 누가 이 함수를 예전(3초·3종)으로 되돌리면 이 테스트가
    그대로 깨져야 한다. 사본을 검사하면 아무것도 못 잡는다."""
    src = _source()
    start = src.index(f"function {name}(")
    depth, index = 0, src.index("{{", start)
    while True:
        if src.startswith("{{", index):
            depth += 1
            index += 2
            continue
        if src.startswith("}}", index):
            depth -= 1
            index += 2
            if depth == 0:
                break
            continue
        index += 1
    return src[start:index].replace("{{", "{").replace("}}", "}")


def _run_node(script: str) -> str:
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("node 실행 파일이 없어 동작 검증을 건너뛴다")
    with tempfile.TemporaryDirectory(prefix="thunder_reveal_") as tmp:
        path = Path(tmp) / "check.js"
        path.write_text(script, encoding="utf-8")
        proc = subprocess.run(
            [node, str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90
        )
    assert proc.returncode == 0, f"추출한 JS가 계약을 어겼다(node exit {proc.returncode}): {proc.stderr or proc.stdout}"
    return (proc.stdout or "").strip()


class RevealConstantsTest(unittest.TestCase):
    """R1 — 길이·종류의 기준점은 한 곳이고, 화면(JS·CSS)이 그 값을 그대로 받아 쓴다."""

    def test_r1_single_reference_point(self) -> None:
        self.assertEqual(_py_constant("THUNDER_REVEAL_ANIM_MS"), 6000)
        self.assertEqual(_py_constant("THUNDER_REVEAL_VARIANTS"), 5)
        src = _source()
        self.assertIn("const REVEAL_ANIM_MS = {THUNDER_REVEAL_ANIM_MS};", src)
        self.assertIn("const REVEAL_VARIANTS = {THUNDER_REVEAL_VARIANTS};", src)
        # v1 잔광(CSS)도 같은 값을 쓴다 — 숫자를 두 곳에 적지 않는다.
        self.assertIn("animation: resultRowSettle {THUNDER_REVEAL_ANIM_MS}ms", src)

    def test_r1_no_leftover_3s_or_3_variant_values(self) -> None:
        src = _source()
        for stale in ("duration: 5500", "duration: 3000", "v % 3", "v > 3", "i * 320"):
            self.assertNotIn(stale, src, f"예전 값이 남아 있다: {stale}")

    def test_r1_cycle_key_is_unchanged(self) -> None:
        # 기존 저장 키가 바뀌면 이미 1~3 을 저장해 둔 방문자가 전부 1번으로 돌아간다.
        self.assertIn("const REVEAL_STORE = 'thunder_reveal_cycle_{reveal_scope_js}';", _source())


class RevealDispatchTest(unittest.TestCase):
    """R2 — 다섯 변형이 정의돼 있고 renderGame 이 전부 분기하며, 각 경로가 자리를 교체한다."""

    def test_r2_all_five_variants_defined(self) -> None:
        src = _source()
        for name in ("renderGameV2", "renderGameV3", "renderGameV4", "renderGameV5"):
            self.assertIn(f"function {name}(nums) {{", src, f"{name} 정의가 없다")
        self.assertIn("function renderGame(nums) {{", src, "v1 경로(renderGame)가 없다")

    def test_r2_dispatch_covers_v2_to_v5(self) -> None:
        body = _js_function("renderGame")
        for version in (2, 3, 4, 5):
            self.assertIn(f"ver === {version} ||", body, f"v{version} 분기가 없다")
            self.assertIn(f"renderGameV{version}(nums);", body, f"v{version} 호출이 없다")

    def test_r2_every_path_replaces_in_place(self) -> None:
        src = _source()
        self.assertEqual(src.count(INSERT_CALL), 5, "결과 줄 자리 교체가 v1~v5 다섯 경로에 있어야 한다")
        for name in ("renderGameV2", "renderGameV3", "renderGameV4", "renderGameV5"):
            self.assertIn(INSERT_CALL, _js_function(name), f"{name} 경로가 자리 교체를 쓰지 않는다")


_TIMELINE_HARNESS = r"""
const REVEAL_ANIM_MS = __REVEAL__;
let NOW = 0;
let seq = 0;
const queue = [];
const dead = new Set();
const animations = [];
const activeGenTimers = [];
const activeGenIntervals = [];

function setTimeout(fn, ms) { queue.push({ t: NOW + (ms || 0), fn: fn, id: ++seq, every: 0 }); return seq; }
function setInterval(fn, ms) { queue.push({ t: NOW + (ms || 0), fn: fn, id: ++seq, every: ms }); return seq; }
function clearTimeout(id) { dead.add(id); }
function clearInterval(id) { dead.add(id); }
const performance = { now: () => NOW };
const per = 0;

class El {
  constructor(tag) {
    this.tag = tag; this.className = ''; this.children = []; this.style = {};
    this.innerText = ''; this._parent = null;
  }
  appendChild(c) { this.children.push(c); c._parent = this; return c; }
  remove() {
    if (!this._parent) { return; }
    const i = this._parent.children.indexOf(this);
    if (i >= 0) { this._parent.children.splice(i, 1); }
    this._parent = null;
  }
  querySelector() { return null; }
  animate(keyframes, options) {
    animations.push({ start: NOW, duration: (options && options.duration) || 0 });
    return { cancel: function () {}, finish: function () {} };
  }
}
const resultArea = new El('div');
const document = {
  createElement: (tag) => new El(tag || 'div'),
  getElementById: () => resultArea,
};
const window = { parent: { postMessage: function () {} } };

function createBallEl(n) { ballsCreated.push(n); const ball = new El('div'); ball.innerText = n; return ball; }
let ballsCreated = [];
function insertResultRow(area, row) { area.appendChild(row); }
function scrollToResultsIfFirst() {}

__EXTRACTED__

function run() {
  for (let step = 0; step < 5000; step++) {
    if (!queue.length) { return; }
    queue.sort((a, b) => a.t - b.t);
    const item = queue.shift();
    if (dead.has(item.id)) { continue; }
    NOW = Math.max(NOW, item.t);
    if (item.every) { queue.push({ t: NOW + item.every, fn: item.fn, id: item.id, every: item.every }); }
    item.fn();
  }
  throw new Error('가상 타이머가 끝나지 않는다(무한 반복)');
}

const out = {};
const variants = [['v2', renderGameV2], ['v3', renderGameV3], ['v4', renderGameV4], ['v5', renderGameV5]];
for (const entry of variants) {
  NOW = 0; seq = 0; queue.length = 0; animations.length = 0; dead.clear();
  activeGenTimers.length = 0; activeGenIntervals.length = 0;
  resultArea.children.length = 0;
  ballsCreated = [];
  entry[1]([1, 2, 3, 4, 5, 6]);
  run();
  const ends = animations.map((a) => a.start + a.duration);
  out[entry[0]] = {
    animations: animations.length,
    balls: ballsCreated.length,
    rows: resultArea.children.length,
    maxEnd: Math.max.apply(null, ends),
    overEnd: ends.filter((end) => end > REVEAL_ANIM_MS).length,
  };
}
console.log(JSON.stringify(out));
"""


class RevealTimelineTest(unittest.TestCase):
    """R3 — 네 변형 모두 자기 연출을 6초 안에 마치고, 정확히 6초에 끝난다."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.reveal_ms = _py_constant("THUNDER_REVEAL_ANIM_MS")
        script = _TIMELINE_HARNESS.replace("__REVEAL__", str(cls.reveal_ms))
        script = script.replace("__EXTRACTED__", "\n".join(_js_function(f) for f in
                                                           ("renderGameV2", "renderGameV3", "renderGameV4", "renderGameV5")))
        cls.timeline = json.loads(_run_node(script))

    def test_r3_each_variant_ends_at_the_same_length(self) -> None:
        for name, info in self.timeline.items():
            with self.subTest(variant=name):
                self.assertEqual(info["maxEnd"], self.reveal_ms, f"{name} 연출이 {self.reveal_ms}ms 에 끝나지 않는다")
                self.assertEqual(info["overEnd"], 0, f"{name} 연출에 {self.reveal_ms}ms 를 넘는 애니메이션이 있다")

    def test_r3_each_variant_draws_one_row_of_six_balls(self) -> None:
        for name, info in self.timeline.items():
            with self.subTest(variant=name):
                self.assertEqual(info["rows"], 1, f"{name} 가 결과 줄을 하나만 그려야 한다")
                self.assertEqual(info["balls"], 6, f"{name} 가 볼 여섯 개를 그리지 않는다")
                # v3는 볼을 animate() 가 아니라 100ms 간격으로 직접 움직인다 — 그래서 1개도 정상이다.
                self.assertGreaterEqual(info["animations"], 1, f"{name} 애니메이션이 하나도 없다")


_CYCLE_HARNESS = r"""
const REVEAL_VARIANTS = __VARIANTS__;
const REVEAL_STORE = 'thunder_reveal_cycle_test';
let activeRevealVersion = __SEED__;
const storage = {};
__SEEDED_PUT__
const localStorage = {
  getItem: (k) => (k in storage ? storage[k] : null),
  setItem: (k, v) => { storage[k] = String(v); },
};

__EXTRACTED__

const picked = [];
for (let i = 0; i < __CALLS__; i++) { picked.push(consumeRevealVersion()); }
console.log(JSON.stringify({ picked: picked, stored: storage[REVEAL_STORE] === undefined ? null : storage[REVEAL_STORE] }));
"""


def _cycle(seed: str | None = "1", calls: int = 1) -> dict:
    seeded_put = ""
    seed_js = "'1'"
    if seed is not None:
        seed_js = f"'{seed}'"
        seeded_put = f"storage['thunder_reveal_cycle_test'] = '{seed}';"
    script = (
        _CYCLE_HARNESS.replace("__VARIANTS__", str(_py_constant("THUNDER_REVEAL_VARIANTS")))
        .replace("__SEED__", seed_js)
        .replace("__SEEDED_PUT__", seeded_put)
        .replace("__CALLS__", str(calls))
        .replace("__EXTRACTED__", _js_function("consumeRevealVersion"))
    )
    return json.loads(_run_node(script))


class RevealCycleTest(unittest.TestCase):
    """R4 — 순환이 1→2→3→4→5→1 이고, 예전 저장값(1~3)·깨진 값 모두 안전하다."""

    def test_r4_cycles_through_all_five(self) -> None:
        result = _cycle(seed="1", calls=8)
        self.assertEqual(result["picked"], [1, 2, 3, 4, 5, 1, 2, 3], "다섯 변형 순환이 아니다")
        self.assertEqual(result["stored"], "4", "다음에 보여줄 변형을 저장하지 않는다")

    def test_r4_continues_from_legacy_value_three(self) -> None:
        # 예전에 3 까지만 돌던 브라우저 — 3 다음은 4 로 이어져야 한다(1 로 되돌아가면 신규 2종이 안 보인다).
        result = _cycle(seed="3", calls=3)
        self.assertEqual(result["picked"], [3, 4, 5])

    def test_r4_broken_stored_value_falls_back_to_first(self) -> None:
        for seed, expected in (("99", [1]), ("0", [1]), ("abc", [1]), (None, [1])):
            with self.subTest(seed=seed):
                self.assertEqual(_cycle(seed=seed, calls=1)["picked"], expected)

    def test_r4_stored_next_value_stays_in_range(self) -> None:
        result = _cycle(seed="5", calls=1)
        self.assertEqual(result["picked"], [5])
        self.assertEqual(result["stored"], "1", "5 다음은 1 이어야 한다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
