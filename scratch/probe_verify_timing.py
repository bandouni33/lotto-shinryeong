# -*- coding: utf-8 -*-
"""외부 검증기(scratch/verify_workbook_ranking.py)를 별도 프로세스로 돌려
exit code와 소요 시간을 잰다(읽기 전용).
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scratch" / "probe_verify_timing_out.txt"

t0 = time.time()
p = subprocess.run(
    [sys.executable, "-X", "utf8", str(ROOT / "scratch" / "verify_workbook_ranking.py")],
    cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
)
elapsed = time.time() - t0
tail = [ln for ln in (p.stdout or "").splitlines() if ln.strip()][-6:]
OUT.write_text(
    f"exit={p.returncode}\nelapsed={elapsed:.1f}s\nstdout tail:\n"
    + "\n".join(tail)
    + f"\nstderr:\n{(p.stderr or '')[-500:]}\n",
    encoding="utf-8",
)
print(f"exit={p.returncode} elapsed={elapsed:.1f}s -> {OUT}")
