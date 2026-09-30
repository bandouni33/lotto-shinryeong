"""번개조합 빈 자리(placeholder) 채움 순서 계약 - 2026-09-30 "결과가 다 나올 때까지 화면이 빈 칸" 수정 검증.

배경: 생성 시작 시 목표 게임 수만큼 빈 자리를 미리 깔아 최종 레이아웃 높이를 확보하는
설계(의도)는 그대로 두고, "게임이 하나 나올 때마다 빈 자리 하나를 실제 결과로 교체"하는
부분만 구현이 어긋나 있었다 - 실제로는 위쪽 빈 자리를 remove하고 새 결과를 맨 아래에
append해서, 결과가 위에서부터 채워지지 않고 아래에서부터 쌓였다. 위에서 몇 줄만 보이는
화면에서는 결과가 전부 나올 때까지 빈 칸으로 보인다(예: 10개 중 5줄 보임 -> 6번째부터).

불변식:
  P1. 위에서 지우고 아래에 붙이던 예전 구조(fillOnePlaceholder)가 정의/호출 어디에도 남아 있지 않다.
  P2. 세 렌더 경로(V2, V3, 기본 renderGame)가 모두 insertResultRow로 자리를 교체한다
      (resultArea에 직접 appendChild(row)하는 코드가 남아 있지 않다).
  P3. insertResultRow는 첫 빈 자리를 replaceChild로 그 자리에서 교체하고, 빈 자리가 없으면
      appendChild로 폴백한다.
  P4. (동작, Node) page_thunder.py에서 **실제로 추출한** JS를 최소 DOM 위에서 돌려, 목표 수
      count마다 그리고 결과를 k개 넣은 **모든 k**에 대해:
        a) 자식 개수가 count로 고정된다(레이아웃 높이가 도중에 변하지 않는다 - 원래 설계 의도)
        b) 앞 k개가 실제 결과이고 순서가 투입 순서 그대로다(위에서부터 채워진다)
        c) 나머지는 전부 빈 자리다
        d) count개를 다 넣으면 빈 자리가 0개다
      그리고 복원 경로(결과를 먼저 그린 뒤 빈 자리를 추가)에서도 첫 빈 자리부터 채운다.

한계: 브라우저(실제 레이아웃/애니메이션)가 아니라 최소 DOM 대역이다 - 확인하는 것은
"어느 자리에 꽂히는가"라는 순서 계약이고, 그건 DOM 연산만으로 결정된다. 애니메이션 자체는
이번 수정에서 건드리지 않았다(같은 노드를 그 자리에 넣을 뿐).

pytest 없이도 돌도록 표준 assert + __main__ 러너를 함께 둔다. node가 없으면 P4만 건너뛰고
그 사실을 출력한다(P1~P3은 항상 검사).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

THUNDER = ROOT / "page_thunder.py"
RESULT_AREA_APPEND = "getElementById('resultArea').appendChild(row)"
INSERT_CALL = "insertResultRow(document.getElementById('resultArea'), row);"


def _source() -> str:
    return THUNDER.read_text(encoding="utf-8")


def _js_region() -> str:
    """createPlaceholderRow + insertResultRow 구간을 소스에서 그대로 떼어내 실행 가능한 JS로 만든다.

    화면 HTML이 f-string이라 중괄호가 겹쳐 있으므로({{ }}) 여기서만 되돌린다. 손으로 옮겨
    적지 않고 소스에서 뽑아 쓰는 이유: 누가 이 함수를 예전 구조로 되돌리면 이 테스트가
    그대로 깨져야 하기 때문이다(사본을 검사하면 아무 것도 못 잡는다)."""
    src = _source()
    start = src.find("function createPlaceholderRow() {{")
    assert start != -1, "createPlaceholderRow 정의를 찾지 못했다"
    end = src.find("function generateCombination() {{", start)
    assert end != -1, "generateCombination 정의를 찾지 못했다(추출 구간 끝)"
    region = src[start:end]
    return region.replace("{{", "{").replace("}}", "}")


# ── P1~P3: 소스 구조 계약 ───────────────────────────────────────────────────
def test_p1_old_remove_then_append_structure_is_gone() -> None:
    """P1 - 위에서 지우고 아래에 붙이던 예전 구조가 어디에도 남아 있지 않다."""
    src = _source()
    assert "fillOnePlaceholder" not in src, (
        "예전 구조(fillOnePlaceholder)가 아직 남아 있다 - 빈 자리를 지우고 아래에 "
        "append하면 결과가 맨 아래부터 쌓여 위쪽이 빈 칸으로 보인다"
    )


def test_p2_all_three_render_paths_replace_in_place() -> None:
    """P2 - V2, V3, 기본 renderGame 세 경로가 모두 자리 교체를 쓴다."""
    src = _source()
    assert src.count(INSERT_CALL) == 3, (
        f"자리 교체 호출이 정확히 3곳(V2, V3, 기본)이어야 한다: {src.count(INSERT_CALL)}곳"
    )
    assert RESULT_AREA_APPEND not in src, (
        "resultArea에 직접 appendChild(row)하는 코드가 남아 있다 - 그 경로만 결과가 "
        "맨 아래에 붙는다"
    )
    # 세 함수 안에 각각 들어 있는지(한 함수에 몰려 있지 않은지) 확인한다.
    for fn in ("function renderGameV2(nums) {{", "function renderGameV3(nums) {{", "function renderGame(nums) {{"):
        start = src.find(fn)
        assert start != -1, f"{fn} 정의를 찾지 못했다"
        end = src.find("\n            function ", start + 10)
        body = src[start : end if end != -1 else len(src)]
        assert INSERT_CALL in body, f"{fn} 경로가 자리 교체를 쓰지 않는다"


def test_p3_insert_replaces_first_placeholder_and_falls_back() -> None:
    """P3 - 첫 빈 자리를 그 자리에서 교체하고, 빈 자리가 없으면 끝에 붙인다."""
    js = _js_region()
    assert "function insertResultRow(resultArea, row) {" in js, "insertResultRow 정의가 없다"
    assert "querySelector('.result-row-placeholder')" in js, "첫 빈 자리를 찾지 않는다"
    assert "replaceChild(row, ph)" in js, "빈 자리를 그 자리에서 교체하지 않는다"
    assert "appendChild(row)" in js, "빈 자리가 없을 때의 폴백(appendChild)이 없다"


# ── P4: 실제 JS를 Node에서 돌려 순서를 본다 ──────────────────────────────────
_HARNESS = r"""
class El {
  constructor() { this.className = ''; this.children = []; this._parent = null; this._seq = null; }
  appendChild(c) {
    if (c._parent) { c.remove(); }
    this.children.push(c); c._parent = this; return c;
  }
  remove() {
    if (!this._parent) { return; }
    const i = this._parent.children.indexOf(this);
    if (i >= 0) { this._parent.children.splice(i, 1); }
    this._parent = null;
  }
  replaceChild(next, old) {
    const i = this.children.indexOf(old);
    if (i < 0) { throw new Error('replaceChild: old node is not a child of this node'); }
    this.children[i] = next; next._parent = this; old._parent = null; return old;
  }
  querySelector(sel) {
    const cls = sel.replace(/^\./, '');
    const walk = (el) => {
      for (const c of el.children) {
        if ((' ' + (c.className || '') + ' ').includes(' ' + cls + ' ')) { return c; }
        const found = walk(c);
        if (found) { return found; }
      }
      return null;
    };
    return walk(this);
  }
}
const document = { createElement: () => new El() };

