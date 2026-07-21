"""로또최근당첨내역.xlsb 기반 통계 집계 (과거 데이터 사실 기반)."""

from collections import Counter

import pandas as pd

DATA_FILE = "로또최근당첨내역.xlsb"
DATA_START_ROW = 4  # 0-indexed, 헤더(3행) 다음부터 1회차
COL_DRAW = 1
COL_NUM_START = 3
COL_NUM_END = 9
COL_AC = 11

PATTERN_DEFAULT_N = 20
DECADE_BANDS = (
    ("1번대", 1, 9),
    ("10번대", 10, 19),
    ("20번대", 20, 29),
    ("30번대", 30, 39),
    ("40번대", 40, 45),
)


def load_lotto_data(filepath: str = DATA_FILE) -> pd.DataFrame:
    df = pd.read_excel(filepath, engine="pyxlsb", header=None)
    return df.iloc[DATA_START_ROW:].reset_index(drop=True)


def _draw_numbers(row) -> list[int]:
    nums = []
    for i in range(COL_NUM_START, COL_NUM_END):
        val = pd.to_numeric(row[i], errors="coerce")
        if pd.notna(val):
            nums.append(int(val))
    return sorted(nums)


def calc_cold_numbers(data: pd.DataFrame, recent_n: int = 15) -> list[int]:
    """최근 N회차 1~6구에 한 번도 안 나온 번호."""
    recent = data.iloc[0:recent_n, COL_NUM_START:COL_NUM_END]
    recent_nums = set(
        int(x)
        for x in recent.values.flatten()
        if pd.notna(pd.to_numeric(x, errors="coerce"))
    )
    return sorted(set(range(1, 46)) - recent_nums)


def calc_hot_numbers(data: pd.DataFrame, top_n: int = 10) -> list[tuple[int, int]]:
    """전체 회차 1~6구 등장 횟수 상위 N개 (번호, 횟수)."""
    all_nums = data.iloc[:, COL_NUM_START:COL_NUM_END].apply(pd.to_numeric, errors="coerce")
    counts = Counter(
        int(x) for x in all_nums.values.flatten() if pd.notna(x)
    )
    return counts.most_common(top_n)


def get_latest_draw_stats(data: pd.DataFrame) -> dict:
    """최신 회차: 회차번호, 당첨번호, 총합, AC값(파일 값 그대로)."""
    row = data.iloc[0]
    numbers = _draw_numbers(row)
    draw_no = int(float(row[COL_DRAW]))
    ac_raw = row[COL_AC] if len(row) > COL_AC else None
    ac_val = int(ac_raw) if pd.notna(pd.to_numeric(ac_raw, errors="coerce")) else ac_raw
    return {
        "draw_no": draw_no,
        "numbers": numbers,
        "sum": sum(numbers) if len(numbers) == 6 else 0,
        "ac": ac_val,
    }


def calc_carryover_in_last_n(data: pd.DataFrame, n: int = 5) -> dict:
    """
    이월수: 직전 회차 당첨번호가 이번 회차에도 1개 이상 포함된 경우.
    최근 n회(최신 회차 포함) 각각에 대해 직전 회차와 비교해 출현 횟수를 센다.
    """
    details = []
    count = 0
    limit = min(n, len(data) - 1)
    for i in range(limit):
        curr_draw = int(float(data.iloc[i][COL_DRAW]))
        prev_draw = int(float(data.iloc[i + 1][COL_DRAW]))
        curr_set = set(_draw_numbers(data.iloc[i]))
        prev_set = set(_draw_numbers(data.iloc[i + 1]))
        overlap = sorted(curr_set & prev_set)
        has_carry = len(overlap) >= 1
        if has_carry:
            count += 1
        details.append(
            {
                "draw": curr_draw,
                "prev_draw": prev_draw,
                "overlap": overlap,
                "has_carry": has_carry,
            }
        )
    return {"count": count, "checked": limit, "details": details}


def _pattern_draw_limit(data: pd.DataFrame, n: int) -> int:
    return min(n, len(data))


