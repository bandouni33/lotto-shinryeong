"""동시접속 부하테스트 — 운영 URL에 실제 Streamlit 세션 N개를 동시에 열어
어느 지점부터 새로고침이 느려지거나 실패하는지 관찰한다.

2026-10-03 신규 작성. 기존 `scratch/sim_concurrency.py`가 "DB가 감당하는 렌더 수"
라는 서버측 상한을 실측·시뮬레이션하는 반면, 이 스크립트는 반대편에서
"실사용자 패턴 N명을 실제로 붙여봤을 때"를 관찰한다. 둘을 같이 봐야
어느 쪽이 먼저 병목인지(입장 제한 상한 / DB 처리량 / 플랫폼 RAM) 구분된다.

사용법:
    venv312\\Scripts\\python.exe scripts\\load_test_concurrency.py --self-test
    venv312\\Scripts\\python.exe scripts\\load_test_concurrency.py --steps 10,20 --hold 60

안전 수칙 — 이 스크립트가 구조적으로 강제하는 것:
  * 브라우저는 `goto`(최초 접속)와 `reload`(화면이동 흉내)만 한다. 결제·충전·
    구독·구매를 누르는 코드 경로가 아예 없다. 로그인도 하지 않는다 —
    비로그인 게스트로만 접속하므로 포인트·결제 상태를 건드릴 수 없다.
  * 이 PC의 여유 RAM이 바닥나면 스스로 멈춘다(기본 2.5GB). 그 시점의 숫자는
    **서버 한계가 아니라 이 PC가 띄운 탭 수**다 — 보고서에 그렇게 표시한다.
    (2026-10-03 실측 이 PC: RAM 16GB·여유 10.3GB·논리코어 8개.
     headless 컨텍스트 1개당 대략 80~150MB라 160개 ramp는 서버보다 PC가 먼저 죽는다.)
  * 연속 실패가 쌓이면 즉시 중단하고 그때의 동시 수를 기록한다.

무엇을 재는가 — 두 가지를 따로 잰다:
  * shell  = domcontentloaded까지. Streamlit은 정적 껍데기(index.html+JS)를
    먼저 보내므로 이건 "껍데기가 뜬 시간"이다. 부하가 걸리면 여기부터 늘어나긴
    하지만 서버가 실제로 한 일은 아니다.
  * render = 그 뒤 웹소켓으로 파이썬 스크립트가 다 돌 때까지. Cloud 로그의
    [dbtrace] script_ms와 비교해야 하는 숫자가 이쪽이다.
  관찰 표에 둘을 나란히 찍으므로 "껍데기는 멀쩬한데 렌더만 느려진다"와
  "아예 안 뜬다"를 구분할 수 있다.

  * 여기서 말하는 shell의 "껍데기"는 Streamlit 프론트엔드 껍데기(index.html+JS)이고,
    최상위 주소(Streamlit Cloud 껍데기)와는 다르다 — 대상 주소는 반드시 앱
    프레임(/~/+/)일 것. 아래 DEFAULT_URL 주석 참고.

실행 전제(스크립트가 대신 못 하는 것):
  * 운영자 대시보드에서 "동시접속 상한"을 미리 올려둘 것. 안 올리면 상한(기본 60)을
    넘는 신규 세션은 전부 입장 제한 안내화면을 받아 **진짜 기술적 한계에 도달하기
    전에 실험이 끝난다**. 이 스크립트는 그 안내화면을 `[게이트]`로 구분해서 세므로,
    게이트가 뜨기 시작하면 "그건 상한값이지 성능 한계가 아니다"로 바로 읽으면 된다.
  * 새벽 등 실사용자가 거의 없는 시간대에 실행. 토요일 추첨 전후는 피할 것.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def force_live_output() -> None:
    """표준출력을 '줄 단위 즉시'로 바꾼다.

    2026-10-03 실제 문제: 파이프로 넘겨 실행하면 stdout이 블록 버퍼링(8KB)이라
    단계별 진행이 실시간으로 안 보였다 — 13분짜리 램프 중 어느 단계까지 갔는지
    볼 수 없어 내가 램프 진행을 계속 못 읽었다. `-u` 없이 돌려도 진행이 보이게
    여기서 고정한다(그때는 `-u`를 빼먹어서 생긴 사고다).

    스트림이 reconfigure를 지원하지 않아도(테스트가 대역 객체로 바꿔치기하는 등)
    절대 예외를 내지 않는다 — 출력 설정 하나 때문에 측정이 죽으면 안 된다.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(line_buffering=True)
        except Exception:
            pass


