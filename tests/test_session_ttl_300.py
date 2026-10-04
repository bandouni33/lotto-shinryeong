"""disconnectedSessionTTL 120 → 300 (2026-10-04, 동시접속 확장 3단계) 불변식.

왜 올리는가: Streamlit은 웹소켓이 끊긴 세션을 곧바로 버리지 않고
`server.disconnectedSessionTTL` 초 동안 붙들고 있다가 정리한다(기본 120초).
모바일은 화면을 벗어나면 웹소켓이 끊기므로, 2분을 넘겨 돌아온 사용자는
세션이 사라져 처음부터 다시 그려야 했다(재렌더·재조회 비용). 300초로 올린다.
대가는 메모리다 — 끊긴 세션을 최대 3분 더 보유한다(실측 세션당 약 3.2MB).

이 테스트가 고정하는 것:
  T1 기준점은 한 곳(`.streamlit/config.toml`)이고, `[server]` 표 안의 값이 300이다.
  T2 그 파일을 **Streamlit 자신의 로더**로 읽으면 300이 나온다(기본값 120이 아니다).
     "파일에 썼으니 될 것"이라고 말하지 않기 위해, 서버가 기동할 때 부르는 것과
     같은 함수(`streamlit.web.bootstrap.load_config_options`)로 확인하고,
     설정 파일이 없는 디렉터리에서는 120(기본)이 나오는 것까지 대조한다.
  T3 이 값을 덮어쓸 수 있는 다른 곳(서버 실행 .ps1·CLI 플래그·다른 설정 파일)이 없다
     — 있으면 "기준점 한 곳만 고친다"는 규칙이 깨진다.
  T4 보고서가 대가(메모리 보유)·되돌리는 방법·재시작 필요·직접 재지 못한 부분을
     숨기지 않고 적는다.

실행: venv312\\Scripts\\python.exe -X utf8 tests\\test_session_ttl_300.py
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
CONFIG = ROOT / ".streamlit" / "config.toml"
REPORT = "동시접속확장_3단계_TTL300_2026-10-04.txt"
EXPECTED_TTL = 300
# Streamlit 1.64 기본값(설정 파일이 없을 때 나오는 값)
DEFAULT_TTL = 120

# 설정을 담을 수 있는 파일만 본다(보고서·문서는 제외).
SCAN_SUFFIXES = {".ps1", ".cmd", ".bat", ".toml", ".ini", ".cfg", ".json", ".py"}
# .astra 는 Astra 앱의 세션 기록(대화·체크포인트)이라 설정이 아니다 — 여기에 우연히
# Streamlit 설정 예문이 인용되어 있어도 값을 정하는 파일이 아니다(2026-10-04 실제로 걸렸다).
SCAN_SKIP_DIRS = {"venv312", "__pycache__", ".git", "node_modules", "builds",
                  ".expo", "dist", "htmlcov", ".astra"}

# 서버가 기동할 때 실제로 부르는 경로로 값을 읽는다(파일 파싱이 아니라 로더로).
RESOLVE_CODE = (
    "from streamlit import config\n"
    "from streamlit.web import bootstrap\n"
    "bootstrap.load_config_options({'server.address': '127.0.0.1'})\n"
    "print('RESOLVED_TTL=' + str(config.get_option('server.disconnectedSessionTTL')))\n"
)


def _resolve_ttl(cwd: Path) -> int:
    """Streamlit 로더로 해석한 TTL — cwd를 바꿔 '이 저장소 파일 때문인지'를 가른다."""
    env = {"PYTHONIOENCODING": "utf-8"}
    import os

    full_env = {**os.environ, **env}
    proc = subprocess.run([sys.executable, "-X", "utf8", "-c", RESOLVE_CODE],
                          cwd=str(cwd), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=full_env,
                          timeout=180)
    out = (proc.stdout or "") + (proc.stderr or "")
    found = re.findall(r"RESOLVED_TTL=(\d+)", out)
    assert found, f"TTL을 읽지 못했다(exit={proc.returncode}):\n{out[-1500:]}"
    return int(found[-1])


class ConfigPointTests(unittest.TestCase):
    """T1 — 값은 한 곳에만, 그리고 [server] 표 안에."""

    def test_config_file_exists_and_has_the_value(self):
        self.assertTrue(CONFIG.exists(), f"기준점 파일이 없다: {CONFIG}")
        text = CONFIG.read_text(encoding="utf-8")
        hits = [ln for ln in text.splitlines()
                if ln.strip().startswith("disconnectedSessionTTL")]
        self.assertEqual(len(hits), 1, f"이 줄이 정확히 하나여야 한다: {hits}")
        self.assertEqual(hits[0].strip(), f"disconnectedSessionTTL = {EXPECTED_TTL}")

    def test_value_sits_inside_the_server_table(self):
        try:
            import tomllib
        except ModuleNotFoundError:  # 3.10 이하 — 파이썬이 낮으면 파싱만 건너뛴다
            self.skipTest("tomllib 없음(파이썬 < 3.11)")
        data = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
        self.assertIn("server", data, "[server] 표가 없다")
        self.assertEqual(data["server"].get("disconnectedSessionTTL"), EXPECTED_TTL,
                         "[server] 안에 값이 없다 — 다른 표에 들어가면 무시된다")
        # 최상위(표 밖)에 있으면 Streamlit이 읽지 않는다 — 그 실수를 잠근다.
        self.assertNotIn("disconnectedSessionTTL", data)


class LoaderTests(unittest.TestCase):
    """T2 — 서버가 쓰는 로더가 300을 본다. 기본값 120과 대조한다."""

    def test_loader_resolves_project_setting(self):
        self.assertEqual(_resolve_ttl(ROOT), EXPECTED_TTL,
                         "이 저장소에서 Streamlit이 300을 읽지 못한다")

    def test_loader_falls_back_to_default_without_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(_resolve_ttl(Path(tmp)), DEFAULT_TTL,
                             f"설정이 없을 때 기본값이 {DEFAULT_TTL}이 아니다 — "
                             "그렇다면 300이 이 파일 때문인지 알 수 없다")


class NoOverrideTests(unittest.TestCase):
    """T3 — 덮어쓰는 곳이 없어야 '한 곳만 고친다'가 성립한다."""

    def _scan(self) -> dict[Path, list[str]]:
        me = Path(__file__).resolve()
        hits: dict[Path, list[str]] = {}
        for path in ROOT.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SCAN_SUFFIXES:
                continue
            if any(part in SCAN_SKIP_DIRS for part in path.parts):
                continue
            if path.resolve() in (me, CONFIG.resolve()):
                # 검사기 자신은 설정이 아니고(설명 문장), config.toml은 기준점이다.
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            lines = [ln for ln in text.splitlines() if "disconnectedSessionTTL" in ln]
            if lines:
                hits[path] = lines
        return hits

    def test_no_other_file_sets_or_overrides_it(self):
        for path, lines in self._scan().items():
            for line in lines:
                stripped = line.strip()
                if stripped.startswith(("#", "//", "<!--", "*")):
                    continue  # 주석은 값이 아니다(실행에 영향 없음)
                self.fail(f"{path.relative_to(ROOT)} 가 값을 건드린다: {stripped}")

    def test_server_scripts_do_not_pass_a_cli_flag(self):
        for name in ("run_server.ps1", "keep_server_up.ps1", "register_server_task.ps1"):
            path = ROOT / name
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            self.assertNotIn("--server.disconnectedSessionTTL", text,
                             f"{name} 이 CLI 플래그로 덮어쓴다 — 기준점이 둘이 된다")


class ReportTests(unittest.TestCase):
    """T4 — 대가와 한계를 적은 보고서가 두 곳에 같은 크기로 있는가."""

    def _report(self) -> str:
        path = ROOT / REPORT
        self.assertTrue(path.exists(), f"보고서가 없다: {path}")
        return path.read_text(encoding="utf-8")

    def test_report_states_change_cost_and_rollback(self):
        text = self._report()
        self.assertIn(f"{DEFAULT_TTL} → {EXPECTED_TTL}", text)
        self.assertIn("3.2MB", text, "메모리 보유라는 대가를 수치로 적어야 한다")
        self.assertIn("되돌리", text, "되돌리는 방법이 있어야 한다")
        self.assertIn("재시작", text, "재시작이 필요하다는 사실이 있어야 한다")

    def test_report_is_honest_about_what_was_not_measured(self):
        text = self._report()
        self.assertIn("미검증", text,
                      "직접 재지 못한 부분(실제 보유 시간)을 적어야 한다")
        self.assertIn("격리", text, "검증에 쓴 방법(격리 인스턴스)을 밝혀야 한다")

    def test_both_copies_match(self):
        project = ROOT / REPORT
        self.assertGreater(project.stat().st_size, 800)
        downloads = Path.home() / "Downloads" / REPORT
        if downloads.parent.exists():
            self.assertTrue(downloads.exists(), f"다운로드 사본이 없다: {downloads}")
            self.assertEqual(downloads.stat().st_size, project.stat().st_size)


if __name__ == "__main__":
    unittest.main(verbosity=2)