def calc_odd_even_pattern(data: pd.DataFrame, n: int = PATTERN_DEFAULT_N) -> dict:
    """최근 N회 각 회차의 홀/짝 개수 조합 빈도."""
    limit = _pattern_draw_limit(data, n)
    combo_counts: Counter[tuple[int, int]] = Counter()
    for i in range(limit):
        nums = _draw_numbers(data.iloc[i])
        odds = sum(1 for x in nums if x % 2 == 1)
        evens = len(nums) - odds
        combo_counts[(odds, evens)] += 1
    top_combo, top_count = combo_counts.most_common(1)[0]
    return {
        "checked": limit,
        "top_odds": top_combo[0],
        "top_evens": top_combo[1],
        "top_count": top_count,
        "distribution": dict(combo_counts),
    }


def calc_low_high_pattern(data: pd.DataFrame, n: int = PATTERN_DEFAULT_N) -> dict:
    """최근 N회 각 회차의 저(1~22)/고(23~45) 개수 조합 빈도."""
    limit = _pattern_draw_limit(data, n)
    combo_counts: Counter[tuple[int, int]] = Counter()
    for i in range(limit):
        nums = _draw_numbers(data.iloc[i])
        low = sum(1 for x in nums if 1 <= x <= 22)
        high = len(nums) - low
        combo_counts[(low, high)] += 1
    top_combo, top_count = combo_counts.most_common(1)[0]
    return {
        "checked": limit,
        "top_low": top_combo[0],
        "top_high": top_combo[1],
        "top_count": top_count,
        "distribution": dict(combo_counts),
    }


def _count_in_band(nums: list[int], lo: int, hi: int) -> int:
    return sum(1 for x in nums if lo <= x <= hi)


def calc_decade_pattern(data: pd.DataFrame, n: int = PATTERN_DEFAULT_N) -> dict:
    """
    10단위 구간(1~9, 10~19, 20~29, 30~39, 40~45) 분포.
    최신 회차부터 연속 0출현(전멸)이 2회 이상인 구간만 경고로 반환.
    """
    limit = _pattern_draw_limit(data, n)
    per_draw: list[dict[str, int]] = []
    band_totals: Counter[str] = Counter()

    for i in range(limit):
        nums = _draw_numbers(data.iloc[i])
        row_counts: dict[str, int] = {}
        for band_name, lo, hi in DECADE_BANDS:
            count = _count_in_band(nums, lo, hi)
            row_counts[band_name] = count
            band_totals[band_name] += count
        per_draw.append(row_counts)

    warnings = []
    for band_name, lo, hi in DECADE_BANDS:
        streak = 0
        for row_counts in per_draw:
            if row_counts[band_name] == 0:
                streak += 1
            else:
                break
        if streak >= 2:
            warnings.append(
                {
                    "band": band_name,
                    "range": f"{lo}~{hi}",
                    "streak": streak,
                }
            )

    return {
        "checked": limit,
        "warnings": warnings,
        "band_totals": dict(band_totals),
    }


def calc_last_digit_pattern(data: pd.DataFrame, n: int = PATTERN_DEFAULT_N) -> dict:
    """최근 N회 당첨번호 일의 자리(0~9) 출현 빈도."""
    limit = _pattern_draw_limit(data, n)
    digit_counts: Counter[int] = Counter()
    for i in range(limit):
        nums = _draw_numbers(data.iloc[i])
        for num in nums:
            digit_counts[num % 10] += 1
    top_digit, top_count = digit_counts.most_common(1)[0]
    return {
        "checked": limit,
        "top_digit": top_digit,
        "top_count": top_count,
        "distribution": dict(digit_counts),
    }


def compute_pattern_stats(data: pd.DataFrame, n: int = PATTERN_DEFAULT_N) -> dict:
    return {
        "basis_n": n,
        "odd_even": calc_odd_even_pattern(data, n),
        "low_high": calc_low_high_pattern(data, n),
        "decade": calc_decade_pattern(data, n),
        "last_digit": calc_last_digit_pattern(data, n),
    }


