# -*- coding: utf-8 -*-
"""Actions 워커가 **첫 게이트로** 확인하는 것과 같은 것을 로컬에서 먼저 확인한다(2026-09-27).

왜 필요한가: weekly_combo_gen.yml은 오늘 13:30 KST에 처음 돈다. 워커는 무거운 계산(149초~)에
들어가기 전에 `_load_rules()`로 필터 규칙을 읽는다. 규칙은 DB(app_settings)에만 있고 로컬 JSON은
.gitignore라 Actions 체크아웃에는 없다 — 즉 DB에 규칙이 없으면 그 실행은 error로 끝나고
→ G3가 매주 실패 → 백업 정리가 영영 안 된다. 그래서 지금 DB 상태를 확인한다.

읽기 전용(DB SELECT만). 백업 폴더·스케줄러·DB를 바꾸지 않는다.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import env_loader  # noqa: E402

env_loader.load_dotenv_file()

import app_settings  # noqa: E402
import combo_filter_v2  # noqa: E402
import combo_gen_worker  # noqa: E402
import draw_results_db  # noqa: E402
import marketing_db  # noqa: E402


def main() -> int:
    print("=" * 90)
    print("① DB(app_settings) 안의 필터 규칙 — Actions가 읽게 될 그 값")
    for stage, key in ((1, "filter_rules_stage1_json"), (2, "filter_rules_stage2_json")):
        raw = app_settings.get_setting(key, "")
        print(f"  {key}: {'비어 있음 ← Actions라면 즉시 실패' if not raw.strip() else f'{len(raw):,}자'}")
        if raw.strip():
            try:
                data = json.loads(raw)
                auto = sum(1 for r in data if r.get("is_auto"))
                print(f"    JSON 파싱 OK · 규칙 {len(data)}개 (고정 {len(data) - auto} / AUTO {auto})")
            except Exception as e:  # noqa: BLE001
                print(f"    !! JSON 파싱 실패: {type(e).__name__}: {e}")

    print("\n② 로컬 JSON 사본 존재 여부(있으면 DB가 비어도 조용히 대체돼 착각하게 만든다)")
    for stage, f in ((1, combo_filter_v2._STAGE1_FILE), (2, combo_filter_v2._STAGE2_FILE)):
        p = Path(f)
        print(f"  {stage}차 {p.name}: {'있음(' + str(p.stat().st_size) + 'B)' if p.exists() else '없음'}")

    print("\n③ 워커의 첫 게이트와 동일한 호출: _load_rules()")
    static_rules, auto_rules, stage2_rules = combo_filter_v2._load_rules()
    counts = (len(static_rules), len(auto_rules), len(stage2_rules))
    print(f"  로드 결과 (고정, AUTO, 2차) = {counts}")
    print(f"  워커 기대값 EXPECTED_RULE_COUNTS = {combo_gen_worker.EXPECTED_RULE_COUNTS} "
          f"→ {'일치(경고 없이 진행)' if counts == combo_gen_worker.EXPECTED_RULE_COUNTS else '!! 불일치(경고만 찍고 진행)'}")
    fail = (not static_rules) or (not auto_rules) or (not stage2_rules)
    print(f"  워커가 이 상태에서 죽는가(return 1): {'!! 예 — Actions가 실패로 기록된다' if fail else '아니오(계산 단계로 진행)'}")

    print("\n④ 대상 회차 계산(워커와 같은 함수: peek_target_round)")
    history = draw_results_db.get_all_draw_results()
    target = combo_filter_v2.peek_target_round(history)
    print(f"  이력 {len(history)}회차 · 최신 {max(d['draw_round'] for d in history)} → target_round={target}")
    print(f"  DB 풀: {target}회차={marketing_db.get_combination_count_by_draw(target):,}개")
    print(f"  오늘(일) 생성 대상={target}회차 / 다음 일요일 생성 대상={target + 1}회차")
    return 0


if __name__ == "__main__":
    # os._exit는 버퍼를 흘려보내지 않아 파이프로 받으면 출력이 통째로 사라진다(실측: exit 0 +
    # 빈 출력). 그래서 먼저 flush 한다.
    code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)  # db_turso non-daemon 스레드가 프로세스를 붙잡는 문제 회피
