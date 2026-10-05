"""문서 변경의 불변식 — `AI_STATUS.md` §7 "협업 방식" + `AGENTS.md` §2 #P 행 (2026-10-05).

왜 테스트가 필요한가: 이번 변경은 코드가 아니라 **합의를 적은 문서**라 컴파일·실행으로
검증할 수 없다. 대신 문서가 스스로 어긋나지 않고, 가리키는 코드·테스트가 실제로 있는지를
고정한다. 한 사례(예: "#P 행이 보인다")가 아니라 **모든 행·모든 항목**에 대해 성립해야
하는 성질만 검사한다.

  D1. §2 기준점 표가 표로 성립한다 — 모든 행의 열 수가 같고, 행 번호가 A부터 연속·중복 없음.
  D2. #P 행의 기준점 이름이 **실제 코드에 존재**한다(문서가 없는 심볼을 가리키지 않는다).
  D3. #P 행이 가리키는 테스트 파일이 실제로 있고, 그 파일이 조각 규칙(CHUNK_SIZE)을 쓴다.
  D4. `AI_STATUS.md`에 §7 협업 방식이 있고 네 항목(역할·작업 순서·미해결·검증 관행)이 다 있다.
  D5. §7-3의 "저장내역 2열 배치" 기준점 이름이 AGENTS.md #P 행과 **한 글자도 다르지 않다**
      (두 문서가 같은 기준점을 다르게 적으면 다음 세션이 다른 파일을 고치게 된다).
  D6. 두 문서가 말하는 실행 환경이 어긋나지 않는다(venv312 = Python 3.12, pytest 없음).

실행: venv312\\Scripts\\python.exe -X utf8 tests\\test_docs_ai_status.py
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

AGENTS = ROOT / "AGENTS.md"
STATUS = ROOT / "AI_STATUS.md"
CHUNK_TEST = ROOT / "tests" / "test_history_chunk_pairing.py"

# #P 행이 정본으로 지정한 심볼 — 여기가 어긋나면 §2의 "기준점"이 아니라 사본을 고치게 된다.
P_REFERENCE_SYMBOLS = ("CHUNK_SIZE", "chunk_pairs", "chunk_is_from_newest")


def _s2_rows() -> list[tuple[str, list[str]]]:
    """§2 기준점 표의 데이터 행을 (행번호, [열…])로 돌려준다."""
    text = AGENTS.read_text(encoding="utf-8")
    start = text.index("## §2")
    end = text.index("### A(다이얼로그)")
    rows: list[tuple[str, list[str]]] = []
    for line in text[start:end].splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells[0].startswith("#") or set(cells[0]) <= set("-: "):
            continue  # 머리글·구분선
        rows.append((cells[0], cells))
    return rows


def _row(letter: str) -> list[str]:
    for rid, cells in _s2_rows():
        if rid == letter:
            return cells
    raise AssertionError(f"§2에 #{letter} 행이 없다")


def _codes(text: str) -> set[str]:
    return set(re.findall(r"`([A-Za-z_][A-Za-z0-9_.()]*)`", text))


class Section2TableTests(unittest.TestCase):
    """D1 — 표 자체가 표로 성립하는가(모든 행)."""

    def test_D1_every_row_has_the_same_columns_and_ids_are_contiguous(self):
        rows = _s2_rows()
        self.assertGreater(len(rows), 15, "§2 행이 너무 적다 — 파싱이 어긋났거나 행이 사라졌다")
        widths = {len(cells) for _rid, cells in rows}
        self.assertEqual(len(widths), 1, f"열 수가 행마다 다르다: {sorted(widths)}")
        self.assertEqual(widths.pop(), 5, "§2 표는 #·기능·기준점·연계·테스트 5열이어야 한다")

        ids = [rid for rid, _cells in rows]
        self.assertEqual(ids, sorted(ids), "행 번호가 순서대로가 아니다")
        self.assertEqual(len(set(ids)), len(ids), "행 번호가 중복됐다")
        expected = [chr(ord("A") + i) for i in range(len(ids))]
        self.assertEqual(ids, expected, "행 번호가 A부터 연속이 아니다(A~P)")

    def test_D1_every_row_names_a_reference_point_and_marks_deferrals(self):
        """모든 행이 기준점·연계·검사를 적고 있는가.

        E·F·G는 §3에서 보류한 항목이라 기준점이 "보류"다 — 그런 행은 **검사 칸에도
        보류라고 적혀 있어야** 한다(안 적혀 있으면 "테스트가 지켜주는 항목"으로 오해된다).
        """
        for rid, cells in _s2_rows():
            self.assertTrue(cells[2], f"#{rid} 행에 단일 기준점이 비어 있다")
            self.assertTrue(cells[3], f"#{rid} 행에 연계 항목이 비어 있다")
            self.assertTrue(cells[4], f"#{rid} 행에 검사 항목이 비어 있다")
            if "보류" in cells[2]:
                self.assertIn("보류", cells[4],
                              f"#{rid} 행은 기준점이 보류인데 검사 칸에 그 사실이 없다")


class RowPTests(unittest.TestCase):
    """D2·D3 — #P 행이 실재하는 코드·테스트를 가리키는가."""

    def test_D2_row_p_exists_and_lists_the_reference_symbols(self):
        cells = _row("P")
        self.assertIn("저장내역", cells[1], "#P 행의 기능 이름이 바뀌었다")
        reference = cells[2]
        self.assertIn("combo_history_ui", reference, "기준점 파일이 적혀 있지 않다")
        for name in P_REFERENCE_SYMBOLS:
            self.assertIn(name, reference, f"기준점 {name}이 #P 행에 없다")
        self.assertIn("page_auto", cells[3], "연계 파일(page_auto.py)이 적혀 있지 않다")
        self.assertIn("test_history_chunk_pairing", cells[4], "걸리는 테스트가 적혀 있지 않다")

    def test_D2_reference_symbols_really_exist_in_the_code(self):
        import combo_history_ui as chu

        for name in P_REFERENCE_SYMBOLS:
            self.assertTrue(hasattr(chu, name), f"combo_history_ui에 {name}이 없다 — 문서가 죽은 이름을 가리킨다")
        self.assertIsInstance(chu.CHUNK_SIZE, int)
        self.assertGreater(chu.CHUNK_SIZE, 0)

    def test_D2_page_auto_reuses_them_instead_of_copying(self):
        src = (ROOT / "page_auto.py").read_text(encoding="utf-8")
        self.assertIn("from combo_history_ui import", src, "page_auto가 조각 규칙을 import하지 않는다")
        for name in ("chunk_pairs", "chunk_is_from_newest"):
            self.assertIn(name, src, f"page_auto가 {name}을 쓰지 않는다 — #P 행의 '재사용' 서술과 어긋난다")
        self.assertNotIn("CHUNK_SIZE = ", src, "page_auto에 CHUNK_SIZE 사본이 생겼다(기준점 중복)")

    def test_D3_the_cited_test_file_exists_and_covers_the_chunk_rule(self):
        self.assertTrue(CHUNK_TEST.is_file(), f"걸리는 테스트 파일이 없다: {CHUNK_TEST.name}")
        src = CHUNK_TEST.read_text(encoding="utf-8")
        self.assertGreater(len(src), 5000, "테스트 파일이 비어 있다")
        self.assertIn("chu.CHUNK_SIZE", src, "조각 크기 기준점을 쓰지 않는다")

    def test_D3_chunk_pairs_never_loses_or_reorders(self):
        """#P 행이 가리키는 규칙의 핵심 불변식(모든 길이에 대해)."""
        import combo_history_ui as chu

        for n in range(0, 42):
            pairs = chu.chunk_pairs(list(range(n)))
            flat = [x for left, right in pairs for x in (left + right)]
            self.assertEqual(flat, list(range(n)), f"n={n}: 순서가 바뀌거나 빠졌다")
            for left, right in pairs:
                self.assertLessEqual(len(left), chu.CHUNK_SIZE, f"n={n}: 조각이 기준점을 넘었다")
                self.assertLessEqual(len(right), chu.CHUNK_SIZE, f"n={n}: 조각이 기준점을 넘었다")
                self.assertTrue(left, f"n={n}: 빈 조각이 생겼다")


