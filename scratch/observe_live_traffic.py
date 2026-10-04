"""토요일 추첨 버스트 실사용 관측 (2026-10-04 승인 — "토요일 실사용 관측").

무엇을 보는가(한 줄씩 CSV로):
  · 가용성·응답 : 60초마다 HTTP 상태/지연 + 웹소켓 세션 1개로 **실제 렌더 1회**를 돌려
                  script_ms 를 잰다(합성 프로브). 대기화면이면 gate=1 로 남긴다 —
                  실사용자 전원이 막힌 상황을 우리 프로브가 먼저 알려준다.
  · 서버 자원   : 서버 프로세스 RSS·CPU (Win32 API — scratch/monitor_streamlit_resources.py
                  함수를 그대로 가져다 쓴다. 같은 계측을 두 벌 만들지 않는다).
  · 실사용 렌더 : run_server.ps1 이 남기는 server_out.log 의 `[dbtrace]` 줄을 읽어
                  **실제 사용자 렌더의** script_ms·DB 호출 수·db_ms 분포를 모은다.
                  (프로브 자신의 렌더는 빼야 진짜 사용자 수가 나온다 — probe_renders 로 보정)

왜 이 조합인가:
  서버 안에서 도는 게이트(입장 제한)는 외부에서 직접 셀 수 없다. 대신 ① 프로브가 주기적으로
  대기화면을 받는지(=게이트가 켜져 있는지) ② 실사용 렌더가 서버 로그에 몇 건 찍히는지
  ③ 프로브 자체의 script_ms 가 튀는지 — 이 셋으로 "버스트가 왔는가"를 판단한다.

실행(토요일 창에서 백그라운드):
  venv312\\Scripts\\python.exe -u -X utf8 scratch\\observe_live_traffic.py --duration 10800

주의: 이 도구는 **읽기 전용**이다. 서버 설정·DB에 아무것도 쓰지 않는다(프로브 세션 1개만 연다).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import importlib.util
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRATCH = ROOT / "scratch"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 계측 코드는 한 벌만 둔다 — RSS/CPU/포트→PID 는 기존 모니터 도구를 그대로 쓴다.
_spec = importlib.util.spec_from_file_location(
    "monitor_tool", SCRATCH / "monitor_streamlit_resources.py")
monitor = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = monitor
_spec.loader.exec_module(monitor)

from streamlit.proto.BackMsg_pb2 import BackMsg  # noqa: E402
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg  # noqa: E402

GATE_MARKERS = ("admission-overload-wrap".encode("utf-8"),
                "이용자 폭증으로 잠시 대기".encode("utf-8"))
DBTRACE_RE = re.compile(r"\[dbtrace\] page=(\S+) calls=(\d+) db_ms=(\d+) script_ms=(\d+)")


def _db_event_probe(last_seen: str | None) -> tuple[int, str | None]:
    """운영 DB(공유)에서 이번 간격에 새로 생긴 보안 이벤트 수를 읽는다(읽기 전용).

    왜 필요한가: Cloud는 우리가 CPU/RSS를 볼 수 없다. 그런데 **Cloud도 같은 Turso에 쓴다**
    (2026-10-04 확인) — 로그인 직후 세션은 `cookie_reachable` 이벤트를 1건 남기므로
    이 개수가 "이 사이에 서버에 붙은 세션 수"의 가장 가까운 대리값이 된다.
    프로브 자신도 1건을 남기므로 표시 이름에 그 사실을 밝힌다(과대 계상 방지).
    """
    try:
        from env_loader import load_dotenv_file

        load_dotenv_file()
        import db_turso

        conn = db_turso.connect()
        if last_seen:
            rows = conn.execute(
                "SELECT count(*), max(created_at) FROM security_events WHERE created_at > ?",
                (last_seen,)).fetchall()
        else:
            rows = conn.execute(
                "SELECT count(*), max(created_at) FROM security_events "
                "WHERE created_at >= ?",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),)).fetchall()
        row = rows[0] if rows else None
        if row is None:
            return 0, last_seen
        return int(row[0] or 0), (row[1] or last_seen)
    except Exception:
        return -1, last_seen  # -1 = 조회 실패(0과 구분 — 실패를 '없음'으로 오해하면 안 된다)


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * p))]


class LogWatcher:
    """server_out.log 에서 새로 추가된 [dbtrace] 줄만 읽어 실사용 렌더 통계를 모은다."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.inode = None
        self.offset = 0
        self.rows: list[dict] = []
        self.skipped_at_start = 0

    def start_at_end(self) -> None:
        """관측 **시작 이전**의 로그는 세지 않는다.

        안 그러면 과거의 렌더(예전 프로브·예전 테스트)가 '이번 창의 실사용 렌더'로
        둔갑한다 — 실제로 기준선 실행에서 그렇게 잘못 셌다(22건이 전부 내 프로브였다).
        """
        if not self.path.exists():
            return
        with self.path.open("rb") as fh:
            fh.seek(0, 2)
            self.offset = fh.tell()
        self.skipped_at_start = self.offset
        # inode를 기억해 둬야 다음 poll 에서 "새 파일"로 오인해 처음부터 다시 읽지 않는다
        # (첫 poll 에서 그렇게 되어 과거 줄을 이번 창의 렌더로 잘못 셌다).
        self.inode = self.path.stat().st_ino

    def poll(self) -> list[dict]:
        if not self.path.exists():
            return []
        stat = self.path.stat()
        # st_ino 는 정수다 — 튜플과 비교하면 항상 True라 매 poll 마다 처음부터 다시 읽고
        # 과거 줄을 이번 창의 렌더로 중복 계산한다(2026-10-04 실제로 그렇게 잘못 셌다).
        if self.inode != stat.st_ino or stat.st_size < self.offset:
            # 파일이 새로 만들어졌거나 잘렸다(서버 재시작으로 리다이렉트가 새로 시작)
            self.offset = 0
        self.inode = stat.st_ino
        new: list[dict] = []
        with self.path.open("r", encoding="utf-8", errors="replace") as fh:
            fh.seek(self.offset)
            for line in fh:
                m = DBTRACE_RE.search(line)
                if m:
                    row = {"page": m.group(1), "calls": int(m.group(2)),
                           "db_ms": int(m.group(3)), "script_ms": int(m.group(4))}
                    self.rows.append(row)
                    new.append(row)
            self.offset = fh.tell()
        return new


