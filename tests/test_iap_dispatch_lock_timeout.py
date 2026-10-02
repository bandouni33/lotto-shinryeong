"""IAP 결제 실행 락(purchaseInFlightRef)이 '멈춘 호출'에서 실제로 풀리는지 — 계약 (§7, 2026-10-01).

배경: §6(카카오 로그인 락)과 같은 구조. 결제 실행 `useEffect`는 fetchProducts/
requestPurchase를 await하는 동안 `purchaseInFlightRef`를 true로 세우고 `finally`에서만
푼다. 둘 중 하나가 응답 없이 멈추면 락이 영원히 안 풀려 이후 결제 요청이 전부 조용히
무시된다(가드: `if (!iapRequest || Platform.OS !== 'android' || purchaseInFlightRef.current) return;`).

안전성도 여기서 같이 검사한다: requestPurchase는 결제 완료가 아니라 '요청 전달 확인'만
돌려주고 실제 결과는 purchaseUpdatedListener로 온다 — 설치본 expo-iap 5.6.3의
ExpoIapModule.kt(addPurchasePromise → resolvePurchasePromises가 openIap.requestPurchase
반환 직후의 유일 호출)와 공식 문서(openiap.dev/docs/apis/request-purchase)가 그렇게
규정한다. 그래서 타임아웃을 걸어도 사용자가 결제창에서 입력 중인 걸 끊지 않는다.

tsx에서 **본문을 원문 그대로 추출**해(TS 전용 표기만 제거) 가짜 환경(Platform·
fetchProducts·requestPurchase·Alert·setIapRequest)에 묶은 하네스를 node로 실행한다.
타임아웃 상수 값만 줄인다(20000 → 60ms).

  I1. 성공 경로: in-app과 구독(offerToken 분기) 모두 호출 1회·락 해제·요청 정리·알림 없음,
      그리고 감싼 뒤에도 스토어로 넘어가는 요청 내용(인자)이 그대로다.
  I2. 멈춘 fetchProducts: 실행 중에는 락이 잡혀 중복 요청이 무시되지만, 타임아웃 뒤에는
      락이 풀리고 재시도가 실제로 다시 시작된다.
  I3. 멈춘 requestPurchase: 같은 결과(락 해제 + 사용자 알림 1건).
  I4. 디스패치 실패(throw): 락 해제 + 알림 1건(기존 catch 그대로).
  I5. 대조군: 수정 전 소스는 같은 시나리오에서 락이 안 풀린다(테스트가 구분력을 가진다).
  I6. 문구 배선: 결제용 타임아웃 문구는 §7 호출부 3곳에만 붙고, §6 호출부는 그대로다.

pytest 없음(이 프로젝트 규칙) — 표준 assert + `__main__` 러너.
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

EFFECT_START = "useEffect(() => {\n    if (!iapRequest"
EFFECT_END = "  }, [iapRequest]);"
CONST_RE = re.compile(r"const IAP_DISPATCH_TIMEOUT_MS = (\d+);")
WITH_TIMEOUT_HEAD = "function withTimeout<T>("
# 결제 실행 effect 안에 있는 TS 전용 캐스트(`as const`, `as ProductSubscription`,
# `as Array<...>` 등) — 로직은 그대로 두고 이것만 벗긴다.
CAST_RE = re.compile(r"\s+as\s+(?:const|[A-Za-z_$][\w$.]*(?:<[^;()]*?>)?)")
TEST_TIMEOUT_MS = 60  # 상수 값만 줄여서 실행(20초를 기다리면 테스트가 느려진다)


# ── 원문 추출 ────────────────────────────────────────────────────────────────
def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _tsx() -> str:
    return TSX.read_text(encoding="utf-8").replace("\r\n", "\n")


def _span(text: str, start: str, end: str) -> str:
    assert start in text, f"원문에서 시작 앵커를 못 찾았다: {start!r}"
    i = text.index(start)
    j = text.index(end, i)
    return text[i : j + len(end)]


def _block(text: str, start: str) -> str:
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
    """이 수정 직전 소스(대조군). 아직 커밋 전이면 HEAD가 곧 직전 소스다."""
    found = _git("log", "-S", "IAP_DISPATCH_TIMEOUT_MS", "--format=%H", "-1", "--", TSX_REL)
    hashes = [h for h in found.stdout.split() if h]
    rev = f"{hashes[0]}^" if hashes else "HEAD"
    shown = _git("show", f"{rev}:{TSX_REL}")
    assert shown.returncode == 0, f"수정 전 소스를 얻지 못했다({rev}): {shown.stderr[:200]}"
    return shown.stdout.replace("\r\n", "\n")


# ── 하네스 ──────────────────────────────────────────────────────────────────
HARNESS = r"""'use strict';
const out = { scenarios: {}, unhandled: [] };
process.on('unhandledRejection', (e) => { out.unhandled.push(String((e && e.message) || e)); });

