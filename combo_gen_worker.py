"""1241회차부터: 1차+2차+4차 필터 조합을 매주 자동 생성해 lotto_combinations에
적재하는 백그라운드 워커. filter_worker.py와 같은 패턴(서브프로세스로 실행,
상태를 파일+app_settings에 기록) — Streamlit 요청-응답 안에서 처리하기엔
83만개 조합 계산이 너무 오래 걸려서(3~5분) 별도 프로세스로 뺀다.

app.py 쪽 트리거가 새 회차 감지 후 이 스크립트를 subprocess.Popen으로 띄운다.
subprocess로 뜰 때는 부모(Streamlit) 프로세스가 이미 app.py 맨 위에서
load_dotenv_file()을 호출해둔 환경변수(os.environ)를 그대로 물려받아서 문제가
없었는데, 2026-09-20에 이 스크립트를 터미널에서 단독 실행(수동 실행)해보니
그 부모 프로세스가 없어 TURSO_DATABASE_URL/TURSO_AUTH_TOKEN이 비어
RuntimeError가 났다 — app.py·check_real_toss_charges.py 등 기존 단독 실행
스크립트들과 동일하게 이 파일도 자체적으로 .env를 로드하도록 아래 두 줄을
추가한다(이미 환경변수가 설정돼 있으면 override=False라 아무 영향 없음 —
subprocess로 뜨는 기존 자동 실행 경로는 그대로 안전).
"""

from __future__ import annotations

import csv
import json
import math
import os
import random
import sys
import traceback

from env_loader import load_dotenv_file

load_dotenv_file()

STATUS_FILE = os.path.join(os.path.dirname(__file__), "combo_gen_job.status")

# 2026-09-07 확정(2026-09-05 값 1.5%에서 정정), 2026-09-13 재정정(10%→5%,
# 사용자 지시 — 4차 조건이 top3→top6/상중하1~4로 바뀌며 통과 풀 크기 자체가
# 달라져서 비율을 다시 낮춤): 필터 통과 조합 전체(80만~120만개대)를 다
# 저장하지 않고, 실제 판매/배포용으로는 5%만 무작위 추출해서 저장한다.
# 실제 추출 수량 자체는 비공개 방침이라 사용자 화면(자동구매 하단 표)에는
# 노출하지 않는다(2026-09-07, "추출수량" 열 제거). "적용패턴수"는 실제 사용한
# 규칙 개수(1차 381 + 2차 48 + 4차 조건 2 = 431)의 15배로 고정 표시(=6,465)
# — 조합 개수와 무관한 별도 값.
EXTRACT_RATE = 0.05
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


def save_full_stage4_pool(target_round: int, combos: list[tuple[int, ...]]) -> str:
    """2026-09-08 신규: 4차 필터 통과 조합 전체(80만개대, 10% 추출 전 원본
    풀) — 추첨 후 "당첨번호에 1~2위 예측이 포함됐는지" 확인하는 이벤트
    기능(스펙 확정 예정)에 쓸 데이터. 용량이 크므로(회차당 80만행 안팎)
    DB가 아니라 로컬 파일로만 남긴다. 사용자 지시대로 "최근 1회차만 보관,
    지나면 폐기" — 영구 보관 대상이 아니라 매 회차 생성 시
    cleanup_old_full_stage4_pools()가 이전 회차분을 자동으로 지운다."""
    folder = os.path.join(os.path.dirname(__file__), f"{target_round}회차")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "4차필터_전체풀.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["num1", "num2", "num3", "num4", "num5", "num6"])
        for combo in combos:
            writer.writerow(list(combo))
    return path


def delete_full_stage4_pool(target_round: int) -> bool:
    """save_full_stage4_pool()로 남긴 대용량 파일을 지운다."""
    path = os.path.join(os.path.dirname(__file__), f"{target_round}회차", "4차필터_전체풀.csv")
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def cleanup_old_full_stage4_pools(keep_round: int) -> list[int]:
    """2026-09-08 확정(사용자 지정): 4차 전체풀 파일은 "최근 1회차만 보관,
    지나면 폐기" — keep_round(이번에 새로 저장한 회차)보다 오래된 회차의
    "{회차}회차/4차필터_전체풀.csv"를 전부 지운다. 축하배너 이벤트가 아직
    없어도(추후 스펙 확정 예정) 매주 새 회차 생성 시점에 자동으로 정리되게
    해서 대용량 파일이 계속 쌓이지 않게 한다. "조합_확인용.csv"(배포 샘플,
    용량이 훨씬 작음)는 이 정리 대상이 아니다 — 건드리지 않는다."""
    base = os.path.dirname(__file__)
    removed: list[int] = []
    for name in os.listdir(base):
        if not name.endswith("회차"):
            continue
        round_str = name[: -len("회차")]
        if not round_str.isdigit():
            continue
        round_num = int(round_str)
        if round_num >= keep_round:
            continue
        path = os.path.join(base, name, "4차필터_전체풀.csv")
        if os.path.exists(path):
            os.remove(path)
            removed.append(round_num)
    return removed


