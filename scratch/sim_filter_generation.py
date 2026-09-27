# -*- coding: utf-8 -*-
"""다음회차 배포용 조합 생성 — 14시 워커(combo_gen_worker)와 **같은 계산 경로**를
DB 쓰기 없이 그대로 돌려보는 드라이런.

combo_gen_worker.main()이 실제로 하는 일:
    peek_target_round → (이미 있으면 스킵) → generate_next_round_combos
    → extract_sample_by_rank_tier_ratio(5%, 1~5위그룹 1:1:1:1:1)
    → bulk_insert_lotto_combinations ...
이 스크립트는 위 계산 단계 전부를 그대로 호출하고, 마지막 적재(쓰기)만 하지 않는다.

실행:
    venv312\\Scripts\\python.exe scratch\\sim_filter_generation.py
"""

from __future__ import annotations

import os
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import env_loader  # noqa: E402

env_loader.load_dotenv_file()


def main() -> int:
    import combo_filter_v2
    import combo_gen_worker
    import draw_results_db
    import marketing_db

    t0 = time.time()
    history = draw_results_db.get_all_draw_results()
    anchor = history[0]["draw_round"]
    target = combo_filter_v2.peek_target_round(history)
    print(f"[1] 당첨번호 {len(history)}건 읽음({time.time() - t0:.1f}s) — anchor={anchor}, target={target}")

    already = marketing_db.get_combination_count_by_draw(target)
    print(f"[2] DB에 이미 등록된 {target}회차 조합: {already:,}개 → "
          f"{'워커는 계산 전에 스킵한다' if already else '워커가 생성해야 한다(계산 시작)'}")

    t1 = time.time()
    target_round, combos, stats = combo_filter_v2.generate_next_round_combos(history)
    elapsed = time.time() - t1
    print(f"[3] 1차+2차+4차 필터 계산 완료 — {elapsed:.1f}초 (워커가 실제로 쓰는 시간)")
    print(f"    anchor_round={stats['anchor_round']}, target_round={stats['target_round']}")
    print(f"    1차+2차 통과={stats['static_gap_count']:,} → 2차(AUTO포함) 통과={stats['stage2_count']:,} "
          f"→ 4차 통과(전체풀)={stats['final_count']:,}")
    print(f"    top5_numbers={list(stats['top5_numbers'])} (top3={list(stats['top3_numbers'])})")

    t2 = time.time()
    sample = combo_gen_worker.extract_sample_by_rank_tier_ratio(combos, stats["top5_numbers"])
    print(f"[4] 5% 추출 완료 — {time.time() - t2:.1f}초")
    print(f"    EXTRACT_RATE={combo_gen_worker.EXTRACT_RATE}, RANK_TIER_RATIO={combo_gen_worker.RANK_TIER_RATIO}")
    print(f"    추출 조합 {len(sample):,}개 (전체의 {len(sample) / max(1, stats['final_count']) * 100:.2f}%)")

    full = Counter(combo_gen_worker._rank_tier(c, stats["top5_numbers"]) for c in combos)
    pick = Counter(combo_gen_worker._rank_tier(c, stats["top5_numbers"]) for c in sample)
    print("    그룹별 배분(4차 통과 전체 → 5% 추출):")
    for i in range(5):
        print(f"      {i + 1}위그룹: 전체 {full[i]:,}개 → 추출 {pick[i]:,}개 "
              f"({pick[i] / max(1, full[i]) * 100:.2f}%)")
    print(f"    (검증) 그룹 합 == 전체: {sum(full.values()) == len(combos)}, "
          f"추출 합 == 표본: {sum(pick.values()) == len(sample)}")
    print(f"    → 이번 주 판매 가능한 최대 '5개 묶음' 수 = 그룹별 최소 추출 수 = {min(pick.values()):,}묶음 "
          f"(5개묶음당 1~5위 각 1개씩 소진)")

    dup = len(sample) - len(set(sample))
    print(f"[5] 표본 중복 검사: 추출 {len(sample):,}개 중 고유 {len(set(sample)):,}개, 중복 {dup}개 (0이어야 정상)")
    print("[6] 여기까지가 워커의 계산 경로 전체 — 이 스크립트는 DB에 아무것도 쓰지 않았다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