async def _probe(url: str, timeout: float) -> dict:
    """웹소켓 세션 1개로 실제 렌더 1회 — script_ms 와 대기화면 여부."""
    import websockets

    t0 = time.perf_counter()
    out = {"script_ms": None, "gate": 0, "deltas": 0, "ok": 0, "err": ""}
    try:
        async with websockets.connect(url, open_timeout=min(timeout, 30), max_size=None) as ws:
            msg = BackMsg()
            msg.rerun_script.query_string = "page=main"
            msg.rerun_script.page_name = ""
            msg.rerun_script.page_script_hash = ""
            await ws.send(msg.SerializeToString())
            deadline = time.time() + timeout
            while time.time() < deadline:
                raw = await asyncio.wait_for(ws.recv(), timeout=deadline - time.time())
                if isinstance(raw, str):
                    continue
                if any(m in raw for m in GATE_MARKERS):
                    out["gate"] = 1
                fwd = ForwardMsg()
                fwd.ParseFromString(raw)
                kind = fwd.WhichOneof("type")
                if kind == "delta":
                    out["deltas"] += 1
                if kind == "script_finished":
                    out["script_ms"] = round((time.perf_counter() - t0) * 1000)
                    out["ok"] = 1
                    break
    except Exception as exc:  # noqa: BLE001 — 관측이 예외로 죽으면 안 된다
        out["err"] = f"{type(exc).__name__}: {str(exc)[:60]}"
    return out


def _http(url: str, timeout: float) -> tuple[int, int]:
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            resp.read(2048)
            return int(resp.status), round((time.perf_counter() - t0) * 1000)
    except Exception:
        return 0, round((time.perf_counter() - t0) * 1000)


