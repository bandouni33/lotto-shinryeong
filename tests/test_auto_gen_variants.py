"""자동조합 조합 생성 연출 — 5초 · 5종 순환 (2026-10-18 사용자 지시).

배경: 자동조합은 조합시작(적립금 확인 후) 때 신령 이미지가 3초 동안 지진처럼 흔들리는 연출 1종만
보여줬다(`AUTO_GEN_ANIM_SECONDS = 3.0`, `_spirit2_gen_layer`). 요청: 번개조합과 같은 순환 구조를
새로 들여 기존 연출을 변형 1로 두고 2~5를 더하며, 길이를 5초로 늘리고 각 변형 타이밍을 5초에 맞춘다.
순환은 번개조합과 같이 게스트별 localStorage 에서 JS 가 한다 — 연출은 CSS 애니메이션뿐이고
DB·서버 호출이 없다.

불변식:
  A1. 길이·종류의 기준점은 `AUTO_GEN_ANIM_SECONDS`(5.0)·`AUTO_GEN_VARIANT_COUNT`(5) 이고,
      결과 표시를 미루는 두 함수(`_finish_auto_generation_if_due`·`_render_auto_generation_timer`)가
      그 상수를 그대로 쓴다(숫자를 두 곳에 적지 않는다).
  A2. 기존 연출(변형 1 — 배경 영역별 지진 요동)이 그대로 남아 있고, 변형 2~5 층이 함께 실려 나간다.
  A3. 배경층·변형 효과의 모든 CSS 애니메이션이 반복 횟수까지 포함해 AUTO_GEN_ANIM_SECONDS 안에
      끝난다(예전 infinite 는 사라졌다).
  A4. (동작, Node) `_auto_reveal_pick_script` 가 게스트별로 1→2→3→4→5→1 로 돌고, 저장값이 깨졌으면
      1, 같은 생성(token)이 다시 그려질 때는 같은 변형을 다시 칠할 뿐 순환을 한 칸 더 넘기지 않는다.

pytest 없이도 돌도록 unittest 로 썼다: venv312\\Scripts\\python.exe tests\\test_auto_gen_variants.py
node 가 없으면 A4 만 건너뛰고 그 사실을 출력한다.
"""

from __future__ import annotations

import inspect
import json
import os
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

import page_auto  # noqa: E402

TOKEN = "1710000000123"
GUEST = "guest-test-1"