function assert(cond, msg) { if (!cond) { throw new Error(msg); } }
function isPlaceholder(el) { return (' ' + el.className + ' ').includes(' result-row-placeholder '); }

/* __EXTRACTED_JS__ */

const COUNTS = [1, 2, 5, 10, 20];
for (const count of COUNTS) {
  const area = new El();
  for (let i = 0; i < count; i++) { area.appendChild(createPlaceholderRow()); }
  assert(area.children.length === count, 'count=' + count + ' 초기 빈 자리 수가 ' + count + '가 아니다');
  assert(area.children.every(isPlaceholder), 'count=' + count + ' 초기 자식이 빈 자리가 아니다');

  for (let k = 1; k <= count; k++) {
    const row = document.createElement();
    row.className = 'result-row reveal';
    row._seq = k;
    insertResultRow(area, row);

    assert(area.children.length === count,
      'count=' + count + ' k=' + k + ': 자식 수가 ' + area.children.length + '로 변했다(레이아웃 높이 흔들림)');
    for (let i = 0; i < k; i++) {
      assert(area.children[i]._seq === i + 1,
        'count=' + count + ' k=' + k + ': 위에서 ' + (i + 1) + '번째가 실제 결과가 아니다(빈 자리가 남아 있다)');
    }
    for (let i = k; i < count; i++) {
      assert(isPlaceholder(area.children[i]),
        'count=' + count + ' k=' + k + ': ' + (i + 1) + '번째가 빈 자리가 아니다(순서 어긋남)');
    }
  }
  assert(area.children.filter(isPlaceholder).length === 0,
    'count=' + count + ': 결과를 전부 넣었는데 빈 자리가 남았다');
}
console.log('INSERT_ORDER_OK counts=' + JSON.stringify(COUNTS));

