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

        # 2026-08-30: "3종필터 업로드하면 적용패턴수 바로 계산되는데, 회차 저장할
        # 때 그 값이 안 따라온다"는 지적 — 지금까지는 "로또최근당첨내역.xlsb"
        # 당번시트 N5 셀을 관리자가 손으로 옮겨 적어야만 회차 저장 시점에 반영됐다
        # (.xlsb는 pyxlsb가 읽기 전용이라 여기서 직접 써넣을 방법이 없음). N5 셀
        # 대신 여기서 곧바로 방금 계산된 최종 결과(stage3_interval, 필터를 전부
        # 통과한 조합 수)를 DB 설정값으로 저장해두면, 회차 저장 시점
        # (admin_dashboard.py의 _current_filter_pattern_count)이 이 값을 그대로
        # 읽어가서 수동 입력 없이 항상 최신 상태로 맞물린다.
        try:
            from app_settings import init_settings_table, set_setting

            init_settings_table()
            set_setting("latest_filter_pattern_count", str(len(final_data)))
        except Exception:
            pass

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
