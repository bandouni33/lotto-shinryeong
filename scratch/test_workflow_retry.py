# -*- coding: utf-8 -*-
"""주간 워크플로의 3회 재시도 루프 검증 (2026-09-27 추가분).

`.github/workflows/weekly_combo_gen.yml`의 조합생성 스텝은 hourly_draw_sync.yml과 같은
3회 재시도 구조다. 이 파일은 그 **구조와 실제 종료 의미**를 검증한다 — 재시도가 성공/실패를
정확히 보고하는지(조용한 성공 금지), 시도 횟수 상한이 지켜지는지.

워커는 bash 함수 스텁으로 대체한다(실제 DB·조합 계산을 건드리지 않는다).
`sleep 30`만 `sleep 0`으로 바꿔 돌린다(상수만 대체, 논리는 그대로).

불변식:
  1) 첫 시도에서 성공하면 재시도하지 않는다 → 종료코드 0, 시도 1회
  2) 3번째 시도에서 성공하면 종료코드 0, 시도 3회 (성공은 성공으로 보고)
  3) 세 번 모두 실패하면 시도 3회(상한) 후 종료코드 1 (실패를 성공으로 넘기지 않음)
  4) YAML 텍스트에 성공 경로 exit 0 / 전부 실패 시 exit 1 이 들어 있다

실행: venv312\\Scripts\\python.exe scratch\\test_workflow_retry.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)

YAML_PATH = ROOT / ".github" / "workflows" / "weekly_combo_gen.yml"


def _find_bash() -> str | None:
    """bash 찾기 — PATH에 없으면 Git for Windows 기본 설치 경로를 본다(실측: 이 PC는 PATH에 없음)."""
    found = shutil.which("bash")
    if found:
        return found
    for cand in (r"C:\Program Files\Git\bin\bash.exe",
                 r"C:\Program Files\Git\usr\bin\bash.exe",
                 r"C:\Program Files (x86)\Git\bin\bash.exe"):
        if Path(cand).exists():
            return cand
    return None


BASH = _find_bash()


def load_generate_run_block() -> str:
    """YAML에서 'combo_gen_worker.py' 실행 스텝의 run: | 블록만 뽑는다(외부 파서 불필요)."""
    lines = YAML_PATH.read_text(encoding="utf-8").splitlines()
    start = next(i for i, l in enumerate(lines) if "combo_gen_worker.py) —" in l)
    run_idx = next(i for i in range(start, len(lines)) if lines[i].strip().startswith("run: |"))
    indent = len(lines[run_idx]) - len(lines[run_idx].lstrip())
    body = []
    for line in lines[run_idx + 1:]:
        if line.strip() and (len(line) - len(line.lstrip())) <= indent:
            break
        body.append(line[indent + 2:] if len(line) > indent else "")
    return "\n".join(body).strip("\n")


class RetryStructureTests(unittest.TestCase):
    """4) YAML 텍스트 불변식 — 재시도 구조가 남아 있는가."""

    def setUp(self):
        self.block = load_generate_run_block()

    def test_has_three_attempt_loop(self):
        self.assertIn("for attempt in 1 2 3", self.block)

    def test_exits_zero_on_success_and_one_after_all_failures(self):
        self.assertIn("exit 0", self.block, "성공 경로가 종료코드를 명시하지 않으면 실패를 성공으로 넘길 수 있다")
        self.assertIn("exit 1", self.block, "전부 실패했는데 종료코드가 없으면 Actions가 성공으로 본다")

    def test_retry_delay_present(self):
        self.assertIn("sleep 30", self.block)

    def test_short_circuits_after_success(self):
        """`if python ...; then exit 0` 형태여야 성공 즉시 빠져나온다(불필요한 재시도 방지)."""
        self.assertRegex(self.block, r"if\s+python\s+combo_gen_worker\.py;\s*then")


@unittest.skipUnless(BASH, "bash 없음 — 실행 검증은 건너뛰고 구조 검증만")
class RetryExecutionTests(unittest.TestCase):
    """1·2·3) 실제로 돌려서 종료코드와 시도 횟수를 본다."""

    def _run(self, succeed_at: int) -> tuple[int, int, str]:
        block = load_generate_run_block().replace("sleep 30", "sleep 0")
        workdir = Path(tempfile.mkdtemp(prefix="lotto_retry_test_"))
        counter = workdir / "counter"
        script = (
            "python() {\n"
            f'  n=$(( $(cat "{counter}" 2>/dev/null || echo 0) + 1 ))\n'
            f'  echo "$n" > "{counter}"\n'
            '  echo "  (워커 스텁 호출 $n회차)"\n'
            f'  [ "$n" -ge {succeed_at} ] && return 0 || return 1\n'
            "}\n"
            + block + "\n"
        )
        # 2026-09-27 수정: bash 출력은 UTF-8인데 text=True는 Windows ANSI(cp949)로 디코딩해
        # 리더 스레드에서 UnicodeDecodeError가 났고 그 탓에 stdout이 None이 됐다(실측).
        proc = subprocess.run([BASH, "-c", script], capture_output=True,
                              encoding="utf-8", errors="replace", timeout=60)
        tries = int(counter.read_text().strip()) if counter.exists() else 0
        shutil.rmtree(workdir, ignore_errors=True)
        return proc.returncode, tries, (proc.stdout or "") + (proc.stderr or "")

    def test_succeeds_first_try_without_retrying(self):
        code, tries, out = self._run(succeed_at=1)
        self.assertEqual(code, 0, out)
        self.assertEqual(tries, 1, f"첫 시도 성공인데 {tries}회 시도함\n{out}")

    def test_third_try_success_reports_success(self):
        code, tries, out = self._run(succeed_at=3)
        self.assertEqual(code, 0, out)
        self.assertEqual(tries, 3, f"3번째 성공인데 {tries}회\n{out}")

    def test_all_failures_end_with_exit_1_and_capped_attempts(self):
        code, tries, out = self._run(succeed_at=99)
        self.assertEqual(tries, 3, f"시도 상한(3)이 지켜지지 않음: {tries}회\n{out}")
        self.assertEqual(code, 1, f"전부 실패했는데 종료코드가 {code}\n{out}")


if __name__ == "__main__":
    import os as _os

    program = unittest.main(verbosity=2, exit=False)
    _os._exit(0 if program.result.wasSuccessful() else 1)
