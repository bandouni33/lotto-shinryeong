"""2단계(상한 120 · 30분 관측) 산출물·도구의 불변식 (2026-10-04 신규).

무엇을 고정하는가 — 이번 단계에서 실제로 사고가 날 수 있었던 지점들이다.

  S1 관측 보고서 수치는 **커밋된 증거에서 재계산**되어야 한다. 특히 모니터 CSV는 열이
     t,elapsed_s,rss_mb,... 순서라 **위치로 읽으면 경과 초를 RSS로 착각**한다
     (2026-10-04 실제로 그렇게 잘못 읽어 "RSS 1,293MB 누수"로 오판할 뻔했다).
     → 이 테스트는 열 **이름**으로만 읽고, 보고서에 적힌 RSS 범위·마지막 값과 대조한다.
  S2 렌더 수치도 증거(observe_step2.json)와 일치해야 한다.
  S3 관측 도구는 실패의 **원인 문구를 남겨야** 한다(전에는 세션 상세를 버려 "오류 1건"의
     이유를 나중에 볼 수 없었다). 소스가 그 키를 만들도록 되어 있는지 확인한다.
  S4 보고서는 두 곳(프로젝트·다운로드)에 같은 크기로 있고, 한계·정정·원인을 숨기지 않는다.
  S5 .env.example 의 DDNS 예시에는 "EAS 는 eas.json 이 우선"이라는 주의가 함께 있어야 한다
     (이걸 빼먹으면 로컬 .env 만 보고 빌드 주소가 바뀐 줄 오해한다).

실행: venv312\\Scripts\\python.exe -X utf8 tests\\test_step2_soak_artifacts.py
"""

from __future__ import annotations

import csv
import json
import re
import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
SCRATCH = ROOT / "scratch"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORT = "동시접속확장_2단계_상한120_30분관측_2026-10-04.txt"
RSS_CSV = SCRATCH / "rss_step2.csv"
OBS_JSON = SCRATCH / "observe_step2.json"
WS_TOOL = SCRATCH / "load_test_ws_sessions.py"
ENV_EXAMPLE = ROOT / "LottoShinryeong" / ".env.example"
# 보고서 2번이 말한 관측 창(18:45~19:15) — 증거를 이 창으로 잘라 대조한다.
WINDOW_START = "18:45:00"
WINDOW_END = "19:15:59"


def read_report() -> str:
    return (ROOT / REPORT).read_text(encoding="utf-8")


def rss_series() -> list[tuple[str, float]]:
    """(시각, RSS) — **열 이름으로** 읽고 **보고서가 말한 관측 창으로 자른다**.

    감시 도구는 창이 끝난 뒤에도 샘플을 몇 개 더 남긴다 — 잘라두지 않으면 "마지막 값"이
    시간이 지날수록 달라져 보고서와 영원히 어긋난다(2026-10-04 실제로 겪음).
    """
    with RSS_CSV.open(encoding="utf-8", newline="") as fh:
        return [(r["t"], float(r["rss_mb"])) for r in csv.DictReader(fh)
                if (r.get("rss_mb") or "").strip()
                and WINDOW_START <= r["t"] <= WINDOW_END]


