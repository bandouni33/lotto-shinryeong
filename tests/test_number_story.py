"""신령엔터 45인조(번호 인물전) 계산 — 2026-10-18.

  S1 컴백: 직전 공백 10회 이상 후 이번 회차 출현
  S2 연속 활동·이번 주 무대·공백기·대기 중
  S3 최애 듀오(함께 나온 횟수 최다), 포지션 개수(센터 5·메인 10·서브 15·히든 15)
  S4 목요일 질문 후보 = 공백기 상위 6, 토요일 결과 = 후보 중 출현
실행: python tests/test_number_story.py
"""
from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from weekly_content import number_story as ns  # noqa: E402


def _draws():
    d = {}
    for r in range(1, 31):
        d[r] = {"nums": [1, 2, 3, 4, 5, 6] if r % 2 else [1, 2, 7, 8, 9, 10]}
    d[31] = {"nums": [1, 2, 40, 41, 42, 43]}   # 40~43: 처음 등장(직전 공백 없음), 1·2: 31회 연속
    d[32] = {"nums": [3, 11, 12, 13, 14, 15]}  # 3: 29회에 나온 뒤 3회 만(컴백 아님)
    return d


class NumberStoryTest(unittest.TestCase):
    def test_S1_comeback(self):
        d = _draws()
        d[33] = {"nums": [40, 20, 21, 22, 23, 24]}
        d[44] = {"nums": [3, 30, 31, 32, 33, 34]}   # 3: 32 → 44 = 12회 만
        m = {x["n"]: x for x in ns.members(d, 44)}
        self.assertEqual(m[3]["status"], "컴백")
        self.assertEqual(m[3]["prev_gap"], 12)
        self.assertEqual(ns.headline(d, 44)["star"], 3)

    def test_S2_statuses(self):
        d = _draws()
        m = {x["n"]: x for x in ns.members(d, 32)}
        self.assertEqual(m[3]["status"], "이번 주 무대")
        self.assertEqual(m[45]["status"], "공백기")      # 한 번도 안 나옴 → gap 32
        self.assertEqual(m[1]["status"], "대기 중")       # 31회 뒤 1회 쉼
        d[33] = {"nums": [3, 11, 16, 17, 18, 19]}
        m = {x["n"]: x for x in ns.members(d, 33)}
        self.assertEqual((m[3]["status"], m[3]["streak"]), ("연속 활동", 2))

    def test_S3_buddy_positions(self):
        m = {x["n"]: x for x in ns.members(_draws(), 32)}
        self.assertEqual(m[1]["buddy"], {"n": 2, "count": 31})
        c = Counter(x["position"] for x in m.values())
        self.assertEqual(c, Counter({"센터": 5, "메인": 10, "서브": 15, "히든": 15}))

    def test_S4_question_answer(self):
        d = _draws()
        q = ns.question(d, 32)
        self.assertEqual(q["round"], 33)
        self.assertEqual(len(q["candidates"]), 6)
        d[33] = {"nums": [q["candidates"][0], 1, 2, 3, 4, 5]}
        a = ns.answer(d, 33)
        self.assertEqual(a["hit"], [q["candidates"][0]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