const runtime = {
  effects: [], alerts: [], fetchCalls: 0, requestCalls: 0, requestArgs: [],
  fetch: () => Promise.resolve([]), request: () => Promise.resolve(),
};
const Platform = { OS: 'android' };
const useRef = (initial) => ({ current: initial });
const useEffect = (fn) => { runtime.effects.push(fn); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const Alert = { alert: (title, message) => { runtime.alerts.push({ title, message }); } };
const fetchProducts = (args) => { runtime.fetchCalls += 1; return runtime.fetch(args); };
const requestPurchase = (args) => {
  runtime.requestCalls += 1;
  runtime.requestArgs.push(args);
  return runtime.request(args);
};
const purchaseInFlightRef = useRef(false);
let iapRequest = null;
const setIapRequest = (value) => { iapRequest = value; };

__CONST__
__WITHTIMEOUT__
__EFFECT__

const startRequest = (request) => {          // 컴포넌트가 iapRequest를 세팅해 effect가 도는 상황
  iapRequest = request;
  for (const fn of runtime.effects) { fn(); }
};
const reset = () => {
  runtime.alerts.length = 0;
  runtime.fetchCalls = 0;
  runtime.requestCalls = 0;
  runtime.requestArgs.length = 0;
  iapRequest = null;
};
const snap = () => ({ lock: purchaseInFlightRef.current, iapRequest, alerts: runtime.alerts.slice() });

const run = async () => {
  const PRODUCT = { id: 'points_1000' };
  const SUB = {
    id: 'premium',
    subscriptionOffers: [{ basePlanIdAndroid: 'premium-monthly', offerTokenAndroid: 'OFFER_TOK' }],
  };

  // I1a 성공(in-app) — 감싼 뒤에도 스토어로 가는 인자가 그대로인지까지 본다
  reset();
  runtime.fetch = () => Promise.resolve([PRODUCT]);
  runtime.request = () => Promise.resolve({ productId: 'points_1000' });
  startRequest({ sku: 'points_1000' });
  out.scenarios.success_inapp_inflight = { lock: purchaseInFlightRef.current };
  await sleep(30);
  out.scenarios.success_inapp = {
    ...snap(),
    fetchCalls: runtime.fetchCalls,
    requestCalls: runtime.requestCalls,
    skus: (runtime.requestArgs[0] || {}).request?.google?.skus ?? null,
  };

  // I1b 성공(구독 — offerToken 분기)
  reset();
  runtime.fetch = () => Promise.resolve([SUB]);
  runtime.request = () => Promise.resolve({ productId: 'premium' });
  startRequest({ sku: 'premium', basePlanId: 'premium-monthly' });
  await sleep(30);
  out.scenarios.success_subs = {
    ...snap(),
    requestCalls: runtime.requestCalls,
    offers: (runtime.requestArgs[0] || {}).request?.google?.subscriptionOffers ?? null,
    type: (runtime.requestArgs[0] || {}).type ?? null,
  };

  // I2 멈춘 fetchProducts
  reset();
  runtime.fetch = () => new Promise(() => {});
  startRequest({ sku: 'points_1000' });
  await sleep(20);
  out.scenarios.hang_fetch_inflight = { lock: purchaseInFlightRef.current, fetchCalls: runtime.fetchCalls };
  startRequest({ sku: 'points_1000' });                 // I2b 실행 중 중복 요청
  out.scenarios.hang_fetch_duplicate = { fetchCalls: runtime.fetchCalls };
  await sleep(250);                                     // 테스트 타임아웃(60ms) 초과
  out.scenarios.hang_fetch_after_timeout = { ...snap(), requestCalls: runtime.requestCalls };

  // I2c 타임아웃 뒤 재시도가 실제로 다시 시작된다
  reset();
  runtime.fetch = () => Promise.resolve([PRODUCT]);
  runtime.request = () => Promise.resolve({ productId: 'points_1000' });
  startRequest({ sku: 'points_1000' });
  await sleep(30);
  out.scenarios.retry_after_hang = {
    ...snap(), fetchCalls: runtime.fetchCalls, requestCalls: runtime.requestCalls,
  };

  // I3 멈춘 requestPurchase
  reset();
  runtime.fetch = () => Promise.resolve([PRODUCT]);
  runtime.request = () => new Promise(() => {});
  startRequest({ sku: 'points_1000' });
  await sleep(20);
  out.scenarios.hang_request_inflight = { lock: purchaseInFlightRef.current, requestCalls: runtime.requestCalls };
  await sleep(250);
  out.scenarios.hang_request_after_timeout = snap();

  // I4 디스패치 실패(스토어가 요청 자체를 거부)
  reset();
  runtime.fetch = () => Promise.resolve([PRODUCT]);
  runtime.request = () => Promise.reject(Object.assign(new Error('dispatch failed'), { code: 'not-prepared' }));
  startRequest({ sku: 'points_1000' });
  await sleep(30);
  out.scenarios.dispatch_failure = snap();

  out.done = true;
};

run().then(
  () => { console.log('HARNESS_JSON:' + JSON.stringify(out)); },
  (e) => { console.log('HARNESS_ERROR:' + String((e && e.stack) || e)); process.exitCode = 3; }
);
"""

_CACHE: dict[str, dict] = {}


def _build_harness(source: str) -> str:
    effect = _span(source, EFFECT_START, EFFECT_END)
    casts = CAST_RE.findall(effect)
    assert casts, "결제 실행 effect에서 TS 캐스트를 못 찾았다(추출이 어긋났다)"
    effect = CAST_RE.sub("", effect)
    assert " as " not in effect, f"TS 캐스트가 남아 JS로 실행할 수 없다: {casts!r}"

    const_match = CONST_RE.search(source)
    const_js = ""
    if const_match:
        const_js = f"const IAP_DISPATCH_TIMEOUT_MS = {TEST_TIMEOUT_MS};"
        assert const_js != const_match.group(0), "타임아웃 상수를 테스트용 값으로 줄이지 못했다"

    with_timeout_js = _with_timeout_js(source)

    return (
        HARNESS.replace("__CONST__", const_js)
        .replace("__WITHTIMEOUT__", with_timeout_js)
        .replace("__EFFECT__", effect)
    )


def _run_node(source: str, label: str) -> dict:
    node = shutil.which("node")
    assert node, "node가 없어 변경된 동작을 실행할 수 없다"
    harness = _build_harness(source)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"iap_harness_{label}.js"
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
    return result


def _new_run() -> dict:
    if "new" not in _CACHE:
        _CACHE["new"] = _run_node(_tsx(), "new")
    return _CACHE["new"]


def _old_run() -> dict:
    if "old" not in _CACHE:
        _CACHE["old"] = _run_node(_previous_source(), "old")
    return _CACHE["old"]


# ── I1: 성공 경로(기존 동작이 그대로인가) ────────────────────────────────────
def test_I1_success_path_dispatches_once_and_releases_the_lock() -> None:
    run = _new_run()
    s = run["scenarios"]
    inapp = s["success_inapp"]
    assert s["success_inapp_inflight"]["lock"] is True, "실행 중에는 락이 잡혀 있어야 한다(중복 결제창 방지)"
    assert inapp["lock"] is False, f"성공 뒤 락이 안 풀렸다: {inapp!r}"
    assert inapp["iapRequest"] is None, "성공 뒤 요청 상태가 정리되지 않았다"
    assert inapp["alerts"] == [], f"성공인데 알림이 떴다: {inapp['alerts']!r}"
    assert inapp["fetchCalls"] == 1 and inapp["requestCalls"] == 1, (
        f"상품조회/결제요청 횟수가 다르다: {inapp!r}"
    )
    assert inapp["skus"] == ["points_1000"], f"감싼 뒤 스토어로 가는 인자가 달라졌다: {inapp['skus']!r}"

    subs = s["success_subs"]
    assert subs["lock"] is False and subs["alerts"] == [], f"구독 성공 경로가 깨졌다: {subs!r}"
    assert subs["type"] == "subs", f"구독 분기가 in-app으로 나갔다: {subs['type']!r}"
    assert subs["offers"] == [{"sku": "premium", "offerToken": "OFFER_TOK"}], (
        f"구독 offerToken(요금제) 인자가 달라졌다: {subs['offers']!r}"
    )
    assert run["unhandled"] == [], f"잡히지 않은 거절이 남았다: {run['unhandled']!r}"
    print("  (I1 성공: in-app·구독 각 1회, 락 해제·요청 정리·알림 없음, 스토어 인자 보존)")


# ── I2·I3: 멈춘 호출에서 락이 풀리는가 ──────────────────────────────────────
def test_I2_hung_fetch_products_releases_the_lock_and_allows_retry() -> None:
    s = _new_run()["scenarios"]
    assert s["hang_fetch_inflight"]["lock"] is True, "실행 중에는 락이 잡혀 있어야 한다"
    assert s["hang_fetch_duplicate"]["fetchCalls"] == 1, (
        f"실행 중 중복 요청이 그대로 시작됐다(결제창 중복 위험): {s['hang_fetch_duplicate']!r}"
    )
    after = s["hang_fetch_after_timeout"]
    assert after["lock"] is False, "fetchProducts가 멈추면 락이 영원히 안 풀린다 — 고치려던 증상 그대로다"
    assert after["iapRequest"] is None, "타임아웃 뒤 요청 상태가 안 풀렸다"
    assert len(after["alerts"]) == 1, f"타임아웃인데 사용자 알림이 없다: {after['alerts']!r}"
    assert after["alerts"][0]["message"] == "iap_dispatch_timeout", (
        f"결제 타임아웃인데 카카오 문구가 그대로 노출된다: {after['alerts']!r}"
    )
    assert after["requestCalls"] == 0, "상품을 못 받았는데 결제창을 띄웠다"

    retry = s["retry_after_hang"]
    assert retry["fetchCalls"] == 1 and retry["requestCalls"] == 1, (
        f"타임아웃 뒤 재시도가 실제로 시작되지 않았다: {retry!r}"
    )
    assert retry["lock"] is False and retry["alerts"] == [], f"재시도가 정상 진행되지 않았다: {retry!r}"
    print(
        "  (I2 멈춘 상품조회: 실행 중 중복 차단 → 20초 상당 뒤 락 해제·알림 1건 → 재시도가 다시 시작)"
    )


def test_I3_hung_request_purchase_releases_the_lock() -> None:
    s = _new_run()["scenarios"]
    assert s["hang_request_inflight"]["lock"] is True and s["hang_request_inflight"]["requestCalls"] == 1
    after = s["hang_request_after_timeout"]
    assert after["lock"] is False, "requestPurchase가 멈추면 락이 영원히 안 풀린다"
    assert after["iapRequest"] is None, "타임아웃 뒤 요청 상태가 안 풀렸다"
    assert len(after["alerts"]) == 1, f"타임아웃인데 사용자 알림이 없다: {after['alerts']!r}"
    assert after["alerts"][0]["message"] == "iap_dispatch_timeout", (
        f"결제 타임아웃 문구가 다르다(카카오 문구 노출): {after['alerts']!r}"
    )
    print("  (I3 멈춘 결제요청: 20초 상당 뒤 락 해제·알림 1건 - 문구 'iap_dispatch_timeout')")


def test_I4_dispatch_failure_alerts_and_releases_the_lock() -> None:
    after = _new_run()["scenarios"]["dispatch_failure"]
    assert after["lock"] is False, "디스패치 실패 뒤 락이 안 풀렸다(기존 catch/finally 경로)"
    assert len(after["alerts"]) == 1, f"실패인데 알림이 없다: {after['alerts']!r}"
    assert after["alerts"][0]["title"] == "결제를 시작할 수 없습니다", f"알림 제목이 다르다: {after['alerts']!r}"
    print("  (I4 디스패치 실패: 락 해제 + 기존 알림 문구 그대로)")


# ── I5: 대조군 — 수정 전 소스는 이 계약을 통과하지 못한다 ────────────────────
def test_I5_the_previous_source_keeps_the_lock() -> None:
    old = _old_run()["scenarios"]
    assert old["success_inapp"]["lock"] is False, "수정 전에도 성공 경로는 정상이었어야 한다"
    assert old["hang_fetch_inflight"]["lock"] is True
    assert old["hang_fetch_after_timeout"]["lock"] is True, (
        "수정 전 소스에서도 락이 풀렸다면 이 테스트는 아무것도 구분하지 못한다"
    )
    assert old["hang_fetch_after_timeout"]["alerts"] == [], "수정 전 소스에 타임아웃 알림이 있었다"
    assert old["retry_after_hang"]["fetchCalls"] == 0, "수정 전인데 재시도가 다시 시작됐다"
    assert old["hang_request_after_timeout"]["lock"] is True, "수정 전인데 결제요청 멈춤에서 락이 풀렸다"
    print("  (대조군: 수정 전 소스는 두 멈춤 시나리오 모두 락이 안 풀리고 재시도도 못 한다)")


# ── I6: 문구 배선 — §7 호출부만 결제용 문구를 넘기는가 ───────────────────
def test_message_wiring_is_iap_only() -> None:
    text = _tsx()
    count = text.count("'iap_dispatch_timeout'")
    assert count == 3, f"§7 호출부 3곳에만 결제용 문구가 넘어가야 한다(현재 {count}곳)"
    assert text.count("IAP_DISPATCH_TIMEOUT_MS,") == 3, "타임아웃 상수 뒤에 문구가 안 붙은 호출이 있다"
    assert "await withTimeout(kakaoNativeLogin(), KAKAO_NATIVE_LOGIN_TIMEOUT_MS)" in text, (
        "§6 호출부가 바뀌었다(문구를 넘기면 카카오 로그인 안내가 결제용 문구로 바뀐다)"
    )
    print("  (I6 문구 배선: §7 3곳은 'iap_dispatch_timeout', §6 호출부는 기본값 그대로)")


# ── 타이머 정리 ─────────────────────────────────────────────────────────────
def test_timers_are_always_cleared() -> None:
    elapsed = _new_run()["elapsed_sec"]
    assert elapsed < 3.0, f"끝난 호출의 타임아웃 타이머가 남아 node가 붙잡혔다: {elapsed:.2f}s"
    print(f"  (타이머 정리: 하네스 전체 실행 {elapsed:.2f}s)")


def _main() -> int:
    tests = [
        test_I1_success_path_dispatches_once_and_releases_the_lock,
        test_I2_hung_fetch_products_releases_the_lock_and_allows_retry,
        test_I3_hung_request_purchase_releases_the_lock,
        test_I4_dispatch_failure_alerts_and_releases_the_lock,
        test_I5_the_previous_source_keeps_the_lock,
        test_message_wiring_is_iap_only,
        test_timers_are_always_cleared,
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
