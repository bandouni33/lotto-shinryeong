"""Cloud 관측 재조준(2026-10-04)의 불변식 — 대상·경로·읽기 전용 성질을 잠근다.

배경: 관측 도구·예약 작업이 **트래픽 0인 이 PC**를 보고 있었다(대상 오류). Cloud로 바꾸면서
실측으로 알게 된 제약이 둘 있다.
  · Cloud는 **익명 웹소켓을 HTTP 401로 거부**한다(같은 시각 HTTP 페이지는 200). 그래서
    Cloud 모드에서는 웹소켓 렌더를 시도하면 안 되고, 시도하지 않은 것을 '성공(ok=1)'처럼
    남기면 조용한 거짓이 된다.
  · Cloud 경로는 `/~/+/` 여야 한다(루트 `/` 와 `/_stcore/health` 는 303으로 돌려보낸다).
그리고 관측자는 **읽기 전용**이어야 한다(운영 DB에 아무것도 쓰지 않는다).

이 테스트가 고정하는 것:
  C1 대상 가드 : 웹소켓 렌더는 local 분기에서만 한다.
  C2 실패 표식 : Cloud 분기의 probe 는 ok=0 + 명시적 사유를 담는다(0으로 위장 금지).
  C3 경로·대상 : 예약 작업 스크립트가 `/~/+/` 를 쓰고 --target cloud 를 넘긴다.
  C4 실패 구분 : 공유 DB 세션 조회는 실패 시 -1(0='없음'과 구분).
  C5 읽기 전용 : 관측자 소스에 쓰기 SQL(INSERT/UPDATE/DELETE)이 없다.
  C6 보고서    : 롤백 사실과 값(60)이 적혀 있고 두 사본이 같다.

실행: venv312\\Scripts\\python.exe -X utf8 tests\\test_cloud_observation_target.py
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OBSERVER = ROOT / "scratch" / "observe_live_traffic.py"
OBSERVER_SRC = OBSERVER.read_text(encoding="utf-8")
REGISTER_SRC = (ROOT / "register_observer_task.ps1").read_text(encoding="utf-8")
REPORT_NAME = "Cloud_공유DB_확인_상한롤백_2026-10-04.txt"


class TargetGuardTests(unittest.TestCase):
    def test_C1_websocket_probe_runs_only_in_local_mode(self):
        self.assertIn("if local:", OBSERVER_SRC,
                      "local/cloud 분기가 사라졌다 — Cloud에서 웹소켓을 시도하게 된다")
        body = OBSERVER_SRC.split("if local:")[1].split("else:")[0]
        self.assertIn("await _probe(", body,
                      "local 분기가 웹소켓 렌더를 하지 않는다(로컬 관측이 무의미해진다)")
        cloud_body = OBSERVER_SRC.split("if local:")[1].split("else:")[1]
        self.assertNotIn("await _probe(", cloud_body.split("new_rows")[0],
                         "Cloud 분기에서 웹소켓 렌더를 시도한다 — 401로 실패만 쌓인다")

    def test_C2_cloud_mode_marks_the_probe_as_disabled_not_successful(self):
        cloud_body = OBSERVER_SRC.split("if local:")[1].split("else:")[1]
        head = cloud_body.split("new_rows")[0]
        self.assertIn('"ok": 0', head, "Cloud 분기가 성공(ok=1)으로 위장할 수 있다")
        self.assertIn("401", head, "Cloud 401 사유가 코드에 남아 있지 않다(왜 못 쓰는지 알 수 없다)")
        self.assertIn('"script_ms": None', head,
                      "측정하지 않은 렌더 시간을 숫자처럼 남기면 안 된다")

    def test_C3_task_points_at_cloud_with_the_real_path(self):
        self.assertIn('$Target = "cloud"', REGISTER_SRC,
                      "기본 대상이 Cloud가 아니다(트래픽 0인 PC를 관측하게 된다)")
        self.assertIn("/~/+/", REGISTER_SRC,
                      "Cloud 경로(/~/+/)를 쓰지 않는다 — 루트 / 는 303이다")
        self.assertNotIn('$BaseUrl/_stcore/health"', REGISTER_SRC.replace(
            "_stcore/health --page", "X"), "health 를 루트 바로 아래 경로로 부른다")
        for needed in ("--target", "--health", "--page", "--url", "--interval", "--duration"):
            self.assertIn(needed, REGISTER_SRC, f"예약 작업 인자에서 {needed} 가 빠졌다")

    def test_C4_db_lookup_failure_is_distinguishable_from_zero(self):
        self.assertIn("return -1", OBSERVER_SRC,
                      "DB 조회 실패를 0(없음)으로 뭉개면 '조용한 0건'이 된다")
        self.assertIn("db_sessions_since_last", OBSERVER_SRC)

    def test_C5_observer_never_writes(self):
        for verb in ("INSERT ", "UPDATE ", "DELETE "):
            self.assertNotIn(verb, OBSERVER_SRC,
                             f"관측자에 쓰기 SQL({verb.strip()})이 들어 있다 — 읽기 전용이어야 한다")


class ReportTests(unittest.TestCase):
    def _report(self) -> str:
        path = ROOT / REPORT_NAME
        self.assertTrue(path.exists(), f"보고서가 없다: {path}")
        return path.read_text(encoding="utf-8")

    def test_C6_report_records_the_rollback_and_the_value(self):
        text = self._report()
        self.assertIn("60", text, "롤백한 값이 보고서에 없다")
        self.assertIn("22:37:10", text, "롤백 시각(DB 재확인 근거)이 없다")
        self.assertIn("공유", text, "DB 공유 사실이 적혀 있어야 한다")
        self.assertRegex(text, re.compile(r"22:19:55"),
                         "공유 판정의 핵심 증거(서버 다운타임 중 기록)가 빠졌다")

    def test_C6_report_states_what_we_cannot_see(self):
        text = self._report()
        self.assertIn("401", text, "Cloud 웹소켓 401 한계가 적혀 있어야 한다")
        self.assertIn("대시보드", text, "Cloud 자원을 우리가 볼 수 없다는 한계가 필요하다")

    def test_C6_both_copies_match(self):
        project = ROOT / REPORT_NAME
        downloads = Path.home() / "Downloads" / REPORT_NAME
        if downloads.parent.exists():
            self.assertTrue(downloads.exists(), f"다운로드 사본이 없다: {downloads}")
            self.assertEqual(downloads.stat().st_size, project.stat().st_size)


if __name__ == "__main__":
    unittest.main(verbosity=2)