class StatusDocTests(unittest.TestCase):
    """D4·D5·D6 — AI_STATUS.md §7이 요구한 내용을 갖추고 코드와 어긋나지 않는가."""

    def setUp(self):
        self.text = STATUS.read_text(encoding="utf-8")

    def test_D4_section_7_exists_with_all_four_items(self):
        self.assertIn("## 7. 협업 방식", self.text)
        for heading in ("### 7-1. 역할", "### 7-2. 작업 순서 원칙",
                        "### 7-3. 미해결 작업", "### 7-4. 검증 관행"):
            self.assertIn(heading, self.text, f"{heading} 항목이 없다")

    def test_D4_roles_and_principles_are_written(self):
        self.assertIn("Astra", self.text, "Astra 역할이 없다")
        self.assertIn("push 권한", self.text, "push 권한 보유 사실이 없다")
        self.assertIn("AGENTS.md", self.text, "작업 순서 원칙이 AGENTS.md를 가리키지 않는다")
        self.assertIn("2026-10-05", self.text, "사용자 지시 날짜가 없다")

    def test_D5_unresolved_item_is_marked_resolved_and_matches_agents_row(self):
        section = self.text.split("### 7-3. 미해결 작업")[1].split("###")[0]
        self.assertIn("[해소]", section, "해소 표시가 없다 — 아직 미해결로 남아 있다")
        self.assertIn("§2", section, "어느 표에 반영했는지가 없다")
        self.assertIn("#P", section, "반영한 행 번호(#P)가 없다")

        # 두 문서가 같은 기준점 이름을 적는가(한쪽만 고치면 다음 세션이 다른 파일을 만진다).
        row_codes = _codes(_row("P")[2]) | _codes(_row("P")[1])
        doc_codes = _codes(section)
        missing = {name for name in P_REFERENCE_SYMBOLS if name in row_codes and name not in doc_codes}
        self.assertEqual(missing, set(), f"§7-3에 빠진 기준점 이름: {sorted(missing)}")
        for name in P_REFERENCE_SYMBOLS:
            self.assertIn(name, section, f"§7-3이 기준점 {name}을 적지 않았다")

    def test_D6_environment_claims_do_not_contradict_agents(self):
        agents = AGENTS.read_text(encoding="utf-8")
        for text in (agents, self.text):
            self.assertIn("venv312", text, "실행 환경(venv312) 표기가 빠졌다")
        self.assertIn("Python 3.12", self.text, "검증 관행에 3.12 환경이 적혀 있지 않다")
        self.assertIn("pytest 없음", agents, "AGENTS.md §3의 테스트 환경 서술이 바뀌었다")
        self.assertIn("tests/test_history_chunk_pairing.py", self.text,
                      "§7이 #P 행의 테스트 파일을 인용하지 않는다")


