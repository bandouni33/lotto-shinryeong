"""로또최근당첨내역.xlsb 기반 통계 집계 (과거 데이터 사실 기반)."""

from collections import Counter

import pandas as pd

DATA_FILE = "로또최근당첨내역.xlsb"
DATA_START_ROW = 4  # 0-indexed, 헤더(3행) 다음부터 1회차
COL_DRAW = 1
COL_NUM_START = 3
COL_NUM_END = 9
COL_AC = 11


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


def compute_all_stats(filepath: str = DATA_FILE) -> dict:
    data = load_lotto_data(filepath)
    latest = get_latest_draw_stats(data)
    hot = calc_hot_numbers(data, 10)
    cold = calc_cold_numbers(data, 15)
    carry = calc_carryover_in_last_n(data, 5)
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
    }
