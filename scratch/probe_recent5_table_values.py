# -*- coding: utf-8 -*-
"""'최근 5회차 생성 현황' 표가 보여줄 값의 실측 (읽기 전용).

diff가 조합하는 세 함수만 쓴다 — get_draw_extraction_stats / get_draw_generation_stats /
get_pattern_recorded_at. 새 스키마·쓰기 없음. 표의 '총 조합 개수·조합 개수·생성시간'이 실제
DB 값과 맞는지 대조할 기준값을 남기는 것이 목적이다(py_compile·화면 확인과 별개의 근거).

실행: venv312\\Scripts\\python.exe scratch\\probe_recent5_table_values.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from env_loader import load_dotenv_file  # noqa: E402

load_dotenv_file()

import marketing_db as m  # noqa: E402


def w(s: str = "") -> None:
    try:
        print(s, flush=True)
    except UnicodeEncodeError:
        print(str(s).encode("cp949", errors="replace").decode("cp949", errors="replace"),
              flush=True)


rows = m.get_draw_extraction_stats(limit=6)
w(f"get_draw_extraction_stats(limit=6) → {len(rows)}개 회차")
w("")
w(f"{'회차':>6} | {'총 조합 개수':>13} | {'stage2':>10} | {'조합 개수(stage4)':>11} | "
  f"{'생성시간(기록)':<26} | pattern_count")
w("-" * 110)
for r in rows:
    rnd = r["draw_round"]
    g = m.get_draw_generation_stats(rnd) or {}
    at = m.get_pattern_recorded_at(rnd)
    w(f"{rnd:>6} | {r['total_count']:>13,} | "
      f"{(g.get('stage2_count') if g else None) if g else '-':>10} | "
      f"{(g.get('stage4_count') if g else None) if g else '-':>11} | "
      f"{str(at):<26} | {r['pattern_count']}")
w("")
w("1243회차 단독 확인:")
g1243 = m.get_draw_generation_stats(1243)
w(f"  get_draw_generation_stats(1243) = {g1243}")
w(f"  get_pattern_recorded_at(1243)    = {m.get_pattern_recorded_at(1243)}")
w(f"  get_draw_extraction_stats 중 1243 = "
  f"{next((r for r in rows if r['draw_round'] == 1243), '없음')}")

os._exit(0)