/* 복원 경로: 이미 나온 결과를 먼저 그리고(빈 자리 없음 -> 폴백) 그 뒤 빈 자리를 깔고 채운다. */
const restored = new El();
for (let i = 1; i <= 3; i++) {
  const row = document.createElement();
  row.className = 'result-row reveal';
  row._seq = i;
  insertResultRow(restored, row);
}
assert(restored.children.length === 3, '복원: 빈 자리가 없을 때 폴백(appendChild)이 걸리지 않았다');
assert(restored.children.every((el) => el._seq !== null), '복원: 먼저 그린 결과가 빈 자리로 취급됐다');

for (let i = 0; i < 7; i++) { restored.appendChild(createPlaceholderRow()); }
for (let k = 4; k <= 10; k++) {
  const row = document.createElement();
  row.className = 'result-row reveal';
  row._seq = k;
  insertResultRow(restored, row);
}
assert(restored.children.length === 10, '복원: 총 개수가 10이 아니다');
for (let i = 0; i < 10; i++) {
  assert(restored.children[i]._seq === i + 1, '복원: ' + (i + 1) + '번째 순서가 어긋났다');
}
assert(restored.children.filter(isPlaceholder).length === 0, '복원: 빈 자리가 남았다');
console.log('RESUME_ORDER_OK total=10');
"""


def test_p4_extracted_js_fills_from_the_top_for_every_count() -> None:
    """P4(동작) - 소스에서 뽑은 실제 JS를 최소 DOM 위에서 돌려 순서 계약을 확인한다."""
    node = shutil.which("node")
    if node is None:
        print("  SKIP P4: node 실행 파일이 없어 동작 검증만 건너뛴다(P1~P3은 검사됨)")
        return

    js = _HARNESS.replace("/* __EXTRACTED_JS__ */", _js_region())
    with tempfile.TemporaryDirectory(prefix="thunder_placeholder_") as tmp:
        path = Path(tmp) / "check.js"
        path.write_text(js, encoding="utf-8")
        proc = subprocess.run(
            [node, str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    assert proc.returncode == 0, f"추출한 JS가 순서 계약을 어겼다(node exit {proc.returncode}): {err or out}"
    assert "INSERT_ORDER_OK" in out and "RESUME_ORDER_OK" in out, f"node 출력이 예상과 다르다: {out!r}"
    print(f"  (node v{_node_version(node)}: {out.replace(chr(10), ' | ')})")


def _node_version(node: str) -> str:
    try:
        proc = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=30)
        return (proc.stdout or "").strip().lstrip("v")
    except Exception:
        return "?"


def _main() -> int:
    tests = [
        test_p1_old_remove_then_append_structure_is_gone,
        test_p2_all_three_render_paths_replace_in_place,
        test_p3_insert_replaces_first_placeholder_and_falls_back,
        test_p4_extracted_js_fills_from_the_top_for_every_count,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"ERROR {t.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"PASS {t.__name__}")
        sys.stdout.flush()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.stdout.flush()
    import os

    os._exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