def compute_all_stats(filepath: str = DATA_FILE) -> dict:
    data = load_lotto_data(filepath)
    latest = get_latest_draw_stats(data)
    hot = calc_hot_numbers(data, 10)
    cold = calc_cold_numbers(data, 15)
    carry = calc_carryover_in_last_n(data, 5)
    pattern = compute_pattern_stats(data, PATTERN_DEFAULT_N)
    first_draw = int(float(data.iloc[-1][COL_DRAW]))
    last_draw = latest["draw_no"]
    return {
        "total_draws": len(data),
        "draw_range": (first_draw, last_draw),
        "latest": latest,
        "hot": hot,
        "cold": cold,
        "cold_basis_n": 15,
        "carry": carry,
        "pattern": pattern,
    }


# ── 번개조합 자연스러움 필터 (역대 당첨 데이터 기반) ──
THUNDER_FILTER_MAX_CONSECUTIVE = 4   # 3연번까지 허용, 4연번+ 재추첨 (역대 ~0.49%)
THUNDER_FILTER_MAX_DECADE = 4        # 동일 10단위 4개+ 재추첨 (역대 ~5.76%)
THUNDER_FILTER_MAX_LAST_DIGIT = 3    # 동일 끝수 3개+ 재추첨 (역대 ~8.28%)
THUNDER_FILTER_MAX_RETRIES = 100


def _longest_consecutive_run(nums: list[int]) -> int:
    if not nums:
        return 0
    sorted_nums = sorted(nums)
    best = cur = 1
    for i in range(1, len(sorted_nums)):
        if sorted_nums[i] == sorted_nums[i - 1] + 1:
            cur += 1
            best = max(best, cur)
        else:
            cur = 1
    return best


def _max_decade_count(nums: list[int]) -> int:
    best = 0
    for _, lo, hi in DECADE_BANDS:
        best = max(best, sum(1 for x in nums if lo <= x <= hi))
    return best


def _max_last_digit_count(nums: list[int]) -> int:
    if not nums:
        return 0
    return max(Counter(x % 10 for x in nums).values())


def analyze_thunder_filter_rates(filepath: str = DATA_FILE) -> dict:
    """역대 당첨번호 기준 부자연스러운 패턴 발생률 및 필터 임계값."""
    data = load_lotto_data(filepath)
    total = len(data)
    cons = {3: 0, 4: 0, 5: 0}
    band4 = band5 = 0
    digit3 = digit4 = 0

    for i in range(total):
        nums = _draw_numbers(data.iloc[i])
        run = _longest_consecutive_run(nums)
        if run >= 3:
            cons[3] += 1
        if run >= 4:
            cons[4] += 1
        if run >= 5:
            cons[5] += 1
        mb = _max_decade_count(nums)
        if mb >= 4:
            band4 += 1
        if mb >= 5:
            band5 += 1
        md = _max_last_digit_count(nums)
        if md >= 3:
            digit3 += 1
        if md >= 4:
            digit4 += 1

    pct = lambda n: round(100 * n / total, 3) if total else 0.0
    return {
        "total_draws": total,
        "thresholds": {
            "max_consecutive_run": THUNDER_FILTER_MAX_CONSECUTIVE,
            "max_decade_count": THUNDER_FILTER_MAX_DECADE,
            "max_last_digit_count": THUNDER_FILTER_MAX_LAST_DIGIT,
            "max_retries": THUNDER_FILTER_MAX_RETRIES,
        },
        "historical_rates": {
            "consecutive_ge_3": pct(cons[3]),
            "consecutive_ge_4": pct(cons[4]),
            "consecutive_ge_5": pct(cons[5]),
            "decade_ge_4": pct(band4),
            "decade_ge_5": pct(band5),
            "last_digit_ge_3": pct(digit3),
            "last_digit_ge_4": pct(digit4),
        },
    }


def get_thunder_filter_config(filepath: str = DATA_FILE) -> dict:
    """page_thunder.py JS 필터에 전달할 설정."""
    return analyze_thunder_filter_rates(filepath)


def get_marketing_win_rank_summary(draw_round: int) -> dict[int, int]:
    """익명 lotto_combinations 기준 회차별 1~5등 당첨 수량 (마케팅 집계)."""
    from marketing_db import get_win_rank_counts_by_draw, init_marketing_tables

    init_marketing_tables()
    return get_win_rank_counts_by_draw(int(draw_round))
