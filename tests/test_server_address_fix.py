"""PC서버 주소 고정 1단계 — 스크립트·보고서의 불변식 (2026-10-04 신규).

이번 단계에서 실제로 사고가 난 지점이 둘이고, 둘 다 "파일이 그냥 존재하는가"로는 안 잡힌다.

  S1 인코딩 — PowerShell 5.1은 **BOM 없는 UTF-8을 ANSI(cp949)로 읽는다.** 한글 주석을 넣은
     스크립트는 따옴표 짝이 무너져 **파싱 자체가 실패**했다(그래서 서버 자동 복구가 안 돌았다).
     → 세 스크립트는 ASCII 전용이어야 하고, PowerShell 파서가 0 오류로 읽어야 한다.
  S2 구버전 IP 하드코딩 — 죽은 IP가 두 곳(.env, run_server.ps1 기본값)에 박혀 있었다.
     → 스크립트에 공인 IP 상수가 남아 있으면 안 된다(자동 감지 + 호스트명 인자).
  S3 schtasks 거짓 성공 — `schtasks /create`는 작업을 만들지 못해도 종료코드 0을 준다.
     → 등록 스크립트는 **작업 존재 여부를 조회해서** 성공을 판정해야 한다.
  S4 보고서 — 두 곳(프로젝트·다운로드)에 같은 크기로 있어야 하고, 가리키는 파일이 실재해야 하며,
     실측값(현 공인 IP·PID·감시 로그 문구·작업 이름)이 그대로 들어 있어야 한다.
  S5 조립 상태 — 작업 스케줄러에 작업이 실제로 등록돼 있고, 8501이 응답해야 한다.

실행: venv312\\Scripts\\python.exe -X utf8 tests\\test_server_address_fix.py
"""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
import urllib.request
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCRIPTS = ("run_server.ps1", "keep_server_up.ps1", "register_server_task.ps1")
REPORT_NAME = "동시접속확장_1단계_서버주소고정_2026-10-04.txt"
TASK_NAME = "LottoShinryeongServer"
# 절대 남아 있으면 안 되는 죽은 주소들(2026-10-04 실측).
STALE_IPS = ("210.99.230.83", "220.127.15.204")
DOWNLOADS = Path.home() / "Downloads"


def powershell(script: str, timeout: int = 60) -> str:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT),
        timeout=timeout,
    )
    return (out.stdout or "") + (out.stderr or "")


class EncodingAndParseTests(unittest.TestCase):
    """S1 — 이번 단계에서 실제로 스크립트를 못 돌게 만든 함정."""

    def test_scripts_are_ascii_only(self):
        for name in SCRIPTS:
            path = ROOT / name
            self.assertTrue(path.exists(), f"없다: {name}")
            data = path.read_bytes()
            bad = [(i, b) for i, b in enumerate(data) if b > 127]
            self.assertFalse(
                bad,
                f"{name}에 비-ASCII 바이트 {len(bad)}개(첫 위치 {bad[:1]}) — PS 5.1은 BOM 없는 "
                f"파일을 cp949로 읽어 파싱이 깨진다",
            )

    def test_powershell_parser_accepts_every_script(self):
        listing = ",".join(f"'{n}'" for n in SCRIPTS)
        script = (
            f"foreach ($f in @({listing})) {{ "
            "$e=$null; "
            "[void][System.Management.Automation.Language.Parser]::ParseFile("
            "(Join-Path (Get-Location) $f), [ref]$null, [ref]$e); "
            "'{0} {1}' -f $f, $e.Count }"
        )
        out = powershell(script)
        counts = dict(re.findall(r"([\w.\-]+\.ps1)\s+(\d+)", out))
        for name in SCRIPTS:
            self.assertIn(name, counts, f"파서 결과를 못 읽었다: {out!r}")
            self.assertEqual(int(counts[name]), 0, f"{name} 파싱 오류 {counts[name]}건")


