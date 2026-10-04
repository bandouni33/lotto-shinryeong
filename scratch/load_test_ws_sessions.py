"""서버측 동시접속 실측 — 브라우저 없이 Streamlit 세션만 N개 붙인다 (2026-10-04 조사 지시 1번).

왜 필요한가:
  scripts/load_test_concurrency.py(공식 부하테스트)는 헤드리스 브라우저 컨텍스트를 세션마다
  하나씩 띄운다 → 이 PC 실측 **세션당 약 160MB**(여유 RAM 6882→5287MB/10세션)에, 서버와
  같은 4코어를 나눠 쓰면서 CPU를 함께 먹는다. 그래서 30명만 넘어도 "서버가 느린 것"과
  "클라이언트가 코어를 뺏은 것"을 구분할 수 없다(실측: 30명 구간에서 shell 25초·render 26초).
  세션 하나에 서버가 얼마를 쓰는지(메모리·CPU)를 알고 싶으면 클라이언트 비용을 0에 가깝게
  만들어야 한다 — 그게 이 스크립트다.

무엇을 하는가:
  Streamlit의 실제 프로토콜을 그대로 쓴다(공식 경로 /_stcore/stream, 바이너리 protobuf):
    ① WebSocket 연결 → 서버가 세션을 만든다(runtime.connect_session)
    ② BackMsg(rerun_script: query_string="page=main") 를 보내면 서버가 스크립트를 돌린다
    ③ ForwardMsg.script_finished 가 올 때까지의 시간 = **서버가 실제로 쓴 시간**(script_ms).
       브라우저 렌더·이미지·폰트 비용이 전혀 섞이지 않는다.
  각 세션은 실사용자처럼 --rerun-interval 초마다 다시 돌리고(기본 25초), 연결은 유지한다.

읽는 법(중요):
  * 여기서 나온 script_ms 는 **Turso 왕복을 포함하지 않는다**(측정용 서버가 격리 sqlite를 씀).
    운영에서는 렌더마다 DB 왕복이 더해지므로 이 값보다 커진다 — 부하테스트용 서버
    (scratch/serve_for_concurrency.py)의 docstring 참고.
  * 메모리(RSS)·CPU 는 이 스크립트가 아니라 scratch/monitor_streamlit_resources.py 가 그
    서버 프로세스를 직접 샘플링한다. 두 출력을 맞추려면 단계 머리의 시각(HH:MM:SS)을 보면 된다.
  * 신규 60/100/150 단계는 **입장 제한 게이트에 막히지 않는다** — 게이트는 스크립트 본문
    안(admission_control.check_admission)에서 판단하므로, 넘으면 그 세션의 렌더가
    게이트 화면(짧은 문서)으로 끝난다. 그 사실은 script_ms 가 비정상적으로 짧아지는 것으로
    드러난다(운영 상한이 60일 때 60명 초과 구간에서 나타난다).

실행:
  venv312\\Scripts\\python.exe -u -X utf8 scratch\\load_test_ws_sessions.py --steps 10,30,60,100,150 --hold 45
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from streamlit.proto.BackMsg_pb2 import BackMsg  # noqa: E402
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg  # noqa: E402

DEFAULT_WS = "ws://127.0.0.1:8598/_stcore/stream"
DEFAULT_QUERY = "page=main"


def _rerun_bytes(query: str) -> bytes:
    msg = BackMsg()
    msg.rerun_script.query_string = query
    msg.rerun_script.page_name = ""
    msg.rerun_script.page_script_hash = ""
    return msg.SerializeToString()


async def _session(idx: int, url: str, query: str, interval: float, hold: float,
                   stop: asyncio.Event, out: dict) -> None:
    """세션 1개 — 연결 유지 + interval마다 재렌더. 브라우저는 쓰지 않는다."""
    import websockets

    t_end = time.time() + hold
    try:
        async with websockets.connect(url, open_timeout=20, max_size=None) as ws:
            out["connected"] += 1
            while time.time() < t_end and not stop.is_set():
                t0 = time.perf_counter()
                await ws.send(_rerun_bytes(query))
                script_ms = None
                deadline = time.time() + 120
                while time.time() < deadline:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=deadline - time.time())
                    except asyncio.TimeoutError:
                        break
                    if isinstance(raw, str):
                        continue
                    fwd = ForwardMsg()
                    fwd.ParseFromString(raw)
                    kind = fwd.WhichOneof("type")
                    out["frames"][kind] = out["frames"].get(kind, 0) + 1
                    if kind == "script_finished":
                        script_ms = (time.perf_counter() - t0) * 1000
                        break
                if script_ms is None:
                    out["timeouts"].append(idx)
                    break
                out["script_ms"].append(script_ms)
                gap = interval - (script_ms / 1000.0)
                if gap > 0:
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=gap)
                    except asyncio.TimeoutError:
                        pass
    except Exception as exc:  # noqa: BLE001
        out["errors"].append(f"{type(exc).__name__}: {str(exc)[:80]}")
    finally:
        out["closed"] += 1


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * p))]


async def run(args) -> dict:
    steps = [int(s) for s in str(args.steps).split(",") if s.strip()]
    report: dict = {"url": args.url, "query": args.query, "started": None,
                    "hold_seconds": args.hold, "rerun_interval": args.rerun_interval,
                    "rows": []}
    stop = asyncio.Event()
    live: list[asyncio.Task] = []
    report["started"] = datetime.now().isoformat(timespec="seconds")

    for step in steps:
        add = step - len(live)
        if add > 0:
            for _ in range(add):
                out = {"script_ms": [], "timeouts": [], "errors": [], "frames": {},
                       "connected": 0, "closed": 0}
                report.setdefault("session_out", []).append(out)
                live.append(asyncio.create_task(
                    _session(len(live), args.url, args.query, args.rerun_interval,
                             args.hold, stop, out)))
        print(f"\n=== 단계: 동시 {step}명 ({datetime.now():%H:%M:%S}) 신규 +{max(0, add)} ===",
              flush=True)
        t0 = time.time()
        while time.time() - t0 < args.hold and not stop.is_set():
            await asyncio.sleep(5)
            conn = sum(o["connected"] for o in report["session_out"])
            errs = sum(len(o["errors"]) for o in report["session_out"])
            print(f"  [관찰] {datetime.now():%H:%M:%S} 동시 {step}명 · 연결 {conn}"
                  f"/{len(report['session_out'])} · 오류 {errs}", flush=True)

        script_ms: list[float] = []
        for o in report["session_out"]:
            script_ms.extend(o["script_ms"])
        row = {"concurrent": step, "sessions": len(live),
               "connected": sum(o["connected"] for o in report["session_out"]),
               "renders": len(script_ms),
               "script_p50": round(_pct(script_ms, 0.5)),
               "script_p95": round(_pct(script_ms, 0.95)),
               "script_max": round(max(script_ms)) if script_ms else 0,
               "timeouts": sum(len(o["timeouts"]) for o in report["session_out"]),
               "errors": sum(len(o["errors"]) for o in report["session_out"])}
        report["rows"].append(row)
        print(f"  [결과] {datetime.now():%H:%M:%S} 렌더 {row['renders']}건 · "
              f"script p50 {row['script_p50']}ms p95 {row['script_p95']}ms · "
              f"실패 {row['timeouts'] + row['errors']}건", flush=True)
        if row["connected"] < step * 0.9:
            print("  ⚠️ 연결이 단계 인원에 못 미친다 — 이 지점부터는 서버가 새 세션을 못 받는다",
                  flush=True)
            break

    stop.set()
    await asyncio.gather(*live, return_exceptions=True)
    report["finished"] = datetime.now().isoformat(timespec="seconds")
    frames: dict = {}
    for o in report["session_out"]:
        for k, v in o["frames"].items():
            frames[k] = frames.get(k, 0) + v
    report["frames"] = frames
    # 2026-10-04: 세션 상세를 통째로 버려서 "오류 1건"의 **원인 문구**를 나중에 볼 수 없었다
    # (30분 관측에서 실제로 겪음). 개수는 세션별로, 원인 문구는 중복 없이 최대 5종만 남긴다.
    report["errors_by_session"] = [len(o["errors"]) for o in report["session_out"]]
    report["timeouts_by_session"] = [len(o["timeouts"]) for o in report["session_out"]]
    seen: list[str] = []
    for o in report["session_out"]:
        for err in o["errors"]:
            if err not in seen:
                seen.append(err)
    report["error_samples"] = seen[:5]
    report.pop("session_out", None)
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_WS)
    ap.add_argument("--query", default=DEFAULT_QUERY)
    ap.add_argument("--steps", default="10,30,60,100,150")
    ap.add_argument("--hold", type=float, default=45.0)
    ap.add_argument("--rerun-interval", type=float, default=25.0)
    ap.add_argument("--out", default=str(ROOT / "scratch" / "load_test_ws.json"))
    args = ap.parse_args()

    rep = asyncio.run(run(args))
    print("\n" + "=" * 72)
    print("서버측(웹소켓 세션) 결과 — 시간은 서버가 스크립트를 다 돌린 시간(script_ms)")
    print("=" * 72)
    print(f"{'동시':>5} | {'연결':>5} | {'렌더':>5} | {'p50':>7} | {'p95':>7} | {'최대':>7} | 실패")
    for r in rep["rows"]:
        print(f"{r['concurrent']:>5} | {r['connected']:>5} | {r['renders']:>5} | "
              f"{r['script_p50']:>7} | {r['script_p95']:>7} | {r['script_max']:>7} | "
              f"{r['timeouts'] + r['errors']}")
    print(f"\n프레임 종류: {rep.get('frames')}")
    Path(args.out).write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"결과 저장: {args.out}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