def _run_node(script: str) -> str:
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("node 실행 파일이 없어 동작 검증을 건너뛴다")
    with tempfile.TemporaryDirectory(prefix="auto_gen_variants_") as tmp:
        path = Path(tmp) / "check.js"
        path.write_text(script, encoding="utf-8")
        proc = subprocess.run(
            [node, str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90
        )
    assert proc.returncode == 0, f"스크립트가 계약을 어겼다(node exit {proc.returncode}): {proc.stderr or proc.stdout}"
    return (proc.stdout or "").strip()


class LengthConstantsTest(unittest.TestCase):
    """A1 — 5초·5종의 기준점은 한 곳이고, 화면 흐름도 그 상수를 따라간다."""

    def test_a1_five_seconds_five_variants(self) -> None:
        self.assertEqual(page_auto.AUTO_GEN_ANIM_SECONDS, 5.0, "연출 길이가 5초가 아니다")
        self.assertEqual(page_auto.AUTO_GEN_VARIANT_COUNT, 5, "연출 종류가 5종이 아니다")
        self.assertEqual(len(page_auto._AUTO_GEN_VARIANTS), 5, "변형 목록과 상수가 어긋난다")

    def test_a1_three_seconds_value_is_gone(self) -> None:
        src = (ROOT / "page_auto.py").read_text(encoding="utf-8")
        self.assertNotIn("AUTO_GEN_ANIM_SECONDS = 3.0", src, "예전 3초 값이 남아 있다")

    def test_a1_generation_flow_uses_the_constant(self) -> None:
        due = inspect.getsource(page_auto._finish_auto_generation_if_due)
        timer = inspect.getsource(page_auto._render_auto_generation_timer)
        self.assertIn("AUTO_GEN_ANIM_SECONDS", due, "결과 표시를 미루는 판정이 상수를 쓰지 않는다")
        self.assertIn("AUTO_GEN_ANIM_SECONDS", timer, "다시 그리는 시각 계산이 상수를 쓰지 않는다")


class VariantLayerTest(unittest.TestCase):
    """A2·A3 — 생성 연출 HTML 이 변형 1을 그대로 두고 2~5를 함께 싣되, 모두 5초 안에 끝난다."""

    @classmethod
    def setUpClass(cls) -> None:
        # _spirit2_gen_layer 는 실제 그림 파일(spirit2_layers/*.png·로또신령2_*.webp)을 읽는다 —
        # 실행 위치에 상관없이 리포지터리 루트에서 만든다(끝나면 원래 위치로 되돌린다).
        cls._cwd = os.getcwd()
        os.chdir(ROOT)
        try:
            cls.html = page_auto._spirit2_gen_layer("x", TOKEN)
        finally:
            os.chdir(cls._cwd)
        cls.cls = page_auto._auto_gen_wrap_class(TOKEN)

    def test_a2_base_effect_kept(self) -> None:
        # 변형 1 = 2026-10-10 연출 그대로: 배경판 + 영역 가림막 + 인물.
        self.assertIn(f'class="auto-spirit2-gen {self.cls}-wrap"', self.html, "연출 칸에 변형 클래스를 붙일 자리가 없다")
        self.assertIn("data:image/webp;base64,", self.html, "인물 이미지가 빠졌다")
        for name, _frames, _dur, _delay, _origin in page_auto._SPIRIT2_QUAKE_LAYERS:
            self.assertIn(f".{self.cls}-{name}{{", self.html, f"배경 요동층({name}) CSS 가 없다")
            self.assertIn(f'class="{self.cls} {self.cls}-{name}"', self.html, f"배경 요동층({name}) 마크업이 없다")

    def test_a2_variants_two_to_five_present(self) -> None:
        for variant in range(2, page_auto.AUTO_GEN_VARIANT_COUNT + 1):
            self.assertIn(f".{self.cls}-v{variant} ", self.html, f"변형 {variant} CSS 규칙이 없다")

    def test_a2_every_effect_layer_is_markuped(self) -> None:
        counts = {"wave": 3, "mote": 8, "breath": 1, "aurora": 2, "flash": 1, "bolt": 2}
        for element, expected in counts.items():
            with self.subTest(element=element):
                found = len(re.findall(rf'class="{re.escape(self.cls)}-{element}"', self.html))
                self.assertEqual(found, expected, f"{element} 층 개수가 다르다")
                self.assertIn(f".{self.cls}-{element}{{", self.html, f"{element} 모양 CSS 가 없다")
                self.assertIn(f"@keyframes {self.cls}-{element}{{", self.html, f"{element} 애니메이션 정의가 없다")

    def test_a3_no_endless_animation(self) -> None:
        self.assertNotIn("infinite", self.html, "끝없이 도는 애니메이션이 남아 있다(연출 길이 5초와 어긋난다)")

    def test_a3_every_declared_animation_fits(self) -> None:
        declarations = re.findall(r"animation:([^;\"'}]+)", self.html)
        self.assertGreaterEqual(len(declarations), len(page_auto._SPIRIT2_QUAKE_LAYERS), "애니메이션 선언이 너무 적다")
        for declaration in declarations:
            with self.subTest(declaration=declaration.strip()):
                seconds = [float(value) for value in re.findall(r"(\d+(?:\.\d+)?)s", declaration)]
                self.assertTrue(seconds, f"길이 없는 애니메이션: {declaration}")
                repeat_match = re.search(r"\s(\d+)\s*$", declaration.strip())
                repeat = int(repeat_match.group(1)) if repeat_match else 1
                self.assertGreaterEqual(repeat, 1)
                self.assertLessEqual(
                    max(seconds) * repeat,
                    page_auto.AUTO_GEN_ANIM_SECONDS,
                    f"연출 시간(5초)을 넘는다: {declaration.strip()}",
                )

    def test_a3_variant_table_includes_delays(self) -> None:
        for variant, element, duration, repeat, instances in page_auto._AUTO_GEN_VARIANT_EFFECTS:
            latest = max(delay for delay, _left in instances)
            with self.subTest(variant=variant, element=element):
                self.assertLessEqual(
                    latest + duration * repeat,
                    page_auto.AUTO_GEN_ANIM_SECONDS,
                    f"변형 {variant} 의 {element} 가 5초를 넘는다",
                )

    def test_a3_quake_layers_finish_in_time(self) -> None:
        for name, _frames, duration, delay, _origin in page_auto._SPIRIT2_QUAKE_LAYERS:
            loops = page_auto._auto_gen_loop_count(duration)
            with self.subTest(layer=name):
                self.assertGreaterEqual(loops, 1, "반복 횟수가 0 이면 배경이 흔들리지 않는다")
                self.assertLessEqual(delay + duration * loops, page_auto.AUTO_GEN_ANIM_SECONDS)


_PICK_HARNESS = r"""
const store = {};
__SEED__
const wrapEl = {
  classList: {
    add: function (name) { globalThis.classes.push(name); },
    remove: function () {},
  },
};
globalThis.classes = [];
globalThis.window = {
  localStorage: {
    getItem: function (key) { return (key in store) ? store[key] : null; },
    setItem: function (key, value) { store[key] = String(value); },
  },
  parent: {
    document: { querySelector: function () { return __PRESENT__ ? wrapEl : null; } },
  },
};
globalThis.window.parent.localStorage = globalThis.window.localStorage;

const result = { picks: [], stores: [] };
function run(src) { globalThis.classes.length = 0; new Function(src)(); return globalThis.classes.slice(); }
function reset() { globalThis.classes.length = 0; }

__RUNS__
console.log(JSON.stringify(result));
"""


def _run_picker(tokens: list[str], seed: dict[str, str] | None = None, present: bool = True) -> dict:
    seed_js = "".join(f"store[{json.dumps(k)}] = {json.dumps(v)};" for k, v in (seed or {}).items())
    runs = []
    for token in tokens:
        script = page_auto._auto_reveal_pick_script(token, GUEST)
        runs.append(
            "result.picks.push(run(%s)); result.stores.push(JSON.stringify(store));" % json.dumps(script)
        )
    js = (
        _PICK_HARNESS.replace("__SEED__", seed_js)
        .replace("__PRESENT__", "true" if present else "false")
        .replace("__RUNS__", "\n".join(runs))
    )
    return json.loads(_run_node(js))


def _variant_of(classes: list[str], wrap_class: str) -> int:
    picked = [name for name in classes if name.startswith(f"{wrap_class}-v")]
    assert len(picked) == 1, f"칠한 변형 클래스가 하나가 아니다: {classes}"
    return int(picked[0].rsplit("-v", 1)[1])


class RevealCycleTest(unittest.TestCase):
    """A4 — 게스트별 localStorage 순환(1→5)과 재렌더 안전성."""

    wrap_class = page_auto._auto_gen_wrap_class(TOKEN)

    def test_a4_cycles_through_five_generations(self) -> None:
        tokens = [f"{TOKEN}{index}" for index in range(8)]
        result = _run_picker(tokens)
        variants = [_variant_of(classes, page_auto._auto_gen_wrap_class(tok)) for classes, tok in zip(result["picks"], tokens)]
        self.assertEqual(variants, [1, 2, 3, 4, 5, 1, 2, 3], "다섯 변형 순환이 아니다")

    def test_a4_continues_from_stored_value(self) -> None:
        seed = {page_auto._AUTO_REVEAL_STORE_PREFIX + GUEST: "4"}
        result = _run_picker([TOKEN], seed=seed)
        self.assertEqual(_variant_of(result["picks"][0], self.wrap_class), 4)
        stored = json.loads(result["stores"][0])[page_auto._AUTO_REVEAL_STORE_PREFIX + GUEST]
        self.assertEqual(stored, "5", "다음에 보여줄 변형을 저장하지 않는다")

    def test_a4_broken_stored_value_falls_back_to_first(self) -> None:
        for broken in ("99", "0", "abc"):
            with self.subTest(broken=broken):
                seed = {page_auto._AUTO_REVEAL_STORE_PREFIX + GUEST: broken}
                result = _run_picker([TOKEN], seed=seed)
                self.assertEqual(_variant_of(result["picks"][0], self.wrap_class), 1)

    def test_a4_same_generation_is_not_advanced_twice(self) -> None:
        # 같은 조합 생성(token)이 다시 그려질 때(재렌더) — 같은 변형을 다시 칠할 뿐 순환은 넘어가지 않는다.
        result = _run_picker([TOKEN, TOKEN])
        first = _variant_of(result["picks"][0], self.wrap_class)
        second = _variant_of(result["picks"][1], self.wrap_class)
        self.assertEqual(first, 1)
        self.assertEqual(second, first, "재렌더에서 변형이 바뀌었다(순환이 새고 있다)")
        stored = json.loads(result["stores"][1])[page_auto._AUTO_REVEAL_STORE_PREFIX + GUEST]
        self.assertEqual(stored, "2", "재렌더에서 다음 변형이 또 넘어갔다")

    def test_a4_missing_wrapper_does_not_break_the_page(self) -> None:
        # 화면에 연출 칸이 아직 없으면(부모 문서 교체 중 등) 조용히 아무것도 하지 않아야 한다.
        result = _run_picker([TOKEN], present=False)
        self.assertEqual(result["picks"], [[]], "연출 칸이 없는데 클래스를 칠했다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
