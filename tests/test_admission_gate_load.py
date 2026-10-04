"""게이트 부하 검증 도구·산출물의 불변식 (2026-10-04, 2단계 미검증 항목).

왜: 이 도구의 결론("게이트가 cap에서 정확히 작동한다")이 곧 판정이다. 조용히 틀리면
없는 버그를 만들거나 진짜 버그를 놓친다. 실제로 위험한 지점은 셋이다.
  ① 대기화면을 '정상'으로 세면 → "게이트가 안 뜬다"는 정반대 결론이 난다.
  ② 판정 기준 문자열이 화면 코드와 어긋나면 → ①이 실제로 일어난다(조용히).
  ③ 검증 도구가 운영을 건드리면 → "영향 0인 방법"이라는 전제 자체가 무너진다.

그래서 이 테스트는 판정 신호를 admission_control.py와 교차 확인하고, 산출물의
**요약이 아니라 세션별 원자료에서 다시 세어** 요약과 맞는지 확인한다.

실행: venv312\\Scripts\\python.exe -X utf8 tests\\test_admission_gate_load.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
SCRATCH = ROOT / "scratch"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TOOL_PATH = SCRATCH / "verify_admission_gate_load.py"
ADMISSION_SRC = (ROOT / "admission_control.py").read_text(encoding="utf-8")
TOOL_SRC = TOOL_PATH.read_text(encoding="utf-8")
REPORT = "동시접속확장_2단계_게이트부하검증_2026-10-04.txt"

# (산출물, 상한, 신규 세션 수, 그 실행이 붙았어야 할 포트) — 도구가 실제로 돈 두 번의 기록
RUNS = (("gate_load_cap5.json", 5, 12, 8597), ("gate_load_cap120.json", 120, 128, 8598))

_SPEC = importlib.util.spec_from_file_location("gate_load_tool", TOOL_PATH)
tool = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = tool
_SPEC.loader.exec_module(tool)


def _artifact(name: str) -> dict:
    path = SCRATCH / name
    assert path.exists(), f"산출물이 없다: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _renders(rep: dict, idx: int, phase: str) -> list[dict]:
    for sess in rep["session_renders"]:
        if sess["idx"] == idx:
            return [r for r in sess["renders"] if r["phase"] == phase]
    raise AssertionError(f"세션 {idx} 의 원자료가 없다")


def _p1_counts(rep: dict) -> dict:
    out = {"NORMAL": 0, "GATE": 0, "TIMEOUT": 0, "ERROR": 0}
    for sess in rep["session_renders"]:
        for row in sess["renders"]:
            if row["phase"] == "P1":
                out[row["verdict"]] = out.get(row["verdict"], 0) + 1
    return out


class SignalContractTests(unittest.TestCase):
    """① ② — 판정 신호가 화면 코드와 같은가, 게이트를 정상으로 세지 않는가."""

    def test_marker_strings_come_from_the_real_screen_code(self):
        for marker in (tool.GATE_CLASS, tool.GATE_TEXT):
            self.assertIn(marker, ADMISSION_SRC,
                          f"탐지 문자열 {marker!r} 이 admission_control.py 에 없다 — "
                          "화면 마크업이 바뀌었는데 도구만 옛 문자열을 찾고 있다")
            self.assertIn(marker, TOOL_SRC, f"{marker!r} 가 도구에서 사라졌다")

    def test_marker_is_utf8_bytes_not_a_proto_field_name(self):
        self.assertEqual(len(tool.GATE_MARKERS), 2)
        for marker in tool.GATE_MARKERS:
            self.assertIsInstance(marker, bytes,
                                  "proto 내부 필드에 기대면 버전업에 조용히 깨진다")

    def test_verdict_only_finishes_on_script_finished(self):
        # 판정은 script_finished 를 본 뒤에만 확정되어야 한다(프레임 하나 보고 성급히
        # '정상'이라고 하면 대기화면 직전 프레임을 정상으로 셀 수 있다).
        body = TOOL_SRC.split("async def rerun")[1].split("async def close")[0]
        self.assertIn('kind = fwd.WhichOneof("type")', body,
                      "프레임 종류를 읽어두지 않으면 판정 시점을 확인할 수 없다")
        self.assertIn('if kind == "script_finished":', body)
        self.assertLess(body.index('if kind == "script_finished":'),
                        body.index('return ("GATE" if gate else "NORMAL")'),
                        "script_finished 확인보다 판정 반환이 먼저다")
        self.assertIn('return "TIMEOUT"', body, "끝나지 않은 렌더를 판정하지 않는다")

    def test_heartbeat_ttl_matches_the_app(self):
        # 도구의 대기 시간은 앱의 하트비트 TTL에 맞춰져 있어야 한다 — 앱이 이 TTL을
        # 바꾸면 P3(복귀) 판정이 조용히 틀린다(너무 짧게 기다려 '복귀 실패'로 오판).
        m = __import__("re").search(r"_HEARTBEAT_TTL_SECONDS\s*=\s*(\d+)", ADMISSION_SRC)
        self.assertIsNotNone(m, "admission_control 에서 하트비트 TTL을 찾지 못했다")
        self.assertEqual(int(tool.HEARTBEAT_TTL_SECONDS), int(m.group(1)),
                         "앱의 하트비트 TTL과 도구의 판정 기준이 다르다")
        self.assertGreaterEqual(tool.DRAIN_WAIT_DEFAULT, tool.HEARTBEAT_TTL_SECONDS + 5)


class SafetyTests(unittest.TestCase):
    """③ — 이 도구는 측정만 한다(운영·상한·DB 어느 것도 건드리지 않는다)."""

    def test_tool_never_writes_the_cap(self):
        self.assertNotIn("set_max_concurrent_sessions", TOOL_SRC,
                         "검증 도구가 상한을 바꾸면 '영향 0'이라는 전제가 깨진다")

    def test_tool_defaults_to_loopback_only(self):
        self.assertIn("ws://127.0.0.1:", tool.DEFAULT_WS,
                      "기본 대상이 로컬이 아니면 운영에 부하를 줄 수 있다")
        self.assertNotIn("duckdns", TOOL_SRC)
        self.assertNotIn("streamlit.app", TOOL_SRC)

    def test_tool_keeps_per_session_evidence(self):
        self.assertIn("session_renders", TOOL_SRC,
                      "세션별 원자료를 버리면 요약이 틀렸을 때 원인을 볼 수 없다")
        for rep_name, _cap, n, _port in RUNS:
            rep = _artifact(rep_name)
            self.assertEqual(len(rep["session_renders"]), n + 2,
                             "세션별 원자료 수가 (워밍업+본세션+복귀)와 다르다")

    def test_each_run_reports_the_instance_it_actually_hit(self):
        # 2026-10-04 실제 사고: 상한 120 을 확인하려던 128세션 실행이 **기본 주소(8597)로
        # 가서** 상한 5 인 인스턴스를 재고 "5개만 통과"라는 거짓 결론을냈다. 실행마다
        # 어느 인스턴스에 붙었는지가 산출물에 남고, 그 포트가 계획과 같아야 한다.
        for rep_name, _cap, _n, port in RUNS:
            url = _artifact(rep_name)["url"]
            self.assertIn(f"127.0.0.1:{port}", url,
                          f"{rep_name}: 다른 인스턴스에 붙었다 — {url}")
        ports = {_artifact(name)["url"] for name, *_ in RUNS}
        self.assertEqual(len(ports), len(RUNS), f"두 실행이 같은 인스턴스를 썼다: {ports}")

    def test_refuses_a_run_without_an_excess_region(self):
        argv = sys.argv
        try:
            sys.argv = ["prog", "--cap", "10", "--n", "5"]
            self.assertEqual(tool.main(), 2,
                             "상한 이하만 붙이는 실행은 게이트를 볼 수 없으니 거부해야 한다")
        finally:
            sys.argv = argv


class ArtifactTests(unittest.TestCase):
    """④ — 요약을 원자료에서 다시 세어 확인한다(요약을 믿지 않는다)."""

    def test_summary_matches_raw_renders(self):
        for name, cap, n, _port in RUNS:
            rep = _artifact(name)
            self.assertEqual(rep["cap"], cap, name)
            self.assertEqual(rep["n"], n, name)
            self.assertEqual(rep["excess"], n - cap, name)
            self.assertEqual(rep["p1"]["counts"], _p1_counts(rep),
                             f"{name}: 요약과 원자료가 어긋난다")
            self.assertIn("first_render_empty", rep["p1"],
                          f"{name}: 내용 없는 첫 렌더 건수를 남겨야 한다")

    def test_boundary_is_exact_in_both_runs(self):
        for name, cap, n, _port in RUNS:
            rep = _artifact(name)
            counts = _p1_counts(rep)
            self.assertEqual(counts["NORMAL"], cap,
                             f"{name}: 통과가 정확히 {cap}개여야 한다 (경계가 밀리면 "
                             "상한이 사실상 다른 값이 된다)")
            self.assertEqual(counts["GATE"], n - cap, f"{name}: 차단 수가 초과분과 다르다")
            self.assertEqual(counts["TIMEOUT"] + counts["ERROR"], 0,
                             f"{name}: 초과 구간에서 실패가 나면 '막아서 지켜진 것'이 아니다")
            self.assertTrue(rep["verdict"]["boundary_exact"], name)

    def test_gate_session_indexes_match_raw(self):
        for name, _cap, _n, _port in RUNS:
            rep = _artifact(name)
            raw = sorted(s["idx"] for s in rep["session_renders"]
                         if any(r["phase"] == "P1" and r["verdict"] == "GATE"
                                for r in s["renders"]))
            self.assertEqual(rep["p1"]["gate_session_indexes"], raw, name)

    def test_admitted_sessions_are_never_reblocked(self):
        for name, _cap, _n, _port in RUNS:
            rep = _artifact(name)
            admitted = [s["idx"] for s in rep["session_renders"]
                        if [r["verdict"] for r in s["renders"] if r["phase"] == "P1"] == ["NORMAL"]]
            rounds = rep["p2"]["rounds"]
            self.assertEqual(len(admitted), rep["p2"]["admitted_sessions"], name)
            self.assertEqual(rep["p2"]["admitted_counts"]["NORMAL"],
                             len(admitted) * rounds,
                             f"{name}: 입장한 세션이 다시 막혔다 — 결제 중 튕김 방지 약속 위반")
            self.assertTrue(rep["verdict"]["admitted_not_reblocked"], name)

    def test_blocked_sessions_stay_blocked_while_the_crowd_persists(self):
        # 이건 실패가 아니라 설계의 결과다: 자리가 나지 않았는데 게이트 세션이
        # 통과하면 상한이 무의미해진다 — 그래서 '통과 0'을 성질로 잠근다.
        for name, _cap, _n, _port in RUNS:
            rep = _artifact(name)
            blocked = [s["idx"] for s in rep["session_renders"]
                       if any(r["phase"] == "P1" and r["verdict"] == "GATE" for r in s["renders"])]
            for idx in blocked:
                for row in _renders(rep, idx, "P2"):
                    self.assertEqual(row["verdict"], "GATE",
                                     f"{name}: 세션 {idx} 가 자리 없이 통과했다")

    def test_recovery_after_ttl(self):
        for name, cap, _n, _port in RUNS:
            rep = _artifact(name)
            self.assertGreaterEqual(rep["drain_wait_s"], 60,
                                    "하트비트 TTL보다 짧게 기다리면 복귀 판정이 무의미하다")
            late = _renders(rep, -2, "P3")
            self.assertEqual(len(late), 1, name)
            self.assertEqual(rep["p3"]["fresh_verdict"], late[0]["verdict"], name)
            self.assertEqual(late[0]["verdict"], "NORMAL",
                             f"{name}: cap {cap} — 자리가 났는데도 못 들어왔다(게이트가 잠겼다)")
            self.assertTrue(rep["verdict"]["recovery_ok"], name)

    def test_all_verdict_flags_are_recorded_and_true(self):
        for name, _cap, _n, _port in RUNS:
            rep = _artifact(name)
            self.assertEqual(set(rep["verdict"]),
                             {"boundary_exact", "no_errors", "admitted_not_reblocked",
                              "recovery_ok", "normal_screen_has_content"}, name)
            self.assertTrue(all(rep["verdict"].values()), f"{name}: {rep['verdict']}")

    def test_normal_verdict_is_backed_by_content_not_by_absence(self):
        # 마커가 안 보였다는 '부재'만으로 정상이라고 하면 빈 화면도 정상으로 센다.
        # 증거는 두 갈래다: ① 대기화면은 항상 마크다운 한 덩(delta)을 그린다
        # ② 정상 판정을 받은 세션은 **다음 라운드(P2)**에서 실제 페이지 내용을 그린다.
        # ③ 새 세션의 첫 렌더가 내용 없이 끝나는 것은 부하 중 실제 현상이므로(측정
        #    편차가 아니라 기록해야 할 사실) 건수를 남기되, 그런 렌더는 **그 세션의
        #    첫 렌더여야 한다** — P1에서 0-delta '정상'은 첫 렌더에만 허용된다.
        for name, _cap, _n, _port in RUNS:
            rep = _artifact(name)
            self.assertIsInstance(rep["p1"]["first_render_empty"], int, name)
            for sess in rep["session_renders"]:
                first_p1_seen = False
                for row in sess["renders"]:
                    if row["phase"] != "P1":
                        continue
                    if row["verdict"] == "GATE":
                        self.assertGreaterEqual(row.get("deltas", 0), 1,
                                                f"{name}: 대기화면 판정에 마크다운이 없다")
                    if row["verdict"] == "NORMAL":
                        if row.get("deltas", 0) == 0:
                            self.assertFalse(first_p1_seen,
                                             f"{name}: 세션 {sess['idx']} 의 첫 렌더가 아닌데도 "
                                             "내용이 없다 — 판정 근거가 없다")
                        first_p1_seen = True
            # ② 다음 라운드의 실제 내용 = '정상'의 존재 증거
            self.assertGreater(rep["p2"]["admitted_deltas_p50"], 0,
                               f"{name}: 입장한 세션이 다음 라운드에서 아무것도 그리지 않았다")
            self.assertGreater(rep["p2"]["admitted_deltas_p50"],
                               rep["p1"]["gate_deltas_p50"], name)
            self.assertTrue(rep["verdict"]["normal_screen_has_content"], name)

    def test_gate_render_is_short_and_admitted_render_is_not(self):
        # 대기화면(마크다운 1개)과 정상 화면(P2, 60여 개)의 요소 수가 뒤집히면
        # 어느 쪽을 재고 있는지 의심해야 한다.
        for name, _cap, _n, _port in RUNS:
            rep = _artifact(name)
            gate = rep["p1"]["gate_deltas_p50"]
            admitted = rep["p2"]["admitted_deltas_p50"]
            self.assertGreater(admitted, gate * 5,
                               f"{name}: 대기 {gate} · 정상 {admitted} — 배율이 비상식적이다")

    def test_limitations_are_recorded_in_the_artifact(self):
        for name, _cap, _n, _port in RUNS:
            rep = _artifact(name)
            notes = " ".join(rep["notes"])
            self.assertIn("Turso", notes, "격리 sqlite 라 Turso 왕복이 빠졌다는 한계를 적어야 한다")
            self.assertIn("쓰지 않는다", notes, "운영을 건드리지 않았다는 사실을 적어야 한다")


class ReportTests(unittest.TestCase):
    """⑤ — 보고서가 결과·한계·다음 판단 근거를 담고 두 곳에 있는가."""

    def _report(self) -> str:
        path = ROOT / REPORT
        self.assertTrue(path.exists(), f"보고서가 없다: {path}")
        return path.read_text(encoding="utf-8")

    def test_report_carries_the_production_boundary_numbers(self):
        rep120 = _artifact("gate_load_cap120.json")
        text = self._report()
        self.assertIn("120", text)
        self.assertIn("128", text, "신규 세션 수를 적어야 한다")
        self.assertIn(str(rep120["p1"]["counts"]["NORMAL"]), text)
        self.assertIn(str(rep120["p1"]["counts"]["GATE"]), text, "차단 수를 적어야 한다")
        self.assertIn("cap 5", text, "경계 정밀도 확인(작은 상한)도 함께 적어야 한다")

    def test_report_states_what_was_not_verified(self):
        text = self._report()
        self.assertIn("미검증", text, "검증하지 못한 것을 숨기면 안 된다")
        self.assertIn("실사용자", text, "실사용 트래픽이 없다는 한계를 적어야 한다")
        self.assertIn("격리", text, "운영에 영향 0인 방법을 밝혀야 한다")
        self.assertIn("Turso", text, "Turso 지연이 빠졌다는 한계를 적어야 한다")

    def test_report_gives_the_next_decision_a_basis(self):
        text = self._report()
        self.assertIn("150", text, "다음 판단(150~200 상향)의 근거가 있어야 한다")
        self.assertIn("되돌리", text, "문제가 생겼을 때 되돌리는 방법이 있어야 한다")
        self.assertIn("재현", text, "같은 검증을 다시 돌리는 명령이 있어야 한다")

    def test_both_copies_match(self):
        project = ROOT / REPORT
        self.assertGreater(project.stat().st_size, 1500)
        downloads = Path.home() / "Downloads" / REPORT
        if downloads.parent.exists():
            self.assertTrue(downloads.exists(), f"다운로드 사본이 없다: {downloads}")
            self.assertEqual(downloads.stat().st_size, project.stat().st_size)


class NoPlaceholderTests(unittest.TestCase):
    def test_tool_has_no_leftover_placeholder(self):
        self.assertNotIn("TODO", TOOL_SRC)
        self.assertNotIn("FIXME", TOOL_SRC)


if __name__ == "__main__":
    unittest.main(verbosity=2)
