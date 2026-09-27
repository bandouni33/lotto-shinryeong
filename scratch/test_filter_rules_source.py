# -*- coding: utf-8 -*-
"""필터 규칙 소스 관련 불변식 고정 — 진단 스크립트(check_filter_rules_source.py)의 발견을
단언으로 못박는다. 누군가 동작을 바꾸면 이 테스트가 먼저 깨져서 알려준다.

고정하는 불변식:
  1) 규칙 읽기 우선순위: DB에 값이 있으면 **로컬 파일보다 DB가 이긴다**
     (combo_filter_v2._load_stage_json: DB 우선 → 없으면 파일 폴백)
  2) 로컬 JSON이 없어도(= Streamlit Cloud·Actions와 같은 조건) DB만으로 1차 378+3 / 2차 48이 나온다
  3) DB에도 로컬 파일에도 규칙이 없으면 **반드시 예외로 실패**한다 (조용히 빈 규칙으로 진행하지 않는다)
  4) peek_target_round()는 규칙을 읽지 않는다 → 그 드라이런 성공은 'DB 규칙 정상'의 근거가 아니다
  5) 실제 생성 경로(_compute_pool_for_anchor)는 _load_rules()를 거친다

읽기 전용(DB 쓰기 없음). 실행:
    venv312\\Scripts\\python.exe scratch\\test_filter_rules_source.py
"""

from __future__ import annotations

import inspect
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # 진단 스크립트 재사용
os.chdir(ROOT)

import app_settings  # noqa: E402
import combo_filter_v2 as cf  # noqa: E402
from check_filter_rules_source import local_json_hidden  # noqa: E402


class RuleSourcePrecedenceTests(unittest.TestCase):
    """1) DB가 있으면 DB가 이긴다 (폴백이 아니라 우선순위)."""

    def test_db_value_wins_over_local_file(self):
        fake_stage = json.dumps([{"name": "FAKE", "targets": [1], "min": 1, "max": 1, "is_auto": False}])
        orig = app_settings.get_filter_rules_json
        app_settings.get_filter_rules_json = lambda stage: fake_stage
        try:
            static, auto, stage2 = cf._load_rules()
        finally:
            app_settings.get_filter_rules_json = orig
        self.assertEqual([r["name"] for r in static], ["FAKE"], "DB 값이 무시되고 로컬 파일이 쓰였다")
        self.assertEqual(auto, [])
        self.assertEqual(stage2[0]["name"], "FAKE")


class CloudLikeEnvironmentTests(unittest.TestCase):
    """2) 로컬 JSON이 없는 환경에서도 DB만으로 규칙이 나와야 한다."""

    def test_rules_load_from_db_without_local_files(self):
        self.assertTrue(app_settings.get_filter_rules_json(1), "1차 규칙이 DB에 없다")
        self.assertTrue(app_settings.get_filter_rules_json(2), "2차 규칙이 DB에 없다")
        with local_json_hidden():
            static, auto, stage2 = cf._load_rules()
        self.assertEqual((len(static), len(auto), len(stage2)), (378, 4, 48),
                         "DB만으로는 1차 378+4 / 2차 48이 나오지 않는다"
                         "(2026-09-27: '후보패턴 이웃수(200회)'를 파일과 같게 추가해 AUTO가 3→4)")


