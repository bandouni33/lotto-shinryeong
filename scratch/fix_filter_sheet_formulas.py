# -*- coding: utf-8 -*-
"""4차필터/추적결과/3차필터 시트의 '적중' 열·합계 범위 수식 수리 (1회성, 승인 후 실행).

2026-09-27 진단(실측):
  · '적중'(J) 열이 **자기 행이 아닌 2행 위**를 가리키는 오프셋 오류가 4개 시트에 있었다:
      샘플/200회검증용의 1차추적결과·2차추적결과·4차필터 (머리글 2행, 데이터 3~104행)
        J3=SUM(K3:M3) ✓ … J5=SUM(K3:M3) ✗(3행 중복) J7=SUM(K5:M5) ✗ … J104=SUM(K102:M102) ✗
      샘플의 3차필터(100출현빈도순 후보) (머리글 6행, 데이터 7~105행)
        J8=SUM(K8:M8) ✓ … J104=SUM(K102:M102) ✗ J105=SUM(K103:M103) ✗
    → 각 행이 "다른 회차의 상/중/하 합계"를 적중으로 보여주고 있었다(표시가 거짓).
  · 1행/5행 합계 범위도 서로 어긋나 있었다: 실제 데이터가 3~104행(또는 7~105행)인데
    K1=SUM(K3:K101), L1=SUM(L3:L500) 처럼 101에서 끊기거나 빈 400행까지 포함.

이 스크립트의 규칙(좁고 안전하게):
  · J열 머리글이 '적중'인 시트만 대상(머리글 행은 1~10행에서 찾는다 — 시트마다 2행/6행으로 다름).
  · 데이터 행 = 머리글 아래에서 A열이 회차번호(정수 ≥1000)인 행.
  · **이미 SUM 수식인 칸만** 제 행을 가리키도록 고친다. 빈 칸이나 '-' 같은 값을
    수식으로 바꾸지 않는다(회차별 추적표 J3='-'는 그 시트의 COUNT/AVERAGE 통계가
    숫자만 세기 때문에 건드리면 통계 자체가 달라진다).
  · 1행(=SUM(...)이 이미 있는 열)의 합계 범위는 그 시트의 실제 회차행 범위로 통일한다.

실행(기본은 미리보기):
    venv312\\Scripts\\python.exe scratch\\fix_filter_sheet_formulas.py
    venv312\\Scripts\\python.exe scratch\\fix_filter_sheet_formulas.py --apply
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
TRACKER = ROOT / "★조합생성_후보숫자_추적표"
TARGETS = {
    "샘플": TRACKER / "조합생성_후보숫자_추적표_샘플.xlsx",
    "200회검증용": TRACKER / "조합생성_후보숫자_추적표_샘플_200회검증용.xlsx",
}
BACKUP_DIR = TRACKER / "_backup_20260927_formulas"

J_COL, ROUND_COL = 10, 1


def header_row(ws) -> int | None:
    """J열 머리글이 '적중'인 행(시트마다 2행/6행으로 다르다)."""
    for r in range(1, 11):
        if ws.cell(r, J_COL).value == "적중":
            return r
    return None


def data_rows(ws, header: int) -> list[int]:
    """머리글 아래에서 A열이 회차번호(정수 ≥1000)인 행들."""
    return [r for r in range(header + 1, ws.max_row + 1)
            if isinstance(ws.cell(r, ROUND_COL).value, int) and ws.cell(r, ROUND_COL).value >= 1000]


def plan_for_sheet(ws):
    """(머리글행, 고칠 J행들, 합계 범위를 바꿀 열들, (좌표, 이전, 이후) 목록, 회차행들)"""
    hdr = header_row(ws)
    if hdr is None:
        return None
    rows = data_rows(ws, hdr)
    if not rows:
        return None

    j_rows, changes = [], []
    for r in rows:
        want = f"=SUM(K{r}:M{r})"
        cur = ws.cell(r, J_COL).value
        if isinstance(cur, str) and cur.upper().startswith("=SUM(") and cur != want:
            j_rows.append(r)
            changes.append((f"J{r}", str(cur), want))

    cols = []
    for c in range(11, 17):  # K..P — 1행에 합계가 있는 열만
        cur = ws.cell(1, c).value
        if isinstance(cur, str) and cur.upper().startswith("=SUM("):
            letter = openpyxl.utils.get_column_letter(c)
            want = f"=SUM({letter}{min(rows)}:{letter}{max(rows)})"
            if cur != want:
                cols.append(c)
                changes.append((f"{letter}1", cur, want))
    return hdr, j_rows, cols, changes, rows


def main() -> int:
    apply = "--apply" in sys.argv
    total = 0

    for label, path in TARGETS.items():
        if not path.exists():
            print(f"[오류] 파일 없음: {path}")
            return 1

        wb = openpyxl.load_workbook(path, data_only=False)
        planned = []
        for ws in wb.worksheets:
            plan = plan_for_sheet(ws)
            if plan and plan[3]:
                planned.append((ws, *plan))

        print(f"\n=== {label} ===")
        if not planned:
            print("  수정 대상 없음")
            wb.close()
            continue

        for ws, hdr, j_rows, cols, changes, rows in planned:
            print(f"  [{ws.title}] 머리글 {hdr}행 · 회차행 {min(rows)}~{max(rows)} · "
                  f"J열 {len(j_rows)}행 · 합계열 {len(cols)}개")
            for coord, old, new in changes[:3]:
                print(f"      {coord}: {old}  →  {new}")
            if len(changes) > 3:
                print(f"      … 외 {len(changes) - 3}건")
            total += len(changes)

        if apply:
            # 백업은 **저장 전에, 파일마다 한 번만** 뜬다. (시트마다 떠서 두 번째 시트의
            # 백업이 이미 고친 상태를 덮어쓰던 결함을 2026-09-27에 발견해 고쳤다.)
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, BACKUP_DIR / path.name)

            for ws, hdr, j_rows, cols, changes, rows in planned:
                for r in j_rows:
                    ws.cell(r, J_COL, f"=SUM(K{r}:M{r})")
                for c in cols:
                    letter = openpyxl.utils.get_column_letter(c)
                    ws.cell(1, c, f"=SUM({letter}{min(rows)}:{letter}{max(rows)})")
            wb.save(path)
            print(f"  저장 완료(백업: {BACKUP_DIR.name}/{path.name})")

            try:
                from candidate_tracker_auto_update import recalc_and_save

                recalc_and_save(path)
                print("  엑셀 재계산·저장 완료(캐시값 반영)")
            except Exception as e:  # noqa: BLE001
                print(f"  [경고] 엑셀 재계산 생략: {e}")
        wb.close()

    print(f"\n{'적용' if apply else '미리보기(변경 없음)'} — 수정 대상 {total}건")
    if not apply and total:
        print("실제 반영: --apply 를 붙여 다시 실행")
    return 0


if __name__ == "__main__":
    sys.exit(main())
