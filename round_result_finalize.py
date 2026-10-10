"""토요일 밤 — 방금 추첨된 회차의 '회차별 당첨번호 배출' 등수를 바로 확정한다 (2026-10-10 사용자 지시).

배경: 등수는 일요일 13:30(KST) 조합 생성 작업(combo_gen_worker.py)이 같이 계산해 표에 고정했다 —
추첨(토 20:30경) 뒤 약 17시간 동안 자동조합 화면 표의 최신 회차가 비어(0) 보였다. 동행복권은
추첨 1시간쯤 뒤 당첨 결과를 발표하므로, 당첨번호가 들어오는 즉시(hourly_draw_sync 직후) 같은
계산(combo_filter_v2.compute_reference_stats — 전주 풀을 지금 규칙으로 재현해 이번 당첨번호와 대조)을
돌려 참고등수를 저장하고 스냅샷을 확정한다.

멱등: 이미 참고등수가 있거나(일요일 작업이 먼저 했거나 이전 실행이 끝냄), 1241회 미만이거나,
그 회차 스냅샷 행이 없으면 계산 없이 끝난다. 일요일 작업은 그대로 둔다 — 같은 값을 다시 쓰고
finalize 는 WHERE finalized_at IS NULL 이라 이미 확정된 값은 안 바뀐다.

실행: python round_result_finalize.py   (GitHub Actions hourly_draw_sync.yml 의 두 번째 단계)
"""

from __future__ import annotations

import os

REFERENCE_START_ROUND = 1241  # combo_gen_worker 의 anchor_round >= 1241 조건과 같은 기준


def finalize_latest_round() -> str:
    """결과 한 줄(로그용)을 돌려준다. 예외는 호출부(재시도)로 그대로 올린다."""
    import combo_filter_v2
    import draw_results_db
    import marketing_db

    draw_results_db.init_draw_results_table()
    marketing_db.init_marketing_tables()
    latest = draw_results_db.get_latest_draw_round()
    if latest is None:
        return "skip: 당첨번호 데이터 없음"
    latest = int(latest)
    if latest < REFERENCE_START_ROUND:
        return f"skip: {latest}회는 참고등수 대상(1241회~)이 아님"
    if marketing_db.get_reference_ranks(latest) is not None:
        # 등수 근거는 있는데 스냅샷 확정만 빠졌을 수도 있다(이전 실행이 중간에 끊긴 경우) — 확정만 시도.
        done = marketing_db.finalize_round_stats(latest)
        return f"skip: {latest}회 참고등수 이미 있음(스냅샷 확정 {'이번에 함' if done else '이미 됨/대상 없음'})"
    snapshot_rounds = {int(s["draw_round"]) for s in marketing_db.get_round_stats_snapshot(limit=10)}
    if latest not in snapshot_rounds:
        return f"skip: {latest}회 스냅샷 행 없음(그 회차 조합을 배포하지 않음)"

    static_rules, auto_rules, stage2_rules = combo_filter_v2._load_rules()
    if not static_rules or not auto_rules or not stage2_rules:
        raise RuntimeError("필터 규칙을 DB 에서 읽지 못했다 — app_settings.filter_rules_* 확인")

    history = draw_results_db.get_all_draw_results()
    ref = combo_filter_v2.compute_reference_stats(history, latest)
    if ref is None:
        return f"skip: {latest}회 또는 직전 회차 당첨번호가 없어 계산 불가"
    pool_size, detail = ref
    marketing_db.set_reference_ranks(latest, detail["ref_ranks"])
    done = marketing_db.finalize_round_stats(latest)
    return (
        f"ok: {latest}회 참고등수 {tuple(detail['ref_ranks'])} 저장(풀 {pool_size:,}개), "
        f"스냅샷 확정 {'완료' if done else '이미 됨'}"
    )


def main() -> int:
    print(f"[round_result_finalize] {finalize_latest_round()}")
    return 0


if __name__ == "__main__":
    # hourly_draw_sync.py 와 같은 이유(db_turso 의 non-daemon 스레드가 종료를 붙잡음)로 즉시 종료.
    try:
        code = main()
    except Exception as exc:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        print(f"[round_result_finalize] 실패: {exc}")
        code = 1
    os._exit(code)