class SoakEvidenceTests(unittest.TestCase):
    """S1·S2 — 보고서 수치가 커밋된 증거에서 재계산된다."""

    def test_evidence_files_exist(self):
        for path in (RSS_CSV, OBS_JSON, WS_TOOL, ROOT / REPORT):
            self.assertTrue(path.exists(), f"증거 파일이 없다: {path}")

    def test_rss_column_names_are_what_the_analysis_assumes(self):
        with RSS_CSV.open(encoding="utf-8", newline="") as fh:
            header = next(csv.reader(fh))
        self.assertEqual(header[:3], ["t", "elapsed_s", "rss_mb"],
                         "열 순서가 바뀌면 위치로 읽는 분석이 조용히 틀린다")

    def test_report_rss_facts_match_the_evidence(self):
        series = rss_series()
        self.assertGreater(len(series), 30, "30분 창을 덮을 만큼 샘플이 있어야 한다")
        values = [v for _t, v in series]
        report = read_report()
        self.assertIn(f"{min(values):.1f} ~ {max(values):.1f}MB", report,
                      f"보고서의 RSS 범위 {min(values):.1f}~{max(values):.1f} 가 증거와 다르다")
        self.assertIn(f"마지막 샘플 {values[-1]:.1f}MB", report,
                      f"보고서의 관측 창 마지막 RSS {values[-1]:.1f} 가 증거와 다르다")
        # "증가 없음"이라는 결론의 근거
        self.assertLess(values[-1], max(values), "마지막 RSS 가 최대와 같으면 '증가 없음' 근거가 약하다")
        self.assertLess(max(values), 300, "RSS 가 300MB 를 넘으면 '안정' 결론을 다시 봐야 한다")
        self.assertGreater(values[-1], 0)

    def test_report_render_facts_match_the_evidence(self):
        with OBS_JSON.open(encoding="utf-8") as fh:
            obs = json.load(fh)
        rows = obs["rows"]
        self.assertTrue(rows, "관측 결과 행이 없다")
        worst = max(r["script_p95"] for r in rows)
        report = read_report()
        # 보고서는 천단위 쉼표로 적는다(1,994ms) — 표기 그대로 확인한다.
        self.assertIn(f"{worst:,}ms", report, f"보고서에 최대 p95({worst}ms)가 없다")
        # 도구의 rows.errors 는 그 단계까지의 **누적**이다(1단계 1건 + 2단계 1건 = 2) —
        # 행을 더하면 누적을 두 번 세게 된다.
        self.assertEqual(max(r["errors"] for r in rows), 2,
                         "이번 관측의 실패는 세션마다 유휴 1건씩 총 2건이었다")
        self.assertLessEqual(rows[0]["errors"], max(r["errors"] for r in rows),
                             "누적값은 단계가 늘수록 줄어들 수 없다")

    def test_report_states_what_was_not_verified(self):
        report = read_report()
        self.assertIn("미검증", report, "검증하지 못한 항목을 숨기면 안 된다")
        self.assertIn("app_heartbeat", report, "유휴 종료의 원인을 적어야 한다")
        self.assertIn("오독", report, "계측 오독 정정을 적어야 한다")


class WsToolTests(unittest.TestCase):
    """S3 — 실패 원인을 잃지 않는가(전에는 세션 상세를 통째로 버렸다)."""

    def test_tool_keeps_failure_details(self):
        src = WS_TOOL.read_text(encoding="utf-8")
        for key in ("errors_by_session", "timeouts_by_session", "error_samples"):
            self.assertIn(key, src, f"도구가 {key} 를 남기지 않는다")
        self.assertNotIn('report.pop("error_samples"', src)

    def test_tool_source_has_no_placeholder_left(self):
        src = WS_TOOL.read_text(encoding="utf-8")
        self.assertNotIn("TODO", src)
        self.assertNotIn("pass  # not implemented", src)


class ReportArtifactTests(unittest.TestCase):
    """S4 — 두 사본 + 한계 기재."""

    def test_both_copies_match(self):
        project = ROOT / REPORT
        self.assertGreater(project.stat().st_size, 5000)
        downloads = Path.home() / "Downloads" / REPORT
        if downloads.parent.exists():
            self.assertTrue(downloads.exists(), f"다운로드 사본이 없다: {downloads}")
            self.assertEqual(downloads.stat().st_size, project.stat().st_size)

    def test_approved_setting_change_is_documented_with_rollback(self):
        report = read_report()
        self.assertIn("60 → 120", report)
        self.assertIn("되돌리기", report, "즉시 롤백 방법이 적혀 있어야 한다")
        self.assertIn("코드 배포 없음", report)


class EnvExampleTests(unittest.TestCase):
    """S5 — 추적되는 템플릿에 DDNS 예시가 있고, 그 함정이 함께 적혀 있는가."""

    def test_example_has_ddns_and_the_eas_warning(self):
        text = ENV_EXAMPLE.read_text(encoding="utf-8")
        self.assertIn("lottoshinryeong.duckdns.org", text)
        self.assertIn("eas.json", text, "EAS 빌드는 eas.json 이 우선이라는 주의가 필요하다")
        # 활성 라인은 여전히 하나(Production)여야 한다 — 예시가 활성으로 새면 빌드가 바뀐다.
        active = [ln for ln in text.splitlines()
                  if ln.strip().startswith("EXPO_PUBLIC_STREAMLIT_URL=")]
        self.assertEqual(len(active), 1, f"활성 EXPO_PUBLIC 라인이 하나가 아니다: {active}")
        self.assertIn("streamlit.app", active[0], "활성 라인은 Cloud(현행)여야 한다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