# import되는 순간 적용된다(진입점이 이 모듈 자체이므로 main()에서 부르면
# 중간에 빠뜨릴 수 있다).
force_live_output()

BASE_URL = "https://lotto-shinryeong.streamlit.app/"

# 2026-10-03 실측: 최상위 주소(BASE_URL)는 Streamlit Cloud의 *껍데기* 페이지다
# ('Hosted with Streamlit / Created by bandouni33', DOM 3.5KB, data-testid 1개).
# 실제 앱은 그 안의 프레임 /~/+/ 에서 돈다 — 프로브 결과 프레임 목록이
# ['…/', '…/~/+/', statuspage iframe] 이었고 stAppViewContainer는 /~/+/ 쪽에만 있었다.
# 최상위를 재면 앱이 아니라 껍데기를 재게 되고, '동시 160명에서도 500ms'처럼
# 그럴듯하지만 무의미한 숫자가 나온다(실제로 처음에 그렇게 나왔다).
DEFAULT_URL = BASE_URL + "~/+/"
DEFAULT_STEPS = [10, 20, 30, 45, 60, 80, 100, 130, 160]  # 단계적으로 증가
DEFAULT_HOLD = 90            # 각 단계 유지·관찰 시간(초)
DEFAULT_RELOAD = 25          # 실사용자 화면이동을 흉내내는 새로고침 주기(초)
DEFAULT_TIMEOUT_MS = 30_000
DEFAULT_MIN_FREE_MB = 2500   # 이 PC 여유 RAM이 이 아래로 가면 중단
DEFAULT_ABORT_FAILURES = 5   # 연속 실패 이만큼이면 중단
WATCH_INTERVAL = 5           # 자원 관찰 주기(초)

# 입장 제한 장치가 신규 세션을 막을 때 뜨는 화면의 CSS 클래스
# (admission_control._render_overload_screen의 .admission-overload-wrap).
# 문구가 아니라 클래스로 찾는 이유: 160세션이 25초마다 innerText를 뜯으면
# 관찰 행위 자체가 부하가 된다. querySelector는 사실상 공짜다.
GATE_SELECTOR = ".admission-overload-wrap"

# "이 회차가 다 그렸다"를 판정하는 신호. 렌더 완료를 알려주는 깔끔한 이벤트가
# 없어서 다음 순서로 본다:
#   1) 화면 좌상단 "메인으로" 아이콘(a.brand-home-link) 또는 입장 제한 게이트
#      화면 — 뜨면 그 자체로 "스크립트가 여기까지 돌았다"다. 다만 이 아이콘은
#      모든 화면에 있지는 않다(메인 화면에는 없다 — 2026-10-03 프로브로 확인됨:
#      렌더 후 data-testid 227개·본문 349자인데 brand-home-link는 나타나지 않고
#      예산 25초를 전부 썼다).
#   2) 그래서 실제 판정은 본문 텍스트 길이가 STABLE_SECONDS 동안 안 변하는
#      시점을 기본으로 한다. Streamlit은 조각조각 그리므로 렌더 중에도 잠깐
#      멈춘 것처럼 보인다 — 창을 넉넉히 잡아 "조금 크게" 나오는 쪽을 택한다.
#      과소평가하면 느려진 걸 놓쳐 한계를 못 찾지만, 상수만큼 부풀려지면
#      단계 간 비교에는 영향이 없다.
# stStatusWidget은 이 앱에서 끝내 나타나지 않아 신호로 못 쓴다(2026-10-03 확인).
STABLE_SECONDS = 2.0
RENDER_POLL_SECONDS = 0.3
SNAP_JS = """
() => ({
  marker: !!document.querySelector('a.brand-home-link'),
  gate: !!document.querySelector('.admission-overload-wrap'),
  appview: !!document.querySelector('[data-testid="stAppViewContainer"]'),
  len: document.body ? document.body.innerText.length : -1,
})
"""

