# -*- coding: utf-8 -*-
"""1차필터 규칙에 '후보패턴 이웃수(200회)'(행 484)를 추가한다 — 사용자 결정 ③.

왜: 샘플 추적표의 1차 규칙표에는 행 484에 '후보패턴 이웃수(200회)'(0~4)가 있는데
앱 규칙(DB/JSON)에는 없어서, 같은 회차의 2차 통과수가 앱 > 파일로 약 5% 어긋났다.
실측(scratch/probe_auto_rule_window.py): 앱이 쓰는 창은 100회뿐이고, 창이 다르면
대상집합이 13개 vs 14개(8개·9개 상이)로 갈린다.

이 스크립트가 하는 일(안전장치 포함)
  1) 로컬 JSON을 파싱해 그대로 다시 덤프 → 원문과 바이트 단위로 같은지 확인
     (다르면 서식이 달라진다는 뜻이므로 **아무것도 쓰지 않고 중단**)
  2) DB(app_settings)의 값과 로컬 파일이 **바이트 단위로 같은지** 확인
     (다르면 어느 쪽이 진짜인지 정해야 하므로 중단 — 이 스크립트가 임의로 고르지 않는다)
  3) 이미 그 규칙이 있으면 아무것도 하지 않는다(멱등)
  4) AUTO 3개 뒤에 새 항목을 넣어 로컬 JSON을 다시 쓴다(백업 먼저)
  DB 반영은 이 스크립트가 하지 않는다 — 기존 정식 경로인 migrate_filter_rules_to_db.py가
  로컬 파일을 DB에 올리고 왕복 일치를 검증한다.

실행: venv312\\Scripts\\python.exe scratch\\add_auto_rule_200.py
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
BACKUP = ROOT / "scratch" / "_backup_combo_filter_rules_stage1.json"
NEW_RULE = {"row": 484, "name": "후보패턴 이웃수(200회)", "is_auto": True,
            "targets": None, "min": 0, "max": 4}
OUT = ROOT / "scratch" / "add_auto_rule_200_out.txt"
R: list[str] = []


def w(s: str = "") -> None:
    R.append(str(s))
    print(s, flush=True)


def die(msg: str) -> None:
    w(f"[중단] {msg}")
    OUT.write_text("\n".join(R), encoding="utf-8")
    sys.exit(1)


original = RULE_FILE.read_text(encoding="utf-8")
try:
    data = json.loads(original)
except ValueError as e:
    die(f"로컬 규칙 JSON 파싱 실패: {e}")

redump = json.dumps(data, ensure_ascii=False, indent=2)
trailing = "" if original.endswith(redump) else "\n"
if redump + trailing != original:
    die("로컬 규칙 JSON의 서식이 json.dumps(indent=2)와 달라 그대로 다시 쓰면 서식이 바뀝니다 "
        "— 서식이 다른 도구로 관리되는 파일일 수 있어 여기서 멈춥니다")
w(f"서식 확인 OK (json.dumps(indent=2)로 원문 재현 가능, {len(original):,}자)")

db_raw = app_settings.get_filter_rules_json(1)
w(f"DB 값 {len(db_raw or ''):,}자 / 로컬 파일 {len(original):,}자")
if (db_raw or "") != original:
    die("DB 값과 로컬 파일이 바이트 단위로 다릅니다 — 어느 쪽을 정본으로 할지 정한 뒤 진행하세요")
w("DB == 로컬 파일 (바이트 단위) 확인 OK")

autos_before = [e["name"] for e in data if e.get("is_auto")]
w(f"추가 전: 항목 {len(data)}개 / AUTO {autos_before}")

if any(e.get("name") == NEW_RULE["name"] for e in data):
    w("이미 그 규칙이 있습니다 — 아무것도 하지 않았습니다(멱등).")
    OUT.write_text("\n".join(R), encoding="utf-8")
    sys.exit(0)

idx = max(i for i, e in enumerate(data) if e.get("is_auto"))     # 마지막 AUTO 뒤에 넣는다
data.insert(idx + 1, dict(NEW_RULE))
new_text = json.dumps(data, ensure_ascii=False, indent=2) + trailing

parsed_new = json.loads(new_text)
assert parsed_new[:idx + 1] == json.loads(original)[:idx + 1], "앞부분이 변했다"
assert parsed_new[idx + 1] == NEW_RULE, "삽입 위치가 예상과 다르다"
assert len(parsed_new) == len(json.loads(original)) + 1, "항목 수가 1개만 늘어야 한다"
w(f"추가 후: 항목 {len(parsed_new)}개 / AUTO {[e['name'] for e in parsed_new if e.get('is_auto')]}")

shutil.copy2(RULE_FILE, BACKUP)
w(f"백업: {BACKUP.name}")
RULE_FILE.write_text(new_text, encoding="utf-8")
w(f"로컬 규칙 파일 저장 완료 ({len(new_text):,}자). 다음 단계는 migrate_filter_rules_to_db.py")

OUT.write_text("\n".join(R), encoding="utf-8")
print(f"written {OUT}")
os._exit(0)
