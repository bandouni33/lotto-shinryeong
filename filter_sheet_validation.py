"""3종 필터 엑셀 → pkl 검증 (업로드 시)."""

from __future__ import annotations

import pandas as pd

SHEET_KEYS = ("basic", "absolute", "interval")
SHEET_LABELS = {
    "basic": "기본필터",
    "absolute": "절대필터",
    "interval": "이격수필터",
}

EMPTY_FILTER_COLUMNS = ["그룹명", "구분", "입력데이터", "최소", "최대"]


def normalize_three_filter_data(filters_data: dict) -> dict:
    """pkl/엑셀 → 3종(basic, absolute, interval)만. 특수필터(special)는 무시."""
    out: dict = {}
    for key in SHEET_KEYS:
        df = filters_data.get(key)
        if isinstance(df, pd.DataFrame):
            out[key] = df
        else:
            out[key] = pd.DataFrame(columns=EMPTY_FILTER_COLUMNS)
    return out


def _parse_targets(cell) -> set[int]:
    targets: set[int] = set()
    for part in str(cell).split(","):
        if part.strip().isdigit():
            targets.add(int(part.strip()))
    return targets


def _validate_ball_targets(sheet_key: str, row_idx: int, targets: set[int]) -> list[str]:
    bad = [n for n in targets if n < 1 or n > 45]
    if not bad:
        return []
    return [
        f"{SHEET_LABELS[sheet_key]} {row_idx}행 J열: 볼 번호는 1~45만 허용 (오류: {sorted(bad)[:8]})"
    ]


def _validate_gap_targets(sheet_key: str, row_idx: int, targets: set[int]) -> list[str]:
    bad = [n for n in targets if n < 1 or n > 44]
    if not bad:
        return []
    return [
        f"{SHEET_LABELS[sheet_key]} {row_idx}행 J열: 간격 값은 1~44만 허용 (오류: {sorted(bad)[:8]})"
    ]


def validate_three_filter_sheets(filters_data: dict) -> tuple[list[str], dict]:
    """
    Returns (errors, summary).
    errors 비어 있으면 저장·연산 가능.
    """
    data = normalize_three_filter_data(filters_data)
    errors: list[str] = []
    summary: dict[str, int | str] = {}

    for key in SHEET_KEYS:
        df = data[key]
        active = df[df["입력데이터"].astype(str).str.strip() != ""]
        summary[f"{key}_rows"] = len(active)

        for idx, row in active.iterrows():
            row_no = int(idx) + 1
            targets = _parse_targets(row.get("입력데이터", ""))
            if not targets:
                continue

            if key == "basic":
                errors.extend(_validate_ball_targets(key, row_no, targets))
                continue

            label = str(row.get("구분", "")).strip()
            if not label.isdigit():
                errors.append(
                    f"{SHEET_LABELS[key]} {row_no}행: I열(절대수)는 1~45 정수 필요"
                )
                continue
            ball = int(label)
            if not (1 <= ball <= 45):
                errors.append(
                    f"{SHEET_LABELS[key]} {row_no}행: I열 절대수 {ball} (1~45만 허용)"
                )

            if key == "interval":
                errors.extend(_validate_gap_targets(key, row_no, targets))
            else:
                errors.extend(_validate_ball_targets(key, row_no, targets))

    return errors, summary


# 하위 호환
validate_four_filter_sheets = validate_three_filter_sheets
