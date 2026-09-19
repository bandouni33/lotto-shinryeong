"""Turso 클라이언트 풀 — 전/후 처리량 실측 (같은 부하 조건 비교).

같은 스크립트를 풀 크기만 바꿔 두 번 돌려서 비교한다(그 외 조건은 전부 동일):

    cmd /c "set \"TURSO_CLIENT_POOL_SIZE=1\"&& venv312\\Scripts\\python.exe scripts\\bench_turso_pool.py"
    cmd /c "set \"TURSO_CLIENT_POOL_SIZE=4\"&& venv312\\Scripts\\python.exe scripts\\bench_turso_pool.py"

- 실제 Turso에 SELECT 1만 던진다(사용자 데이터 조회 없음 → 행 읽기 사용량 최소).
- 스레드 수/스레드당 쿼리 수는 BENCH_THREADS / BENCH_QUERIES로 고정한다.
- db_turso.connect()를 그대로 쓰므로 앱과 완전히 같은 코드 경로를 측정한다.
"""

from __future__ import annotations

import os
import statistics
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

import db_turso  # noqa: E402

THREADS = int(os.getenv("BENCH_THREADS", "12"))
QUERIES = int(os.getenv("BENCH_QUERIES", "4"))
QUERY = os.getenv("BENCH_QUERY", "SELECT 1")


def main() -> int:
    total = THREADS * QUERIES
    print(
        f"[bench] pool={db_turso._POOL_SIZE} threads={THREADS} "
        f"queries/thread={QUERIES} total={total} query={QUERY!r}"
    )

    latencies: list[float] = []
    errors: list[str] = []
    slots: list[int | None] = []
    lock = threading.Lock()
    barrier = threading.Barrier(THREADS)

    def worker():
        try:
            barrier.wait(timeout=30)
        except Exception:
            pass
        for _ in range(QUERIES):
            try:
                conn = db_turso.connect()
            except Exception as e:  # noqa: BLE001
                with lock:
                    errors.append(f"connect: {type(e).__name__}: {e}")
                continue
            started = time.perf_counter()
            try:
                conn.execute(QUERY)
            except Exception as e:  # noqa: BLE001
                with lock:
                    errors.append(f"execute: {type(e).__name__}: {e}")
                continue
            elapsed = time.perf_counter() - started
            with lock:
                latencies.append(elapsed)
                slots.append(conn.slot)

    threads = [threading.Thread(target=worker) for _ in range(THREADS)]
    started = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=180)
    wall = time.perf_counter() - started

    ok = len(latencies)
    print(
        f"[bench] wall={wall:.2f}s ok={ok}/{total} errors={len(errors)} "
        f"throughput={ok / wall if wall else 0:.1f} q/s"
    )
    if latencies:
        ordered = sorted(latencies)

        def pct(q: float) -> float:
            return ordered[min(len(ordered) - 1, int(len(ordered) * q))] * 1000

        print(
            f"[bench] latency mean={statistics.mean(latencies) * 1000:.0f}ms "
            f"p50={pct(0.5):.0f}ms p95={pct(0.95):.0f}ms max={ordered[-1] * 1000:.0f}ms"
        )
    if slots:
        counts: dict[int | None, int] = {}
        for s in slots:
            counts[s] = counts.get(s, 0) + 1
        print(f"[bench] slots used={sorted(counts.items(), key=lambda kv: (kv[0] is None, kv[0]))}")
    for e in errors[:5]:
        print(f"[bench] ERROR {e}")

    sys.stdout.flush()
    return 1 if errors else 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    # db_turso가 import 시점에 만드는 비데몬 스레드 때문에 프로세스가 스스로
    # 끝나지 않는다 — 테스트 러너와 같은 방식으로 즉시 종료한다.
    os._exit(code)
