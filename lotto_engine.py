import itertools
from collections import defaultdict

import pandas as pd

PREV_WINNING_NUMS = {1, 10, 23, 29, 33, 37}

PREV_NEIGHBORS = set()
for n in PREV_WINNING_NUMS:
    PREV_NEIGHBORS.add(n)
    if n > 1:
        PREV_NEIGHBORS.add(n - 1)
    if n < 45:
        PREV_NEIGHBORS.add(n + 1)

TWIN_NUMS = {11, 22, 33, 44}

# 소자배 독립 세트 (교집합 버그 방지)
PRIMES = {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43}
MULT3 = {6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36, 39, 42, 45}
NATURALS = {1, 4, 8, 10, 14, 16, 20, 22, 25, 26, 28, 32, 34, 35, 38, 40, 44}


def _parse_targets(cell) -> set[int]:
    targets = set()
    for x in str(cell).split(","):
        if x.strip().isdigit():
            targets.add(int(x.strip()))
    return targets


def prep_set_filters(df) -> list[dict]:
    """기본/특수/고급필터: 조합 번호와 입력데이터 교집합 개수."""
    processed = []
    if not isinstance(df, pd.DataFrame):
        return processed
    for _, row in df.iterrows():
        targets = _parse_targets(row["입력데이터"])
        if not targets:
            continue
        processed.append(
            {
                "targets": targets,
                "min": int(float(row["최소"])),
                "max": int(float(row["최대"])),
            }
        )
    return processed


def prep_interval_filters(df) -> dict[int, list[dict]]:
    """이격수: I열 볼 절대수(1~45) — 해당 볼이 조합에 있을 때 J 간격 집합 검사."""
    grouped: dict[int, list[dict]] = defaultdict(list)
    if not isinstance(df, pd.DataFrame):
        return grouped
    for _, row in df.iterrows():
        label = str(row["구분"]).strip()
        if not label.isdigit():
            continue
        number = int(label)
        if not (1 <= number <= 45):
            continue
        targets = _parse_targets(row["입력데이터"])
        if not targets:
            continue
        grouped[number].append(
            {
                "targets": targets,
                "min": int(float(row["최소"])),
                "max": int(float(row["최대"])),
            }
        )
    return grouped


def prep_absolute_filters(df) -> dict[int, list[dict]]:
    """절대: 구분(1~45) 번호별 규칙 — 조합에 포함된 번호에만 적용."""
    grouped: dict[int, list[dict]] = defaultdict(list)
    if not isinstance(df, pd.DataFrame):
        return grouped
    for _, row in df.iterrows():
        label = str(row["구분"]).strip()
        if not label.isdigit():
            continue
        number = int(label)
        if not (1 <= number <= 45):
            continue
        targets = _parse_targets(row["입력데이터"])
        if not targets:
            continue
        grouped[number].append(
            {
                "targets": targets,
                "min": int(float(row["최소"])),
                "max": int(float(row["최대"])),
            }
        )
    return grouped


def combo_gaps(combo) -> list[int]:
    """정렬된 6조합 사이 5개 간격 (인접 번호 차이)."""
    return [combo[i + 1] - combo[i] for i in range(5)]


def passes_set_filters(combo_set: set[int], rules: list[dict]) -> bool:
    for rule in rules:
        count = len(combo_set & rule["targets"])
        if not (rule["min"] <= count <= rule["max"]):
            return False
    return True


def passes_interval_filters(combo, grouped_rules: dict[int, list[dict]]) -> bool:
    """I=볼 절대수: 조합에 그 볼이 있을 때 5간격 중 J 간격값 매칭 개수."""
    gaps = combo_gaps(combo)
    combo_set = set(combo)
    for number in combo_set:
        for rule in grouped_rules.get(number, ()):
            count = sum(1 for g in gaps if g in rule["targets"])
            if not (rule["min"] <= count <= rule["max"]):
                return False
    return True


def passes_absolute_filters(combo_set: set[int], grouped_rules: dict[int, list[dict]]) -> bool:
    for number in combo_set:
        for rule in grouped_rules.get(number, ()):
            count = len(combo_set & rule["targets"])
            if not (rule["min"] <= count <= rule["max"]):
                return False
    return True


def passes_three_sheet_filters(
    combo,
    basic_rules: list[dict],
    interval_rules: dict[int, list[dict]],
    absolute_rules: dict[int, list[dict]],
) -> bool:
    """운영자 3종 엑셀 필터 (기본 → 절대 → 이격) 통합 검증."""
    combo_set = set(combo)

    if basic_rules and not passes_set_filters(combo_set, basic_rules):
        return False
    if absolute_rules and not passes_absolute_filters(combo_set, absolute_rules):
        return False
    if interval_rules and not passes_interval_filters(combo, interval_rules):
        return False
    return True