class ReportCopyTests(unittest.TestCase):
    """D7 — 결과보고서 전달 규칙(2026-10-05 지시: 프로젝트 + 다운로드).

    다운로드 사본은 **전달용**이라 존재를 요구하지 않는다(구름님이 확인 후 직접 지운다 —
    2026-10-04 지시). 남아 있다면 프로젝트 사본과 바이트가 같아야 한다: 다르면 어느 쪽을
    읽었는지에 따라 결론이 달라진다.
    """

    NAME = "AI_STATUS_협업방식_추가_2026-10-05.txt"

    def test_D7_project_report_exists_and_has_no_unfinished_marker(self):
        report = ROOT / self.NAME
        self.assertTrue(report.is_file(), f"프로젝트 보고서가 없다: {self.NAME}")
        text = report.read_text(encoding="utf-8")
        self.assertGreater(len(text), 1500, "보고서가 빈 문서에 가깝다")
        for marker in ("TODO", "TBD", "미정", "???", "작성 예정"):
            self.assertNotIn(marker, text, f"보고서에 미완 표시({marker})가 남아 있다")

    def test_D7_downloads_copy_if_present_is_byte_identical(self):
        report = ROOT / self.NAME
        copy = Path.home() / "Downloads" / self.NAME
        if not copy.exists():
            self.skipTest("다운로드 사본이 없다(전달용이라 존재를 요구하지 않는다)")
        self.assertEqual(copy.read_bytes(), report.read_bytes(),
                         "프로젝트 사본과 다운로드 사본의 내용이 다르다")


def _main() -> int:
    suite = unittest.TestSuite(
        unittest.defaultTestLoader.loadTestsFromTestCase(cls)
        for cls in (Section2TableTests, RowPTests, StatusDocTests, ReportCopyTests)
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.stdout.flush()
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(_main())
