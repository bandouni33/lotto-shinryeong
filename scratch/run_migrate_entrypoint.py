# -*- coding: utf-8 -*-
"""migrate_filter_rules_to_db.py 를 **사용자가 만나는 방식 그대로**(main() 실행) 돌려
격리 DB에서 계약을 확인한다 (2026-09-27).

운영 Turso는 절대 건드리지 않는다 — 이 스크립트는 DB에 **쓰기**를 하므로,
프로젝트 공식 격리(tests/_db_isolation.isolated_db)만 사용한다(AGENTS.md 규칙).

확인하는 불변식:
  A. 자격증명이 없으면 안내를 출력하고 exit 1 — DB를 한 번도 만지지 않는다
  B. 정상 입력이면 두 단계 모두 DB에 들어가고, 되읽은 값이 **원본 파일과 바이트 단위 동일**
  C. 같은 것을 두 번 돌려도(멱등) 결과가 같고 exit 0 — 두 번째는 '이미 값이 있음'을 알린다
  D. 깨진 JSON은 올리지 않는다(stage1 깨짐 → 쓰기 0건 / stage2 깨짐 → stage1만 반영)
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.chdir(ROOT)

import env_loader  # noqa: E402

env_loader.load_dotenv_file()

import app_settings  # noqa: E402
import migrate_filter_rules_to_db as mig  # noqa: E402
from _db_isolation import isolated_db  # noqa: E402

CREDS = ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN")
fails: list[str] = []


def run_entry() -> tuple[int, str]:
    """사용자가 실행하는 그 진입점 — main()을 stdout 캡처와 함께 호출."""
    buf = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(buf):
        try:
            mig.main()
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return code, buf.getvalue()


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
    if not cond:
        fails.append(label)


def main() -> int:
    stage1_raw = Path(mig._STAGE1_FILE).read_text(encoding="utf-8")
    stage2_raw = Path(mig._STAGE2_FILE).read_text(encoding="utf-8")
    print("=" * 92)
    print(f"입력: stage1 {len(stage1_raw):,}자 · stage2 {len(stage2_raw):,}자 (실제 로컬 규칙 파일)")

    # ── A. 자격증명 없음
    print("\nA. 자격증명이 없을 때 (실제로는 .env가 있지만 override=False라 빈 값이 이김)")
    with isolated_db() as db:
        saved = {k: os.environ.get(k) for k in CREDS}
        os.environ["TURSO_DATABASE_URL"] = ""
        os.environ["TURSO_AUTH_TOKEN"] = ""
        try:
            code, out = run_entry()
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        check("exit 1", code == 1, f"code={code}")
        check("안내 문구 출력", "설정돼 있지 않습니다" in out)
        check("DB에 아무것도 안 씀(1차)", app_settings.get_filter_rules_json(1) == "")
        check("DB에 아무것도 안 씀(2차)", app_settings.get_filter_rules_json(2) == "")
        print(f"     (격리 DB 파일: {Path(db).name})")

    # ── B. 정상 이관 (1회차)
    print("\nB. 정상 이관")
    with isolated_db() as db:
        code, out = run_entry()
        check("exit 0", code == 0, f"code={code}")
        check("두 단계 모두 '검증 OK'", out.count("검증 OK") == 2, out.count("검증 OK"))
        check("'이관 완료' 출력", "이관 완료" in out)
        r1, r2 = app_settings.get_filter_rules_json(1), app_settings.get_filter_rules_json(2)
        check("1차 바이트 단위 동일", r1 == stage1_raw, f"{len(r1):,}자 vs {len(stage1_raw):,}자")
        check("2차 바이트 단위 동일", r2 == stage2_raw, f"{len(r2):,}자 vs {len(stage2_raw):,}자")
        check("규칙 개수 보존(1차 381=고정378+AUTO3)",
              len(json.loads(r1)) == 381 and sum(1 for r in json.loads(r1) if r["is_auto"]) == 3)
        check("규칙 개수 보존(2차 48)", len(json.loads(r2)) == 48)

        # ── C. 멱등성 (2회차)
        print("\nC. 같은 것을 두 번 (멱등)")
        before = (r1, r2)
        code2, out2 = run_entry()
        check("2회차 exit 0", code2 == 0, f"code={code2}")
        check("'이미 값이 있습니다' 경고", "이미 값이 있습니다" in out2)
        after = (app_settings.get_filter_rules_json(1), app_settings.get_filter_rules_json(2))
        check("2회차 후에도 내용 동일", before == after)

    # ── D. 깨진 JSON은 올리지 않는다
    print("\nD. 깨진 입력")
    tmp = Path(tempfile.mkdtemp(prefix="lotto_mig_test_"))
    try:
        bad = tmp / "broken_stage1.json"
        bad.write_text("{이건 JSON이 아님", encoding="utf-8")
        good = tmp / "good_stage2.json"
        good.write_text(stage2_raw, encoding="utf-8")
        orig = (mig._STAGE1_FILE, mig._STAGE2_FILE)
        mig._STAGE1_FILE, mig._STAGE2_FILE = str(bad), str(good)
        try:
            with isolated_db():
                # main()은 예외를 잡지 않으므로 JSONDecodeError가 그대로 올라온다
                try:
                    mig.main()
                    raised = False
                except json.JSONDecodeError:
                    raised = True
                check("깨진 stage1 → 예외로 중단", raised)
                check("깨진 stage1 → 1차 쓰기 0건", app_settings.get_filter_rules_json(1) == "")
                check("깨진 stage1 → 2차도 안 씀(순서상 중단)", app_settings.get_filter_rules_json(2) == "")

            # stage2만 깨진 경우 — 1차는 이미 반영된 뒤 중단된다(경계)
            mig._STAGE1_FILE, mig._STAGE2_FILE = str(Path(orig[0])), str(bad)
            with isolated_db():
                try:
                    mig.main()
                    raised2 = False
                except json.JSONDecodeError:
                    raised2 = True
                check("깨진 stage2 → 예외로 중단", raised2)
                check("깨진 stage2 → 1차는 이미 반영됨(알려진 경계)",
                      app_settings.get_filter_rules_json(1) == stage1_raw)
                check("깨진 stage2 → 2차는 안 씀", app_settings.get_filter_rules_json(2) == "")
        finally:
            mig._STAGE1_FILE, mig._STAGE2_FILE = orig
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 92)
    print(f"검사 실패 {len(fails)}건" + ("" if not fails else ": " + " · ".join(fails)))
    print("판정: " + ("모든 계약 확인" if not fails else "!! 위 항목 확인 필요"))
    return 1 if fails else 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