def passes_four_sheet_filters(
    combo,
    basic_rules: list[dict],
    special_rules: list[dict],
    interval_rules: dict[int, list[dict]],
    absolute_rules: dict[int, list[dict]],
) -> bool:
    """하위 호환 — special은 더 이상 사용하지 않음."""
    del special_rules
    return passes_three_sheet_filters(combo, basic_rules, interval_rules, absolute_rules)


def run_admin_three_filter_staged(
    filters_data,
    progress_callback=None,
) -> tuple[list[list[int]], dict[str, int]]:
    """
    운영자 3종 전용 3단계 파이프라인.
    ① 기본 (볼 교집합) → ② 절대 (I 볼) → ③ 이격 (I 볼 + 5간격).
    특수필터 시트는 사용하지 않음.
    """
    from filter_sheet_validation import normalize_three_filter_data

    filters_data = normalize_three_filter_data(filters_data)
    basic_rules = prep_set_filters(filters_data.get("basic"))
    absolute_rules = prep_absolute_filters(filters_data.get("absolute"))
    interval_rules = prep_interval_filters(filters_data.get("interval"))

    total_combos = 8_145_060
    scanned = 0
    stage1: list[list[int]] = []

    for combo in itertools.combinations(range(1, 46), 6):
        scanned += 1
        if progress_callback is not None and scanned % 200_000 == 0:
            progress_callback(scanned, total_combos, "stage1_basic")

        combo_set = set(combo)
        if basic_rules and not passes_set_filters(combo_set, basic_rules):
            continue
        stage1.append(list(combo))

    stats = {
        "total_pool": total_combos,
        "stage1_basic": len(stage1),
    }

    stage2: list[list[int]] = []
    for idx, combo in enumerate(stage1):
        if progress_callback is not None and idx and idx % 50_000 == 0:
            progress_callback(idx, len(stage1), "stage2_absolute")
        if absolute_rules and not passes_absolute_filters(set(combo), absolute_rules):
            continue
        stage2.append(combo)
    stats["stage2_absolute"] = len(stage2)

    stage3: list[list[int]] = []
    for idx, combo in enumerate(stage2):
        if progress_callback is not None and idx and idx % 50_000 == 0:
            progress_callback(idx, len(stage2), "stage3_interval")
        if interval_rules and not passes_interval_filters(tuple(combo), interval_rules):
            continue
        stage3.append(combo)
    stats["stage3_interval"] = len(stage3)

    if progress_callback is not None:
        progress_callback(total_combos, total_combos, "done")

    return stage3, stats


run_admin_four_filter_staged = run_admin_three_filter_staged


