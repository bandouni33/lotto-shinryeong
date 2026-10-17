"""즉시 게시 안전 확인(weekly_content/instant_check.py) — 가짜 DB로 흐름만 검사(2026-10-17).

  I1 동행복권 값이 캡처와 같으면 DB에 반영하고 통과
  I2 다르면 반영하지 않고 중단(2)
  I3 아직 미발표면 기다리지 않고 통과(캡처로 진행, DB 미반영) · --verify 도 보류(0)
  I4 형식 오류(6+1개 아님·중복·범위 밖)는 즉시 중단
실행: python tests/test_instant_check.py
"""
from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from weekly_content import instant_check as ic  # noqa: E402


def fake_db(local: dict, remote_seq: list):
    m = types.ModuleType("draw_results_db")
    m.upserts = []
    m.init_draw_results_table = lambda: None
    m.get_all_draw_results = lambda: [dict(draw_round=k, **v) for k, v in sorted(local.items(), reverse=True)]
    m.fetch_latest_from_dhlottery = lambda: remote_seq.pop(0) if remote_seq else None
    m.upsert_draw_result = lambda r, n, b: m.upserts.append((r, n, b))
    sys.modules["draw_results_db"] = m
    return m


class T(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.f = self.d / "1246.txt"
        self.f.write_text("3 11 19 27 35 44 + 8", encoding="utf-8")
        self.local = {1245: {"numbers": [1, 2, 3, 4, 5, 6], "bonus": 7}}

    def test_I1_match(self):
        m = fake_db(self.local, [{"draw_round": 1246, "numbers": [44, 3, 11, 19, 27, 35], "bonus": 8}])
        self.assertEqual(ic.check(self.f, sleep=lambda *_: None), 0)
        self.assertEqual(m.upserts, [(1246, [3, 11, 19, 27, 35, 44], 8)])

    def test_I2_mismatch(self):
        m = fake_db(self.local, [{"draw_round": 1246, "numbers": [3, 11, 19, 27, 35, 45], "bonus": 8}])
        self.assertEqual(ic.check(self.f, sleep=lambda *_: None), 2)
        self.assertEqual(m.upserts, [])

    def test_I3_wait(self):
        seq = [{"draw_round": 1245, "numbers": [1, 2, 3, 4, 5, 6], "bonus": 7}, None,
               {"draw_round": 1246, "numbers": [3, 11, 19, 27, 35, 44], "bonus": 8}]
        fake_db(self.local, seq)
        self.assertEqual(ic.check(self.f, tries=5, sleep=lambda *_: None), 0)
        m = fake_db(self.local, [])
        self.assertEqual(ic.check(self.f), 0)
        self.assertEqual(m.upserts, [])
        self.assertEqual(ic.check(self.f, verify=True), 0)

    def test_I5_verify_mismatch_after_sync(self):
        local = dict(self.local)
        local[1246] = {"numbers": [3, 11, 19, 27, 35, 45], "bonus": 8}
        fake_db(local, [])
        self.assertEqual(ic.check(self.f, verify=True), 2)

    def test_I4_format(self):
        for bad in ("1 2 3 4 5 + 7", "1 1 2 3 4 5 + 6", "1 2 3 4 5 46 + 7"):
            self.f.write_text(bad, encoding="utf-8")
            with self.assertRaises(SystemExit):
                ic.parse(self.f)


if __name__ == "__main__":
    unittest.main(verbosity=2)
