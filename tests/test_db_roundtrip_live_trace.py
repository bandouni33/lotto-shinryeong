"""DB 왕복 조사 보고서가 **실제 서버가 기록한 렌더 목록**을 모두 담고 있는가 (2026-10-04).

왜 필요한가:
  조사 보고서(DB왕복_축소조사_2026-10-04.txt)는 "웜 렌더 10왕복"의 목록을 제시하고 그걸
  캐시 제안의 근거로 삼는다. 목록이 빠지면 제안의 효과 추정도 같이 틀린다 — 실제로
  프로덕션 서버 로그를 보니 격리 하네스에 없던 **guest_update_notice 조회 2건 + 쓰기 1건**이
  매 렌더 더 나가고 있었다(calls=13). 조사가 "무엇이 나가는지"를 다 담았는지는
  주장이 아니라 **증거 대조**로 잠가야 한다.

증거: scratch/live_render_db_trace.txt — 운영 서버 server_out.log 에서 뽑은 실제 [dbtrace] 줄.
      (한 줄에 그 렌더가 낸 DB 항목이 `top=SELECT namexN(ms), ...` 로 들어 있다)
      ※ top= 목록은 **상위 5개까지만** 찍힌다 — 그래서 L2 의 완전성 검사는
        "실제로 적힌 항목"에 대한 하한선이다(그 목록조차 빠졌으면 보고서가 틀린 것이다).

이 테스트가 고정하는 것:
  L1 증거가 실제 운영 렌더 줄이다(page=main, calls/db_ms/script_ms 존재).
  L2 **완전성**: 실서버가 기록한 모든 DB 항목 이름이 보고서에 등장한다.
  L3 **수치 정합**: 실서버가 관측한 최대 왕복 수(=프로덕션 상한)를 보고서가 적는다.
     격리 하네스 수치(10)만 적고 "일치"라고 단정하면 이 테스트가 잡는다.
  L4 두 사본(프로젝트·다운로드)이 같은 파일이다.

실행: venv312\\Scripts\\python.exe -X utf8 tests\\test_db_roundtrip_live_trace.py
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

TRACE = ROOT / "scratch" / "live_render_db_trace.txt"
REPORT_NAME = "DB왕복_축소조사_2026-10-04.txt"

DBTRACE_RE = re.compile(
    r"\[dbtrace\]\s+page=(?P<page>\S+)\s+calls=(?P<calls>\d+)\s+db_ms=(?P<db_ms>\d+)\s+"
    r"script_ms=(?P<script_ms>\d+)\s+db_share=(?P<share>\d+)%\s+top=(?P<top>.*)$")
ITEM_RE = re.compile(
    r"(?P<verb>SELECT|INSERT|UPDATE|DELETE)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*?)"
    r"x(?P<count>\d+)\((?P<ms>\d+)ms\)")


def trace_rows() -> list[dict]:
    assert TRACE.exists(), f"증거 파일이 없다: {TRACE}"
    rows = []
    for line in TRACE.read_text(encoding="utf-8", errors="replace").splitlines():
        m = DBTRACE_RE.search(line)
        if not m:
            continue
        data = {k: m.group(k) for k in ("page", "db_ms", "script_ms", "share", "top")}
        # 숫자는 정수로 바꿔 둔다 — 문자열이면 assertGreater 가 TypeError 로 죽는다
        # (2026-10-04 실제로 그렇게 L1 이 오류로 중단됐다).
        q = m.groupdict()
        data["calls"] = int(q["calls"])
        data["db_ms"] = int(q["db_ms"])
        data["script_ms"] = int(q["script_ms"])
        data["share"] = int(q["share"])
        data["items"] = {i.group("name") for i in ITEM_RE.finditer(data["top"])}
        rows.append(data)
    return rows


def report_text() -> str:
    path = ROOT / REPORT_NAME
    assert path.exists(), f"보고서가 없다: {path}"
    return path.read_text(encoding="utf-8")


class LiveTraceTests(unittest.TestCase):
    def test_L1_trace_is_real_production_render_lines(self):
        rows = trace_rows()
        self.assertGreater(len(rows), 0, "증거 파일에 [dbtrace] 줄이 없다")
        for row in rows:
            self.assertEqual(row["page"], "main", "main 화면 렌더 줄이 아니다")
            self.assertGreater(row["calls"], 0, "왕복 0건 줄은 판정 근거가 못 된다")
            self.assertGreater(row["script_ms"], 0)
        self.assertTrue(any(r["items"] for r in rows),
                        "top= 목록이 비어 있으면 완전성을 확인할 수 없다")

    def test_L2_report_covers_every_db_item_the_live_server_logged(self):
        text = report_text()
        seen: set[str] = set()
        for row in trace_rows():
            seen |= row["items"]
        self.assertTrue(seen, "실서버 DB 항목을 하나도 못 읽었다")
        missing = sorted(name for name in seen if name not in text)
        self.assertEqual(missing, [],
                         f"보고서가 실서버의 DB 항목을 빠뜨렸다: {missing} "
                         "(목록이 불완전하면 캐시 효과 추정도 틀린다)")

    def test_L3_report_states_the_production_round_trip_max(self):
        rows = trace_rows()
        worst = max(r["calls"] for r in rows)
        isolated = 10  # 격리 하네스에서 잰 값
        text = report_text()
        self.assertIn(str(worst), text,
                      f"실서버 최대 왕복 {worst}건이 보고서에 없다")
        if worst != isolated:
            self.assertGreater(worst, isolated,
                               "프로덕션 왕복이 격리 측정보다 적을 수는 없다")
            # 격리 측정치만 적고 '일치'라고 단정하면 안 된다.
            self.assertIn("프로덕션", text,
                          "격리 값과 프로덕션 값이 다르면 그 차이를 보고서가 설명해야 한다")

    def test_L4_both_copies_match(self):
        project = ROOT / REPORT_NAME
        downloads = Path.home() / "Downloads" / REPORT_NAME
        if downloads.parent.exists():
            self.assertTrue(downloads.exists(), f"다운로드 사본이 없다: {downloads}")
            self.assertEqual(downloads.stat().st_size, project.stat().st_size)


if __name__ == "__main__":
    unittest.main(verbosity=2)