# app.py의 공용 예외 화면 — 서버가 살아 있어도 이게 뜨면 렌더가 깨진 것이다.
ERROR_TEXT = "일시적으로 서비스 점검 중입니다"


# ─────────────────────────────────────────────────────────────
# PC 자원 (psutil 미설치 환경이라 ctypes / procfs로 직접 읽는다)
# ─────────────────────────────────────────────────────────────
def free_ram_mb() -> float | None:
    """이 PC의 가용 물리 메모리(MB). 못 읽으면 None(그 경우 가드가 꺼진다)."""
    try:
        if sys.platform == "win32":
            import ctypes

            class _MemStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = _MemStatus()
            status.dwLength = ctypes.sizeof(_MemStatus)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return None
            return status.ullAvailPhys / (1024 * 1024)
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 1024
    except Exception:
        pass
    return None


def _fmt(ms: float | None) -> str:
    """렌더 시간을 로그 한 줄에 넣기 좋게. None은 못 쟀다는 뜻이다."""
    return "render 측정없음" if ms is None else f"render {ms:.0f}ms"


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(len(ordered) * p))
    return ordered[idx]


# ─────────────────────────────────────────────────────────────
# 측정 결과 수집
# ─────────────────────────────────────────────────────────────
@dataclass
class Stats:
    """동시 수(active)별로 측정값을 모은다 — 어느 단계에서 처음 무너졌는지가
    이 실험의 유일한 질문이므로, 모든 표본에 그때의 동시 수를 붙여둔다."""

    records: list[tuple[int, str, float]] = field(default_factory=list)  # (active, kind, ms)
    failures: list[tuple[int, int, str, str]] = field(default_factory=list)  # (active, idx, kind, msg)
    gate_hits: int = 0
    success_streak: int = 0

    def record(self, active: int, kind: str, ms: float) -> None:
        self.records.append((active, kind, ms))
        self.success_streak = 0

    def fail(self, active: int, idx: int, kind: str, msg: str) -> None:
        self.failures.append((active, idx, kind, msg))

    def by_step(self) -> dict[int, dict[str, list[float]]]:
        out: dict[int, dict[str, list[float]]] = {}
        for active, kind, ms in self.records:
            out.setdefault(active, {}).setdefault(kind, []).append(ms)
        return out

    def failures_by_step(self) -> dict[int, int]:
        out: dict[int, int] = {}
        for active, _idx, _kind, _msg in self.failures:
            out[active] = out.get(active, 0) + 1
        return out


# ─────────────────────────────────────────────────────────────
# 세션 1개
# ─────────────────────────────────────────────────────────────
async def _is_gate_screen(page) -> bool:
    try:
        return bool(await page.evaluate("!!document.querySelector(a)", GATE_SELECTOR))
    except Exception:
        return False


async def _has_error_screen(page) -> bool:
    try:
        return bool(await page.evaluate("document.body.innerText.includes(t)", ERROR_TEXT))
    except Exception:
        return False


async def _measure_render(page, args) -> float | None:
    """스크립트 실행이 끝나기까지 걸린 시간(ms). 못 재면 None.

    붙는 걸 못 보면(이미 끝나 있을 만큼 빨랐거나 이 버전에 위젯이 없으면)
    None을 돌려준다 — 0으로 뭉개면 "아주 빠름"과 "못 쟀음"이 섞이므로, 보고서에
    render 표본 수(n)를 따로 찍는다.
    """
