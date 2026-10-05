# -*- coding: utf-8 -*-
"""weekly_lotto_file_update.self_update_from_github — 실행 전 자기 갱신 (2026-10-05).

임시 git 저장소(원격 역할 bare 저장소 + PC 역할 클론)로 실제 git을 돌려 확인한다.
진짜 lotto-app 폴더·GitHub는 건드리지 않는다.

  U1 원격에 새 커밋 → fast-forward로 받고 True(새 코드로 다시 실행)
  U2 이미 최신 → False, HEAD 그대로
  U3 PC에 충돌하는 미커밋 수정 → git이 거부, False, 로컬 수정·HEAD 그대로(안전 실패)
  U4 LOTTO_SKIP_SELF_UPDATE=1 / 재실행 표시(LOTTO_SELF_UPDATED=1) → git을 부르지 않음
  U5 .git이 없는 폴더 → False(예: 테스트·다른 PC)
  U6 main()에는 자기 갱신이 없다(테스트가 main()을 불러도 git을 건드리지 않음)
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import weekly_lotto_file_update as weekly  # noqa: E402


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True,
                          text=True).stdout.strip()


class SelfUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="selfupd_"))
        self.origin = self.tmp / "origin.git"
        self.seed = self.tmp / "seed"
        self.pc = self.tmp / "pc"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)], check=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.seed)], check=True)
        for repo in (self.seed,):
            _git(repo, "config", "user.email", "t@t")
            _git(repo, "config", "user.name", "t")
        (self.seed / "a.txt").write_text("v1\n", encoding="utf-8")
        _git(self.seed, "add", ".")
        _git(self.seed, "commit", "-q", "-m", "v1")
        _git(self.seed, "remote", "add", "origin", str(self.origin))
        _git(self.seed, "push", "-q", "origin", "main")
        subprocess.run(["git", "clone", "-q", str(self.origin), str(self.pc)], check=True)
        self.env = mock.patch.dict(os.environ, {"LOTTO_SKIP_SELF_UPDATE": "", "LOTTO_SELF_UPDATED": ""})
        self.env.start()
        self.logs: list[str] = []
        self.logp = mock.patch.object(weekly, "log", side_effect=self.logs.append)
        self.logp.start()

    def tearDown(self):
        self.logp.stop()
        self.env.stop()

    def _push_new_commit(self, text: str = "v2\n"):
        (self.seed / "a.txt").write_text(text, encoding="utf-8")
        _git(self.seed, "commit", "-q", "-am", "v2")
        _git(self.seed, "push", "-q", "origin", "main")

    def test_U1_new_commit_is_fast_forwarded(self):
        self._push_new_commit()
        self.assertTrue(weekly.self_update_from_github(self.pc))
        self.assertEqual(_git(self.pc, "rev-parse", "HEAD"), _git(self.seed, "rev-parse", "HEAD"))
        self.assertEqual((self.pc / "a.txt").read_text(encoding="utf-8"), "v2\n")

    def test_U2_already_up_to_date(self):
        head = _git(self.pc, "rev-parse", "HEAD")
        self.assertFalse(weekly.self_update_from_github(self.pc))
        self.assertEqual(_git(self.pc, "rev-parse", "HEAD"), head)
        self.assertTrue(any("이미 최신" in m for m in self.logs))

    def test_U3_conflicting_local_change_fails_safely(self):
        self._push_new_commit()
        (self.pc / "a.txt").write_text("PC local edit\n", encoding="utf-8")
        head = _git(self.pc, "rev-parse", "HEAD")
        self.assertFalse(weekly.self_update_from_github(self.pc))
        self.assertEqual(_git(self.pc, "rev-parse", "HEAD"), head, "충돌 시 HEAD가 바뀌면 안 된다")
        self.assertEqual((self.pc / "a.txt").read_text(encoding="utf-8"), "PC local edit\n",
                         "PC의 미커밋 수정이 사라졌다")
        self.assertTrue(any("git pull 실패" in m for m in self.logs))

    def test_U4_skip_flags_do_not_touch_git(self):
        self._push_new_commit()
        head = _git(self.pc, "rev-parse", "HEAD")
        for key in ("LOTTO_SKIP_SELF_UPDATE", "LOTTO_SELF_UPDATED"):
            with self.subTest(flag=key), mock.patch.dict(os.environ, {key: "1"}):
                with mock.patch.object(weekly, "_git", side_effect=AssertionError("git 호출됨")):
                    self.assertFalse(weekly.self_update_from_github(self.pc))
        self.assertEqual(_git(self.pc, "rev-parse", "HEAD"), head)

    def test_U5_non_git_folder(self):
        plain = self.tmp / "plain"
        plain.mkdir()
        self.assertFalse(weekly.self_update_from_github(plain))

    def test_U6_main_does_not_self_update(self):
        src = (ROOT / "weekly_lotto_file_update.py").read_text(encoding="utf-8")
        main_body = src.split("def main() -> int:", 1)[1].split("\ndef ", 1)[0]
        self.assertNotIn("self_update_from_github", main_body,
                         "main() 안에서 자기 갱신을 부르면 main()을 쓰는 테스트가 실제 git을 건드린다")
        self.assertIn("if self_update_from_github():", src.split('if __name__ == "__main__":', 1)[1])


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(SelfUpdateTests))
    sys.exit(0 if result.wasSuccessful() else 1)
