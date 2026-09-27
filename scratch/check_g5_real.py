# -*- coding: utf-8 -*-
"""G5(대상회차 풀 게이트)의 (b)조건 — 생성기록 recorded_at의 **실제 저장 형식과 나이**를 확인한다.

읽기 전용. 게이트의 진짜 코드 경로(weekly_backup_cleanup.pool_gate)와 DB 실값을 함께 본다.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import env_loader  # noqa: E402

env_loader.load_dotenv_file()

import marketing_db  # noqa: E402
import weekly_backup_cleanup as wbc  # noqa: E402

FRESH = timedelta(hours=wbc.FRESH_HOURS)


def main() -> int:
    print("=" * 92)
    print("recorded_at 실값 — DB에 실제로 저장된 형식(게이트가 파싱한다고 가정한 형식인가)")
    for r in (1241, 1242, 1243, 1244):
        count = marketing_db.get_combination_count_by_draw(r)
        raw = marketing_db.get_pattern_recorded_at(r)
        parsed, age_h = "—", "—"
        if raw:
            try:
                dt = datetime.fromisoformat(str(raw))
                if dt.tzinfo is not None:
                    dt = dt.astimezone().replace(tzinfo=None)
                age_h = f"{(datetime.now() - dt).total_seconds() / 3600:+.1f}h"
                parsed = dt.isoformat(timespec="seconds")
            except ValueError:
                parsed = "!! 파싱 실패"
        print(f"  {r}회차: 풀={count:>7,}개 · recorded_at={raw!r} → {parsed} ({age_h})")

    print("\n" + "=" * 92)
    print(f"게이트 규칙(FRESH_HOURS={wbc.FRESH_HOURS})을 실제 값에 적용하면")
    for r in (1242, 1243, 1244):
        raw = marketing_db.get_pattern_recorded_at(r)
        if not raw:
            print(f"  {r}회차: 기록 없음 → 실패로 닫힘 ✓")
            continue
        dt = datetime.fromisoformat(str(raw))
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        age = datetime.now() - dt
        verdict = "통과" if abs(age) <= FRESH else "실패(지난주 잔여물로 판정)"
        print(f"  {r}회차: {age.total_seconds() / 3600:+.1f}시간 전 생성 → {verdict}")

    print("\n" + "=" * 92)
    print("진짜 게이트 코드 경로(weekly_backup_cleanup.pool_gate)를 지금 실 DB로 실행")
    ok, detail = wbc.pool_gate()
    print(f"  {'통과' if ok else '실패'} · {detail}")
    print("  (오늘 13:30 Actions가 1244를 생성하면 그때부터 통과로 바뀌어야 한다 — 그게 조립 확인)")
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
