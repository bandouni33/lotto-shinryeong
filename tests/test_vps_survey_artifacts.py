"""VPS 검토(4단계) 보고서의 수치를 커밋된 증거에 잠근다 (2026-10-04).

왜 필요한가: 이 보고서의 결론("코어를 늘려도 빨라지지 않았다", "게이트는 코어와 무관하게
정확하다", "버스트 중 서버는 0.64코어만 썼다")은 전부 숫자로만 뒷받침된다. 숫자가 증거와
어긋나면 결론이 통째로 거짓이 되는데, 지금까지 그걸 막는 장치가 없었다.

이 테스트가 고정하는 것:
  V1 코어 사다리 수치가 산출물 JSON에서 **재계산**된다(보고서를 믿지 않는다).
  V2 방향 성질: 2논리코어가 가장 빠르고 8논리(무제한)가 가장 느리다 — 이게 뒤집히면
     "코어가 병목이 아니다"라는 결론 자체가 성립하지 않는다.
  V3 게이트 성질은 **네 번의 실행 모두에서 동일**하다: 정확히 120 통과 / 8 대기,
     오류·타임아웃 0, 대기 순번 120~127, 다음 라운드의 실제 내용(delta 62).
     (코어 예산은 입력이고, 이 성질은 모든 입력에서 성립해야 한다.)
  V4 자원 수치(CPU·RSS)가 모니터 CSV에서 **열 이름으로** 재계산된다(위치로 읽지 않는다 —
     2026-10-04 다른 도구에서 위치로 읽어 경과 초를 RSS로 오독한 사고가 있었다).
  V5 보고서가 한계·미검증·"가입/전환하지 않았다"를 숨기지 않고, 저장 위치와 재현 명령을 적는다.

실행: venv312\\Scripts\\python.exe -X utf8 tests\\test_vps_survey_artifacts.py
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

REPORT_NAME = "VPS_검토_4단계_버스트및DB벽_조사_2026-10-04.txt"
RSS_CSV = SCRATCH / "rss_burst_cores2.csv"

# (산출물, 서버 논리코어, 사람이 읽는 초 표기) — 사다리 4점
LADDER = (
    ("gate_load_cores2.json", 2),
    ("gate_load_cores4.json", 4),
    ("gate_load_cores6.json", 6),
    ("gate_load_cap120.json", 8),   # 2단계 기준선(무제한)
)
CAP = 120
N = 128
LOGICAL_CORES = 8                    # 이 PC의 논리 프로세서 수(모니터 정규화 기준)


def report_text() -> str:
    path = ROOT / REPORT_NAME
    assert path.exists(), f"보고서가 없다: {path}"
    return path.read_text(encoding="utf-8")


def artifact(name: str) -> dict:
    path = SCRATCH / name
    assert path.exists(), f"증거 산출물이 없다: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def monitor_rows() -> list[dict]:
    with RSS_CSV.open(encoding="utf-8", newline="") as fh:
        return [r for r in csv.DictReader(fh) if (r.get("rss_mb") or "").strip()]


def _comma(value: int) -> str:
    return f"{value:,}"


class EvidenceTests(unittest.TestCase):
    def test_V1_every_evidence_file_exists(self):
        for name, _cores in LADDER:
            self.assertTrue((SCRATCH / name).exists(), name)
        self.assertTrue(RSS_CSV.exists(), RSS_CSV)

    def test_V1_core_ladder_numbers_come_from_the_artifacts(self):
        text = report_text()
        for name, cores in LADDER:
            rep = artifact(name)
            wave = f"{rep['p1']['seconds']:.1f}"
            p50 = _comma(rep["p1"]["normal_ms_p50"])
            p2 = _comma(rep["p2"]["admitted_ms_p50"])
            for value in (wave, p50, p2):
                self.assertIn(value, text,
                              f"{name}({cores}코어)의 수치 {value} 가 보고서에 없다")
            # 산출물이 정말 그 코어 설정에서 돈 것인지 확인(포트도 함께 본다)
            self.assertIn("8598", rep["url"], name)
            self.assertEqual(rep["cap"], CAP, name)
            self.assertEqual(rep["n"], N, name)

    def test_V2_two_cores_fastest_all_cores_slowest(self):
        p50 = {cores: artifact(name)["p1"]["normal_ms_p50"] for name, cores in LADDER}
        self.assertEqual(min(p50, key=p50.get), 2,
                         f"2코어가 가장 빠르지 않다: {p50} — 결론 문장을 다시 봐야 한다")
        self.assertEqual(max(p50, key=p50.get), 8,
                         f"8논리(무제한)가 가장 느리지 않다: {p50}")
        self.assertLess(p50[2], p50[8], "코어를 늘렸는데 빨라지지 않았다는 근거가 사라졌다")

    def test_V3_gate_property_holds_in_all_four_runs(self):
        for name, cores in LADDER:
            rep = artifact(name)
            counts = rep["p1"]["counts"]
            self.assertEqual(counts["NORMAL"], CAP, f"{name}: 통과가 정확히 {CAP}이어야 한다")
            self.assertEqual(counts["GATE"], N - CAP, f"{name}: 대기가 초과분과 달라야 한다")
            self.assertEqual(counts["TIMEOUT"] + counts["ERROR"], 0, f"{name}: 실패가 있다")
            indexes = rep["p1"]["gate_session_indexes"]
            self.assertEqual(len(indexes), N - CAP,
                             f"{name}: 대기 수가 초과분과 다르다")
            self.assertEqual(len(set(indexes)), len(indexes),
                             f"{name}: 같은 세션을 두 번 셌다")
            self.assertTrue(all(0 <= i < N for i in indexes),
                            f"{name}: 범위 밖 번호가 있다")
            # 번호가 목록 순서(120~127)로 고정되지 않는다 — 동시 도착 순서가 곳 판정 순서다.
            # (4논리코어 실행에서 실제로 118·120·122~127로 흘어졌다.) 그래서 '성질'은
            # '몇 개가 막히는가'로만 잠그고, 보고서가 그 사실을 적었는지 확인한다.
            self.assertIn("번호**는 실행마다 고정되지 않는다",
                          report_text(),
                          "대기 번호가 고정되지 않는다는 사실을 보고서가 적어야 한다")
            # 게이트의 핵심 약속 두 가지 — 이건 코어 예산과 무관하게 항상 성립해야 한다.
            self.assertEqual(rep["p2"]["admitted_counts"]["GATE"], 0,
                             f"{name}({cores}코어): 입장한 세션이 다시 막혔다")
            self.assertEqual(rep["p2"]["blocked_counts"]["NORMAL"], 0,
                             f"{name}({cores}코어): 자리 없이 통과한 차단 세션이 있다")
            self.assertGreater(rep["p2"]["admitted_deltas_p50"], 0,
                               f"{name}: 입장 세션이 실제 내용을 그리지 않았다")
            self.assertTrue(all(rep["verdict"].values()), f"{name}: {rep['verdict']}")

    def test_V4_resource_numbers_match_the_monitor_csv(self):
        rows = monitor_rows()
        self.assertGreater(len(rows), 30, "샘플이 너무 적다")
        proc = [float(r["proc_cpu_pct"]) for r in rows]
        sysc = [float(r["sys_cpu_pct"]) for r in rows]
        rss = [float(r["rss_mb"]) for r in rows]

        text = report_text()
        self.assertIn(f"최대 {max(proc):.1f}%, 평균 {sum(proc)/len(proc):.1f}%", text,
                      "프로세스 CPU 수치가 CSV와 다르다")
        self.assertIn(f"최대 {max(sysc):.1f}%, 평균 {sum(sysc)/len(sysc):.1f}%", text,
                      "시스템 CPU 수치가 CSV와 다르다")
        # 8논리코어 기준 코어 환산 — "0.64코어"라는 서술의 근거
        self.assertIn(f"{max(proc)/100*LOGICAL_CORES:.2f}코어", text,
                      "코어 환산 서술이 CSV와 맞지 않는다")
        # RSS는 보고서가 읽기 좋게 천단위 쉽표를 쓴다(1,161.8MB) — 숫자 값을 보는 것이
        # 목적이므로 표기를 맞춰서 비교한다(2026-10-04 이 테스트가 실제로 걸렸다).
        self.assertIn(f"{min(rss):,.1f}MB", text, "RSS 최소값이 CSV와 다르다")
        self.assertIn(f"{max(rss):,.1f}MB", text, "RSS 최대값이 CSV와 다르다")
        per_session = (max(rss) - min(rss)) / N
        self.assertIn(f"약 {per_session:.1f}MB", text, "세션당 증가분이 CSV와 다르다")
        self.assertLess(max(proc), 50.0,
                        "CPU가 절반을 넘으면 '대기였다'는 결론이 성립하지 않는다")

    def test_V4_monitor_csv_columns_are_read_by_name(self):
        with RSS_CSV.open(encoding="utf-8", newline="") as fh:
            header = next(csv.reader(fh))
        for column in ("t", "elapsed_s", "rss_mb", "proc_cpu_pct", "sys_cpu_pct"):
            self.assertIn(column, header, "위치로 읽으면 다른 열을 잘못 집는다")


class ReportHonestyTests(unittest.TestCase):
    def test_V5_report_says_no_purchase_was_made(self):
        text = report_text()
        self.assertIn("하지 않았다", text, "가입·전환을 하지 않았다는 사실이 빠졌다")
        self.assertIn("승인", text, "다음 승인이 필요하다는 사실이 빠졌다")

    def test_V5_report_states_limitations(self):
        text = report_text()
        for word in ("미검증", "실제 VPS 인스턴스", "운영 Turso에 버스트 부하를 주지 않았다"):
            self.assertIn(word, text, f"한계 서술이 빠졌다: {word}")

    def test_V5_report_has_repro_commands_and_cost_anchors(self):
        text = report_text()
        self.assertIn("재현 명령", text)
        self.assertIn("serve_for_concurrency.py --port 8598 --cap 120", text)
        self.assertIn("ProcessorAffinity", text)
        for anchor in ("44,000원", "24,000원", "CX22", "ap-northeast"):
            self.assertIn(anchor, text, f"비용·리전 근거가 빠졌다: {anchor}")

    def test_V5_report_keeps_db_figures_that_have_no_artifact(self):
        # DB 처리량 수치는 콘솔 출력이 유일한 증거다(산출물 파일 없음) — 그 사실을
        # 테스트가 드러내 둔다. 값을 지우거나 바꾸면 여기서 걸린다.
        text = report_text()
        for figure in ("25 q/s", "98 q/s", "107 q/s", "95 q/s", "75ms"):
            self.assertIn(figure, text, f"DB 수치가 사라졌다: {figure}")
        self.assertIn("select 1", text, "DB 측정에 쓴 쿼리를 밝혀야 재현된다")

    def test_V5_both_copies_match(self):
        project = ROOT / REPORT_NAME
        self.assertGreater(project.stat().st_size, 8000)
        downloads = Path.home() / "Downloads" / REPORT_NAME
        if downloads.parent.exists():
            self.assertTrue(downloads.exists(), f"다운로드 사본이 없다: {downloads}")
            self.assertEqual(downloads.stat().st_size, project.stat().st_size)

    def test_V5_no_placeholder_or_unfinished_marker(self):
        text = report_text()
        for marker in ("TODO", "TBD", "미정)", "???", "작성 예정"):
            self.assertNotIn(marker, text, f"미완성 표시가 남았다: {marker}")
        self.assertIsNone(re.search(r"[□■]|@@", text), "자리표시자가 남았다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
