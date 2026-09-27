# -*- coding: utf-8 -*-
"""실물 샘플 파일에 '회차 컬럼 전진'을 적용한다 (2026-09-27, 사용자 승인).

하는 일
  1) 실물 파일을 scratch/에 타임스탬프 백업으로 복사한다(되돌릴 수 있게).
  2) 적용 전 상태(라벨·수식 수·오류값)를 찍는다.
  3) 생산 함수 weekly_lotto_file_update.advance_round_columns(path, "샘플")를 부른다.
  4) 적용 후 상태를 같은 방식으로 찍고, 백업과 대조한 요약을 남긴다.
커밋·푸시는 하지 않는다(사용자 지시: 항상 먼저 보고).

실행: venv312\\Scripts\\python.exe scratch\\apply_sample_column_advance.py [--dry-run]
"""
from __future__ import annotations

import datetime
import hashlib
import shutil
import sys
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter as cl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from weekly_lotto_file_update import (  # noqa: E402
    COLUMN_ROUND_SHEETS,
    advance_round_columns,
    scan_errors,
)

SRC = ROOT / "★조합생성_후보숫자_추적표" / "조합생성_후보숫자_추적표_샘플.xlsx"
OUT = ROOT / "scratch" / "apply_sample_column_advance_out.txt"
DRY = "--dry-run" in sys.argv
R: list[str] = []


def w(s: str = "") -> None:
    R.append(str(s))
    print(s, flush=True)


def state(path: Path, tag: str) -> dict:
    wb = openpyxl.load_workbook(path, data_only=False, read_only=True)
    try:
        out = {}
        for sn in COLUMN_ROUND_SHEETS:
            ws = wb[sn]
            labels = [ws.cell(4, c).value for c in range(1, ws.max_column + 1)
                      if isinstance(ws.cell(4, c).value, int)]
            out[sn] = {"labels": labels, "n_labels": len(labels)}
        # 회차 라벨과 수식 개수는 일반 로드로 다시 본다(읽기 전용 모드는 셀 접근이 제한적)
    finally:
        wb.close()
    wb2 = openpyxl.load_workbook(path, data_only=False)
    try:
        for sn in COLUMN_ROUND_SHEETS:
            ws = wb2[sn]
            first = min(c for c in range(1, ws.max_column + 1)
                        if isinstance(ws.cell(4, c).value, int))
            last = max(c for c in range(1, ws.max_column + 1)
                       if isinstance(ws.cell(4, c).value, int))
            n_f = 0
            for c in range(first, last + 1):
                for r in range(1, ws.max_row + 1):
                    v = ws.cell(r, c).value
                    t = v.text if hasattr(v, "text") else v
                    if isinstance(t, str) and t.startswith("="):
                        n_f += 1
            out[sn].update({"range": f"{cl(first)}..{cl(last)}", "formulas": n_f,
                            "merged": sorted(rng.coord for rng in ws.merged_cells.ranges),
                            "max_row": ws.max_row})
        out["_sheets"] = list(wb2.sheetnames)
    finally:
        wb2.close()
    w(f"  [{tag}] " + " · ".join(
        f"{sn}: {out[sn]['n_labels']}열 {out[sn]['range']} 라벨 "
        f"{out[sn]['labels'][0]}→{out[sn]['labels'][-1]} 수식{out[sn]['formulas']:,}"
        for sn in COLUMN_ROUND_SHEETS))
    return out


sha_before = hashlib.sha256(SRC.read_bytes()).hexdigest()
stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = ROOT / "scratch" / f"_backup_샘플_{stamp}.xlsx"

w(f"실물 {SRC.name}")
w(f"sha(앞12) before = {sha_before[:12]}")
w(f"\n== 적용 전 ==")
before = state(SRC, "before")
try:
    errs_before = scan_errors(SRC)
except Exception as e:  # noqa: BLE001
    errs_before = [("scan 실패", "", str(e))]
w(f"  오류값 {len(errs_before)}개 {errs_before[:3]}")

if DRY:
    w("\n--dry-run: 백업·적용 없이 종료")
    OUT.write_text("\n".join(R), encoding="utf-8")
    sys.exit(0)

shutil.copy2(SRC, BACKUP)
w(f"\n백업: {BACKUP.name} ({BACKUP.stat().st_size:,} bytes)")

w("\n== 적용 (생산 함수 advance_round_columns) ==")
stats = advance_round_columns(SRC, "샘플")
for sn, st in stats.items():
    w(f"  {sn}: {st['shifts']}칸 전진 ({st['labels_before']}→{st['labels_after']})")

w("\n== 적용 후 ==")
after = state(SRC, "after")
try:
    errs_after = scan_errors(SRC)
except Exception as e:  # noqa: BLE001
    errs_after = [("scan 실패", "", str(e))]
w(f"  오류값 {len(errs_after)}개 {errs_after[:3]}")

w("\n== 백업 대조 ==")
ok_all = True
for sn in COLUMN_ROUND_SHEETS:
    b, a = before[sn], after[sn]
    same_n = a["n_labels"] == b["n_labels"]
    same_f = a["formulas"] == b["formulas"]
    same_merged = a["merged"] == b["merged"]
    same_max = a["max_row"] == b["max_row"]
    shifted = a["labels"][0] - b["labels"][0]
    cont = a["labels"] == [a["labels"][0] - i for i in range(len(a["labels"]))]
    w(f"  {sn}: 열수 {b['n_labels']}→{a['n_labels']} {'ok' if same_n else 'FAIL'} · "
      f"수식 {b['formulas']:,}→{a['formulas']:,} {'ok' if same_f else 'FAIL'} · "
      f"라벨 {b['labels'][0]}→{a['labels'][0]} (+{shifted}) {'ok' if cont else 'FAIL'} · "
      f"병합 {'ok' if same_merged else 'FAIL'} · 최대행 {'ok' if same_max else 'FAIL'}")
    ok_all &= same_n and same_f and same_merged and same_max and cont and shifted >= 0
w(f"  시트 목록 동일: {after['_sheets'] == before['_sheets']}")
w(f"  sha(앞12) after = {hashlib.sha256(SRC.read_bytes()).hexdigest()[:12]} "
  f"(before {sha_before[:12]} — 실제로 바뀌어야 정상)")
w(f"\n결과: {'정상' if ok_all and after['_sheets'] == before['_sheets'] else '확인 필요'}")
w("주의: openpyxl은 계산을 하지 않으므로 새 열의 캐시값은 엑셀로 열 때/recalc_and_save에서 채워진다.")
OUT.write_text("\n".join(R), encoding="utf-8")
print(f"written {OUT}")
sys.exit(0 if (ok_all and after["_sheets"] == before["_sheets"]) else 1)