async def _measure_render(page, args) -> float | None:
    """이 회차가 다 그려지기까지 걸린 시간(ms). 예산을 넘기면 None.

    판정 순서는 위 STABLE_SECONDS 주석 참고 — 표식(브랜드 아이콘·게이트)이 먼저
    나타나면 그 즉시, 아니면 본문 길이가 STABLE_SECONDS 동안 안 변할 때 끝난
    것으로 본다. 0으로 뭉개지 않고 None을 돌려주는 이유: "아주 빠름"과 "못 쟀음"을
    섞으면 보고서가 거짓말을 한다(그래서 표에 render 표본 수 n을 따로 찍는다).
    """
    if not getattr(args, "wait_render", True):
        return None
    budget_s = min(args.timeout_ms, 30_000) / 1000.0
    t0 = asyncio.get_event_loop().time()
    last_len, last_change = -1, t0
    while True:
        now = asyncio.get_event_loop().time()
        if now - t0 > budget_s:
            return None
        try:
            snap = await page.evaluate(SNAP_JS)
        except Exception:
            await asyncio.sleep(RENDER_POLL_SECONDS)
            continue
        if snap["marker"] or snap["gate"]:
            return (now - t0) * 1000
        if snap["len"] != last_len:
            last_len, last_change = snap["len"], now
        elif last_len > 0 and now - last_change >= STABLE_SECONDS:
            return (now - t0) * 1000
        await asyncio.sleep(RENDER_POLL_SECONDS)


def _note_failure(stats: Stats, active: int, idx: int, kind: str, exc: Exception,
                  args, stop_event: asyncio.Event, abort: dict) -> None:
    msg = f"{type(exc).__name__}: {str(exc)[:120]}"
    stats.fail(active, idx, kind, msg)
    stats.success_streak -= 1          # 성공(record)이 한 번이라도 끼면 0으로 풀린다
    print(f"  [세션{idx}] {kind} 실패: {msg}")
    if -stats.success_streak >= args.abort_failures:
        abort["reason"] = (
            f"연속 실패 {args.abort_failures}건 — 동시 {active}명 지점에서 서버가 응답을 "
            f"못 준 것으로 보인다"
        )
        abort["at"] = active
        stop_event.set()


async def run_one_session(ctx, idx: int, args, stop_event: asyncio.Event,
                          stats: Stats, state: dict) -> None:
    """세션 1개: 최초 접속 → RELOAD_INTERVAL마다 새로고침(화면이동 흉내)만 한다.
    클릭·입력·로그인은 하지 않는다."""
    page = await ctx.new_page()
    try:
        active = state["active"]
        t0 = time.perf_counter()
        try:
            await page.goto(args.url, timeout=args.timeout_ms, wait_until="domcontentloaded")
        except Exception as exc:  # noqa: BLE001
            _note_failure(stats, active, idx, "최초로딩", exc, args, stop_event, state["abort"])
            return
        shell_ms = (time.perf_counter() - t0) * 1000
        stats.record(active, "load", shell_ms)
        render_ms = await _measure_render(page, args)
        if render_ms is not None:
            stats.record(active, "load_render", render_ms)
        tag = "[게이트] " if await _is_gate_screen(page) else ""
        if tag:
            stats.gate_hits += 1
        print(f"  [세션{idx}] {tag}최초 shell {shell_ms:.0f}ms · `{_fmt(render_ms)}`")

        while not stop_event.is_set():
            # 이벤트를 기다리되 시간이 다 되면 그냥 진행한다 — stop_event가 세워지면
            # 남은 대기(최대 reload_interval초)를 버리고 즉시 빠져나오기 위함이다.
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=args.reload_interval)
                break
            except asyncio.TimeoutError:
                pass
            active = state["active"]
            t0 = time.perf_counter()
            try:
                await page.reload(timeout=args.timeout_ms, wait_until="domcontentloaded")
            except Exception as exc:  # noqa: BLE001
                _note_failure(stats, active, idx, "새로고침", exc, args, stop_event, state["abort"])
                break
            shell_ms = (time.perf_counter() - t0) * 1000
            render_ms = await _measure_render(page, args)
            if await _is_gate_screen(page):
                stats.gate_hits += 1
                print(f"  [세션{idx}] [게이트] 입장 제한 안내화면 — 상한값에 막힌 것이지 성능 한계가 아니다")
                continue
            if render_ms is None and await _has_error_screen(page):
                stats.fail(active, idx, "오류화면", ERROR_TEXT)
                print(f"  [세션{idx}] ⚠️ 공용 예외 화면(렌더 실패) shell {shell_ms:.0f}ms")
                continue
            stats.record(active, "reload", shell_ms)
            if render_ms is not None:
                stats.record(active, "reload_render", render_ms)
            print(f"  [세션{idx}] 새로고침 shell {shell_ms:.0f}ms · `{_fmt(render_ms)}`")
    finally:
        try:
            await page.close()
        except Exception:
            pass


