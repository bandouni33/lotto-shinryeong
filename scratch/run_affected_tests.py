"""AGENTS §2 — wallet_ui.py를 건드렸을 때 걸리는 기존 테스트를 모아 실행한다.

배너·적립금 안내창·로그인 게이트는 기준점 A/K/L/M이라, 그 기준점 파일을 고치면
"같이 영향받는 곳"의 테스트를 전부 돌려 결과를 보고해야 한다(§2 표).

pytest 없음(§3) — 각 파일의 __main__ 러너로 돌린다.
실행: venv312\\Scripts\\python.exe scratch\\run_affected_tests.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = [
    "tests/test_dialog_registry.py",          # A/K/L — 다이얼로그 레지스트리·적립금 안내
    "tests/test_login_gate_callbacks.py",     # A  — 배너 버튼 콜백
    "tests/test_kakao_login_branch_links.py", # M  — 카카오 분기 링크(웹/앱)
    "tests/test_resume_and_experiment.py",    # A  — 로그인 후 재개
    "tests/test_tarot_gate_flow.py",          # K/L/M — 타로 게이트
    "tests/test_auth_banner_js_target.py",    # 이번 변경의 불변식
]


def main() -> int:
    bad = []
    for rel in FILES:
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", rel],
            cwd=ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        tail = [ln for ln in proc.stdout.splitlines() if ln.strip()][-1:] or ["(출력 없음)"]
        print(f"{'OK  ' if proc.returncode == 0 else 'FAIL'} {rel}  rc={proc.returncode}  {tail[0]}")
        if proc.returncode != 0:
            bad.append(rel)
            for ln in proc.stdout.splitlines():
                if ln.startswith(("FAIL", "ERROR")):
                    print(f"       {ln}")
            if proc.stderr.strip():
                print(f"       stderr: {proc.stderr.strip()[:300]}")
        sys.stdout.flush()
    print(f"\n{len(FILES) - len(bad)}/{len(FILES)} 파일 통과")
    if bad:
        print("실패: " + ", ".join(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
