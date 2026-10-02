"""카카오 네이티브 로그인 '락 고착' 수정(커밋 8a685545)이 실제로 그렇게 동작하는지 — 계약.

배경: `kakaoNativeLogin()`이 응답 없이 멈추면 `triggerKakaoNativeLoginOnce`의
`kakaoLoginLockRef`가 영원히 안 풀려서, 그 뒤 로그인 버튼을 몇 번을 눌러도 앱이
조용히 무시했다(서버에는 kakao_native_trigger만 쌓이고 ok/fail이 없음). 이번 수정은
그 SDK 호출을 withTimeout으로 감싸 20초에서 끊어 락을 풀어준다.

왜 이 파일이 필요한가: tsc 통과(컴파일)와 tsx 문자열 검사는 "멈추면 정말 풀리는가"
를 하나도 검사하지 않는다. 그래서 `LottoShinryeong/components/streamlit-webview.tsx`
에서 **본문을 원문 그대로 추출**해 가짜 환경(setWebViewUri·reloadWith·
kakaoNativeLogin 스텁)에 묶은 하네스를 node로 실행한다 — 상수 값만 테스트용으로
줄이고(20000 → 60ms), 나머지 분기·락 로직은 추출한 원문 그대로다.

  K1. withTimeout은 먼저 끝난 쪽이 이긴다 — 값은 그대로, 거절은 '같은 오류 객체'로.
  K2. 응답이 없으면 ms 뒤 반드시 거절하고(영원히 대기하지 않는다), 그 뒤 늦게
      성공해도 이미 끝난 결과를 뒤집지 않는다.
  K3. 성공 경로: 토큰이 주소에 그대로 실리고 로드는 정확히 1회, SDK 호출 1회.
  K4. 멈춤 경로: 호출 중에는 락이 걸리지만 타임아웃 뒤 풀리고, 다시 누르면 SDK를
      **다시 실제로 부른다**(재시도가 먹는다). ← 이 항목이 수정 전 소스에서는 실패한다.
  K5. 취소·실패 경로: 주소를 건드리지 않고 락만 풀며, 잡히지 않은 거절이 남지 않는다.
  K6. 타이머는 항상 정리된다 — 안 끝난 타이머가 남아 프로세스를 붙잡지 않는다.
  K7. 정적 배선: SDK 호출이 타임아웃으로 감싸져 있고, 상수는 실제로 쓰이며
      범위 안(0 < ms <= 60초)이다(죽은 상수가 아니다).

pytest 없음(이 프로젝트 규칙) — 표준 assert + `__main__` 러너로 돌린다.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
TSX_REL = "LottoShinryeong/components/streamlit-webview.tsx"
TSX = ROOT / TSX_REL

HANDLE_START = "const handleKakaoNativeLogin = useCallback(async () => {"
HANDLE_END = "}, [reloadWith]);"
TRIGGER_START = "const triggerKakaoNativeLoginOnce = useCallback(() => {"
TRIGGER_END = "}, [handleKakaoNativeLogin]);"
WITH_TIMEOUT_HEAD = "function withTimeout<T>("
CONST_RE = re.compile(r"const KAKAO_NATIVE_LOGIN_TIMEOUT_MS = (\d+);")
TEST_TIMEOUT_MS = 60  # 상수 값만 줄여서 실행(20초를 기다리면 테스트가 느려진다)


# ── 원문 추출 ────────────────────────────────────────────────────────────────
def _tsx() -> str:
    return TSX.read_text(encoding="utf-8")


def _span(text: str, start: str, end: str) -> str:
    assert start in text, f"원문에서 시작 앵커를 못 찾았다: {start!r}"
    i = text.index(start)
    j = text.index(end, i)
    return text[i : j + len(end)]


def _block(text: str, start: str) -> str:
    """`start`부터 중괄호 짝이 맞는 끝까지(함수 선언 하나를 통째로)."""
    assert start in text, f"원문에서 블록 시작을 못 찾았다: {start!r}"
    i = text.index(start)
    depth = 0
    for k in range(text.index("{", i), len(text)):
        if text[k] == "{":
            depth += 1
        elif text[k] == "}":
            depth -= 1
            if depth == 0:
                return text[i : k + 1]
    raise AssertionError(f"블록 끝을 못 찾았다: {start!r}")


def _with_timeout_js(source: str) -> str:
    """원문의 withTimeout을 JS로 실행 가능하게 만든다 — 파라미터 목록(기본 타임아웃 메시지
    포함)은 원문에서 그대로 가져오고 타입 표기만 벗긴다. 그래야 기본값이 테스트에
    하드코딩되지 않고, 인자가 늘어도 하네스가 조용히 옛 시그니처를 쓰지 않는다."""
    if WITH_TIMEOUT_HEAD not in source:
        return ""
    block = _block(source, WITH_TIMEOUT_HEAD)
    head_end = block.index("(")
    params_end = block.index(")", head_end)
    params = block[head_end + 1 : params_end]
    js_params = re.sub(r":\s*Promise<T>", "", params)
    js_params = re.sub(r":\s*(?:number|string)", "", js_params)
    assert ":" not in js_params, f"파라미터 타입 표기가 남았다: {js_params!r}"
    js = "function withTimeout(" + js_params + ") " + block[block.index("{", params_end) :]
    stripped = js.replace("Promise<T>", "Promise")
    assert stripped != js, "withTimeout 본문의 타입 표기를 벗기지 못했다"
    return stripped


def _previous_source() -> str:
    """이 수정 커밋의 직전 소스 — '수정 전에는 이 계약이 실패한다'를 보이기 위한 대조군."""
    found = subprocess.run(
        ["git", "log", "-S", "KAKAO_NATIVE_LOGIN_TIMEOUT_MS", "--format=%H", "-1", "--", TSX_REL],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    hashes = [h for h in found.stdout.split() if h]
    assert hashes, "이 수정 커밋을 git 이력에서 찾지 못했다(대조군 없이는 이 테스트가 아무것도 구분하지 못한다)"
    shown = subprocess.run(
        ["git", "show", f"{hashes[0]}^:{TSX_REL}"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert shown.returncode == 0, f"수정 전 소스를 얻지 못했다: {shown.stderr[:200]}"
    return shown.stdout


# ── 하네스(추출한 원문을 가짜 환경에 묶어 node로 실행) ────────────────────────
HARNESS = r"""'use strict';
const out = { scenarios: {}, unhandled: [] };
process.on('unhandledRejection', (e) => { out.unhandled.push(String((e && e.message) || e)); });