async def hold_and_watch(step: int, args, stop_event: asyncio.Event, state: dict) -> None:
    """단계 유지 시간 동안 이 PC의 자원을 지켜본다.

    여기가 이 스크립트에서 제일 중요한 부분이다 — PC가 먼저 한계에 닿으면
    이후 숫자는 전부 거짓(서버가 아니라 PC의 한계)이므로, 그 순간 멈추고
    그 사실을 결과에 박아둔다.
    """
    deadline = time.perf_counter() + args.hold
    while time.perf_counter() < deadline:
        if stop_event.is_set():
            return
        free = free_ram_mb()
        if free is not None and free < args.min_free_mb:
            state["abort"]["reason"] = (
                f"이 PC의 여유 RAM이 {free:.0f}MB까지 떨어졌다(기준 {args.min_free_mb}MB). "
                f"이 시점부터의 지연은 서버가 아니라 이 PC의 한계다 — "
                f"동시 {step}명에서 중단."
            )
            state["abort"]["at"] = step
            stop_event.set()
            return
        ram_txt = f"{free:.0f}MB" if free is not None else "확인불가"
        print(f"  [관찰] 동시 {step}명 · 이 PC 여유 RAM {ram_txt} · 살아있는 세션 {state['total']}")
        await asyncio.sleep(WATCH_INTERVAL)


# 정리(teardown)에 둘 상한(초). 넘기면 정리를 포기하고 결과를 남긴다.
TEARDOWN_TIMEOUT_SECONDS = 60


async def teardown(tasks, contexts, browser, timeout: float | None = None) -> bool:
    """세션 태스크·컨텍스트·브라우저를 정리한다. 상한 안에 끝났으면 True.

    2026-10-03 실제 사고: 로컬 브라우저가 죽은 뒤 `browser.close()`가 영원히 안
    돌아와 **1372초를 매달렸고**, 보고서는 맨 마지막에 파일로 쓰이므로 측정 결과를
    통째로 잃었다(JSON이 남지 않았다). 정리는 부산물이다 — 못 끝내면 포기하고
    결과를 남기는 쪽이 맞다.

    어떤 경우에도 예외를 밖으로 민지지 않는다. 이 함수가 불리는 곳이 `finally`라,
    거기서 예외가 새면 뒤따르는 `build_report(...)`와 파일 쓰기에 도달하지 못해
    정리 실패가 측정 실패로 번진다.
    """
    if timeout is None:
        timeout = TEARDOWN_TIMEOUT_SECONDS

    async def _close_all() -> None:
        await asyncio.gather(*tasks, return_exceptions=True)
        for ctx in contexts:
            try:
                await ctx.close()
            except Exception:
                pass
        try:
            await browser.close()
        except Exception:
            pass

    try:
        await asyncio.wait_for(_close_all(), timeout=timeout)
        return True
    except (asyncio.TimeoutError, TimeoutError):
        return False
    except Exception:
        # 정리 도중의 예외는 측정 실패가 아니다.
        return True