# 2026-09-08 확정(사용자 지정, 여러 차례 재확인 후 최종 정리), 2026-09-13
# 재정정(사용자 지시 — top3→top5로 4차 조건이 완화되면서 기존 "3그룹
# 2:2:1" 불변식이 깨짐: top4·5위만 포함하고 top1~3위는 전혀 없는 조합도
# 이제 4차를 통과하므로, 3그룹만으로는 그런 조합을 분류할 곳이 없었음.
# 같은 날 중 top6도 검토했으나 배포단위(5개묶음)와 안 맞아떨어져 top5로
# 최종 확정 — 5개묶음에 5개 그룹이 각 1개씩 정확히 대응된다).
# 4차 필터 통과 조합(격차순위 1~5위 중 최소 1개 포함)은 이제 항상 아래
# 5단계 중 정확히 하나에만 속한다(서로 안 겹치고, 합치면 전체와 같음,
# 우선순위 1위>2위>...>5위):
#   1위그룹: 1위 숫자 포함(2~5위 포함 여부 무관)
#   2위그룹: 2위 숫자 포함, 1위는 제외
#   3위그룹: 3위 숫자 포함, 1·2위 제외
#   4위그룹: 4위 숫자 포함, 1~3위 제외
#   5위그룹: 5위 숫자 포함, 1~4위 제외(4차 조건상 이 시점엔 5위가 반드시
#            포함돼 있음)
# "5% 추출 방식은 배포방식(구매 시 배정 비율)과 동일한 사상을 따라야 한다"는
# 지시에 따라, 5개 그룹 각 20%씩(균등, 정수비 1:1:1:1:1)으로 강제 배분한다
# — 5개묶음 배포 시 "그룹당 정확히 1개"와 그대로 대응되는 비율. marketing_db.py의
# 배포(구매 시 배정) 로직과 반드시 같은 5단계 정의를 유지할 것 — 그룹 정의가
# 어긋나면 특정 그룹 조합이 배포 목록에 없거나 중복 분류되는 문제가 재발한다.
RANK_TIER_RATIO = (1, 1, 1, 1, 1)  # (1위,2위,3위,4위,5위그룹) = 각 20%


def _rank_tier(combo: tuple[int, ...], top5_numbers: tuple[int, int, int, int, int]) -> int:
    """combo가 1위그룹(0)~5위그룹(4) 중 어디에 속하는지."""
    combo_set = set(combo)
    for i, num in enumerate(top5_numbers):
        if num in combo_set:
            return i
    raise ValueError("4차 조건상 top1~5위 중 최소 1개는 반드시 포함돼야 함")


def extract_sample_by_rank_tier_ratio(
    combos: list[tuple[int, ...]], top5_numbers: tuple[int, int, int, int, int]
) -> list[tuple[int, ...]]:
    """전체 4차 통과 조합의 5%를 뽑아 5개 그룹에 RANK_TIER_RATIO(1:1:1:1:1
    = 각 20%)로 균등 배분한다 — 배포 시 5개묶음마다 5개 그룹 각 1개씩을
    소진하는 것과 정확히 같은 비율로 미리 저장해둬야, 어느 한쪽 그룹만
    먼저 바닥나지 않는다."""
    groups: list[list] = [[] for _ in range(5)]
    for combo in combos:
        groups[_rank_tier(combo, top5_numbers)].append(combo)

    total_target = math.floor(len(combos) * EXTRACT_RATE)
    ratio_sum = sum(RANK_TIER_RATIO)
    unit, leftover = divmod(total_target, ratio_sum)
    # 나머지는 비율이 큰 그룹부터 1개씩 얹는다(정확히 나눠떨어지지 않을 때의 방어적 처리).
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

        # 2026-09-20 신규: 830만개 조합 계산(수동 실행 시 최대 30분+) 전에
        # 먼저 "이미 저장됐는지" 저비용으로 확인한다 — 1243회차를 수동
        # 재확인하는 과정에서, 이미 저장된 회차를 재실행할 때마다 스킵
        # 여부를 알기도 전에 매번 무거운 재계산을 반복하는 게 실측
        # 확인됐다. peek_target_round()는 generate_next_round_combos()와
        # 동일한 방식으로 target_round만 계산하고 계산 자체는 하지 않는다.
        # 계산 완료 후의 기존 체크(아래)는 동시 실행(레이스 컨디션) 대비로
        # 그대로 남겨둔다 — 안전장치 이중화, 기존 동작 변화 없음.
        early_target_round = combo_filter_v2.peek_target_round(history)
        already_early = marketing_db.get_combination_count_by_draw(early_target_round)
        if already_early > 0:
            write_status(
                "skipped",
                message=f"{early_target_round}회차는 이미 {already_early}개 등록돼 있어 건너뜀(계산 전 확인)",
                target_round=early_target_round,
            )
            return 0

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

        # 2026-09-13(사용자 지시, top3→top5 최종 확정): 추출도 배포와 동일하게
        # top5_numbers 기준 5단계로 한다(위 함수 참고).
        sample = extract_sample_by_rank_tier_ratio(combos, stats["top5_numbers"])
        sample_size = len(sample)
        inserted = marketing_db.bulk_insert_lotto_combinations(
            target_round, sample, top5_numbers=stats.get("top5_numbers")
        )
        marketing_db.record_draw_pattern_count(target_round, PATTERN_COUNT_DISPLAY)
        marketing_db.record_draw_generation_stats(
            target_round, stats["stage2_count"], stats["final_count"], stats["top5_numbers"]
        )
        local_copy_path = save_local_verification_copy(target_round, sample)
        full_pool_path = save_full_stage4_pool(target_round, combos)
        cleaned_full_pools = cleanup_old_full_stage4_pools(target_round)

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
            full_stage4_pool=full_pool_path,
            cleaned_full_pool_rounds=cleaned_full_pools,
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
