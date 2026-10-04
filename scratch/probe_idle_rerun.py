"""유휴 후 재렌더 진단 — 30분 관측에서 나온 "오류 1건"의 원인을 문구로 잡는다.

관측에서 본 것(2026-10-04): 세션을 붙여 첫 렌더는 정상(script_finished)였는데, 그 뒤
**5분 유휴 후 예약된 재렌더**에서 오류 1건이 났고 그 뒤로 재시도가 멈췄다. 원인 후보:
  (1) 서버가 유휴 웹소켓을 닫는다(내 클라이언트가 유휴 동안 소켓을 읽지 않아 닫힘을 못 봄)
  (2) 재렌더 자체가 오래 걸린다(운영 DB·외부 동기화 포함) → 클라이언트 대기(120초) 초과
  (3) 그 밖의 프로토콜 문제
이 스크립트는 **유휴 길이를 바꿔가며** 같은 절차(렌더 → 유휴 → 재렌더)를 돌리고, 실패하면
예외 타입·문구와 걸린 시간을 그대로 찍는다. 유휴 동안에도 소켓을 읽어(recv 루프) 서버가
보내는 프레임(닫힘 코드 포함)을 관찰한다.

실행: venv312\\Scripts\\python.exe -u -X utf8 scratch\\probe_idle_rerun.py --idle 30
      venv312\\Scripts\\python.exe -u -X utf8 scratch\\probe_idle_rerun.py --idle 300
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from streamlit.proto.BackMsg_pb2 import BackMsg  # noqa: E402
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg  # noqa: E402

DEFAULT_WS = "ws://lottoshinryeong.duckdns.org:8501/_stcore/stream"


def rerun_bytes(query: str) -> bytes:
    msg = BackMsg()
    msg.rerun_script.query_string = query
    return msg.SerializeToString()


async def render_once(ws, query: str, budget: float) -> tuple[str, float, list[str]]:
    """재렌더 1회: 보내고 script_finished(또는 닫힘/시간초과)까지. (판정, 경과초, 본 프레임)"""
    t0 = time.perf_counter()
    await ws.send(rerun_bytes(query))
    seen: list[str] = []
    while True:
        left = budget - (time.perf_counter() - t0)
        if left <= 0:
            return "timeout", time.perf_counter() - t0, seen
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=left)
        except asyncio.TimeoutError:
            return "timeout", time.perf_counter() - t0, seen
        except Exception as exc:  # noqa: BLE001
            return f"{type(exc).__name__}: {str(exc)[:120]}", time.perf_counter() - t0, seen
        fwd = ForwardMsg()
        fwd.ParseFromString(raw)
        kind = fwd.WhichOneof("type") or "?"
        seen.append(kind)
        if kind == "script_finished":
            return "ok", time.perf_counter() - t0, seen


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_WS)
    ap.add_argument("--idle", type=float, default=30.0, help="첫 렌더 후 재렌더까지 유휴(초)")
    ap.add_argument("--budget", type=float, default=120.0, help="재렌더 1회 대기 상한(초)")
    args = ap.parse_args()

    import websockets

    print(f"[probe] {args.url} · 유휴 {args.idle:.0f}초 · 대기 상한 {args.budget:.0f}초", flush=True)
    async with websockets.connect(args.url, open_timeout=30, max_size=None) as ws:
        verdict, secs, frames = await render_once(ws, "page=main", args.budget)
        print(f"  1) 첫 렌더 : {verdict} · {secs:.1f}초 · 프레임 {len(frames)}종 {sorted(set(frames))[:6]}",
              flush=True)

        # 유휴 동안 소켓을 계속 읽는다 — 서버가 닫거나 핑을 보내면 여기서 드러난다.
        closed: str | None = None
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < args.idle:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=min(5.0, args.idle))
            except asyncio.TimeoutError:
                continue
            except Exception as exc:  # noqa: BLE001
                closed = f"{type(exc).__name__}: {str(exc)[:120]}"
                break
            fwd = ForwardMsg()
            fwd.ParseFromString(raw)
            print(f"     [유휴 중 프레임] +{time.perf_counter() - t0:5.1f}s "
                  f"{fwd.WhichOneof('type') or '?'}", flush=True)
        print(f"  2) 유휴 {args.idle:.0f}초 : 서버가 닫았나? {closed or '아니오(연결 유지)'}", flush=True)

        if closed is None:
            verdict2, secs2, frames2 = await render_once(ws, "page=main", args.budget)
            print(f"  3) 유휴 후 재렌더 : {verdict2} · {secs2:.1f}초 · "
                  f"프레임 {sorted(set(frames2))[:6]}", flush=True)
        else:
            print("  3) 유휴 후 재렌더 : 시도하지 않음(이미 닫힘)", flush=True)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(asyncio.run(main()))
