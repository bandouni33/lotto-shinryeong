"""1회성 스크립트 — combo_filter_rules_stage1/2.json의 내용을 Turso DB
(app_settings 테이블)로 옮긴다.

2026-09-20: 필터규칙 DB 이관 6-2단계. 이 스크립트는 딱 한 번만 실행하면
된다(여러 번 실행해도 안전 — 매번 같은 내용을 덮어쓸 뿐이라 멱등).

실행 방법 (프로젝트 루트에서):
    python migrate_filter_rules_to_db.py

실행 후 "이관 완료" 메시지가 뜨면 6-3단계(검증)로 넘어가면 된다.
"""

from __future__ import annotations

import json
import os
import sys

import env_loader

env_loader.load_dotenv_file()

import app_settings  # noqa: E402  (dotenv 로드 이후에 import해야 함)

_DIR = os.path.dirname(os.path.abspath(__file__))
_STAGE1_FILE = os.path.join(_DIR, "combo_filter_rules_stage1.json")
_STAGE2_FILE = os.path.join(_DIR, "combo_filter_rules_stage2.json")


def _migrate_stage(stage: int, path: str) -> None:
    print(f"\n[{stage}차] {os.path.basename(path)} 읽는 중...")
    with open(path, encoding="utf-8") as f:
        raw = f.read()

    # 로컬 파일 자체가 깨진 JSON이면 DB에도 깨진 채로 올라가면 안 되니
    # 여기서 먼저 파싱 검증한다.
    parsed = json.loads(raw)
    print(f"  - 로컬 파일 파싱 OK (항목 {len(parsed)}개, {len(raw):,}바이트)")

    existing = app_settings.get_filter_rules_json(stage)
    if existing:
        print(f"  - 주의: DB에 이미 값이 있습니다(덮어씁니다). 기존 {len(existing):,}바이트")

    app_settings.set_filter_rules_json(stage, raw)
    print("  - DB 저장 완료")

    # 되읽어서 원본과 완전히 동일한지(바이트 단위) 확인 — 이관 무결성 확인.
    roundtrip = app_settings.get_filter_rules_json(stage)
    if roundtrip == raw:
        print("  - 검증 OK: DB에서 다시 읽은 내용이 원본 파일과 100% 동일합니다.")
    else:
        print("  - !!! 경고: DB에서 읽은 내용이 원본과 다릅니다. 즉시 보고 필요.")
        sys.exit(1)


def main() -> None:
    if not os.getenv("TURSO_DATABASE_URL") or not os.getenv("TURSO_AUTH_TOKEN"):
        print("TURSO_DATABASE_URL / TURSO_AUTH_TOKEN이 설정돼 있지 않습니다.")
        print(".env 파일에 값이 있는지, 또는 이 스크립트를 프로젝트 루트에서")
        print("실행하고 있는지 확인해주세요.")
        sys.exit(1)

    _migrate_stage(1, _STAGE1_FILE)
    _migrate_stage(2, _STAGE2_FILE)
    print("\n=== 이관 완료 ===")
    print("두 규칙 모두 DB에 안전하게 반영되었고, 원본과 일치함을 확인했습니다.")


if __name__ == "__main__":
    main()