async def run(args) -> int:
    log = LogWatcher(Path(args.log) if Path(args.log).is_absolute() else ROOT / args.log)
    log.start_at_end()
    db_seen_ts: str | None = None
    out_path = Path(args.out) if Path(args.out).is_absolute() else ROOT / args.out
    probe_renders = 0
    frames: list[dict] = []
    started = time.time()
    last_tick = started
    prev_cpu = monitor.cpu_seconds(monitor.pid_on_port(args.port) or args.pid or 0) \
        if (monitor.pid_on_port(args.port) or args.pid) else None
    prev_totals = monitor.cpu_totals()
    cores = os.cpu_count() or 1

    header = ("t,elapsed_s,http_health,http_page,page_ms,probe_script_ms,probe_gate,probe_deltas,"
              "probe_ok,new_user_renders,user_script_ms_p50,user_script_ms_max,user_db_calls_max,"
              "db_sessions_since_last,probe_cpu_pct,rss_mb,sys_cpu_pct,err")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(header + "\n")
    print(f"[observe] 시작 {datetime.now():%Y-%m-%d %H:%M:%S} · {args.interval}초 간격 · "
          f"{args.duration/3600:.1f}시간 · 로그 {log.path}", flush=True)
    print(header, flush=True)

    while time.time() - started < args.duration:
        tick0 = time.time()
        local = args.target == "local"
        health, _ = _http(args.health, args.timeout)
        page_status, page_ms = _http(args.page, args.timeout)
        if local:
            probe = await _probe(args.url, args.timeout)
            probe_renders += 1
        else:
            # 2026-10-04 실측: Cloud는 익명 웹소켓을 **HTTP 401로 거부**한다
            # (`wss://…/~ +/_stcore/stream`). HTTP 페이지는 같은 시각 200이므로
            # 앱이 죽은 게 아니라 우리 프로브가 인증 없이 못 붙는 것이다.
            # → Cloud 모드에서는 웹소켓 렌더를 아예 시도하지 않고, HTTP + 공유 DB로만 본다.
            probe = {"script_ms": None, "gate": 0, "deltas": 0, "ok": 0,
                     "err": "websocket_probe_disabled_for_cloud(HTTP 401)"}
        new_rows = log.poll() if local else []
        user_rows = [r for r in new_rows]
        db_sessions, db_seen_ts = (-1, db_seen_ts) if not local else ("", db_seen_ts)
        if args.target == "cloud":
            db_sessions, db_seen_ts = _db_event_probe(db_seen_ts)
        pid = monitor.pid_on_port(args.port) or args.pid if local else None
        rss = monitor.rss_mb(pid) if pid else None
        # CPU%는 모니터 도구가 쓰는 원시값(cpu_seconds/cpu_totals)에서 직접 계산한다 —
        # 별도 헬퍼를 만들면 같은 계측이 두 벌이 된다.
        now = time.time()
        span = max(now - last_tick, 0.001)
        cur_cpu = monitor.cpu_seconds(pid) if pid else None
        proc_cpu = None
        if cur_cpu is not None and prev_cpu is not None:
            proc_cpu = (cur_cpu - prev_cpu) / span / cores * 100.0
        prev_cpu = cur_cpu
        totals = monitor.cpu_totals()
        sys_cpu = 0.0
        if totals and prev_totals:
            d_idle = totals[0] - prev_totals[0]
            d_busy = totals[1] - prev_totals[1]
            sys_cpu = (1 - d_idle / d_busy) * 100.0 if d_busy > 0 else 0.0
        prev_totals = totals
        last_tick = now
        row = {
            "t": f"{datetime.now():%H:%M:%S}",
            "elapsed_s": round(time.time() - started, 1),
            "http_health": health, "http_page": page_status, "page_ms": page_ms,
            "probe_script_ms": probe["script_ms"] or "", "probe_gate": probe["gate"],
            "probe_deltas": probe["deltas"], "probe_ok": probe["ok"],
            "new_user_renders": len(user_rows),
            "user_script_ms_p50": round(_pct([r["script_ms"] for r in user_rows], 0.5)) if user_rows else "",
            "user_script_ms_max": max((r["script_ms"] for r in user_rows), default=""),
            "user_db_calls_max": max((r["calls"] for r in user_rows), default="") if local else "",
            "db_sessions_since_last": db_sessions,
            "probe_cpu_pct": "" if proc_cpu is None else round(proc_cpu, 1),
            "rss_mb": "" if rss is None else round(rss, 1),
            "sys_cpu_pct": sys_cpu, "err": probe["err"],
        }
        frames.append(row)
        with out_path.open("a", encoding="utf-8", newline="") as fh:
            csv.DictWriter(fh, fieldnames=header.split(",")).writerow(row)
        print(",".join(str(row[k]) for k in header.split(",")), flush=True)
        sleep = args.interval - (time.time() - tick0)
        remaining = args.duration - (time.time() - started)
        if sleep > 0:
            # 마지막 간격이 창을 넘지 않게 자른다 — 안 그러면 duration을 넘겨서
            # 루프가 한 번 더 돌고(그만큼 명령이 오래 붙잡힌다).
            await asyncio.sleep(max(0.0, min(sleep, remaining)))

    # ── 요약 ───────────────────────────────────────────────
    user_renders = log.rows
    real_user_renders = max(0, len(user_renders) - probe_renders)
    probe_ms = [f["probe_script_ms"] for f in frames if f["probe_script_ms"]]
    summary = {
        "started": datetime.fromtimestamp(started).strftime("%Y-%m-%d %H:%M:%S"),
        "minutes": round((time.time() - started) / 60, 1),
        "ticks": len(frames),
        "http_failures": sum(1 for f in frames if f["http_health"] != 200),
        "probe_renders": probe_renders,
        "probe_gate_seen": sum(f["probe_gate"] for f in frames),
        "probe_script_ms_p50": round(_pct(probe_ms, 0.5)),
        "probe_script_ms_p95": round(_pct(probe_ms, 0.95)),
        "probe_script_ms_max": max(probe_ms, default=0),
        "log_db_renders": len(user_renders),
        "log_bytes_skipped_at_start": log.skipped_at_start,
        "real_user_renders_est": real_user_renders,
        "user_script_ms_p50": round(_pct([r["script_ms"] for r in user_renders], 0.5)),
        "user_script_ms_p95": round(_pct([r["script_ms"] for r in user_renders], 0.95)),
        "user_db_calls_max": max((r["calls"] for r in user_renders), default=0),
        "rss_mb_max": max([f["rss_mb"] for f in frames if f["rss_mb"]] or [0]),
        "probe_cpu_pct_max": max([f["probe_cpu_pct"] for f in frames
                                 if f["probe_cpu_pct"] != ""] or [0]),
    }
    Path(args.summary).write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    print("\n[observe] 요약", json.dumps(summary, ensure_ascii=False), flush=True)
    print(f"[observe] 저장: {out_path} · {args.summary}", flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="토요일 버스트 실사용 관측(읽기 전용)")
    ap.add_argument("--target", choices=("local", "cloud"), default="local",
                    help="local=이 PC의 서버(로그·RSS/CPU·웹소켓 렌더) / "
                         "cloud=Cloud URL(HTTP + 공유 DB의 세션 수. 익명 웹소켓은 401로 거부됨)")
    ap.add_argument("--port", type=int, default=8501)
    ap.add_argument("--pid", type=int, default=None)
    ap.add_argument("--health", default="http://127.0.0.1:8501/_stcore/health")
    ap.add_argument("--page", default="http://127.0.0.1:8501/?page=main")
    ap.add_argument("--url", default="ws://127.0.0.1:8501/_stcore/stream")
    ap.add_argument("--log", default="server_out.log")
    ap.add_argument("--interval", type=float, default=60.0)
    ap.add_argument("--duration", type=float, default=10 * 3600)
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--out", default="scratch/live_observation.csv")
    ap.add_argument("--summary", default="scratch/live_observation_summary.json")
    args = ap.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