class MissingRuleFailureTests(unittest.TestCase):
    """3) 규칙이 어디에도 없으면 조용히 진행하지 않고 예외로 실패한다."""

    def test_no_db_no_file_raises(self):
        orig = app_settings.get_filter_rules_json
        app_settings.get_filter_rules_json = lambda stage: ""
        try:
            with local_json_hidden():
                with self.assertRaises(Exception) as ctx:
                    cf._load_rules()
        finally:
            app_settings.get_filter_rules_json = orig
        self.assertIsInstance(ctx.exception, (FileNotFoundError, RuntimeError),
                              f"예외 종류가 예상 밖: {type(ctx.exception).__name__}")

    def test_error_message_names_cause_and_recovery(self):
        """2026-09-27: 날것의 FileNotFoundError 대신 원인(DB 키)과 복구 방법을 말해줘야 한다."""
        orig = app_settings.get_filter_rules_json
        app_settings.get_filter_rules_json = lambda stage: ""
        try:
            with local_json_hidden():
                with self.assertRaises(RuntimeError) as ctx:
                    cf._load_rules()
        finally:
            app_settings.get_filter_rules_json = orig
        msg = str(ctx.exception)
        self.assertIn("filter_rules_stage1_json", msg)
        self.assertIn("migrate_filter_rules_to_db.py", msg)

    def test_local_file_fallback_still_works_when_present(self):
        """개발 PC처럼 로컬 JSON이 있으면 예전과 동일하게 그 파일로 폴백한다(동작 변화 없음)."""
        orig = app_settings.get_filter_rules_json
        app_settings.get_filter_rules_json = lambda stage: ""
        try:
            static, auto, stage2 = cf._load_rules()   # 숨기지 않음 = 파일 존재
        finally:
            app_settings.get_filter_rules_json = orig
        self.assertEqual((len(static), len(auto), len(stage2)), (378, 4, 48))

    def test_db_read_error_does_not_silently_succeed(self):
        """DB 조회가 예외여도 규칙 없이 진행하지 않는다(파일 폴백 시도 후 실패)."""
        def boom(stage):
            raise TimeoutError("Turso 무응답")

        orig = app_settings.get_filter_rules_json
        app_settings.get_filter_rules_json = boom
        try:
            with local_json_hidden():
                with self.assertRaises(Exception):
                    cf._load_rules()
        finally:
            app_settings.get_filter_rules_json = orig


class DryRunScopeTests(unittest.TestCase):
    """4·5) 어떤 함수가 규칙을 읽는지 — 드라이런의 의미를 정확히 못박는다."""

    def test_peek_target_round_does_not_read_rules(self):
        calls = []
        orig = cf._load_rules

        def counting():
            calls.append(1)
            return orig()

        cf._load_rules = counting
        try:
            import draw_results_db

            target = cf.peek_target_round(draw_results_db.get_all_draw_results())
        finally:
            cf._load_rules = orig
        self.assertGreater(target, 0)
        self.assertEqual(calls, [], "peek_target_round가 규칙을 읽는다면 이 테스트의 전제를 갱신해야 한다")

    def test_real_generation_path_reads_rules(self):
        """실제 생성 경로가 규칙을 **실제로** 읽는가 — 규칙을 못 읽게 만들면 생성 경로가
        무거운 계산(8백만 조합)을 시작하기 전에 멈춰서 여야 한다(규칙 없이 조용히 돌면 안 된다).

        2026-09-27: 마스크 계산이 compute_stage_masks로 모이면서 경로가
        _compute_pool_for_anchor → compute_stage_masks → build_base_masks → _load_rules로
        이어지게 됐다 — 그래서 특정 함수의 소스 문구가 아니라 '멈추는가'로 확인한다."""
        def boom():
            raise RuntimeError("규칙을 읽지 못함(시험용)")

        orig = cf._load_rules
        cf._load_rules = boom
        try:
            with self.assertRaises(RuntimeError):
                cf.compute_stage_masks([{"draw_round": 1, "nums": [1, 2, 3, 4, 5, 6],
                                         "bonus": 7}], 1)
        finally:
            cf._load_rules = orig

    def test_rules_have_expected_shape(self):
        with local_json_hidden():
            static, auto, stage2 = cf._load_rules()
        for rules in (static, stage2):
            for r in rules:
                self.assertIn("targets", r)
                self.assertLessEqual(r["min"], r["max"])
                self.assertTrue(1 <= r["min"] or r["min"] == 0)


if __name__ == "__main__":
    # 2026-09-27: 테스트는 0.9초에 OK로 끝나는데 프로세스가 종료되지 않아 실행 도구가 강제 종료했다
    # (exit 124, 실측). 원인은 db_turso가 만드는 non-daemon 스레드가 인터프리터 종료를 붙잡는 것 —
    # 이 앱에서 이미 아는 문제이고 hourly_draw_sync.py가 os._exit()로 대응한 선례를 그대로 따른다.
    import os as _os

    program = unittest.main(verbosity=2, exit=False)
    _os._exit(0 if program.result.wasSuccessful() else 1)