# ─────────────────────────────────────────────────────────────
# 본 실험
# ─────────────────────────────────────────────────────────────
async def run_load_test(args) -> dict:
    from playwright.async_api import async_playwright

    stats = Stats()
    stop_event = asyncio.Event()
    state = {"active": 0, "total": 0, "abort": {"reason": None, "at": 0}}
    started = datetime.now()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        contexts, tasks = [], []
        try:
            # Streamlit Cloud는 유휴 시 잠들어 있어 첫 요청만 30~60초 걸린다.
            # 그 한 번을 ramp에 섞으면 1단계가 통째로 거짓이 되므로 미리 깨운다.
            warm_ctx = await browser.new_context()
            warm_page = await warm_ctx.new_page()
            print("[워밍업] 운영 앱을 깨우는 중(유휴 상태면 30~60초 걸린다)...")
            t0 = time.perf_counter()
            try:
                await warm_page.goto(args.url, timeout=max(args.timeout_ms, 90_000),
                                     wait_until="domcontentloaded")
                print(f"[워밍업] 첫 로딩 {(time.perf_counter() - t0) * 1000:.0f}ms")
            except Exception as exc:  # noqa: BLE001
                print(f"[워밍업] 실패: {type(exc).__name__}: {exc}")
                print("  → 앱이 잠들었거나 주소가 바뀌었을 수 있다. 중단한다.")
                return {"aborted": True, "reason": "워밍업 실패", "steps": []}
            else:
                # 주소가 앱이 아니라 Cloud 껍데기면 여기서 잡는다. 그냥 진행하면
                # 앱이 아니라 껍데기를 재면서 그럴듯한 숫자를 내놓게 되는데,
                # 그 숫자는 홍보 방향을 정하는 데 쓰이므로 반드시 실패해야 한다.
                has_container = await warm_page.evaluate(
                    "() => !!document.querySelector('[data-testid=\"stAppViewContainer\"]')")
                if not has_container:
                    print("[워밍업] ⚠️ 앱 컨테이너(stAppViewContainer)가 없다 — 이 주소는 앱 화면이 "
                          "아니라 Streamlit Cloud 껍데기일 가능성이 크다(--url 확인). 중단한다.")
                    return {"aborted": True, "reason": "앱 컨테이너 없음(껍데기 주소 의심)", "steps": []}
            finally:
                await warm_ctx.close()

            for step in args.steps:
                if stop_event.is_set():
                    break
                add = step - state["active"]
                if add <= 0:
                    continue
                print(f"\n=== 단계: 동시 {step}명 (신규 +{add}) ===")
                state["active"] = step
                for i in range(add):
                    ctx = await browser.new_context()
                    contexts.append(ctx)
                    state["total"] += 1
                    tasks.append(asyncio.create_task(
                        run_one_session(ctx, state["total"] - 1, args, stop_event, stats, state)
                    ))
                print("  (지금 운영자 대시보드의 동시접속 숫자와 Cloud 로그의 [dbtrace]를 확인하세요)")
                await hold_and_watch(step, args, stop_event, state)
        finally:
            stop_event.set()
            closed = await teardown(tasks, contexts, browser)
            if not closed:
                # 정리를 포기해도 보고서는 쓴다 — 이게 상한을 둔 이유다.
                print(f"[정리] {TEARDOWN_TIMEOUT_SECONDS}초 안에 정리를 못 끝냈다(브라우저가 "
                      f"죽었을 가능성) — 정리를 포기하고 결과는 그대로 쓴다", flush=True)
                if state["abort"]["reason"] is None:
                    state["abort"]["reason"] = (
                        f"정리 단계가 {TEARDOWN_TIMEOUT_SECONDS}초를 넘겼다(브라우저 이상) — "
                        f"측정값은 정리 전까지 받은 것만 유효하다"
                    )

    return build_report(args, stats, state["abort"], started)


