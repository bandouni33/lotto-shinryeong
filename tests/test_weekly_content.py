"""주간 리포트 자동 제작(weekly_content) — 2026-10-15.

  C1 안전 확인: 번호 중복·범위 밖·보너스 겹침·빠진 회차 → 중단
  C2 날짜상 최신 회차: 토 19:55 전/후 경계 (1245회 = 2026-10-10)
  C3 제작: 카드 5장(1080x1350)·문구(고지·블로그 주소 포함, 예측·보장 표현 없음)·3장은 '추첨결과, 당첨지역 집계중' 한 줄(필터 결과 미게재)
  C4 쇼츠: ffmpeg 있으면 mp4 생성
실행: python tests/test_weekly_content.py
"""
from __future__ import annotations

import random
import shutil
import sys
import tempfile
import types
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from weekly_content import cards, run_weekly as rw  # noqa: E402


def _draws(n=60):
    r = random.Random(1)
    out = {}
    for i in range(1, n + 1):
        ns = sorted(r.sample(range(1, 46), 7))
        out[i] = {"nums": ns[:6], "bonus": ns[6]}
    return out


class WeeklyContentTest(unittest.TestCase):
    def test_C1_validate(self):
        d = _draws()
        rw.validate(d, 60)
        bad = dict(d); bad[60] = {"nums": [1, 1, 2, 3, 4, 5], "bonus": 9}
        with self.assertRaises(SystemExit):
            rw.validate(bad, 60)
        bad = dict(d); bad[60] = {"nums": [1, 2, 3, 4, 5, 6], "bonus": 6}
        with self.assertRaises(SystemExit):
            rw.validate(bad, 60)
        bad = dict(d); del bad[30]
        with self.assertRaises(SystemExit):
            rw.validate(bad, 60)

    def test_C2_expected_round(self):
        kst = ZoneInfo("Asia/Seoul")
        self.assertEqual(rw.expected_latest_round(datetime(2026, 10, 10, 19, 54, tzinfo=kst)), 1244)
        self.assertEqual(rw.expected_latest_round(datetime(2026, 10, 10, 21, 20, tzinfo=kst)), 1245)
        self.assertEqual(rw.draw_date_text(1245), "2026.10.10")

    def test_C3_build(self):
        d = _draws()
        with tempfile.TemporaryDirectory() as t:
            ps = cards.build(d, 60, Path(t), date_text="2026.10.10")
            self.assertEqual(len(ps), 5)
            from PIL import Image
            for p in ps:
                self.assertEqual(Image.open(p).size, (1080, 1350))
            self.assertEqual(cards.PENDING_TEXT, "추첨결과, 당첨지역 집계중")
            cap = cards.caption(d, 60)
            self.assertIn("당첨을 보장하지 않습니다", cap)
            self.assertIn(cards.BLOG_URL, cap)
            for bad in ("예측", "확률 상승", "보장합니다", "1등 배출"):
                self.assertNotIn(bad, cap)
            if shutil.which("ffmpeg"):           # C4
                mp4 = rw.make_shorts(ps, Path(t) / "s.mp4")
                self.assertTrue(mp4.exists() and mp4.stat().st_size > 10000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
