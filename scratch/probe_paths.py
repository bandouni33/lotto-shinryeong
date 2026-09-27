# -*- coding: utf-8 -*-
"""추적표 폴더 원시 목록 + 바탕화면 최상위 항목 + DB 최신 회차(읽기 전용, 빠른 진단)."""
from __future__ import annotations

import datetime
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scratch" / "probe_paths_out.txt"
DESKTOP = Path(r"C:\Users\PC\Desktop")
TRACKER = ROOT / "★조합생성_후보숫자_추적표"

lines: list[str] = []


def w(s: str = "") -> None:
    lines.append(s)


def mtime(p: Path) -> str:
    try:
        return f"{datetime.datetime.fromtimestamp(p.stat().st_mtime):%Y-%m-%d %H:%M}"
    except OSError:
        return "-"


w(f"scan start {datetime.datetime.now():%Y-%m-%d %H:%M:%S}")

for d in (TRACKER, TRACKER / "_backup_20260927", TRACKER / "_backup_20260927_formulas"):
    w(f"\n== raw listdir {d} ==")
    try:
        for e in sorted(os.listdir(d)):
            p = d / e
            w(f"  {e} | dir={p.is_dir()} | size={p.stat().st_size if p.is_file() else '-'} | {mtime(p)}")
    except Exception as e:  # noqa: BLE001
        w(f"  !! {type(e).__name__}: {e}")

w(f"\n== Desktop top level ({DESKTOP}) ==")
try:
    ents = sorted(os.listdir(DESKTOP), key=lambda e: mtime(DESKTOP / e), reverse=True)
    for e in ents[:60]:
        p = DESKTOP / e
        w(f"  {mtime(p)} | {'DIR ' if p.is_dir() else 'FILE'} | {e}")
except Exception as e:  # noqa: BLE001
    w(f"  !! {type(e).__name__}: {e}")

w("\n== DB draw_results latest round ==")
try:
    sys.path.insert(0, str(ROOT))
    import draw_results_db
    rows = draw_results_db.get_all_draw_results()
    rounds = sorted(int(r["draw_round"]) for r in rows)
    w(f"  n={len(rounds)} min={rounds[0] if rounds else None} max={rounds[-1] if rounds else None}")
    if rounds:
        last = next(r for r in rows if int(r["draw_round"]) == rounds[-1])
        w(f"  last row: {last}")
except Exception as e:  # noqa: BLE001
    w(f"  !! DB read failed: {type(e).__name__}: {e}")

OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"written {OUT} ({len(lines)} lines)")
