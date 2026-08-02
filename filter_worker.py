"""3종 필터 백그라운드 연산 — Streamlit 워커 블로킹 방지."""

from __future__ import annotations

import json
import os
import pickle
import sys
import traceback

import pandas as pd

STATUS_FILE = "filter_job.status"
FILTER_SAVE_FILE = "saved_filters.pkl"
COMBO_SAVE_FILE = "saved_combinations.csv"


def write_status(state: str, **extra) -> None:
    payload = {"state": state, **extra}
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


def main() -> int:
    write_status("running", pid=os.getpid())
    try:
        from lotto_engine import run_admin_three_filter_staged
        from filter_sheet_validation import validate_three_filter_sheets

        with open(FILTER_SAVE_FILE, "rb") as f:
            saved_filters = pickle.load(f)
        from filter_sheet_validation import normalize_three_filter_data

        saved_filters = normalize_three_filter_data(saved_filters)
        val_errors, _summary = validate_three_filter_sheets(saved_filters)
        if val_errors:
            write_status(
                "error",
                message="3종 필터 검증 실패 — 엑셀 J/I 열을 확인해 주세요.",
                validation_errors=val_errors[:30],
                pid=os.getpid(),
            )
            return 1
        final_data, stage_stats = run_admin_three_filter_staged(saved_filters)
        df = pd.DataFrame(
            final_data,
            columns=["번호1", "번호2", "번호3", "번호4", "번호5", "번호6"],
        )
        df.to_csv(COMBO_SAVE_FILE, index=False)
        write_status(
            "done",
            total=len(final_data),
            stage_stats=stage_stats,
            pid=os.getpid(),
        )
        return 0
    except Exception as exc:
        write_status(
            "error",
            message=str(exc),
            traceback=traceback.format_exc(),
            pid=os.getpid(),
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
