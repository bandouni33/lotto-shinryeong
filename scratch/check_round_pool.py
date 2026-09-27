# -*- coding: utf-8 -*-
"""대상 회차(=최신 추첨 + 1)와 그 회차 조합 풀이 실제로 생성돼 있는지 확인한다(2026-09-27).

읽기 전용(Turso SELECT + 동행복권 조회 + CSV 읽기).
"""
from __future__ import annotations

import csv
import os
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import env_loader  # noqa: E402

env_loader.load_dotenv_file()
import draw_results_db  # noqa: E402
import marketing_db  # noqa: E402


def draw_date_of(round_no: int) -> str:
    """회차 → 추첨일(토). history.csv에 회차·날짜가 있으면 그걸 쓰고, 없으면 계산."""
    for name in ("history.csv", "frequency.csv", "data_s.csv"):
        p = ROOT / name
        if not p.exists():
            continue
        try:
            with open(p, encoding="utf-8-sig", newline="") as f:
                rows = list(csv.reader(f))
        except Exception:
            continue
        if not rows:
            continue
        header = [c.strip() for c in rows[0]]
        if not any("회차" in h or "round" in h.lower() for h in header):
            continue
        idx_round = next(i for i, h in enumerate(header) if "회차" in h or "round" in h.lower())
        idx_date = next((i for i, h in enumerate(header) if "날짜" in h or "date" in h.lower() or "추첨" in h), None)
        print(f"  [{name}] 헤더={header}")
        for r in rows[1:]:
            if len(r) > max(idx_round, idx_date if idx_date is not None else 0) and r[idx_round].strip().isdigit():
                if int(r[idx_round]) == round_no:
                    return r[idx_date].strip() if idx_date is not None else "?"
    return "?"


def main() -> int:
    latest = draw_results_db.get_latest_draw_round()
    target = (latest or 0) + 1
    print("=" * 90)
    print(f"DB 최신 추첨 회차 = {latest}   →   대상(생성 대상) 회차 = {target}")

    remote = draw_results_db.fetch_latest_from_dhlottery()
    print(f"동행복권 사이트 최신 회차 = {remote['draw_round'] if remote else '조회 실패'}"
          f"{'  → DB와 일치(새 추첨 없음)' if remote and remote['draw_round'] == latest else ''}")

    print("\n회차별 조합 풀(DB 적재 수):")
    for r in (latest - 1, latest, target, target + 1):
        try:
            print(f"  {r}회차: {marketing_db.get_combination_count_by_draw(r):,}개")
        except Exception as e:  # noqa: BLE001
            print(f"  {r}회차: 조회 실패({type(e).__name__}: {e})")

    print("\n회차 → 추첨일(토) 매핑 확인:")
    print(f"  {latest}회차 추첨일: {draw_date_of(latest)}")
    print(f"  {target}회차 추첨일: {draw_date_of(target)}")
    if draw_date_of(latest) not in ("?", ""):
        d = date.fromisoformat(draw_date_of(latest).replace("/", "-")[:10])
        print(f"  계산: {latest}회차 {d}({d.strftime('%a')}) → {target}회차 {d + timedelta(days=7)}"
              f"({(d + timedelta(days=7)).strftime('%a')})")
    print("\n오늘/다음 일요일 기준:")
    today = date.today()
    print(f"  오늘={today}({today.strftime('%a')}) → 오늘 생성 대상={target}회차")
    print(f"  다음 일요일={today + timedelta(days=7)} → 그날 생성 대상={target + 1}회차")
    return 0


if __name__ == "__main__":
    # 실측 문제: 이 스크립트는 보고를 다 찍고도 프로세스가 끝나지 않아 115초에 강제 종료됐다
    # (db_turso의 non-daemon 스레드 — 같은 이유로 weekly_backup_cleanup.py도 os._exit를 쓴다).
    # os._exit는 버퍼를 안 흘려보내므로 먼저 flush 한다.
    code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
