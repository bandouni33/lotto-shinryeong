# -*- coding: utf-8 -*-
"""토요일 밤 '즉시 게시' 안전 확인 — 2026-10-17(사용자 지시: 당첨번호 발표 즉시 캡처 → 바로 게시).

캡처에서 읽은 번호를 weekly_content/instant/<회차>.txt 에 한 줄로 넣고 push 하면
(.github/workflows/weekly_content.yml 의 push 트리거) 이 스크립트가:
  1) 동행복권 공식 최신 회차를 최대 25분(60초 간격) 기다려 가져오고
  2) 회차·번호·보너스가 캡처와 '완전히 같을 때만' DB에 반영한다(다르면 중단 — 잘못된 번호 게시 방지)
  3) 이미 DB에 있으면 DB 값과 대조만 한다.
캡처 번호는 확인용일 뿐 DB에 직접 넣지 않는다(공식 값만 반영).

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


def check(path: Path, tries: int = 25, wait: float = 60, sleep=time.sleep) -> int:
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
        print(f"  ({i}/{tries}) 동행복권에 {rnd}회 아직 미발표 — {wait:.0f}초 후 다시")
        sleep(wait)
    print(f"[중단] {rnd}회가 {tries}회 확인 동안 발표되지 않음 — 정기 실행(21:10·22:00·23:00)이 이어서 처리")
    return 1


if __name__ == "__main__":
    code = check(Path(sys.argv[1]))
    sys.stdout.flush()
    os._exit(code)
