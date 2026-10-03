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
import json
import sys
from datetime import datetime
from pathlib import Path

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
                abort_failures=5, self_test=False, out=None)
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