def build_report(args, stats: Stats, abort: dict, started: datetime) -> dict:
    by_step = stats.by_step()
    fails = stats.failures_by_step()
    rows = []
    for step in sorted(set(list(by_step) + list(fails))):
        group = by_step.get(step, {})
        row = {"concurrent": step, "failures": fails.get(step, 0)}
        for kind, key in (("load", "load"), ("load_render", "load_render"),
                          ("reload", "reload"), ("reload_render", "reload_render")):
            vals = group.get(kind, [])
            row[f"{key}_n"] = len(vals)
            row[f"{key}_p50"] = round(percentile(vals, 0.5))
            row[f"{key}_p95"] = round(percentile(vals, 0.95))
        rows.append(row)
    return {
        "url": args.url,
        "started": started.isoformat(timespec="seconds"),
        "finished": datetime.now().isoformat(timespec="seconds"),
        "steps": args.steps,
        "hold_seconds": args.hold,
        "reload_interval_seconds": args.reload_interval,
        "gate_hits": stats.gate_hits,
        "aborted": abort["reason"] is not None,
        "abort_reason": abort["reason"],
        "abort_at_concurrent": abort["at"],
        "rows": rows,
    }


def print_report(rep: dict) -> None:
    print("\n" + "=" * 66)
    print("결과 요약")
    print("=" * 66)
    if not rep.get("rows"):
        print("측정된 표본이 없다.")
        return
    header = (f"{'동시':>4} | {'최초shell':>9} | {'최초render p50/p95':>17} | "
              f"{'새로고침shell':>12} | {'새로고침render p50/p95':>21} | {'실패':>4}")
    print(header)
    print("-" * len(header))
    for r in rep["rows"]:
        load_r = (f"{r['load_render_p50']}/{r['load_render_p95']}" if r["load_render_n"] else "-")
        rel_r = (f"{r['reload_render_p50']}/{r['reload_render_p95']}" if r["reload_render_n"] else "-")
        print(f"{r['concurrent']:>4} | {r['load_p50']:>9} | {load_r:>17} | "
              f"{r['reload_p50']:>12} | {rel_r:>21} | {r['failures']:>4}")
    print("\n단위 ms. shell = 정적 껍데기, render = 파이썬 스크립트가 다 돈 시점"
          "(Cloud 로그 [dbtrace] script_ms와 비교할 값). '-'는 그 단계에서 못 쟀다는 뜻.")
    print(f"입장 제한 게이트에 막힌 횟수: {rep['gate_hits']} "
          f"(이건 상한값이지 성능 한계가 아니다)")
    if rep["aborted"]:
        print(f"\n중단됨 — 동시 {rep['abort_at_concurrent']}명 지점")
        print(f"  {rep['abort_reason']}")


