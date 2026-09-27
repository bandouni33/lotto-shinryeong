# -*- coding: utf-8 -*-
"""주간 자동화 결선 테스트 — process_one_round_for_file이 컬럼 전진을 '어떻게' 부르는가.

왜 이 테스트가 필요한가: 샘플 워크북은 openpyxl 로드/저장만 각 1~1.5분이 걸려
(수식 7,860개 × 수천 자) 실물 경로 통합 테스트가 이 세션에서 5분+ 걸린다. 그래서
  · 무거운 부분(전진·추가·재계산)은 '호출되었는가/순서/인자'로 검증하고(이 파일),
  · 실제 전진 결과는 임시 복사본 불변식 190건(scratch/sim_sample_column_advance.py)과
    실물 적용 후 백업 대조(scratch/check_sim_advance_static.py)가 검증한다.
즉 이 파일은 "자동화가 매주 그 함수를 실제로 부르는가"를 값싸고 결정적으로 확인한다.

핵심 계약:
  C1 샘플(컬럼 파일)은 append → save → advance_round_columns 순서로 부른다
     (전진이 전체당첨내역 추가보다 먼저면 헬퍼행 MATCH가 빈 값을 잡는다).
  C2 컬럼 전진 대상이 아닌 파일(200회검증용)은 advance_round_columns를 부르지 않는다.
  C3 엑셀 재계산이 실패해도 회차 처리는 예외 없이 끝난다(경고만 남긴다).

실행: venv312\\Scripts\\python.exe scratch\\test_weekly_column_wiring.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import weekly_lotto_file_update as wk  # noqa: E402

OUT = ROOT / "scratch" / "test_weekly_column_wiring_out.txt"
R: list[str] = []
FAILS: list[str] = []


def w(s: str = "") -> None:
    R.append(str(s))
    print(s, flush=True)


def ok(cond: bool, msg: str) -> bool:
    if cond:
        w(f"  ok   {msg}")
    else:
        FAILS.append(msg)
        w(f"  FAIL {msg}")
    return bool(cond)


class _FakeWB:
    def __init__(self, calls):
        self.calls = calls
        self.all_sheet = object()

    def __getitem__(self, key):
        assert key == "전체당첨내역", f"예상 밖 시트 접근: {key}"
        return self.all_sheet

    def save(self, path):
        self.calls.append("save")          # 저장도 호출 순서에 기록한다(계약의 일부)

    def close(self):
        pass


class _FakeOpenpyxl:
    """wk.openpyxl 만 바꿔치기한다 — 진짜 openpyxl 모듈은 건드리지 않는다."""

    def __init__(self, wb):
        self._wb = wb

    def load_workbook(self, *a, **k):
        return self._wb


REC = {"round": 9999, "nums": [3, 11, 19, 27, 35, 44], "bonus": 7}


def run_case(label: str, recalc_raises: bool = False) -> list[str]:
    calls: list[str] = []
    wb = _FakeWB(calls)

    real_openpyxl = wk.openpyxl
    real_append, real_advance, real_recalc = wk.append_draw_result, wk.advance_round_columns, wk.recalc_and_save
    wk.openpyxl = _FakeOpenpyxl(wb)                                    # type: ignore[assignment]

    def fake_append(ws_all, r):
        calls.append("append")
        assert ws_all is wb.all_sheet, "엉뚱한 시트에 회차를 추가했다"

    def fake_advance(path, lb):
        calls.append("advance_round_columns")
        assert lb == label, f"전진 대상 라벨이 다르다: {lb} != {label}"
        return {sn: {"shifts": 1, "labels_before": 1243, "labels_after": 1244}
                for sn in wk.COLUMN_ROUND_SHEETS}

    def fake_recalc(path):
        calls.append("recalc_and_save")
        if recalc_raises:
            raise RuntimeError("엑셀 없음(시험용)")

    wk.append_draw_result, wk.advance_round_columns, wk.recalc_and_save = (
        fake_append, fake_advance, fake_recalc)
    try:
        wk.process_one_round_for_file(Path("가짜_경로.xlsx"), label, dict(REC))
    finally:
        wk.openpyxl = real_openpyxl                                      # type: ignore[assignment]
        wk.append_draw_result, wk.advance_round_columns, wk.recalc_and_save = (
            real_append, real_advance, real_recalc)
    return calls


w("== C1: 샘플(컬럼 파일) 호출 순서 ==")
calls = run_case("샘플")
w(f"  호출 순서: {calls}")
ok(calls == ["append", "save", "advance_round_columns", "recalc_and_save"],
   "전체당첨내역 추가 + 저장이 컬럼 전진보다 먼저 일어난다")
ok("advance_round_columns" in calls and "recalc_and_save" in calls,
   "컬럼 전진과 엑셀 재계산이 모두 호출된다")
ok(calls.index("advance_round_columns") < calls.index("recalc_and_save"),
   "전진이 재계산보다 먼저 호출된다(전진 뒤에 값 굽기)")

w("\n== C2: 컬럼 전진 대상이 아닌 파일 ==")
calls2 = run_case("200회검증용")
w(f"  호출 순서: {calls2}")
ok("advance_round_columns" not in calls2,
   "200회검증용은 컬럼 전진을 부르지 않는다(승인 범위 밖)")
ok(calls2 == ["append", "save", "recalc_and_save"], "전체당첨내역 갱신은 그대로 한다")

w("\n== C3: 엑셀 재계산 실패는 치명적이지 않다 ==")
try:
    calls3 = run_case("샘플", recalc_raises=True)
    ok(True, "재계산이 예외를 던져도 process_one_round_for_file이 정상 종료")
    w(f"  호출 순서: {calls3}")
except Exception as e:  # noqa: BLE001
    ok(False, f"재계산 실패가 회차 처리를 중단시켰다: {type(e).__name__}: {e}")

w("\n== 설정 계약 ==")
ok(wk.COLUMN_ROUND_FILES == {"샘플"},
   f"컬럼 전진 대상 파일 = {sorted(wk.COLUMN_ROUND_FILES)} (승인대로 샘플만)")
ok(wk.COLUMN_ROUND_SHEETS == ("1차필터(7기본필터)", "2차필터(5이격수)"),
   f"전진 대상 시트 = {list(wk.COLUMN_ROUND_SHEETS)}")
ok(all(lb not in wk.ADVANCE_3CHA_FILES for lb in wk.COLUMN_ROUND_FILES),
   "컬럼 파일이 3차필터 예측행 전진 대상(ADVANCE_3CHA_FILES)에 섞여 있지 않다")

w(f"\n단언 실패 {len(FAILS)}건" + ("" if not FAILS else ": " + " | ".join(FAILS[:5])))
OUT.write_text("\n".join(R), encoding="utf-8")
print(f"written {OUT}")
sys.exit(1 if FAILS else 0)
