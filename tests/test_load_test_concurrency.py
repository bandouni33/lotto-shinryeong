"""동시접속 부하테스트 하네스(scripts/load_test_concurrency.py) 불변식 검증 — 2026-10-03.

배경: 이 하네스의 숫자는 "홍보 방향을 정하는 근거"로 쓰이므로, 조용히 틀리면
아무도 모른 채 잘못된 결론에 도달한다. 실제로 처음 작성본은 (a) 앱이 아니라
Streamlit Cloud 껍데기 페이지를 재고 있었고 (b) 렌더 완료 신호로 잡은
stStatusWidget이 이 앱에서 나타나지 않아 매 세션 20초를 버렸다. 그래서
"한 번 잘 나오는 것"이 아니라 아래 성질이 항상 성립하는지를 잠근다.

  P1 대상 주소: 기본값이 앱 프레임(/~/+/)을 가리킨다 — 최상위 주소는 껍데기다
  P2 안전: 결제·충전·구독·로그인을 누르는 코드 경로가 소스에 없다(정적 검사)
  P3 하네스 자체 중단장치: PC 자원 가드와 앱 컨테이너 가드가 살아 있다(정적 검사)
  P4 백분위: p0=최솟값, p100=최댓값, 단조 비감소, 빈 입력은 0.0(NaN 금지)
  P5 집계: 모든 표본이 그 시점의 동시 수에 귀속되고 총합이 보존된다
  P6 보고서: 표본 수와 통계가 일치하고, 실패만 있는 단계도 빠지지 않으며,
     빈 결과에서도 인쇄가 죽지 않는다(JSON 직렬화 가능)
  P7 중단 판정: 연속 실패 임계치에서만 선다. 성공이 끼면 풀린다
  P8 자원 가드: 여유 RAM이 기준 미만이면 그 단계에서 멈추고 기록한다
  P9 렌더 판정: 표식이 뜨면 즉시, 아니면 '충분히 긴' 무변화 창이 지나야 끝난다.
     못 재면 0이 아니라 None이다(빠름과 못 잼을 섞지 않는다)

pytest 없이 돌도록 표준 assert + __main__ 러너를 둔다(§3 테스트 실행 환경).
실행: venv312\\Scripts\\python.exe tests\\test_load_test_concurrency.py
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import itertools
import json
import sys
import time
from datetime import datetime
from pathlib import Path

# 이 러너는 실패 사유를 콘솔로 출력한다. 사유에 em-dash(—)나 가운뎃점 같은 문자가
# 있으면 cp949에서 UnicodeEncodeError가 나고 **러너가 죽어 실패를 보고하지 못한다**
# (2026-10-03 실제 발생: P12e 실패가 트레이스백에 묻혀 몇 개가 통과했는지도 못 봤다).
# 러너가 자기 실패를 못 찍으면 테스트가 있어도 소용이 없으므로 출력 인코딩을 고정한다.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_SPEC = importlib.util.spec_from_file_location(
    "load_test_concurrency", ROOT / "scripts" / "load_test_concurrency.py")
lts = importlib.util.module_from_spec(_SPEC)
# exec 전에 sys.modules에 등록해야 한다 — @dataclass가 cls.__module__로
# sys.modules를 조회하므로, 빠지면 데코레이터가 AttributeError로 죽는다.
sys.modules[_SPEC.name] = lts
_SPEC.loader.exec_module(lts)

SOURCE = (ROOT / "scripts" / "load_test_concurrency.py").read_text(encoding="utf-8")


def _args(**over):
    base = dict(url=lts.DEFAULT_URL, steps=[10, 20], hold=1, reload_interval=1,
                timeout_ms=30_000, wait_render=True, min_free_mb=2500,
                abort_failures=5, self_test=False, out=None,
                abort_window=lts.DEFAULT_ABORT_WINDOW,
                abort_failure_share=lts.DEFAULT_ABORT_FAILURE_SHARE)
    base.update(over)
    return argparse.Namespace(**base)


def _report(stats, steps=(10, 20), abort=None):
    return lts.build_report(_args(steps=list(steps)), stats,
                            abort or {"reason": None, "at": 0}, datetime.now())


# ── P1 대상 주소 ────────────────────────────────────────────────
def test_P1_default_url_is_app_frame_not_cloud_chrome():
    # 최상위 주소는 Streamlit Cloud 껍데기('Hosted with Streamlit')이고 실제 앱은
    # 그 안의 프레임에서 돈다 — 기본값이 최상위로 되돌아가면 그 순간 측정이
    # 무의미해지므로, 회귀를 여기서 막는다.
    assert lts.BASE_URL.endswith("streamlit.app/")
    assert lts.DEFAULT_URL == lts.BASE_URL + "~/+/", (
        f"기본 주소가 앱 프레임이 아니다: {lts.DEFAULT_URL!r}")
    assert lts.DEFAULT_URL != lts.BASE_URL
    assert lts.parse_args([]).url == lts.DEFAULT_URL
    assert lts.parse_args(["--url", "http://x/"]).url == "http://x/"


# ── P2·P3 하네스 자체 불변식 (정적) ─────────────────────────────
def test_P2_no_clicking_or_login_path_in_source():
    banned = (".click(", ".fill(", ".press(", ".type(", ".select_option(",
              ".check(", ".set_input_files(")
    offenders = [tok for tok in banned if tok in SOURCE]
    assert not offenders, (
        f"세션을 조작하는 코드가 생겼다: {offenders} — 이 하네스는 goto/reload만 해야 한다")
    # 로그인·결제로 흐르는 URL 파라미터를 스스로 조립하지도 않는다.
    for tok in ("native=1", "payment", "charge", "subscribe", "pg_"):
        assert tok not in SOURCE, f"결제·로그인 경로로 흐를 수 있는 문자열: {tok}"


def test_P3_abort_guards_are_present_in_source():
    # PC 자원 가드가 사라지면 '서버가 아니라 이 PC의 한계'를 서버 한계로 보고하게 된다.
    assert "min_free_mb" in SOURCE and "free_ram_mb" in SOURCE
    assert "stAppViewContainer" in SOURCE, "껍데기 주소를 잡는 워밍업 가드가 없다"
    assert "admission-overload-wrap" in SOURCE, "입장 제한 게이트 판정이 없다"
    a = lts.parse_args([])
    assert a.min_free_mb == lts.DEFAULT_MIN_FREE_MB > 0
    assert a.abort_failures == lts.DEFAULT_ABORT_FAILURES > 0
    assert a.wait_render is True
    assert lts.parse_args(["--no-wait-render"]).wait_render is False


# ── P4 백분위 ───────────────────────────────────────────────────
def test_P4_percentile_is_bounded_and_monotone():
    cases = [
        [],
        [7.0],
        [0.0],
        [5.0, 5.0, 5.0],
        [1.0, 2.0, 3.0, 4.0, 5.0],
        [900.0, 100.0, 500.0, 100.0],
        list(range(1, 200)),
        [float(n) for n in range(200, 0, -1)],
    ]
    for values in cases:
        if not values:
            assert lts.percentile(values, 0.5) == 0.0, "빈 입력은 0.0이어야 한다(NaN 금지)"
            continue
        lo, hi = min(values), max(values)
        assert lts.percentile(values, 0.0) == lo, f"p0이 최솟값이 아니다: {values[:5]}"
        assert lts.percentile(values, 1.0) == hi, f"p100이 최댓값이 아니다: {values[:5]}"
        prev = None
        for p in (0.0, 0.25, 0.5, 0.75, 0.95, 1.0):
            got = lts.percentile(values, p)
            assert lo <= got <= hi, f"p{p}가 범위를 벗어났다: {got}"
            if prev is not None:
                assert got >= prev, f"p{p}에서 단조성이 깨졌다: {prev} → {got}"
            prev = got


def test_P4b_fmt_distinguishes_measured_from_unmeasured():
    assert lts._fmt(None) == "render 측정없음"
    for ms in (0.0, 1.0, 1234.0):
        assert "ms" in lts._fmt(ms) and "측정없음" not in lts._fmt(ms)


# ── P5 집계 ────────────────────────────────────────────────────
def test_P5_every_sample_is_attributed_and_totals_are_conserved():
    stats = lts.Stats()
    plan = [(10, "load", 100.0), (10, "reload", 200.0), (20, "reload", 300.0),
            (20, "reload", 400.0), (20, "load_render", 500.0)]
    for active, kind, ms in plan:
        stats.record(active, kind, ms)
    for i in range(3):
        stats.fail(20, i, "새로고침", f"boom{i}")

    by_step = stats.by_step()
    total = sum(len(v) for group in by_step.values() for v in group.values())
    assert total == len(plan), f"표본이 사라졌다: {total} != {len(plan)}"
    assert len(by_step[10]["load"]) == 1 and len(by_step[10]["reload"]) == 1
    assert len(by_step[20]["reload"]) == 2
    assert all(ms in by_step[a][k] for a, k, ms in plan), "표본이 다른 단계에 붙었다"
    assert sum(stats.failures_by_step().values()) == len(stats.failures) == 3


# ── P6 보고서 ──────────────────────────────────────────────────
def test_P6_report_counts_and_stats_agree_with_samples():
    stats = lts.Stats()
    reloads_10 = [120.0, 130.0, 140.0, 900.0]
    for ms in reloads_10:
        stats.record(10, "reload", ms)
    for ms in (5000.0, 5100.0):
        stats.record(20, "reload", ms)
    stats.record(20, "reload_render", 8000.0)
    stats.fail(45, 9, "새로고침", "timeout")

    rep = _report(stats, steps=(10, 20, 45))
    rows = {r["concurrent"]: r for r in rep["rows"]}
    assert list(rows) == [10, 20, 45], f"단계가 빠지거나 순서가 틀렸다: {list(rows)}"
    assert rows[10]["reload_n"] == len(reloads_10)
    assert rows[10]["reload_p50"] == lts.percentile(reloads_10, 0.5)
    assert rows[10]["reload_p95"] == lts.percentile(reloads_10, 0.95)
    assert rows[20]["reload_n"] == 2 and rows[20]["reload_render_n"] == 1
    assert rows[45]["failures"] == 1, "실패만 있는 단계가 사라졌다"
    assert rows[45]["reload_n"] == 0
    for r in rep["rows"]:
        assert r["reload_p50"] <= r["reload_p95"], f"p50 > p95: {r}"
        for key, val in r.items():
            assert isinstance(val, int) and val >= 0, f"{key}가 정수가 아니다: {val!r}"
    assert rep["aborted"] is False and rep["abort_reason"] is None


def test_P6b_report_is_json_serialisable_and_prints_when_empty():
    stats = lts.Stats()
    stats.record(10, "load", 1.0)
    stats.gate_hits = 3
    rep = _report(stats, steps=(10,))
    # 스크립트가 그대로 파일로 쓰는 값이므로 반드시 직렬화돼야 한다.
    json.loads(json.dumps(rep, ensure_ascii=False))
    assert rep["gate_hits"] == 3
    lts.print_report(rep)                       # 표본 있음 — 죽지 않아야 한다
    lts.print_report(_report(lts.Stats(), steps=(10,)))   # 표본 없음 — 죽지 않아야 한다


# ── P7 중단 판정 ───────────────────────────────────────────────
def test_P7_aborts_exactly_at_the_consecutive_failure_threshold():
    stop = asyncio.Event()
    abort = {"reason": None, "at": 0}
    stats = lts.Stats()
    args = _args(abort_failures=3)

    for attempt in (1, 2):
        lts._note_failure(stats, 80, attempt, "새로고침", TimeoutError("x"),
                          args, stop, abort)
        assert not stop.is_set(), f"{attempt}번째 실패에서 너무 일찍 중단했다"
    lts._note_failure(stats, 80, 3, "새로고침", TimeoutError("x"), args, stop, abort)
    assert stop.is_set(), "연속 임계치에서 중단하지 않았다"
    assert abort["at"] == 80, f"중단 시점의 동시 수가 기록되지 않았다: {abort['at']}"
    assert "동시 80명" in abort["reason"] and "3건" in abort["reason"]


def test_P7b_success_resets_the_consecutive_counter():
    stop = asyncio.Event()
    abort = {"reason": None, "at": 0}
    stats = lts.Stats()
    args = _args(abort_failures=3)
    for attempt in (1, 2):
        lts._note_failure(stats, 30, attempt, "새로고침", TimeoutError("x"),
                          args, stop, abort)
    stats.record(30, "reload", 100.0)        # 한 번 성공하면 연속이 끊긴다
    for attempt in (3, 4):
        lts._note_failure(stats, 30, attempt, "새로고침", TimeoutError("x"),
                          args, stop, abort)
    assert not stop.is_set(), "성공이 끼었는데도 중단했다(연속 카운터가 안 풀렸다)"
    lts._note_failure(stats, 30, 5, "새로고침", TimeoutError("x"), args, stop, abort)
    assert stop.is_set(), "성공 이후 새로 센 3연속 실패에서 중단하지 않았다"


# ── P8 자원 가드 ───────────────────────────────────────────────
async def _hold_once(free_mb, step=40):
    old_free, old_interval = lts.free_ram_mb, lts.WATCH_INTERVAL
    lts.free_ram_mb = lambda: free_mb
    lts.WATCH_INTERVAL = 0.01
    try:
        stop = asyncio.Event()
        state = {"abort": {"reason": None, "at": 0}, "total": 7}
        await lts.hold_and_watch(step, _args(hold=0.05, min_free_mb=2500), stop, state)
        return stop, state
    finally:
        lts.free_ram_mb, lts.WATCH_INTERVAL = old_free, old_interval


def test_P8_holds_run_when_ram_is_plentiful():
    for free in (9000.0, 2500.0, None):     # 기준값과 같음, 그리고 확인불가(None)
        stop, state = asyncio.run(_hold_once(free))
        assert not stop.is_set(), f"여유 {free}MB에서 중단했다"
        assert state["abort"]["reason"] is None


def test_P8b_stops_and_records_step_when_ram_runs_out():
    stop, state = asyncio.run(_hold_once(1200.0, step=40))
    assert stop.is_set(), "여유 RAM이 기준 미만인데 중단하지 않았다"
    assert state["abort"]["at"] == 40, f"중단 단계가 기록되지 않았다: {state['abort']['at']}"
    reason = state["abort"]["reason"]
    assert "PC" in reason and "1200" in reason and "동시 40명" in reason, reason


# ── P9 렌더 판정 ───────────────────────────────────────────────
class _FakePage:
    """_measure_render가 의존하는 것만 흉내낸다 — evaluate()가 스냅샷을 순서대로
    돌려주고, 목록이 바닥나면 마지막 값을 계속 준다(멈춘 화면 = 안정)."""

    def __init__(self, source):
        self._src = source
        self.calls = 0

    async def evaluate(self, _js):
        self.calls += 1
        if callable(self._src):
            return self._src(self.calls)
        snaps = self._src
        return snaps[min(self.calls - 1, len(snaps) - 1)]


def _snap(marker=False, gate=False, appview=True, length=0):
    return {"marker": marker, "gate": gate, "appview": appview, "len": length}


def _measure(page, budget_ms=30_000, wait_render=True):
    """안정 창·폴링 간격만 짧게 바꿔 실제 시계를 기다리지 않게 한다(값 자체는
    하네스가 쓰는 모듈 전역에서 읽으므로 검증 대상 로직은 그대로다)."""
    old = (lts.STABLE_SECONDS, lts.RENDER_POLL_SECONDS)
    lts.STABLE_SECONDS, lts.RENDER_POLL_SECONDS = 0.15, 0.01
    try:
        return asyncio.run(lts._measure_render(
            page, _args(timeout_ms=budget_ms, wait_render=wait_render)))
    finally:
        lts.STABLE_SECONDS, lts.RENDER_POLL_SECONDS = old


def test_P9_stable_window_is_generous_and_tuned_sanely():
    # 주석의 근거: Streamlit은 조각조각 그려서 렌더 중에도 잠깐 멈춘 것처럼 보인다.
    # 창이 짧아지면 그 '잠깐'을 완료로 오인해 과소평가한다 — 과소평가가 위험하다.
    assert lts.STABLE_SECONDS >= 1.0, f"안정 창이 너무 짧다: {lts.STABLE_SECONDS}"
    assert 0 < lts.RENDER_POLL_SECONDS <= lts.STABLE_SECONDS / 4, "폴링이 창에 비해 거칠다"


def test_P9b_returns_immediately_when_marker_or_gate_appears():
    for kwargs in ({"marker": True}, {"gate": True}):
        page = _FakePage([_snap(), _snap(**kwargs)])
        got = _measure(page)
        assert got is not None, f"표식 {kwargs}를 못 봤다"
        assert got < 120, f"표식이 떴는데 안정 창을 기다렸다: {got:.0f}ms"
        assert page.calls <= 3, f"표식 판정인데 폴링을 계속했다: {page.calls}회"


def test_P9c_does_not_finish_on_a_pause_shorter_than_the_window():
    # 0 → 50 으로 한 번 바뀐 뒤 멈춘 화면: 창이 지나야 끝난다(성급히 끝내지 않는다).
    page = _FakePage([_snap(length=0), _snap(length=50)])
    got = _measure(page)
    assert got is not None
    assert got >= 120, f"안정 창을 기다리지 않고 끝냈다: {got:.0f}ms"
    assert page.calls >= 4, f"창을 채우지 않고 반환했다: {page.calls}회"


def test_P9d_empty_body_is_not_treated_as_settled():
    # 초기 빈 본문(len=0)에서 '변화 없음'으로 조기 반환하면 모든 측정이 0에 가까워진다.
    page = _FakePage(lambda _n: _snap(length=0))
    assert _measure(page, budget_ms=200) is None, "빈 본문을 안정으로 오인했다"


def test_P9e_unmeasurable_returns_none_not_zero():
    growing = _FakePage(lambda n: _snap(length=n))     # 끝없이 자라는 화면 = 안정 없음
    assert _measure(growing, budget_ms=200) is None, "못 쟀는데 값을 만들어냈다"
    assert growing.calls > 0

    skip = _FakePage([_snap(marker=True)])
    assert _measure(skip, wait_render=False) is None, "측정을 껐는데 값을 냈다"
    assert skip.calls == 0, "측정을 껐는데 브라우저를 건드렸다"


def test_P9f_script_self_test_still_passes():
    # 하네스 자체 러너(집계·중단 판정)도 계속 초록이어야 한다.
    assert lts.main(["--self-test"]) == 0


# ── P10 출력 버퍼링 ──────────────────────────────────────
# 2026-10-03 실제 사고: `-u` 없이 돌리자 stdout이 블록 버퍼링되어 13분짜리 램프의
# 진행을 실시간으로 볼 수 없었다(로그가 한참 뒤에 몰려 나왔다). 그래서 이제
# 이 모듈은 import되는 순간 줄 단위 출력을 강제한다.
def test_P10_importing_makes_output_line_buffered():
    stream = sys.stdout
    assert hasattr(stream, "line_buffering"), (
        "이 러너의 stdout이 reconfigure 대상이 아니라 이 불변식을 확인할 수 없다")
    assert stream.line_buffering is True, (
        "출력이 블록 버퍼링이다 — -u 없이 돌리면 긴 램프의 진행이 안 보인다")


def test_P10b_force_live_output_survives_streams_it_cannot_reconfigure():
    # reconfigure가 없는 객체로 바꿔치기해도 예외를 내면 안 된다 — import 시점에
    # 불리므로, 거기서 죽으면 하네스 자체가 안 돌아간다.
    class _HostileStream:
        def write(self, _s):
            return 0

    saved_out, saved_err = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = _HostileStream()
    try:
        lts.force_live_output()          # 예외 없이 지나가야 한다
    finally:
        sys.stdout, sys.stderr = saved_out, saved_err

    lts.force_live_output()               # 반복 호출도 안전
    assert sys.stdout.line_buffering is True
    # 헬퍼만 있고 아무도 안 부르면 소용없다 — 모듈 최상단에서 실제로 부른다.
    assert "\nforce_live_output()\n" in SOURCE, (
        "force_live_output()이 모듈 최상단에서 호출되지 않는다")


# ── P11 티어다운 상한 ─────────────────────────────────────────────────────
# 2026-10-03 실제 사고: 브라우저가 죽은 뒤 browser.close()가 영원히 안 돌아와 1372초를
# 매달렸고, 보고서는 맨 마지막에 쓰이므로 측정 결과를 통째로 잃었다(JSON이 안 남음).
# 정리는 부산물이므로 상한을 넘기면 포기하고 결과를 남겨야 한다.


class _FakeCtx:
    def __init__(self, hang=False, raise_on_close=False):
        self.closed = 0
        self._hang = hang
        self._raise = raise_on_close

    async def close(self):
        self.closed += 1
        if self._hang:
            await asyncio.sleep(3600)
        if self._raise:
            raise RuntimeError("close 실패")


class _FakeBrowser(_FakeCtx):
    pass


async def _never_ending():
    await asyncio.sleep(3600)


async def _boom():
    raise RuntimeError("task 폭발")


def _run_teardown(*, ctx=None, browser=None, tasks=(), timeout=0.2):
    """상한을 인자로 주어 실제 시계를 기다리지 않게 한다(검증 대상 로직은 그대로)."""
    started = time.perf_counter()
    ok = asyncio.run(lts.teardown(
        list(tasks), [ctx] if ctx else [],
        browser if browser is not None else _FakeBrowser(), timeout=timeout))
    return ok, time.perf_counter() - started


def test_P11_normal_teardown_closes_everything_once():
    ctx, browser = _FakeCtx(), _FakeBrowser()
    ok, _elapsed = _run_teardown(ctx=ctx, browser=browser)
    assert ok is True, "정상 정리인데 실패로 보고했다"
    assert ctx.closed == 1, f"컨텍스트를 {ctx.closed}번 닫았다(1번이어야 함)"
    assert browser.closed == 1, f"브라우저를 {browser.closed}번 닫았다(1번이어야 함)"


def test_P11b_a_hanging_browser_still_returns_within_the_cap():
    # 영원히 안 끝나는 close()가 정리 전체를 인질로 잡으면 안 된다.
    ok, elapsed = _run_teardown(browser=_FakeBrowser(hang=True), timeout=0.2)
    assert ok is False, "매달렸는데 끝났다고 보고했다"
    assert elapsed < 2.0, f"상한 0.2초인데 {elapsed:.1f}초 걸렸다 — 상한이 안 먹었다"


def test_P11c_teardown_never_raises_so_the_report_survives():
    # 이 함수가 불리는 곳이 finally다 — 거기서 예외가 새면 build_report와 파일 쓰기에
    # 도달하지 못해 정리 실패가 측정 실패로 번진다.
    ok, _elapsed = _run_teardown(ctx=_FakeCtx(raise_on_close=True),
                                 browser=_FakeBrowser(raise_on_close=True))
    assert ok is True, "정리 중 예외를 측정 실패로 처리했다"
    ok2, _ = _run_teardown(ctx=_FakeCtx(), browser=_FakeBrowser(), tasks=[_boom()])
    assert ok2 is True, "태스크 예외가 정리 실패로 번졌다"


def test_P11d_a_task_that_never_finishes_does_not_block_the_report():
    ok, elapsed = _run_teardown(ctx=_FakeCtx(), browser=_FakeBrowser(),
                                tasks=[_never_ending()], timeout=0.2)
    assert ok is False, "끝나지 않는 태스크가 있는데 정리가 끝났다고 했다"
    assert elapsed < 2.0, f"상한을 안 지켰다: {elapsed:.1f}초"


def test_P11e_the_cap_is_sane_and_wired_before_the_report():
    cap = lts.TEARDOWN_TIMEOUT_SECONDS
    assert isinstance(cap, (int, float)) and 5 <= cap <= 300, (
        f"정리 상한이 {cap}초 — 너무 짧으면 멀쩡한 정리를 자르고 너무 길면 매달림을 못 막는다")
    assert "closed = await teardown(tasks, contexts, browser)" in SOURCE, (
        "teardown 헬퍼가 실제 종료 경로에 연결되어 있지 않다")
    # 보고서 생성이 정리보다 뒤에 있어야 한다(정리에 갇혀 JSON을 놓친 게 이번 사고였다).
    assert SOURCE.index("await teardown(") < SOURCE.index("return build_report("), (
        "보고서 생성이 정리보다 앞에 있다 — 정리에 갇혀 결과를 잃을 수 있다")


# ── P12 new_context() 실패 처리 ────────────────────────────────────────
# 2026-10-03 실제 사고: 브라우저가 죽은 뒤 browser.new_context()가 예외를 던졌고, 그
# 예외가 램프 루프 밖으로 새면서 정리·보고서 작성에 도달하지 못해 측정을 통째로 잃었다.


class _OkBrowser:
    def __init__(self):
        self.made = 0

    async def new_context(self):
        self.made += 1
        return f"ctx{self.made}"


class _CrashyBrowser:
    """succeed_first번까지는 성공하고 그 뒤로는 죽은 브라우저를 흡내낸다."""

    def __init__(self, succeed_first=0, exc=RuntimeError):
        self.made = 0
        self.succeed_first = succeed_first
        self.exc = exc

    async def new_context(self):
        if self.made >= self.succeed_first:
            raise self.exc("browser crash")
        self.made += 1
        return f"ctx{self.made}"


def test_P12_healthy_browser_makes_exactly_what_was_asked():
    for count in (0, 1, 5, 20):
        made, failed = asyncio.run(lts.open_contexts(_OkBrowser(), count))
        assert failed == 0, f"count={count}: 실패로 보고했다"
        assert len(made) == count, f"count={count}: {len(made)}개만 만들었다"
        assert len(set(made)) == count, "만든 컨텍스트가 중복됐다"


def test_P12b_a_dead_browser_returns_instead_of_raising():
    made, failed = asyncio.run(lts.open_contexts(_CrashyBrowser(succeed_first=0), 20))
    assert made == [], f"하나도 못 만들었는데 {made!r}를 돌려줬다"
    assert failed >= 1, "실패를 보고하지 않았다"


def test_P12c_partial_results_are_kept_and_the_loop_stops_early():
    # 중간에 죽으면 그전까지 만든 것은 살려야 한다 — 부분 측정도 값이다.
    browser = _CrashyBrowser(succeed_first=2)
    made, failed = asyncio.run(lts.open_contexts(browser, 5))
    assert len(made) == 2, f"만든 2개를 버렸다: {made!r}"
    assert failed >= 1, "실패를 보고하지 않았다"
    # 남은 3개를 계속 시도하지 않았다(같은 실패에 시간을 쓰지 않는다).
    assert browser.made == 2, f"실패 뒤에도 계속 시도했다: {browser.made}회"


def test_P12d_never_raises_for_any_exception_type_or_count():
    for exc in (RuntimeError, TimeoutError, ValueError, OSError):
        made, failed = asyncio.run(lts.open_contexts(_CrashyBrowser(0, exc), 3))
        assert made == [] and failed >= 1, f"{exc.__name__}: {made!r}/{failed}"
    for count in (0, -1, -100):
        made, failed = asyncio.run(lts.open_contexts(_OkBrowser(), count))
        assert made == [] and failed == 0, f"count={count}: {made!r}/{failed}"


def test_P12e_no_unguarded_new_context_left_in_the_source():
    # 예전의 맨몸 호출이 램프·워밍업에 하나라도 남아 있으면 그 한 줄이 전체를 죽일 수 있다.
    # 가드된 open_contexts 안의 호출 1곳만 남아 있어야 한다.
    occurrences = SOURCE.count("await browser.new_context()")
    assert occurrences == 1, (
        f"browser.new_context() 호출이 {occurrences}곳이다 — 가드된 open_contexts 안의 "
        f"1곳만 있어야 한다")
    helper_start = SOURCE.index("async def open_contexts(")
    helper_end = SOURCE.index("async def run_load_test(")
    assert helper_start < SOURCE.index("await browser.new_context()") < helper_end, (
        "가드되지 않은 위치에서 new_context()를 부른다")
    assert "made, failed = await open_contexts(" in SOURCE, "open_contexts가 램프에 연결되여 있지 않다"
    assert "warm_ctxs, warm_failed = await open_contexts(" in SOURCE, (
        "워밍업 경로가 가드 없이 남아 있다")


def test_P12f_the_runner_can_report_non_ascii_failures():
    # 실패 사유에 em-dash 같은 문자가 있어도 러너가 죽지 않고 보고해야 한다
    # (2026-10-03: 그것 때문에 P12e 실패가 트레이스백에 묻혔다).
    enc = (sys.stdout.encoding or "").lower()
    ok = "utf" in enc or sys.stdout.errors in ("replace", "backslashreplace", "ignore")
    assert ok, (
        f"stdout이 {sys.stdout.encoding}/{sys.stdout.errors} — 실패 사유에 em-dash 같은 문자가 "
        f"있으면 UnicodeEncodeError로 러너가 죽어 실패를 보고하지 못한다")


# ── P13 대규모에서도 걸리는 실패율 중단 ──────────────────────
# 2026-10-03 실제 실패: 130세션 구간에서 세션이 무더기로 죽었는데도 "연속 실패 5건"
# 규칙은 안 걸렸다 — 다른 세션의 성공이 카운터를 계속 0으로 되돌렸기 때문이다.
# 그래서 최근 N건의 실패 '비중'으로도 중단한다.


def _feed(stats, args, stop_event, abort, pattern, active=100):
    """pattern: True=성공, False=실패 — 섮인 트래픽을 흡내낸다."""
    for i, ok in enumerate(pattern):
        if ok:
            stats.record(active, "reload", 100.0)
        else:
            lts._note_failure(stats, active, i, "새로고침", TimeoutError("x"),
                              args, stop_event, abort)
        if stop_event.is_set():
            return


def test_P13_alternating_failures_abort_by_share_even_though_streak_never_builds():
    # 실패 60% / 성공 40%를 교대로 섮는다 — 최대 연속 실패가 2건이라 기존 규칙은
    # 절대 안 걸린다. 그런데도 중단돼야 한다(이게 대규모에서 안 걸리던 그 결함이다).
    pattern = [False, True, False, False, True] * 10
    longest = max(len(list(g)) for k, g in itertools.groupby(pattern) if k is False)
    args = _args(abort_window=10, abort_failure_share=0.5, abort_failures=5)
    assert longest < args.abort_failures, "이 패턴은 연속 규칙으로는 안 걸러야 한다"

    stats = lts.Stats()
    stop, abort = asyncio.Event(), {"reason": None, "at": 0}
    _feed(stats, args, stop, abort, pattern)
    assert stop.is_set(), "실패가 60%인데 중단하지 않았다"
    assert abort["at"] == 100, f"중단 시점의 동시 수가 틀렸다: {abort['at']}"
    assert "60%" in abort["reason"], abort["reason"]


def test_P13b_a_low_failure_share_does_not_abort():
    pattern = [False, True, True, True, True] * 10          # 실패 20%
    stats = lts.Stats()
    args = _args(abort_window=10, abort_failure_share=0.5, abort_failures=5)
    stop, abort = asyncio.Event(), {"reason": None, "at": 0}
    _feed(stats, args, stop, abort, pattern)
    assert not stop.is_set(), f"실패 20%인데 중단했다: {abort['reason']}"


def test_P13c_an_unfilled_window_does_not_abort():
    # 창이 안 찼으면 판단하지 않는다 — 몇 건 실패로 멈추면 안 된다.
    stats = lts.Stats()
    args = _args(abort_window=50, abort_failure_share=0.5, abort_failures=10 ** 6)
    stop, abort = asyncio.Event(), {"reason": None, "at": 0}
    _feed(stats, args, stop, abort, [False] * 10)
    assert not stop.is_set(), "창이 안 찼는데 중단했다"


def test_P13d_failure_share_is_bounded_and_takes_the_tail():
    stats = lts.Stats()
    for ok in (True, False, False, True, False):
        if ok:
            stats.record(0, "reload", 1.0)
        else:
            stats.fail(0, 0, "reload", "x")
    size, fails, share = stats.failure_share(3)     # 마지막 3건 = [실패, 성공, 실패]
    assert (size, fails) == (3, 2), (size, fails)
    assert abs(share - 2 / 3) < 1e-9, share
    for window in (0, 1, 2, 5, 10 ** 6):
        size, fails, share = stats.failure_share(window)
        assert 0 <= fails <= size <= len(stats.recent), (window, size, fails)
        assert 0.0 <= share <= 1.0, (window, share)


def test_P13e_verdict_history_is_bounded():
    # 긴 실행에서 판정 기록이 무한히 자라면 안 된다(창을 위해 담아두는 것뿐이다).
    stats = lts.Stats()
    for _ in range(5000):
        stats.record(0, "reload", 1.0)
    assert len(stats.recent) <= lts._MAX_RECENT_VERDICTS, len(stats.recent)
    assert len(stats.recent) >= lts.DEFAULT_ABORT_WINDOW


def test_P13f_cli_and_report_carry_the_share_rule():
    default = lts.parse_args([])
    assert default.abort_window == lts.DEFAULT_ABORT_WINDOW > 0
    assert 0 < default.abort_failure_share <= 1
    parsed = lts.parse_args(["--abort-window", "5", "--abort-failure-share", "0.25"])
    assert parsed.abort_window == 5 and parsed.abort_failure_share == 0.25
    # 보고서에 어느 규칙이 무장됐었는지 남아야 나중에 그 결과를 해석할 수 있다.
    rep = lts.build_report(_args(), lts.Stats(), {"reason": None, "at": 0}, datetime.now())
    assert rep["abort_window"] == default.abort_window
    assert rep["abort_failure_share"] == default.abort_failure_share


def _main() -> int:
    import os

    tests = [
        test_P1_default_url_is_app_frame_not_cloud_chrome,
        test_P2_no_clicking_or_login_path_in_source,
        test_P3_abort_guards_are_present_in_source,
        test_P4_percentile_is_bounded_and_monotone,
        test_P4b_fmt_distinguishes_measured_from_unmeasured,
        test_P5_every_sample_is_attributed_and_totals_are_conserved,
        test_P6_report_counts_and_stats_agree_with_samples,
        test_P6b_report_is_json_serialisable_and_prints_when_empty,
        test_P7_aborts_exactly_at_the_consecutive_failure_threshold,
        test_P7b_success_resets_the_consecutive_counter,
        test_P8_holds_run_when_ram_is_plentiful,
        test_P8b_stops_and_records_step_when_ram_runs_out,
        test_P9_stable_window_is_generous_and_tuned_sanely,
        test_P9b_returns_immediately_when_marker_or_gate_appears,
        test_P9c_does_not_finish_on_a_pause_shorter_than_the_window,
        test_P9d_empty_body_is_not_treated_as_settled,
        test_P9e_unmeasurable_returns_none_not_zero,
        test_P9f_script_self_test_still_passes,
        test_P10_importing_makes_output_line_buffered,
        test_P10b_force_live_output_survives_streams_it_cannot_reconfigure,
        test_P11_normal_teardown_closes_everything_once,
        test_P11b_a_hanging_browser_still_returns_within_the_cap,
        test_P11c_teardown_never_raises_so_the_report_survives,
        test_P11d_a_task_that_never_finishes_does_not_block_the_report,
        test_P11e_the_cap_is_sane_and_wired_before_the_report,
        test_P12_healthy_browser_makes_exactly_what_was_asked,
        test_P12b_a_dead_browser_returns_instead_of_raising,
        test_P12c_partial_results_are_kept_and_the_loop_stops_early,
        test_P12d_never_raises_for_any_exception_type_or_count,
        test_P12e_no_unguarded_new_context_left_in_the_source,
        test_P12f_the_runner_can_report_non_ascii_failures,
        test_P13_alternating_failures_abort_by_share_even_though_streak_never_builds,
        test_P13b_a_low_failure_share_does_not_abort,
        test_P13c_an_unfilled_window_does_not_abort,
        test_P13d_failure_share_is_bounded_and_takes_the_tail,
        test_P13e_verdict_history_is_bounded,
        test_P13f_cli_and_report_carry_the_share_rule,
    ]
    failed = 0
    for test in tests:
        try:
            test()
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001 — 러너이므로 무엇이든 보고하고 계속
            failed += 1
            print(f"ERROR {test.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
        sys.stdout.flush()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
