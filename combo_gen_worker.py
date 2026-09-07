"""1241회차부터: 1차+2차+4차 필터 조합을 매주 자동 생성해 lotto_combinations에
적재하는 백그라운드 워커. filter_worker.py와 같은 패턴(서브프로세스로 실행,
상태를 파일+app_settings에 기록) — Streamlit 요청-응답 안에서 처리하기엔
83만개 조합 계산이 너무 오래 걸려서(3~5분) 별도 프로세스로 뺀다.

app.py 쪽 트리거가 새 회차 감지 후 이 스크립트를 subprocess.Popen으로 띄운다.
"""

from __future__ import annotations

import csv
import json
import math
import os
import random
import sys
import traceback

STATUS_FILE = os.path.join(os.path.dirname(__file__), "combo_gen_job.status")

# 2026-09-07 확정(2026-09-05 값 1.5%에서 정정): 필터 통과 조합 전체(60~80만개대)를
# 다 저장하지 않고, 실제 판매/배포용으로는 10%만 무작위 추출해서 저장한다.
# 실제 추출 수량 자체는 비공개 방침이라 사용자 화면(자동구매 하단 표)에는
# 노출하지 않는다(2026-09-07, "추출수량" 열 제거). "적용패턴수"는 실제 사용한
# 규칙 개수(1차 381 + 2차 48 + 4차 조건 2 = 431)의 15배로 고정 표시(=6,465)
# — 조합 개수와 무관한 별도 값.
EXTRACT_RATE = 0.10
PATTERN_COUNT_DISPLAY = 431 * 15


def write_status(state: str, **extra) -> None:
    payload = {"state": state, **extra}
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


def save_local_verification_copy(target_round: int, sample: list[tuple[int, ...]]) -> str:
    """2026-09-07 신규: 배포용 저장본(Turso lotto_combinations)과 별개로,
    "확인용" 로컬 사본을 lotto-app 폴더 바로 밑에 회차별 폴더로 남긴다
    ("lotto-app폴더/1241회차… 회차별로" 요청). 배포에는 전혀 쓰이지 않는
    감사·검증 전용 스냅샷이라, git에는 안 올라가게 .gitignore로 막아둔다."""
    folder = os.path.join(os.path.dirname(__file__), f"{target_round}회차")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "조합_확인용.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["num1", "num2", "num3", "num4", "num5", "num6"])
        for combo in sample:
            writer.writerow(list(combo))
    return path


# 2026-09-08 확정(사용자 지정, 여러 차례 재확인 후 최종 정리): 4차 필터
# 통과 조합(격차순위 1~3위 중 최소 1개 포함)은 항상 아래 3개 그룹 중
# 정확히 하나에만 속한다(서로 안 겹치고, 합치면 전체와 같음):
#   1위그룹: 1위 숫자 포함(2·3위 포함 여부 무관)
#   2위그룹: 2위 숫자 포함, 1위는 제외
#   3위그룹: 3위 숫자 포함, 1·2위 둘 다 제외
# "10% 추출 방식은 배포방식(구매 시 배정 비율)과 동일해야 한다"는 지시에
# 따라, 세 그룹의 자연 비율이 아니라 배포 시 실제 소진 비율과 똑같은
# 2:2:1로 강제 배분한다 — marketing_db.RANK_TIER_RATIO와 반드시 같은 값을
# 유지할 것(둘 중 하나만 바뀌면 추출 비율과 배포 소진 비율이 어긋나서
# 특정 그룹만 먼저 바닥나는 문제가 재발한다).
RANK_TIER_RATIO = (2, 2, 1)  # (1위그룹, 2위그룹, 3위그룹)


def _rank_tier(combo: tuple[int, ...], top3_numbers: tuple[int, int, int]) -> int:
    """combo가 1위그룹(0)/2위그룹(1)/3위그룹(2) 중 어디에 속하는지."""
    rank1, rank2, rank3 = top3_numbers
    combo_set = set(combo)
    if rank1 in combo_set:
        return 0
    if rank2 in combo_set:
        return 1
    return 2  # 4차 조건상 이 시점엔 rank3가 반드시 포함돼 있음


def extract_sample_by_rank_tier_ratio(
    combos: list[tuple[int, ...]], top3_numbers: tuple[int, int, int]
) -> list[tuple[int, ...]]:
    """전체 4차 통과 조합의 10%를 뽑되, 1위/2위/3위그룹 자연 비율이 아니라
    RANK_TIER_RATIO(2:2:1)로 강제 배분한다 — 배포 시 5개 구매(1묶음)마다
    1위그룹 2개+2위그룹 2개+3위그룹 1개를 소진하는 것과 똑같은 비율로
    미리 저장해둬야, 어느 한쪽 그룹만 먼저 바닥나지 않는다."""
    groups: tuple[list, list, list] = ([], [], [])
    for combo in combos:
        groups[_rank_tier(combo, top3_numbers)].append(combo)

    total_target = math.floor(len(combos) * EXTRACT_RATE)
    ratio_sum = sum(RANK_TIER_RATIO)
    unit, leftover = divmod(total_target, ratio_sum)
    # 나머지는 비율이 큰 그룹부터 1개씩 얹는다(5의 배수가 아닐 때의 방어적 처리).
    targets = [unit * r for r in RANK_TIER_RATIO]
    order = sorted(range(len(RANK_TIER_RATIO)), key=lambda i: -RANK_TIER_RATIO[i])
    for i in range(leftover):
        targets[order[i % len(order)]] += 1

    sample: list = []
    for group, target in zip(groups, targets):
        n = min(target, len(group))
        sample.extend(random.sample(group, n) if n < len(group) else group)
    return sample