def run_filtering_engine(
    filters_data,
    premium_settings=None,
    progress_callback=None,
    apply_premium_patterns=True,
    apply_builtin_gates=True,
):
    results = []
    if premium_settings is None:
        premium_settings = {}

    min_sum = premium_settings.get("최소총합", 70)
    max_sum = premium_settings.get("최대총합", 205)
    start_hot = premium_settings.get("시작번호", 1)
    end_hot = premium_settings.get("끝번호", 45)

    allowed_odd_even = set(
        premium_settings.get("Camp 비율", premium_settings.get("홀짝 비율", []))
    )
    allowed_low_high = set(premium_settings.get("저고 비율", []))
    allowed_twins = set(premium_settings.get("쌍둥이수", []))
    allowed_carry = set(premium_settings.get("이월수", []))
    allowed_neighbor = set(premium_settings.get("이웃수", []))
    allowed_same_ends = set(premium_settings.get("쌍끝수", []))
    allowed_consec = set(premium_settings.get("연속번호", []))

    allowed_colors = set(premium_settings.get("볼 색상 수", []))
    if "모든" in allowed_colors:
        allowed_colors.add("5")

    so_min, so_max = premium_settings.get("소수", (0, 6))
    ja_min, ja_max = premium_settings.get("자연수", (0, 6))
    ba_min, ba_max = premium_settings.get("3배수", (0, 6))

    t1_min, t1_max = premium_settings.get("1_9", (0, 6))
    t10_min, t10_max = premium_settings.get("10_19", (0, 6))
    t20_min, t20_max = premium_settings.get("20_29", (0, 6))
    t30_min, t30_max = premium_settings.get("30_39", (0, 6))
    t40_min, t40_max = premium_settings.get("40_45", (0, 6))

    from filter_sheet_validation import normalize_three_filter_data

    filters_data = normalize_three_filter_data(filters_data)
    basic_rules = prep_set_filters(filters_data.get("basic"))
    interval_rules = prep_interval_filters(filters_data.get("interval"))
    absolute_rules = prep_absolute_filters(filters_data.get("absolute"))
    has_three_sheet_filters = bool(
        basic_rules or interval_rules or absolute_rules
    )

    total_combos = 8145060
    count = 0

    for combo in itertools.combinations(range(1, 46), 6):
        count += 1

        if progress_callback is not None and count % 200000 == 0:
            progress_callback(count, total_combos)

        if apply_builtin_gates:
            if combo[0] < start_hot:
                continue
            if combo[5] > end_hot:
                continue
            if not (min_sum <= sum(combo) <= max_sum):
                continue

            p_cnt = sum(1 for x in combo if x in PRIMES)
            b_cnt = sum(1 for x in combo if x in MULT3)
            j_cnt = sum(1 for x in combo if x in NATURALS)

            if not (so_min <= p_cnt <= so_max):
                continue
            if not (ba_min <= b_cnt <= ba_max):
                continue
            if not (ja_min <= j_cnt <= ja_max):
                continue

            t_cnt = [0, 0, 0, 0, 0]
            for x in combo:
                if x <= 9:
                    t_cnt[0] += 1
                elif x <= 19:
                    t_cnt[1] += 1
                elif x <= 29:
                    t_cnt[2] += 1
                elif x <= 39:
                    t_cnt[3] += 1
                else:
                    t_cnt[4] += 1

            if not (t1_min <= t_cnt[0] <= t1_max):
                continue
            if not (t10_min <= t_cnt[1] <= t10_max):
                continue
            if not (t20_min <= t_cnt[2] <= t20_max):
                continue
            if not (t30_min <= t_cnt[3] <= t30_max):
                continue
            if not (t40_min <= t_cnt[4] <= t40_max):
                continue

        if apply_premium_patterns:
            combo_set = set(combo)
            odd_cnt = sum(1 for x in combo if x % 2 != 0)
            if f"{odd_cnt}:{6 - odd_cnt}" not in allowed_odd_even:
                continue

            low_cnt = sum(1 for x in combo if x <= 23)
            if f"{low_cnt}:{6 - low_cnt}" not in allowed_low_high:
                continue

            if str(len(combo_set & TWIN_NUMS)) not in allowed_twins:
                continue
            if str(len(combo_set & PREV_WINNING_NUMS)) not in allowed_carry:
                continue
            if str(len(combo_set & PREV_NEIGHBORS)) not in allowed_neighbor:
                continue

            ends = [x % 10 for x in combo]
            end_counts = [ends.count(i) for i in set(ends)]
            pair_end_cnt = sum(1 for c in end_counts if c >= 2)
            if f"{pair_end_cnt}개" not in allowed_same_ends:
                continue

            colors = set()
            for x in combo:
                if x <= 10:
                    colors.add(1)
                elif x <= 20:
                    colors.add(2)
                elif x <= 30:
                    colors.add(3)
                elif x <= 40:
                    colors.add(4)
                else:
                    colors.add(5)
            if str(len(colors)) not in allowed_colors:
                continue

            max_consec = 1
            current_consec = 1
            for i in range(1, 6):
                if combo[i] == combo[i - 1] + 1:
                    current_consec += 1
                    if current_consec > max_consec:
                        max_consec = current_consec
                else:
                    current_consec = 1

            consec_str = "없음"
            if max_consec == 2:
                consec_str = "2연번"
            elif max_consec == 3:
                consec_str = "3연번"
            elif max_consec >= 4:
                consec_str = "4연번"
            if consec_str not in allowed_consec:
                continue

        if has_three_sheet_filters and not passes_three_sheet_filters(
            combo, basic_rules, interval_rules, absolute_rules
        ):
            continue

        results.append(list(combo))

    if progress_callback is not None:
        progress_callback(total_combos, total_combos)

    return results


def run_step2_filtering(combinations_df, filter_rules):
    """[2단계 전용] 1단계 통과 조합에 고급필터(교집합) 규칙 적용."""
    final_results = []
    combos = combinations_df.values.tolist()

    for combo in combos:
        combo_set = set(map(int, combo))
        if passes_set_filters(combo_set, filter_rules):
            final_results.append(combo)

    return pd.DataFrame(final_results, columns=[f"번호{i + 1}" for i in range(6)])
