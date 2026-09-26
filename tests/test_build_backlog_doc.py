"""빌드 대기 목록 문서가 실제 코드·이력과 어긋나지 않는지 (문서 변경의 불변식).

`네이티브_빌드_대기목록.md`는 "빌드할 때 이걸 챙겨라"를 안내하는 유일한 목록이라,
가리키는 커밋·심볼이 실제로 없거나 분류가 틀리면 그 자리에서 사람을 헤매게 한다.
그래서 문서에 적힌 것만, 문서 기준으로 검사한다.

  B1. 문서에 적힌 커밋 해시는 전부 이 저장소에 실제로 존재한다.
  B2. 문서가 "대상 파일/심볼"로 가리키는 것이 실제로 코드에 있다.
  B3. 문서의 분류가 맞다 — "빌드 필요" 항목의 커밋은 `LottoShinryeong/`(네이티브)를
      실제로 건드렸고, "빌드 불필요" 항목의 커밋은 네이티브를 전혀 안 건드린다.
  B4. 문서가 적은 현재 상태(테스터 임시 충전 스위치 ON)가 실제 코드와 같다.

pytest 없이도 돌도록 표준 assert + __main__ 러너를 둔다(이 프로젝트 규칙).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "네이티브_빌드_대기목록.md"
NATIVE_PREFIX = "LottoShinryeong/"

HASH_RE = re.compile(r"`([0-9a-f]{7,40})`")


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _doc() -> str:
    return DOC.read_text(encoding="utf-8")


def _section(start_marker: str, end_marker: str | None = None) -> str:
    text = _doc()
    assert start_marker in text, f"문서에서 구역을 못 찾았다: {start_marker!r}"
    tail = text.split(start_marker, 1)[1]
    if end_marker:
        assert end_marker in tail, f"문서 구역의 끝을 못 찾았다: {end_marker!r}"
        tail = tail.split(end_marker, 1)[0]
    return tail


def test_B1_every_commit_hash_in_the_doc_exists():
    hashes = sorted(set(HASH_RE.findall(_doc())))
    assert hashes, "문서에 커밋 해시가 하나도 없다 - '어느 커밋이었는지' 추적이 안 된다"
    missing = []
    for h in hashes:
        if _git("rev-parse", "--verify", "--quiet", f"{h}^{{commit}}").returncode != 0:
            missing.append(h)
    assert missing == [], f"문서가 가리키는 커밋이 저장소에 없다: {missing}"
    print(f"  (문서의 커밋 해시 {len(hashes)}개 전부 존재)")


def test_B2_referenced_symbols_exist():
    tsx = (ROOT / "LottoShinryeong/components/streamlit-webview.tsx").read_text(encoding="utf-8")
    wallet = (ROOT / "wallet_ui.py").read_text(encoding="utf-8")
    assert "handleNativeBack" in tsx, "문서가 가리키는 네이티브 뒤로가기 처리 심볼이 없다"
    assert "reloadWith({ native_kakao_token" in tsx, (
        "문서가 가리키는 로그인 복귀(현재 주소 기준) 코드가 없다"
    )
    assert "def inject_manual_dialog_back_bridge" in wallet, (
        "문서가 가리키는 다이얼로그 열림 브리지가 없다"
    )
    print("  (문서가 가리키는 심볼 3개 전부 존재)")


def test_B3_the_needs_build_classification_matches_git():
    """문서의 분류를 커밋이 실제로 건드린 파일로 검증한다.

    '빌드가 필요 없다'고 적어둔 항목이 사실은 네이티브를 건드렸다면 그 사람은
    영원히 화면이 안 바뀌는 걸 기다리게 된다 — 반대도 마찬가지다."""
    needs_build = set(HASH_RE.findall(_section("## 2. 로그인 후", "## 3.")))
    assert needs_build, "§2(빌드 필요)에 커밋 해시가 없다"

    no_build = set(HASH_RE.findall(_section("## 참고 — 빌드가 필요")))
    assert no_build, "§참고(빌드 불필요)에 커밋 해시가 없다"

    for h in sorted(needs_build):
        files = _git("show", "--name-only", "--pretty=format:", h).stdout
        touched = [f for f in files.splitlines() if f.startswith(NATIVE_PREFIX)]
        assert touched, f"§2가 '빌드 필요'라고 적은 {h}가 네이티브 파일을 안 건드렸다: {sorted(files.split())}"

    for h in sorted(no_build):
        files = _git("show", "--name-only", "--pretty=format:", h).stdout
        touched = [f for f in files.splitlines() if f.startswith(NATIVE_PREFIX)]
        assert touched == [], (
            f"'빌드 불필요'로 분류한 {h}가 네이티브 파일을 건드렸다(분류 오류): {touched}"
        )
    print(
        f"  (빌드 필요 {len(needs_build)}건은 네이티브를 건드림, "
        f"빌드 불필요 {len(no_build)}건은 서버 파일만 건드림)"
    )


def test_B4_documented_current_state_is_true():
    wallet = (ROOT / "wallet_ui.py").read_text(encoding="utf-8")
    on = "TEST_CHARGE_ENABLED = True" in wallet
    off = "TEST_CHARGE_ENABLED = False" in wallet
    assert on != off, "TEST_CHARGE_ENABLED 스위치를 한 곳에서 못 찾았다(정본은 wallet_ui.py)"
    doc = _doc()
    if on:
        assert "심사 제출 전 `False`" in doc, (
            "테스터 임시 충전이 켜져 있는데 문서에 '제출 전 내릴 것' 경고가 없다"
        )
    print(f"  (임시 충전 스위치 현재 {'ON' if on else 'OFF'} - 문서 상태 표기와 일치)")


def _main() -> int:
    tests = [
        test_B1_every_commit_hash_in_the_doc_exists,
        test_B2_referenced_symbols_exist,
        test_B3_the_needs_build_classification_matches_git,
        test_B4_documented_current_state_is_true,
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
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
