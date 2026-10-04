"""입장 제한 게이트를 **실제 부하**로 검증 — 격리 인스턴스 전용 (2026-10-04, 2단계 미검증 항목).

왜 필요한가:
  상한을 60→120으로 올렸지만(2단계) "120을 넘으면 정말 막히는가"는 확인하지 않았다.
  실사용자가 없는 상태에서 운영 서버에 130명을 밀어 넣는 건 리스크만 크다. 대신
  상한을 **격리 DB에만** 저장한 별도 인스턴스(scratch/serve_for_concurrency.py --cap N)에
  세션을 밀어 넣으면 운영 Turso에 아무 영향이 없다 — 그게 이 도구다.

무엇을 확인하는가(3단계, 각 단계는 별개 성질이다):
  P1 차단 경계 — cap+N'개의 **완전히 새** 세션을 한꺼번에 붙이면 **정확히 cap개**가
     정상 화면, 나머지가 대기화면을 받는가(경계가 한 칸도 안 밀리는가).
  P2 입장자 보호 — 이미 입장한 세션은 그 뒤 상한을 넘어도 다시 막히지 않는가.
     (admission_control의 핵심 약속: 결제/적립 중 튕김 방지)
  P3 복귀 — 전부 끊고 하트비트 TTL(60초)이 지나면 새 세션이 다시 들어오는가.
     (게이트가 영구히 잠기면 그건 서버 정지와 같다)

어떻게 판정하는가(브라우저를 쓰지 않는다):
  Streamlit 프로토콜(/_stcore/stream)로 붙어 BackMsg(rerun_script)를 보내고
  ForwardMsg.script_finished까지의 시간을 잰다. 대기화면도 script_finished로 끝나므로
  **시간만으로는 정상 화면과 구분되지 않는다** → 서버가 보낸 프레임 본문에서 대기화면
  고유 문자열(.admission-overload-wrap / '이용자 폭증으로 잠시 대기')을 찾아 판정한다.
  직렬화된 바이트에서 찾는 이유: proto 내부 필드 이름에 기대지 않고, 화면 코드가 실제로
  내보낸 문자열을 그대로 보기 위해서다(문자열이 바뀌면 tests/test_admission_gate_load.py가
  교차 확인한다).

읽을 때 주의:
  * 여기서 나온 script_ms는 Turso 왕복을 **포함하지 않는다**(격리 sqlite). 절대 지연이
    아니라 "게이트가 뜰 때 서버가 감당 가능한가"를 보는 값이다.
  * 이 도구는 DB에 아무것도 쓰지 않는다(상한 포함). 상한을 바꾸는 건 서버 쪽 인자다.

실행:
  venv312\\Scripts\\python.exe -u -X utf8 scratch\\verify_admission_gate_load.py \\
      --cap 5 --n 12 --out scratch\\gate_load_cap5.json
  venv312\\Scripts\\python.exe -u -X utf8 scratch\\verify_admission_gate_load.py \\
      --cap 120 --n 128 --out scratch\\gate_load_cap120.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from streamlit.proto.BackMsg_pb2 import BackMsg  # noqa: E402
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg  # noqa: E402

DEFAULT_WS = "ws://127.0.0.1:8597/_stcore/stream"
DEFAULT_QUERY = "page=main"

# admission_control._render_overload_screen 이 실제로 내보내는 문자열.
GATE_CLASS = "admission-overload-wrap"
GATE_TEXT = "이용자 폭증으로 잠시 대기"
GATE_MARKERS = (GATE_CLASS.encode("utf-8"), GATE_TEXT.encode("utf-8"))

# 하트비트 TTL(admission_control._HEARTBEAT_TTL_SECONDS)보다 넉넉히 길게 기다려야
# "자리가 났는가"를 볼 수 있다. 값이 바뀌면 이 도구가 조용히 틀린 판정을 한다.
HEARTBEAT_TTL_SECONDS = 60
DRAIN_WAIT_DEFAULT = 65.0


def _rerun_bytes(query: str) -> bytes:
    msg = BackMsg()
    msg.rerun_script.query_string = query
    msg.rerun_script.page_name = ""
    msg.rerun_script.page_script_hash = ""
    return msg.SerializeToString()


class Session:
    """웹소켓 세션 1개. 연결 자체가 Streamlit 세션 1개를 만든다(쿠키·상태 재사용 없음)."""

    def __init__(self, idx: int) -> None:
        self.idx = idx
        self.ws = None
        self.renders: list[dict] = []
        self.errors: list[str] = []

    async def connect(self, url: str, timeout: float) -> None:
        import websockets

        self.ws = await websockets.connect(url, open_timeout=timeout, max_size=None)

    async def rerun(self, query: str, timeout: float) -> tuple[str, float, dict]:
        """한 번 렌더시킨다 → (판정, 걸린 시간 ms, 프레임 종류별 개수).

        판정은 NORMAL / GATE / TIMEOUT / ERROR 네 가지뿐이다 — 여기서 '아마 정상'을
        만들지 않는다(게이트를 정상으로 세면 정반대 결론이 난다).
        **정상 판정의 근거도 함께 남긴다**: 대기화면은 마크다운 한 덩이라 delta
        프레임이 적고, 정상 화면은 그릴 요소가 많아 delta가 많다. 마커가 안 보였다는
        '부재'만으로 정상이라고 하면 화면이 비어 있어도 정상으로 세게 된다.
        """
        if self.ws is None:
            return "ERROR", 0.0, {}
        kinds: dict[str, int] = {}
        t0 = time.perf_counter()
        try:
            await self.ws.send(_rerun_bytes(query))
        except Exception as exc:  # noqa: BLE001
            self.errors.append(f"send {type(exc).__name__}: {str(exc)[:100]}")
            return "ERROR", (time.perf_counter() - t0) * 1000, kinds

        gate = False
        deadline = time.time() + timeout
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                return "TIMEOUT", (time.perf_counter() - t0) * 1000, kinds
            try:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                return "TIMEOUT", (time.perf_counter() - t0) * 1000, kinds
            except Exception as exc:  # noqa: BLE001
                self.errors.append(f"recv {type(exc).__name__}: {str(exc)[:100]}")
                return "ERROR", (time.perf_counter() - t0) * 1000, kinds
            if isinstance(raw, str):
                continue
            if not gate and any(m in raw for m in GATE_MARKERS):
                # 앱의 렌더 실패 화면에도 '잠시' 같은 말이 섞일 수 있으므로
                # 게이트 고유 마커 두 개 중 하나가 보일 때만 게이트로 친다.
                gate = True
            fwd = ForwardMsg()
            fwd.ParseFromString(raw)
            kind = fwd.WhichOneof("type")
            kinds[kind] = kinds.get(kind, 0) + 1
            if kind == "script_finished":
                return ("GATE" if gate else "NORMAL"), (time.perf_counter() - t0) * 1000, kinds

    async def close(self) -> None:
        try:
            if self.ws is not None:
                await self.ws.close()
        except Exception:  # noqa: BLE001
            pass
        self.ws = None


async def _drive(sess: Session, args, phase: str, timeout: float) -> str:
    """세션 하나를 (필요하면 연결하고) 한 번 렌더시켜 결과를 세션에 적는다."""
    kinds: dict[str, int] = {}
    try:
        if sess.ws is None:
            await sess.connect(args.url, timeout=min(timeout, 60.0))
        verdict, ms, kinds = await sess.rerun(args.query, timeout)
    except Exception as exc:  # noqa: BLE001 — 한 세션의 실패가 측정을 죽이면 안 된다
        verdict, ms = "ERROR", 0.0
        sess.errors.append(f"connect {type(exc).__name__}: {str(exc)[:100]}")
    sess.renders.append({"phase": phase, "verdict": verdict, "ms": round(ms),
                         "deltas": kinds.get("delta", 0),
                         "frames": sum(kinds.values()), "kinds": dict(kinds)})
    return verdict


def _verdicts(sessions: list[Session], phase: str) -> list[str]:
    return [r["verdict"] for s in sessions for r in s.renders if r["phase"] == phase]


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * p))]


def _keyed(sessions: list[Session], phase: str, verdict: str, key: str) -> list[float]:
    return [float(r.get(key, 0)) for s in sessions for r in s.renders
            if r["phase"] == phase and r["verdict"] == verdict]


def _ms(sessions: list[Session], phase: str, verdict: str) -> list[float]:
    return _keyed(sessions, phase, verdict, "ms")


def _tally(verdicts: list[str]) -> dict:
    out = {"NORMAL": 0, "GATE": 0, "TIMEOUT": 0, "ERROR": 0}
    for v in verdicts:
        out[v] = out.get(v, 0) + 1
    return out


async def run(args) -> dict:
    report: dict = {
        "url": args.url,
        "cap": args.cap,
        "n": args.n,
        "excess": args.n - args.cap,
        "started": datetime.now().isoformat(timespec="seconds"),
        "render_timeout_s": args.render_timeout,
        "drain_wait_s": args.drain_wait,
        "notes": [
            "script_ms 는 Turso 왕복을 포함하지 않는다(격리 sqlite 인스턴스).",
            "이 도구는 DB에 쓰지 않는다 — 상한은 서버 쪽 인자로만 바뀐다.",
            "새 세션의 첫 렌더는 앱이 스스로 rerun 하는 경우 페이지 내용(delta) 전에 "
            "script_finished 로 끝날 수 있다 → 그 건수는 p1.first_render_empty 에 남기고, "
            "정상 여부는 다음 라운드(P2)의 실제 내용(delta)으로 확인한다.",
        ],
    }

    # ── P0 워밍업: 캐시가 찬 상태에서 경계를 재야 첫 렌더 비용에 판정이 휘둘리지 않는다.
    warm = Session(-1)
    try:
        await _drive(warm, args, "P0", args.render_timeout)
        await _drive(warm, args, "P0", args.render_timeout)
        report["warmup"] = {"verdicts": _verdicts([warm], "P0")}
        print(f"[P0] 워밍업 렌더 {report['warmup']['verdicts']}", flush=True)
    finally:
        await warm.close()
    # 워밍업 세션은 '최근 활동'으로 남아 있어 그대로 두면 자리 하나를 차지한다
    # (하트비트는 서버 메모리에 있고 연결을 끊어도 TTL 동안 남는다) → 비워질 때까지 기다린다.
    print(f"[P0] 하트비트 TTL 소진 대기 {args.drain_wait:.0f}초(자리 계산을 정확히 하기 위해)",
          flush=True)
    await asyncio.sleep(args.drain_wait)

    # ── P1: 완전히 새 세션 cap+초과분 → 정확히 cap개만 통과해야 한다.
    sessions = [Session(i) for i in range(args.n)]
    t_p1 = time.perf_counter()
    verdicts = await asyncio.gather(
        *[_drive(s, args, "P1", args.render_timeout) for s in sessions])

    # 내용 없는 첫 렌더는 **세어만 둔다**(추가 렌더를 걸지 않는다).
    # 왜: 새 세션의 첫 렌더는 앱이 스스로 rerun 하는 경우 페이지 내용(delta) 전에
    # script_finished 로 끝날 수 있다(부하가 클수록 잦다 — 2026-10-04 128세션에서 119/120).
    # 그 렌더는 "게이트가 아니었다"만 말하므로, '정상 화면이었다'는 증거는 **다음 라운드
    # (P2)에서 같은 세션이 실제 내용을 그린 것**으로 댄다. 여기서 확인 렌더를 더 걸면
    # 128세션 구간에 부하가 겹쳐 세션이 끊긴다(같은 날 실측: P2 오류 54건).
    empty_first = [s for s in sessions
                   if s.renders and s.renders[0]["verdict"] == "NORMAL"
                   and s.renders[0]["deltas"] == 0]
    if empty_first:
        print(f"[P1] 내용 없는 첫 렌더 {len(empty_first)}건(부하 중 첫 렌더 특성 · "
              f"정상 확정은 P2 내용으로)", flush=True)
    report["p1"] = {
        "seconds": round(time.perf_counter() - t_p1, 1),
        "counts": _tally(_verdicts(sessions, "P1")),
        "first_render_empty": len(empty_first),
        "expected": {"NORMAL": args.cap, "GATE": args.n - args.cap},
        "normal_ms_p50": round(_pct(_ms(sessions, "P1", "NORMAL"), 0.5)),
        "normal_ms_p95": round(_pct(_ms(sessions, "P1", "NORMAL"), 0.95)),
        "gate_ms_p50": round(_pct(_ms(sessions, "P1", "GATE"), 0.5)),
        "gate_ms_p95": round(_pct(_ms(sessions, "P1", "GATE"), 0.95)),
        # 정상 화면과 대기화면을 '그려진 요소 수'로도 구분해 둔다(부재가 아니라 존재 증거).
        "normal_deltas_p50": round(_pct(_keyed(sessions, "P1", "NORMAL", "deltas"), 0.5)),
        "gate_deltas_p50": round(_pct(_keyed(sessions, "P1", "GATE", "deltas"), 0.5)),
        "normal_frames_p50": round(_pct(_keyed(sessions, "P1", "NORMAL", "frames"), 0.5)),
        "gate_session_indexes": sorted(s.idx for s in sessions
                                       if any(r["phase"] == "P1" and r["verdict"] == "GATE"
                                              for r in s.renders)),
    }
    print(f"[P1] {args.n}개 신규 → {report['p1']['counts']} "
          f"(기대 NORMAL {args.cap} · GATE {args.n - args.cap})"
          + (f" · 내용 없는 첫 렌더 {len(empty_first)}건(정상 확정은 P2 내용으로)"
             if empty_first else ""), flush=True)

    # ── P2: 입장한 세션은 계속, 게이트에 막힌 세션은 재시도 → 결과가 뒤집히면 안 된다.
    admitted = [s for s in sessions if _verdicts([s], "P1") == ["NORMAL"]]
    blocked = [s for s in sessions if _verdicts([s], "P1") == ["GATE"]]
    t_p2 = time.perf_counter()
    for round_no in range(args.p2_reruns):
        await asyncio.gather(*[_drive(s, args, "P2", args.render_timeout) for s in sessions])
        print(f"[P2] {round_no + 1}/{args.p2_reruns} 라운드 완료 "
              f"({time.perf_counter() - t_p2:.0f}초 경과)", flush=True)
    admitted_v = _verdicts(admitted, "P2")
    blocked_v = _verdicts(blocked, "P2")
    report["p2"] = {
        "rounds": args.p2_reruns,
        "admitted_sessions": len(admitted),
        "blocked_sessions": len(blocked),
        "admitted_counts": _tally(admitted_v),
        "blocked_counts": _tally(blocked_v),
        "admitted_ms_p50": round(_pct(_ms(admitted, "P2", "NORMAL"), 0.5)),
        "admitted_ms_p95": round(_pct(_ms(admitted, "P2", "NORMAL"), 0.95)),
        "admitted_deltas_p50": round(_pct(_keyed(admitted, "P2", "NORMAL", "deltas"), 0.5)),
    }
    print(f"[P2] 입장자 재렌더 {report['p2']['admitted_counts']} · "
          f"차단자 재시도 {report['p2']['blocked_counts']}", flush=True)

    # ── P3: 전부 끊고 TTL이 지나면 새 세션이 들어와야 한다(게이트가 잠기지 않는다).
    for s in sessions:
        await s.close()
    print(f"[P3] 전 세션 종료 후 {args.drain_wait:.0f}초 대기(하트비트 TTL)", flush=True)
    await asyncio.sleep(args.drain_wait)
    late = Session(-2)
    try:
        t_p3 = time.perf_counter()
        verdict_p3 = await _drive(late, args, "P3", args.render_timeout)
        report["p3"] = {"fresh_verdict": verdict_p3,
                        "seconds": round(time.perf_counter() - t_p3, 1),
                        "ms": round(float(late.renders[0]["ms"]))}
        print(f"[P3] 자리 회복 후 신규 세션 → {verdict_p3}", flush=True)
    finally:
        await late.close()

    # ── 판정: 기대와 실제를 기계적으로 맞춘다(사람 눈으로 읽지 않아도 되게).
    counts = report["p1"]["counts"]
    report["verdict"] = {
        "boundary_exact": counts["NORMAL"] == args.cap and counts["GATE"] == args.n - args.cap,
        "no_errors": (counts["TIMEOUT"] + counts["ERROR"]) == 0,
        # 정상을 '게이트 마커가 없었다'는 부재로만 세지 않았는지: 첫 렌더가 내용 없이
        # 끝나도, 같은 세션이 다음 라운드에서 실제 내용(delta)을 그렸는가로 확인한다.
        "normal_screen_has_content": (report["p2"]["admitted_deltas_p50"] > 0
                                      and report["p2"]["admitted_deltas_p50"]
                                      > report["p1"]["gate_deltas_p50"]),
        "admitted_not_reblocked": (report["p2"]["admitted_counts"]["NORMAL"]
                                   == report["p2"]["admitted_sessions"] * args.p2_reruns),
        "recovery_ok": report.get("p3", {}).get("fresh_verdict") == "NORMAL",
    }
    # 세션별 원자료를 남긴다 — 요약만 남기면 나중에 "왜 12개 중 7개만 막혔나"를
    # 다시 볼 수 없다(2026-10-04 2단계 관측에서 세션 상세를 버려 겪은 일).
    report["session_renders"] = [
        {"idx": s.idx, "renders": s.renders, "errors": s.errors}
        for s in [warm] + sessions + [late]
    ]
    errors: list[str] = []
    for s in sessions + [warm, late]:
        for err in s.errors:
            if err not in errors:
                errors.append(err)
    report["error_samples"] = errors[:5]
    report["finished"] = datetime.now().isoformat(timespec="seconds")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="입장 제한 게이트 부하 검증(격리 인스턴스 전용)")
    ap.add_argument("--url", default=DEFAULT_WS)
    ap.add_argument("--query", default=DEFAULT_QUERY)
    ap.add_argument("--cap", type=int, required=True,
                    help="격리 서버에 저장해 둔 상한(서버 인자와 같아야 한다)")
    ap.add_argument("--n", type=int, required=True, help="동시에 붙일 신규 세션 수")
    ap.add_argument("--p2-reruns", type=int, default=3, help="입장자 보호 확인 라운드 수")
    ap.add_argument("--render-timeout", type=float, default=120.0)
    ap.add_argument("--drain-wait", type=float, default=DRAIN_WAIT_DEFAULT)
    ap.add_argument("--out", default=str(ROOT / "scratch" / "gate_load.json"))
    args = ap.parse_args()

    if args.n <= args.cap:
        print(f"⚠️ n({args.n}) 이 cap({args.cap}) 이하다 — 초과 구간이 없어 게이트를 볼 수 없다",
              flush=True)
        return 2

    rep = asyncio.run(run(args))
    print("\n" + "=" * 72)
    print(f"cap {rep['cap']} · 신규 {rep['n']} (초과 {rep['excess']})")
    print(f"P1 {rep['p1']['counts']}  기대 {rep['p1']['expected']}")
    print(f"P2 입장자 {rep['p2']['admitted_counts']} · 차단자 재시도 {rep['p2']['blocked_counts']}")
    print(f"P3 회복 후 신규 = {rep.get('p3', {}).get('fresh_verdict')}")
    for key, value in rep["verdict"].items():
        print(f"  {'OK  ' if value else 'FAIL'} {key}")
    print(f"오류 표본: {rep['error_samples']}")
    Path(args.out).write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"결과 저장: {args.out}")
    return 0 if all(rep["verdict"].values()) else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