const useCallback = (fn) => fn;
const useRef = (initial) => ({ current: initial });
const state = { uri: null, loads: 0, sdkCalls: 0, sdk: () => new Promise(() => {}) };
const setWebViewUri = (u) => { state.uri = u; state.loads += 1; };
const reloadWith = (params) => 'url?' + Object.keys(params).map((k) => k + '=' + params[k]).join('&');
const kakaoNativeLogin = () => { state.sdkCalls += 1; return state.sdk(); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

__CONST__
__WITHTIMEOUT__
__HANDLE__
const kakaoLoginLockRef = useRef(false);
__TRIGGER__

const run = async () => {
  // K3 성공 경로
  state.uri = null; state.loads = 0; state.sdkCalls = 0;
  state.sdk = () => Promise.resolve({ accessToken: 'TOK1' });
  triggerKakaoNativeLoginOnce();
  await sleep(30);
  out.scenarios.success = { lock: kakaoLoginLockRef.current, uri: state.uri, loads: state.loads, sdkCalls: state.sdkCalls };

  // K4 멈춘 SDK: 호출 중 잠금 → 타임아웃 후 해제 → 재시도가 실제로 SDK를 다시 부른다
  state.uri = null; state.loads = 0; state.sdkCalls = 0;
  state.sdk = () => new Promise(() => {});   // 영원히 안 끝난다 = 실기기 '응답 없음' 상황
  triggerKakaoNativeLoginOnce();
  out.scenarios.hang_immediately = { lock: kakaoLoginLockRef.current, sdkCalls: state.sdkCalls };
  await sleep(250);                          // 테스트용 타임아웃(60ms)보다 충분히 길게
  out.scenarios.hang_after_timeout = { lock: kakaoLoginLockRef.current, uri: state.uri, loads: state.loads, sdkCalls: state.sdkCalls };
  state.sdk = () => Promise.resolve({ accessToken: 'TOK2' });
  triggerKakaoNativeLoginOnce();             // 사용자가 다시 누른다
  await sleep(40);
  out.scenarios.retry_after_hang = { lock: kakaoLoginLockRef.current, uri: state.uri, loads: state.loads, sdkCalls: state.sdkCalls };

  // K5 취소·실패
  state.uri = null; state.loads = 0; state.sdkCalls = 0;
  state.sdk = () => Promise.reject(new Error('user cancelled'));
  triggerKakaoNativeLoginOnce();
  await sleep(30);
  out.scenarios.cancel = { lock: kakaoLoginLockRef.current, uri: state.uri, loads: state.loads };

  // K1·K2 withTimeout 자체의 계약 (이 함수가 없는 소스에서는 건너뛴다)
  if (typeof withTimeout === 'function') {
    const probe = {};
    probe.resolve_wins = (await withTimeout(Promise.resolve('VAL'), 60)) === 'VAL';
    const err = new Error('boom');
    probe.reject_same_error = false;
    try { await withTimeout(Promise.reject(err), 60); } catch (e) { probe.reject_same_error = e === err; }
    const t0 = Date.now();
    probe.timeout_message = null;
    try { await withTimeout(new Promise(() => {}), 60); } catch (e) { probe.timeout_message = String((e && e.message) || e); }
    probe.timeout_elapsed_ms = Date.now() - t0;
    probe.custom_timeout_message = null;
    try { await withTimeout(new Promise(() => {}), 60, 'custom_timeout'); } catch (e) { probe.custom_timeout_message = String((e && e.message) || e); }
    let lateResolve = null;
    const late = new Promise((r) => { lateResolve = r; });
    let settled = null;
    withTimeout(late, 60).catch((e) => { settled = String((e && e.message) || e); });
    await sleep(120);
    lateResolve('LATE');
    await sleep(20);
    probe.late_settle_does_not_flip = settled === 'kakao_native_login_timeout';
    // K6: 타이머가 정리 안 되면 이 5000ms 타이머가 프로세스를 5초 더 붙잡는다
    probe.timer_cleared_value = await withTimeout(Promise.resolve('Q'), 5000);
    out.scenarios.with_timeout = probe;
  }

  out.done = true;
};

run().then(
  () => { console.log('HARNESS_JSON:' + JSON.stringify(out)); },
  (e) => { console.log('HARNESS_ERROR:' + String((e && e.stack) || e)); process.exitCode = 3; }
);
"""

_CACHE: dict[str, dict] = {}


def _build_harness(source: str) -> str:
    const_match = CONST_RE.search(source)
    # 값만 테스트용으로 줄이고 선언은 그대로 (원문 20000ms를 기다리면 테스트가 느려진다)
    const_js = ""
    if const_match:
        const_js = f"const KAKAO_NATIVE_LOGIN_TIMEOUT_MS = {TEST_TIMEOUT_MS};"
        assert const_js != const_match.group(0), "타임아웃 상수를 테스트용 값으로 줄이지 못했다"
    with_timeout_js = _with_timeout_js(source)
    return (
        HARNESS.replace("__CONST__", const_js)
        .replace("__WITHTIMEOUT__", with_timeout_js)
        .replace("__HANDLE__", _span(source, HANDLE_START, HANDLE_END))
        .replace("__TRIGGER__", _span(source, TRIGGER_START, TRIGGER_END))
    )


def _run_node(source: str, label: str) -> dict:
    node = shutil.which("node")
    assert node, "node가 없어 변경된 동작을 실행할 수 없다"
    harness = _build_harness(source)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"harness_{label}.js"
        path.write_text(harness, encoding="utf-8")
        started = time.time()
        proc = subprocess.run(
            [node, str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        elapsed = time.time() - started
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("HARNESS_JSON:")), None)
    error = next((ln for ln in proc.stdout.splitlines() if ln.startswith("HARNESS_ERROR:")), None)
    assert line, (
        f"하네스가 결과를 내지 않았다({label}): rc={proc.returncode}"
        f"\nstdout={proc.stdout[-800:]}\nstderr={proc.stderr[-800:]}\n{error or ''}"
    )
    result = json.loads(line[len("HARNESS_JSON:") :])
    assert result.get("done") is True, f"하네스가 중간에 멈췄다({label}): {result!r}"
    result["elapsed_sec"] = elapsed
    result["_stderr"] = proc.stderr[-400:]
    return result


def _new_run() -> dict:
    if "new" not in _CACHE:
        _CACHE["new"] = _run_node(_tsx(), "new")
    return _CACHE["new"]


def _old_run() -> dict:
    if "old" not in _CACHE:
        _CACHE["old"] = _run_node(_previous_source(), "old")
    return _CACHE["old"]


# ── K1·K2: withTimeout 자체의 계약 ──────────────────────────────────────────
def test_K1_K2_with_timeout_contract() -> None:
    probe = _new_run()["scenarios"].get("with_timeout")
    assert probe, "withTimeout 계약을 검사하지 못했다(함수가 추출되지 않음)"
    assert probe["resolve_wins"] is True, "먼저 성공한 값이 그대로 나오지 않았다"
    assert probe["reject_same_error"] is True, "원래 오류를 감싸서(다른 객체로) 던졌다"
    assert probe["timeout_message"] == "kakao_native_login_timeout", (
        f"§6 기본 문구가 바뀌었다(호출부를 안 고쳤는데 값이 달라졌다): {probe['timeout_message']!r}"
    )
    assert probe["custom_timeout_message"] == "custom_timeout", (
        f"세 번째 인자로 준 문구가 안 쓰였다(문구 구분이 안 된다): {probe['custom_timeout_message']!r}"
    )
    assert 60 <= probe["timeout_elapsed_ms"] <= 1000, (
        f"응답이 없을 때 ms 안에 안 끊겼다: {probe['timeout_elapsed_ms']}ms"
    )
    assert probe["late_settle_does_not_flip"] is True, "타임아웃 뒤 늦게 성공한 값이 결과를 뒤집었다"
    assert probe["timer_cleared_value"] == "Q", "이미 끝난 약속의 값이 그대로 나오지 않았다"
    print("  (K1·K2 withTimeout: 값/오류 그대로, 응답 없으면 ms 뒤 거절, 늦은 성공이 결과를 못 뒤집음, 기본 문구 유지·지정 문구 구분)")


# ── K3·K4·K5: 컴포넌트 조립 동작 ────────────────────────────────────────────
def test_K3_K4_K5_composition_behaviour() -> None:
    run = _new_run()
    s = run["scenarios"]

    assert s["success"]["lock"] is False and s["success"]["loads"] == 1, (
        f"로그인 성공 경로가 깨졌다: {s['success']!r}"
    )
    assert "native_kakao_token=TOK1" in (s["success"]["uri"] or ""), (
        f"토큰이 주소에 그대로 실리지 않았다: {s['success']['uri']!r}"
    )
    assert s["success"]["sdkCalls"] == 1, "성공 경로에서 SDK를 두 번 불렀다"

    assert s["hang_immediately"]["lock"] is True, "호출 중에는 중복 트리거가 막혀야 한다(중복 로그인 방지)"
    assert s["hang_after_timeout"]["lock"] is False, (
        "SDK가 멈추면 락이 영원히 안 풀린다 — 고치려던 증상이 그대로다"
    )
    assert s["hang_after_timeout"]["loads"] == 0, "멈춘 호출이 화면을 이동시켰다"

    assert s["retry_after_hang"]["sdkCalls"] == 2, (
        f"타임아웃 후 재시도가 SDK를 다시 부르지 못했다: {s['retry_after_hang']!r}"
    )
    assert "native_kakao_token=TOK2" in (s["retry_after_hang"]["uri"] or ""), (
        f"재시도가 성공으로 이어지지 않았다: {s['retry_after_hang']!r}"
    )

    assert s["cancel"]["lock"] is False, "사용자 취소 후 락이 안 풀렸다"
    assert s["cancel"]["uri"] is None and s["cancel"]["loads"] == 0, "취소인데 화면을 이동시켰다"
    assert run["unhandled"] == [], f"잡히지 않은 거절이 남았다: {run['unhandled']!r}"
    print("  (K3·K4·K5 조립: 성공 1회 이동, 멈춤→20초 상당 뒤 락 해제·재시도가 실제로 SDK 재호출, 취소는 무이동)")


# ── K4 대조군: 수정 전 소스에서는 실제로 실패한다 ────────────────────────────
def test_K4_the_previous_source_fails_this_contract() -> None:
    old = _old_run()["scenarios"]
    assert old["success"]["loads"] == 1, "수정 전에도 성공 경로는 정상이었어야 한다(기존 동작 보존 확인)"
    assert old["hang_immediately"]["lock"] is True
    assert old["hang_after_timeout"]["lock"] is True, (
        "수정 전 소스에서도 락이 풀렸다면 이 테스트는 아무것도 구분하지 못한다"
    )
    assert old["retry_after_hang"]["sdkCalls"] == 1, "수정 전인데 재시도가 SDK를 다시 불렀다"
    assert old["retry_after_hang"]["uri"] is None
    assert "with_timeout" not in old, "수정 전 소스에 withTimeout이 있었다"
    print("  (대조군: 수정 전 소스는 같은 시나리오에서 락이 안 풀리고 재시도가 SDK를 다시 안 부른다)")


# ── K6: 타이머 정리 ─────────────────────────────────────────────────────────
def test_K6_timers_are_always_cleared() -> None:
    elapsed = _new_run()["elapsed_sec"]
    assert elapsed < 3.0, (
        f"끝난 약속의 타임아웃 타이머가 안 정리돼 node가 붙잡혔다(5초 타이머 프로브 포함): {elapsed:.2f}s"
    )
    print(f"  (K6 타이머 정리: 하네스 전체 실행 {elapsed:.2f}s - 5초 타이머가 남지 않았다)")


# ── K7: 정적 배선·경계 ──────────────────────────────────────────────────────
def test_K7_static_wiring_and_bounds() -> None:
    text = _tsx()
    match = CONST_RE.search(text)
    assert match, "타임아웃 상수 선언을 못 찾았다"
    ms = int(match.group(1))
    assert 0 < ms <= 60000, f"타임아웃이 쓸 수 있는 범위 밖이다: {ms}ms"
    assert text.count("KAKAO_NATIVE_LOGIN_TIMEOUT_MS") >= 2, "상수가 선언만 되고 안 쓰인다(죽은 상수)"
    assert "await withTimeout(kakaoNativeLogin(), KAKAO_NATIVE_LOGIN_TIMEOUT_MS)" in text, (
        "SDK 호출이 타임아웃으로 감싸지지 않았다 — 멈추면 다시 락이 고착된다"
    )
    handle = _span(text, HANDLE_START, HANDLE_END)
    assert "throw" not in handle, "실패를 다시 던지면 .finally() 전에 거절이 새어 나간다"
    assert "handleKakaoNativeLogin().finally(" in text, "락 해제가 .finally()에서 사라졌다"
    assert text.index("kakaoLoginLockRef.current = false;") > text.index("handleKakaoNativeLogin().finally("), (
        "락 해제가 .finally() 밖으로 나갔다"
    )
    assert text.count("triggerKakaoNativeLoginOnce()") >= 3, (
        "트리거 도달 경로(URL 2 + postMessage 1)가 줄었다 — 로그인 버튼이 특정 기기에서 죽는다"
    )
    print(f"  (K7 정적: 상수 {ms}ms 사용 중, SDK 호출 감쌈, 락 해제는 .finally(), 트리거 경로 3곳 유지)")


def _main() -> int:
    tests = [
        test_K1_K2_with_timeout_contract,
        test_K3_K4_K5_composition_behaviour,
        test_K4_the_previous_source_fails_this_contract,
        test_K6_timers_are_always_cleared,
        test_K7_static_wiring_and_bounds,
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
