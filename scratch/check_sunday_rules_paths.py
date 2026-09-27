# -*- coding: utf-8 -*-
"""일요일 14시 배포용 조합생성이 실제로 읽는 경로·규칙 실측(읽기 전용).

DB는 SELECT만 한다(쓰기 없음). 파일도 만들지 않는다.
실행: venv312\\Scripts\\python.exe scratch\\check_sunday_rules_paths.py
"""
from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from env_loader import load_dotenv_file  # noqa: E402

load_dotenv_file()

OUT = ROOT / "scratch" / "check_sunday_rules_paths_out.txt"
LINES: list[str] = []


def w(s: str = "") -> None:
    LINES.append(s)


def mt(p: Path) -> str:
    try:
        return f"{datetime.datetime.fromtimestamp(p.stat().st_mtime):%Y-%m-%d %H:%M}"
    except OSError:
        return "-"


w(f"== 1. 로컬 규칙 파일(폴백 경로) — {ROOT}")
for name in ("combo_filter_rules_stage1.json", "combo_filter_rules_stage2.json"):
    p = ROOT / name
    w(f"  {name}: exists={p.exists()} size={p.stat().st_size if p.exists() else '-'} mtime={mt(p)}")

w("\n== 2. DB 규칙(app_settings, 주 경로)")
try:
    import app_settings
    for stage in (1, 2):
        raw = app_settings.get_filter_rules_json(stage)
        parsed = json.loads(raw) if raw else None
        auto = [r for r in (parsed or []) if r.get("is_auto")]
        w(f"  get_filter_rules_json({stage}): len={len(raw) if raw else 0} chars, "
          f"규칙수={len(parsed) if parsed else 0} (AUTO {len(auto)})")
    w(f"  키: {app_settings.FILTER_RULES_STAGE1_KEY} / {app_settings.FILTER_RULES_STAGE2_KEY}")
except Exception as e:  # noqa: BLE001
    w(f"  !! DB 규칙 조회 실패: {type(e).__name__}: {e}")

w("\n== 3. 실제 로드 결과(_load_rules)와 기준 개수")
try:
    import combo_filter_v2 as cf
    import combo_gen_worker as cw
    static, auto, stage2 = cf._load_rules()
    w(f"  1차 고정 {len(static)} + AUTO {len(auto)} + 2차 {len(stage2)}  "
      f"/ 워커 기대값 {cw.EXPECTED_RULE_COUNTS} — 일치={ (len(static), len(auto), len(stage2)) == cw.EXPECTED_RULE_COUNTS }")
    w(f"  AUTO 규칙 이름: {[r['name'] for r in auto]}")
    w(f"  RECENT_WINDOW(3차 격차순위 기준 최근창) = {cf.RECENT_WINDOW}, MAXGAP = {cf.MAXGAP}")
    w(f"  EXTRACT_RATE = {cw.EXTRACT_RATE}, RANK_TIER_RATIO = {cw.RANK_TIER_RATIO}, "
      f"PATTERN_COUNT_DISPLAY = {cw.PATTERN_COUNT_DISPLAY}")
    w(f"  규칙 파일 경로 상수: {os.path.basename(cf._STAGE1_FILE)} / {os.path.basename(cf._STAGE2_FILE)}")
except Exception as e:  # noqa: BLE001
    w(f"  !! 로드 실패: {type(e).__name__}: {e}")

w("\n== 4. 회차·풀 현황(DB 읽기 전용)")
try:
    import draw_results_db
    import marketing_db
    latest = draw_results_db.get_latest_draw_round()
    w(f"  draw_results 최신 회차 = {latest} (총 {draw_results_db.get_draw_results_count()}건)")
    if latest:
        for r in (latest, latest + 1):
            n = marketing_db.get_combination_count_by_draw(r)
            w(f"  lotto_combinations {r}회차 = {n:,}개")
except Exception as e:  # noqa: BLE001
    w(f"  !! 조회 실패: {type(e).__name__}: {e}")

w("\n== 5. 워커가 남기는 로컬 경로")
status = ROOT / "combo_gen_job.status"
w(f"  combo_gen_job.status: exists={status.exists()} mtime={mt(status)}")
if status.exists():
    w(f"    내용: {status.read_text(encoding='utf-8')[:400]}")
for folder in sorted(p for p in ROOT.iterdir() if p.is_dir() and p.name.endswith("회차")):
    files = {f.name: f.stat().st_size for f in folder.iterdir()}
    w(f"  {folder.name}/: {files}")

OUT.write_text("\n".join(LINES), encoding="utf-8")
print(f"written {OUT} ({len(LINES)} lines)")
