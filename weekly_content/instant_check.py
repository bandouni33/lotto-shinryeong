# -*- coding: utf-8 -*-
"""토요일 밤 '즉시 게시' 안전 확인 — 2026-10-17(사용자 지시: TV 추첨 캡처 → 공식 발표 기다리지 않고 바로 게시).

캡처에서 읽은 번호를 weekly_content/instant/<회차>.txt 에 한 줄로 넣고 push 하면
(.github/workflows/weekly_content.yml 의 push 트리거) 이 스크립트가:
  - 공식 값(DB 또는 동행복권)이 이미 있으면 대조 — 다르면 중단(2), 같고 DB에 없으면 반영
  - 아직 공식 발표 전이면(--now, 기본) 기다리지 않고 통과 → run_weekly --capture 가 캡처 번호로 제작·게시
    (캡처 번호는 DB에 넣지 않는다 — DB는 공식 값만. 정기 동기화 뒤 `--verify` 로 사후 대조, 다르면 실패 표시)

파일 형식: "1 2 3 4 5 6 + 7"   실행: python -m weekly_content.instant_check weekly_content/instant/1246.txt
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def parse(path: Path) -> tuple[int, list[int], int]:
    rnd = int(path.stem)
    nums = [int(x) for x in re.findall(r"\d+", path.read_text(encoding="utf-8"))]
    if len(nums) != 7 or len(set(nums)) != 7 or not all(1 <= n <= 45 for n in nums):
        raise SystemExit(f"[중단] 캡처 번호 형식 오류: {nums} (6개 + 보너스, 1~45, 중복 없음)")
    return rnd, sorted(nums[:6]), nums[6]


def check(path: Path, tries: int = 1, wait: float = 60, sleep=time.sleep, verify: bool = False) -> int:
    import draw_results_db as db

    rnd, nums, bonus = parse(path)
    db.init_draw_results_table()
    for i in range(1, tries + 1):
        local = {r["draw_round"]: r for r in db.get_all_draw_results()[:3]}
        if rnd in local:
            got = (sorted(local[rnd]["numbers"]), local[rnd]["bonus"])
            src = "DB"
        else:
            remote = db.fetch_latest_from_dhlottery()
            got = (sorted(remote["numbers"]), remote["bonus"]) if remote and remote["draw_round"] == rnd else None
            src = "동행복권"
        if got is not None:
            if got != (nums, bonus):
                print(f"[중단] {rnd}회 {src} 값 {got} ≠ 캡처 {(nums, bonus)} — 게시하지 않음")
                return 2
            if src == "동행복권":
                db.upsert_draw_result(rnd, nums, bonus)
            print(f"[확인] {rnd}회 {nums} + {bonus} — {src} 값과 캡처 일치")
            return 0
        if i < tries:
            print(f"  ({i}/{tries}) 동행복권에 {rnd}회 아직 미발표 — {wait:.0f}초 후 다시")
            sleep(wait)
    if verify:
        print(f"[대조 보류] {rnd}회 공식 값이 아직 없음 — 다음 정기 실행에서 다시 대조")
        return 0
    print(f"[진행] {rnd}회 공식 발표 전 — 캡처 번호 {nums} + {bonus} 로 바로 제작·게시(DB 미반영)")
    return 0


if __name__ == "__main__":
    import traceback
    try:
        code = check(Path(sys.argv[1]), verify="--verify" in sys.argv)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
        if not isinstance(e.code, int):
            print(e.code)
    except BaseException:
        traceback.print_exc()
        code = 1
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
