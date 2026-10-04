"""disconnectedSessionTTL 설정의 불변식 (2026-10-04, 값 300 → 120 롤백 반영).

무엇을 고정하는가 — 이 값은 **저장소 설정 파일 하나**가 기준점이다(모든 배포가 이 파일을 읽는다).
  2026-10-04 이력: 3단계에서 300으로 올렸다가 같은 날 120으로 되돌렸다. 이유는 Cloud가 이 파일을
  재배포 때 그대로 읽는데(운영 Turso 공유가 확인됨), "Cloud(2 vCPU/2.7GB 고정)가 끊긴 세션을
  3분 더 보유하는 메모리를 감당하는지"를 우리가 확인할 수단이 없었기 때문이다.
  → 그래서 이름을 값(300)이 아니라 **설정 자체**(session_ttl_setting)로 둔다.

이 테스트가 고정하는 것:
  T1 파일에 **명시적으로** 값이 적혀 있고 `[server]` 표 안에 있다(기본값과 같더라도 명시해야
     의도된 값인지 '아무도 안 정한 값'인지 구분된다).
  T2 그 파일을 **Streamlit 자기 로더**가 실제로 읽는다 — 같은 파일을 임시 위치에 복사해 값을
     다르게 바꿔 넣으면 그 값이 나오는지로 확인한다(기본값과 값이 같아져서 '우리 파일을 읽은
     것'과 '기본값을 쓴 것'이 구분되지 않는 문제를 우회한다).
  T3 덮어쓰는 곳이 없다 — 서버 실행 스크립트의 CLI 플래그, 다른 설정/파이썬 파일.
  T4 문서: Cloud 보고서가 롤백 사실과 값(120)을 적는다(되돌린 경위가 남아야 다음 판단이 된다).

실행: venv312\\Scripts\\python.exe -X utf8 tests\\test_session_ttl_setting.py
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
CONFIG = ROOT / ".streamlit" / "config.toml"
REPORT_NAME = "Cloud_공유DB_확인_상한롤백_2026-10-04.txt"
EXPECTED_TTL = 120
STREAMLIT_DEFAULT = 120  # Streamlit 1.64 기본값

SCAN_SUFFIXES = {".ps1", ".cmd", ".bat", ".toml", ".ini", ".cfg", ".json", ".py"}
SCAN_SKIP_DIRS = {"venv312", "__pycache__", ".git", "node_modules", "builds",
                  ".expo", "dist", "htmlcov", ".astra"}

RESOLVE_CODE = (
    "from streamlit import config\n"
    "from streamlit.web import bootstrap\n"
    "bootstrap.load_config_options({'server.address': '127.0.0.1'})\n"
    "print('RESOLVED_TTL=' + str(config.get_option('server.disconnectedSessionTTL')))\n"
)


def _resolve_ttl(cwd: Path) -> int:
    import os

    proc = subprocess.run([sys.executable, "-X", "utf8", "-c", RESOLVE_CODE],
                          cwd=str(cwd), capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=180)
    out = (proc.stdout or "") + (proc.stderr or "")
    found = re.findall(r"RESOLVED_TTL=(\d+)", out)
    assert found, f"TTL을 읽지 못했다(exit={proc.returncode}):\n{out[-1200:]}"
    return int(found[-1])


class ConfigPointTests(unittest.TestCase):
    def test_T1_value_is_explicit_and_inside_the_server_table(self):
        self.assertTrue(CONFIG.exists(), f"기준점 파일이 없다: {CONFIG}")
        text = CONFIG.read_text(encoding="utf-8")
        hits = [ln for ln in text.splitlines()
                if ln.strip().startswith("disconnectedSessionTTL")]
        self.assertEqual(len(hits), 1, f"이 줄이 정확히 하나여야 한다: {hits}")
        self.assertEqual(hits[0].strip(), f"disconnectedSessionTTL = {EXPECTED_TTL}")
        try:
            import tomllib
        except ModuleNotFoundError:
            self.skipTest("tomllib 없음(파이썬 < 3.11)")
        data = tomllib.loads(text)
        self.assertIn("server", data)
        self.assertEqual(data["server"].get("disconnectedSessionTTL"), EXPECTED_TTL,
                         "[server] 안에 값이 없다 — 다른 표에 있으면 무시된다")
        self.assertNotIn("disconnectedSessionTTL", data, "최상위(표 밖) 값은 읽히지 않는다")


class LoaderTests(unittest.TestCase):
    def test_T2_repo_config_resolves_to_the_expected_value(self):
        self.assertEqual(_resolve_ttl(ROOT), EXPECTED_TTL)

    def test_T2_the_file_is_really_read_by_streamlit(self):
        # 값이 기본값과 같아도 '우리 파일을 읽었다'를 증명해야 한다: 임시 위치에 값을
        # 다르게 바꿔 복사해 넣고, 그 값이 나오는지 본다.
        probe = 137
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / ".streamlit").mkdir()
            text = CONFIG.read_text(encoding="utf-8").replace(
                f"disconnectedSessionTTL = {EXPECTED_TTL}",
                f"disconnectedSessionTTL = {probe}")
            (tmp_path / ".streamlit" / "config.toml").write_text(text, encoding="utf-8")
            self.assertEqual(_resolve_ttl(tmp_path), probe,
                             "설정 파일이 실제로 읽히지 않는다 — 기준점이 무의미해진다")

    def test_T2_default_is_what_we_think_it_is(self):
        # 우리 값이 Streamlit 기본값과 같아졌으므로, 기본값 자체를 확인해 둔다
        # (기본값이 바뀌면 우리 값도 의도와 달라진다).
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(_resolve_ttl(Path(tmp)), STREAMLIT_DEFAULT,
                             "Streamlit 기본값이 바뀌었다 — 이 테스트의 전제를 다시 본다")


class NoOverrideTests(unittest.TestCase):
    def test_T3_no_other_file_sets_or_overrides_it(self):
        me = Path(__file__).resolve()
        for path in ROOT.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SCAN_SUFFIXES:
                continue
            if any(part in SCAN_SKIP_DIRS for part in path.parts):
                continue
            if path.resolve() in (me, CONFIG.resolve()):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line in text.splitlines():
                if "disconnectedSessionTTL" not in line:
                    continue
                stripped = line.strip()
                if stripped.startswith(("#", "//", "<!--", "*")):
                    continue
                self.fail(f"{path.relative_to(ROOT)} 가 값을 건드린다: {stripped}")

    def test_T3_server_scripts_do_not_pass_a_cli_flag(self):
        for name in ("run_server.ps1", "keep_server_up.ps1", "register_server_task.ps1"):
            path = ROOT / name
            if not path.exists():
                continue
            self.assertNotIn("--server.disconnectedSessionTTL",
                             path.read_text(encoding="utf-8", errors="replace"),
                             f"{name} 이 CLI 플래그로 덮어쓴다 — 기준점이 둘이 된다")


class DocumentedRollbackTests(unittest.TestCase):
    def test_T4_cloud_report_records_the_rollback(self):
        path = ROOT / REPORT_NAME
        self.assertTrue(path.exists(), f"보고서가 없다: {path}")
        text = path.read_text(encoding="utf-8")
        self.assertIn("120", text, "롤백한 값이 보고서에 없다")
        self.assertRegex(text, re.compile(r"되돌[리렸]"), "되돌렸다는 사실이 적혀야 한다")

    def test_T4_both_copies_match(self):
        project = ROOT / REPORT_NAME
        downloads = Path.home() / "Downloads" / REPORT_NAME
        if downloads.parent.exists():
            self.assertTrue(downloads.exists(), f"다운로드 사본이 없다: {downloads}")
            self.assertEqual(downloads.stat().st_size, project.stat().st_size)


if __name__ == "__main__":
    unittest.main(verbosity=2)