def main() -> int:
    write_status("running", pid=os.getpid())
    try:
        import combo_filter_v2
        import draw_results_db
        import marketing_db
        import wallet_db
        import app_settings

        draw_results_db.init_draw_results_table()
        app_settings.init_settings_table()

        history = draw_results_db.get_all_draw_results()
        target_round, combos, stats = combo_filter_v2.generate_next_round_combos(history)
        anchor_round = stats["anchor_round"]

        already = marketing_db.get_combination_count_by_draw(target_round)
        if already > 0:
            write_status(
                "skipped",
                message=f"{target_round}회차는 이미 {already}개 등록돼 있어 건너뜀",
                stats=stats,
            )
            return 0

        sample = extract_sample_by_rank_tier_ratio(combos, stats["top3_numbers"])
        sample_size = len(sample)
        inserted = marketing_db.bulk_insert_lotto_combinations(
            target_round, sample, top3_numbers=stats.get("top3_numbers")
        )
        marketing_db.record_draw_pattern_count(target_round, PATTERN_COUNT_DISPLAY)
        local_copy_path = save_local_verification_copy(target_round, sample)

        # 2026-09-06 버그 수정: 예전엔 anchor_round(방금 추첨된 회차) 이하를
        # 전부 즉시 삭제했는데, 이건 "최근 2회차까지는 보관"이라는 확립된
        # 규칙(guest_generated_combos에 이미 올바르게 구현돼 있던 것과 동일한
        # 규칙)을 어기고 있었다 — 그 결과 1237~1240회차 데이터가 복구
        # 불가능하게 삭제됨(실측 확인). cleanup_old_guest_generated_combos와
        # 똑같은 "최근 N개 회차만 보관" 함수로 교체한다.
        cleaned = marketing_db.cleanup_old_lotto_combinations(keep_rounds=2)

        # 번개조합/안티조합/액땜조합 저장분(guest_generated_combos)도 최근
        # 2회차만 남기고 정리 — 이 테이블은 지금까지 정리 로직이 없었다.
        cleaned_guest = marketing_db.cleanup_old_guest_generated_combos(keep_rounds=2)

        # 2026-09-07: 자동구매 주문(guest_auto_orders/auto_orders)도 같은
        # "최근 2회차만 보관" 규칙을 적용 — 이전엔 화면(page_auto.py)에서만
        # 최근 2회차로 잘라 보여줄 뿐 실제 행은 삭제되지 않고 계속 쌓이고
        # 있었다(자동구매/번개조합/안티·액땜조합 공통 4대 원칙 중 "최근
        # 2회차만 보관 후 자동삭제"를 자동구매만 어기고 있던 gap).
        cleaned_guest_auto_orders = marketing_db.cleanup_old_guest_auto_orders(keep_rounds=2)
        cleaned_auto_orders = wallet_db.cleanup_old_auto_orders(keep_rounds=2)

        # 방금 막 추첨된 anchor_round 자체의 "참고용 당첨가능 통계"를
        # 계산해서 기록 — 그 전주에 이 조합군이 어떻게 나왔을지 재현한 뒤
        # 이번에 나온 진짜 당첨번호와 대조한다(1241회부터만 의미 있음 —
        # 그 이전 회차는 이 방식으로 생성된 적이 없어 결과가 실제와 다름).
        ref_note = None
        if anchor_round >= 1241:
            ref = combo_filter_v2.compute_reference_stats(history, anchor_round)
            if ref is not None:
                pool_size, detail = ref
                marketing_db.set_reference_ranks(anchor_round, detail["ref_ranks"])
                ref_note = {"pool_size": pool_size, **detail}

        app_settings.set_setting("combo_gen_last_round", str(target_round))
        app_settings.set_setting("combo_gen_last_count", str(inserted))

        write_status(
            "done",
            target_round=target_round,
            inserted=inserted,
            sample_size=sample_size,
            cleaned_old_rows=cleaned,
            cleaned_guest_rows=cleaned_guest,
            cleaned_guest_auto_orders=cleaned_guest_auto_orders,
            cleaned_auto_orders=cleaned_auto_orders,
            local_verification_copy=local_copy_path,
            stats=stats,
            reference_stats_for_anchor=ref_note,
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        write_status("error", message=str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