# ─────────────────────────────────────────────────────────────
# 자체 검증 — 운영에 아무 요청도 보내지 않고 집계·판정 로직만 검사한다
# ─────────────────────────────────────────────────────────────
def self_test() -> int:
    problems: list[str] = []
    total = [0]

    def check(cond: bool, label: str) -> None:
        total[0] += 1
        print(f"  {'PASS' if cond else 'FAIL'}  {label}")
        if not cond:
            problems.append(label)

    print("== 자체 검증 (운영 요청 없음) ==")

    st_ = Stats()
    for ms in [100, 120, 130, 140, 900]:
        st_.record(10, "reload", ms)
    rows = build_report(argparse.Namespace(url="x", steps=[10], hold=1, reload_interval=1),
                        st_, {"reason": None, "at": 0}, datetime.now())["rows"]
    check(rows[0]["reload_n"] == 5, "표본 수 집계")
    check(rows[0]["reload_p50"] == 130, "p50 = 중간값")
    check(rows[0]["reload_p95"] == 900, "p95 = 최대값(표본 5개)")

    st2 = Stats()
    st2.record(10, "reload", 100)
    st2.record(20, "reload", 5000)
    st2.fail(20, 1, "새로고침", "TimeoutError")
    rep2 = build_report(argparse.Namespace(url="x", steps=[10, 20], hold=1, reload_interval=1),
                        st2, {"reason": None, "at": 0}, datetime.now())
    check([r["concurrent"] for r in rep2["rows"]] == [10, 20], "단계별 분리 집계")
    check(rep2["rows"][1]["failures"] == 1, "실패 건이 그 단계에 붙는다")

    # 연속 실패 → 중단 판정
    args = argparse.Namespace(abort_failures=3)
    st3 = Stats()
    se = asyncio.Event()
    abort = {"reason": None, "at": 0}
    st3.success_streak = -2
    _note_failure(st3, 80, 7, "새로고침", TimeoutError("x"), args, se, abort)
    check(se.is_set() and abort["reason"] is not None, "연속 실패 임계치에서 중단 신호")
    check(abort["at"] == 80 and "동시 80명" in abort["reason"], "중단 사유에 그때의 동시 수가 남는다")

    # 성공하면 연속 실패 카운터가 풀린다
    st4 = Stats()
    st4.success_streak = -2
    st4.record(10, "reload", 100)
    check(st4.success_streak == 0, "성공 시 실패 연속 카운터 초기화")

    print(f"\n{len(problems)}개 실패 / {total[0]}개 검사")
    return 1 if problems else 0


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="로또신령 동시접속 부하테스트")
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--steps", default=",".join(str(s) for s in DEFAULT_STEPS),
                    help="쉼표로 구분한 동시접속 수 (기본: %(default)s)")
    ap.add_argument("--hold", type=int, default=DEFAULT_HOLD, help="단계 유지 시간(초)")
    ap.add_argument("--reload-interval", type=int, default=DEFAULT_RELOAD,
                    help="세션당 새로고침 주기(초)")
    ap.add_argument("--timeout-ms", type=int, default=DEFAULT_TIMEOUT_MS)
    ap.add_argument("--min-free-mb", type=float, default=DEFAULT_MIN_FREE_MB,
                    help="이 PC 여유 RAM이 이 아래로 가면 중단")
    ap.add_argument("--abort-failures", type=int, default=DEFAULT_ABORT_FAILURES)
    ap.add_argument("--out", default=None, help="결과 JSON 경로")
    ap.add_argument("--no-wait-render", dest="wait_render", action="store_false",
                    help="스크립트 실행 완료를 기다리지 않고 정적 껍데기 시간만 잰다")
    ap.add_argument("--self-test", action="store_true", help="운영 요청 없이 집계 로직만 검증")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    args.steps = [int(s) for s in str(args.steps).split(",") if s.strip()]
    if args.self_test:
        return self_test()

    free = free_ram_mb()
    cores = os.cpu_count()
    if free is None:
        print(f"이 PC: 논리코어 {cores} / 메모리 확인 불가(자원 가드 꺼짐)")
    else:
        print(f"이 PC: 여유 RAM {free:.0f}MB / 논리코어 {cores} "
              f"/ 여유 RAM이 {args.min_free_mb:.0f}MB 아래로 가면 중단")
    print(f"대상: {args.url}")
    print(f"단계: {args.steps} · 단계당 {args.hold}초 · 새로고침 주기 {args.reload_interval}초")

    rep = asyncio.run(run_load_test(args))
    print_report(rep)

    out = Path(args.out) if args.out else (
        ROOT / "scripts" / f"load_test_result_{datetime.now():%Y%m%d_%H%M%S}.json")
    try:
        out.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n결과 저장: {out}")
    except Exception as exc:  # noqa: BLE001
        print(f"\n결과 저장 실패: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