class ScriptContentTests(unittest.TestCase):
    """S2·S3 — 죽은 IP 금지, 자동 감지, schtasks 거짓 성공 방지."""

    def test_no_stale_ip_as_a_value(self):
        """구버전 IP가 **주석 밖(코드 값)에** 남아 있으면 안 된다.

        주석에 "예전엔 이 IP가 박혀 있었다"고 적어두는 것은 기록이므로 허용한다.
        """
        for name in SCRIPTS:
            for i, raw in enumerate((ROOT / name).read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if raw.strip().startswith("#"):
                    continue
                for ip in STALE_IPS:
                    self.assertNotIn(ip, raw, f"{name}:{i} 코드에 구버전 IP {ip}가 남아 있다")

    def test_run_server_detects_address_instead_of_hardcoding(self):
        text = (ROOT / "run_server.ps1").read_text(encoding="utf-8")
        self.assertIn("Get-NetIPAddress", text, "현 공인 IP를 스스로 찾아야 한다")
        self.assertIn("$PublicHost", text)
        self.assertIn('Alias("PublicIp")', text, "기존 -PublicIp 사용법을 깨면 안 된다")
        # 주소를 못 찾았을 때 빈 인자를 넘기지 않아야 한다(오리진 판정 보호)
        self.assertIn("if ($PublicHost) {", text)

    def test_keepalive_is_quiet_when_already_listening(self):
        text = (ROOT / "keep_server_up.ps1").read_text(encoding="utf-8")
        self.assertIn("Get-NetTCPConnection", text)
        self.assertRegex(text, r"if \(\$listening\) \{\s*\r?\n\s*exit 0",
                         "이미 떠 있으면 아무 것도 하지 않고 끝나야 한다")
        self.assertIn("run_server.ps1", text, "죽어 있으면 서버를 다시 띄워야 한다")
        self.assertIn("Win32_Process", text, "시작 중인 인스턴스와 겹치지 않게 프로세스도 본다")

    def test_register_script_judges_success_by_querying(self):
        text = (ROOT / "register_server_task.ps1").read_text(encoding="utf-8")
        self.assertIn("Test-TaskExists", text)
        self.assertRegex(text, r"schtasks /query /tn \$Name", "생성 성공을 조회로 판정해야 한다")
        self.assertIn("/sc minute /mo 5", text, "크래시 복구 주기 작업")
        self.assertIn("/ru SYSTEM", text, "관리자 권한이 있을 때의 상시화 명령을 안내해야 한다")


class ReportTests(unittest.TestCase):
    """S4 — 보고서 산출물(사용자 규칙: 프로젝트 + 다운로드 두 곳)."""

    def test_report_exists_in_both_places_with_same_size(self):
        project = ROOT / REPORT_NAME
        self.assertTrue(project.exists(), f"프로젝트 보고서가 없다: {project}")
        self.assertGreater(project.stat().st_size, 5000)
        if DOWNLOADS.exists():
            copy = DOWNLOADS / REPORT_NAME
            self.assertTrue(copy.exists(), f"다운로드 사본이 없다: {copy}")
            self.assertEqual(copy.stat().st_size, project.stat().st_size)

    def test_report_points_only_at_existing_files(self):
        report = (ROOT / REPORT_NAME).read_text(encoding="utf-8")
        tokens = set()
        for raw in report.replace(",", " ").replace("·", " ").split():
            token = raw.split("(")[0].strip().rstrip(".)")
            if token.startswith(("scratch/", "scripts/")) or token in SCRIPTS:
                tokens.add(token)
        self.assertTrue(tokens, "보고서가 파일을 하나도 안 가리킨다")
        for token in sorted(tokens):
            self.assertTrue((ROOT / token).exists(), f"보고서가 가리키는 파일이 없다: {token}")

    def test_report_carries_the_measured_facts(self):
        report = (ROOT / REPORT_NAME).read_text(encoding="utf-8")
        for must in ("220.127.118.224", "125.141.115.106", TASK_NAME, "LottoShinryeongDDNS",
                     "lottoshinryeong.duckdns.org",
                     "port 8501 not listening - starting run_server.ps1",
                     "3/3", "2시간", "공유기 없음(NAT 없음)"):
            self.assertIn(must, report, f"보고서에 실측 근거 {must!r}가 없다")
        # PID·IP 같은 수시로 바뀌는 값을 숫자로 박아두면 보고서가 금방 거짓이 된다 —
        # 숫자 자체가 아니라 "가동 중 서버의 PID를 근거로 적었다"는 사실만 확인한다.
        self.assertRegex(report, r"PID \d{3,7}")
        self.assertIn("script_finished", report, "앱 레벨 확인 근거가 있어야 한다")

    def test_report_limits_are_stated(self):
        """한계를 숨기면 안 된다 — 로그온 유지 필요·onlogon 관리자 필요·DDNS 미완."""
        report = (ROOT / REPORT_NAME).read_text(encoding="utf-8")
        for must in ("로그온해 있는 동안만", "관리자 권한이 필요", "DuckDNS"):
            self.assertIn(must, report, f"한계/차단 사유 {must!r}가 보고서에 없다")


class KeepaliveLogTests(unittest.TestCase):
    """감시 로그가 쌓였다면 형식이 일정해야 한다(없으면 아직 아무 사건도 없었다는 뜻)."""

    def test_log_lines_follow_the_documented_format(self):
        log = ROOT / "server_keepalive.log"
        if not log.exists():
            self.skipTest("감시 로그 없음 = 아직 재시작 사건이 없었다")
        lines = [ln.lstrip("\ufeff") for ln in log.read_text(encoding="utf-8", errors="replace").splitlines()]
        lines = [ln for ln in lines if ln.strip()]
        self.assertTrue(lines)
        for line in lines:
            # 첫 줄에 BOM이 붙는 것은 Add-Content -Encoding UTF8(PS 5.1)의 특성이다 — 내용은 정상.
            self.assertRegex(line, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}  .+$", line)


class AssembledStateTests(unittest.TestCase):
    """S5 — 조립된 상태: 작업이 등록돼 있고, 서버가 실제로 응답한다."""

    def test_scheduled_task_exists(self):
        out = subprocess.run(["schtasks", "/query", "/tn", TASK_NAME],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace")
        self.assertEqual(out.returncode, 0, f"작업이 없다: {out.stdout}{out.stderr}")

    def test_server_answers_on_8501(self):
        with urllib.request.urlopen("http://127.0.0.1:8501/", timeout=15) as resp:
            body = resp.read(4000).decode("utf-8", errors="replace")
        self.assertEqual(resp.status, 200)
        self.assertIn("streamlit", body.lower(), "Streamlit 문서가 아니다")

    def test_keepalive_script_can_be_run_without_side_effects_while_up(self):
        out = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(ROOT / "keep_server_up.ps1")],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(ROOT), timeout=60)
        self.assertEqual(out.returncode, 0, f"{out.stdout}{out.stderr}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
