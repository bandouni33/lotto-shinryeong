# -*- coding: utf-8 -*-
"""1차 고정규칙 row19 max 3 → 2 로 수정한다 — 사용자 결정(2026-09-27).

배경: 파일 1차 시트 row19(H='9   5분', 대상 1~9)는 max=2인데 앱 규칙(DB/JSON)은 max=3이라,
1차+이격 통과수가 앱 2,594,759 vs 파일 2,461,980으로 5.4% 어긋났다(실측 — 이 1개가 전부 설명).
사용자가 "앱을 파일 기준으로 통일"로 결정 → 이 스크립트로 규칙 원문을 고친다.

안전장치(모두 통과해야 쓴다)
  1) 로컬 JSON을 파싱해 그대로 다시 덤프 → 원문과 동일한지(서식 유지 가능성) 확인
  2) DB(app_settings) 값과 로컬 파일이 바이트 단위로 같은지 확인(다르면 어느 쪽이 정본인지 정해야 하므로 중단)
  3) 이미 max=2면 아무것도 하지 않음(멱등)
  4) 바뀐 항목이 row19 하나뿐이고 그 항목에서 max만 달라졌는지 확인
  5) 쓰기 전 백업
DB 반영은 기존 정식 경로인 migrate_filter_rules_to_db.py가 담당한다(왕복 일치까지 검증).

실행: venv312\\Scripts\\python.exe scratch\\set_row19_max2.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from env_loader import load_dotenv_file  # noqa: E402

load_dotenv_file()

import app_settings  # noqa: E402

RULE_FILE = ROOT / "combo_filter_rules_stage1.json"
BACKUP = ROOT / "scratch" / "_backup_combo_filter_rules_stage1_row19.json"
TARGET_ROW = 19
OLD_MAX, NEW_MAX = 3, 2
OUT = ROOT / "scratch" / "set_row19_max2_out.txt"
R: list[str] = []


def w(s: str = "") -> None:
    R.append(str(s))
    print(s, flush=True)


def die(msg: str) -> None:
    w(f"[중단] {msg}")
    OUT.write_text("\n".join(R), encoding="utf-8")
    os._exit(1)


original = RULE_FILE.read_text(encoding="utf-8")
data = json.loads(original)          # 파싱 실패면 여기서 예외
redump = json.dumps(data, ensure_ascii=False, indent=2)
trailing = "" if original.endswith(redump) else "\n"
if redump + trailing != original:
    die("로컬 규칙 JSON 서식이 json.dumps(indent=2)와 달라 그대로 쓰면 서식이 바뀝니다 — 중단")
w(f"서식 확인 OK ({len(original):,}자)")

db_raw = app_settings.get_filter_rules_json(1)
if (db_raw or "") != original:
    die("DB 값과 로컬 파일이 바이트 단위로 다릅니다 — 정본을 정한 뒤 진행하세요")
w("DB == 로컬 파일 (바이트 단위) 확인 OK")

idx = [i for i, e in enumerate(data) if e.get("row") == TARGET_ROW]
if len(idx) != 1:
    die(f"row{TARGET_ROW} 항목이 {len(idx)}개입니다(정확히 1개여야 함)")
i = idx[0]
entry = data[i]
w(f"수정 전 row{TARGET_ROW}: {json.dumps(entry, ensure_ascii=False)}")
if entry.get("targets") != list(range(1, 10)):
    die(f"row{TARGET_ROW} 대상집합이 1~9가 아닙니다: {entry.get('targets')}")
if entry.get("max") == NEW_MAX:
    w(f"이미 max={NEW_MAX} — 아무것도 하지 않았습니다(멱등).")
    OUT.write_text("\n".join(R), encoding="utf-8")
    os._exit(0)
if entry.get("max") != OLD_MAX:
    die(f"row{TARGET_ROW} max가 예상({OLD_MAX})과 다릅니다: {entry.get('max')}")

data[i] = {**entry, "max": NEW_MAX}
new_text = json.dumps(data, ensure_ascii=False, indent=2) + trailing
parsed_new = json.loads(new_text)

# 항목 수·순서 불변, row19만 max가 달라졌는지 확인
if len(parsed_new) != len(data):
    die("항목 수가 변했습니다")
for j, (a, b) in enumerate(zip(json.loads(original), parsed_new)):
    if j == i:
        if {k: v for k, v in b.items() if k != "max"} != {k: v for k, v in a.items() if k != "max"}:
            die(f"row{TARGET_ROW}에서 max 외의 값이 변했습니다: {a} → {b}")
        if (a["max"], b["max"]) != (OLD_MAX, NEW_MAX):
            die(f"max 변경이 예상과 다릅니다: {a['max']} → {b['max']}")
    elif a != b:
        die(f"다른 항목이 변했습니다(row={a.get('row')})")

shutil.copy2(RULE_FILE, BACKUP)
w(f"백업: {BACKUP.name}")
RULE_FILE.write_text(new_text, encoding="utf-8")
w(f"수정 후 row{TARGET_ROW}: {json.dumps(parsed_new[i], ensure_ascii=False)}")
w(f"규칙 원문 저장 완료 ({len(new_text):,}자). 다음: migrate_filter_rules_to_db.py")

OUT.write_text("\n".join(R), encoding="utf-8")
print(f"written {OUT}")
os._exit(0)
