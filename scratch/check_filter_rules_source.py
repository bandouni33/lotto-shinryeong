# -*- coding: utf-8 -*-
"""필터 규칙(1차/2차)이 실제로 **어디서** 오는지, 그리고 DB가 비면 무슨 일이 나는지 실측.

배경(사용자 지적): combo_filter_v2._load_stage_json()는 "DB 우선 → 없으면 로컬 JSON 폴백"
구조인데, 그 로컬 JSON(combo_filter_rules_stage1/2.json)은 .gitignore로 저장소에서 빠져 있다.
→ Streamlit Cloud 배포본과 GitHub Actions 체크아웃에는 그 파일이 **없다**. 그래서 DB 읽기가
실패하면 폴백이 아니라 FileNotFoundError로 죽는다. 이 스크립트가 그 위험이 지금 실재하는지,
그리고 지금 DB 읽기가 정상인지를 함께 확인한다.

★ 주의: 사용자가 제안한 드라이런(peek_target_round)은 이 질문에 답하지 못한다.
   그 함수는 _prep_history()만 거치고 _load_rules()를 호출하지 않는다(아래 C에서 실측).

이 스크립트가 답하는 것:
  A) 로컬 JSON을 일부러 못 쓰게 만든(= Cloud/Actions와 같은) 조건에서 규칙이 읽히는가
  B) DB가 비어 있을 때 실제로 어떤 예외가 나는가 (우려한 실패 모드 재현)
  C) peek_target_round가 규칙 로드를 거치는가

읽기 전용: DB에 쓰지 않는다(모듈 속성만 임시 패치하고 원복).
실행: venv312\\Scripts\\python.exe scratch\\check_filter_rules_source.py
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import env_loader  # noqa: E402

env_loader.load_dotenv_file()

import app_settings  # noqa: E402
import combo_filter_v2 as cf  # noqa: E402


@contextmanager
def local_json_hidden():
    """로컬 JSON 경로를 '존재하지 않는 파일'로 바꿔 Cloud/Actions 조건을 만든다."""
    orig = (cf._STAGE1_FILE, cf._STAGE2_FILE)
    cf._STAGE1_FILE = str(Path(orig[0]).with_name("__cloud_has_no_this_1.json"))
    cf._STAGE2_FILE = str(Path(orig[1]).with_name("__cloud_has_no_this_2.json"))
    try:
        yield
    finally:
        cf._STAGE1_FILE, cf._STAGE2_FILE = orig


def main() -> int:
    print("로컬 JSON 존재 여부:", os.path.exists(cf._STAGE1_FILE), os.path.exists(cf._STAGE2_FILE),
          "(저장소에는 gitignore로 빠져 있음 — Cloud/Actions 체크아웃에는 없음)")

    print("\nA) 로컬 JSON을 숨긴 채 _load_rules() — 즉 DB만으로 읽히는가")
    try:
        with local_json_hidden():
            static, auto, stage2 = cf._load_rules()
        ok = (len(static), len(auto), len(stage2)) == (378, 3, 48)
        print(f"   1차 고정 {len(static)}개 + AUTO {len(auto)}개, 2차 {len(stage2)}개 "
              f"→ {'DB에서 정상적으로 읽음' if ok else '개수가 예상(378+3/48)과 다름 — 확인 필요'}")
        print("   DB 저장 여부:", bool(app_settings.get_filter_rules_json(1)),
              bool(app_settings.get_filter_rules_json(2)))
    except Exception as e:  # noqa: BLE001
        print(f"   → 실패: {type(e).__name__}: {e}")
        return 1

    print("\nB) DB가 빈 값이면? (우려한 폴백 실패 모드 재현)")
    orig_get = app_settings.get_filter_rules_json
    app_settings.get_filter_rules_json = lambda stage: ""
    try:
        with local_json_hidden():
            cf._load_rules()
        print("   → 예외 없이 통과(예상 밖)")
    except Exception as e:  # noqa: BLE001
        print(f"   → {type(e).__name__}: {e}")
        print("     (로컬 JSON이 있는 개발 PC에서는 그 파일로 폴백되지만, Cloud/Actions에는 없으므로 죽는다)")
    finally:
        app_settings.get_filter_rules_json = orig_get

    print("\nC) peek_target_round가 규칙 로드를 거치는가")
    calls = []
    orig_load = cf._load_rules

    def counting_load():
        calls.append(1)
        return orig_load()

    cf._load_rules = counting_load
    try:
        import draw_results_db

        h = draw_results_db.get_all_draw_results()
        target = cf.peek_target_round(h)
        print(f"   peek_target_round = {target} · 그 동안 _load_rules 호출 {len(calls)}회")
        if not calls:
            print("   → 규칙을 읽지 않는다: 이 드라이런이 성공해도 'DB 규칙 읽기 정상'의 근거가 되지 못한다")
        else:
            print("   → 규칙을 읽는다: 이 드라이런이 곧 DB 규칙 확인이 된다")
    finally:
        cf._load_rules = orig_load

    print("\nD) 실제 배포 경로가 거치는 함수(무거운 계산 직전 단계)로 같은지 확인")
    print("   generate_next_round_combos()는 _compute_pool_for_anchor() → _load_rules()를 거친다:", )
    import inspect

    src = inspect.getsource(cf._compute_pool_for_anchor)
    print("   _compute_pool_for_anchor 안에 _load_rules() 호출 존재 =", "_load_rules()" in src)
    return 0


if __name__ == "__main__":
    code = main()
    os._exit(code)  # db_turso의 non-daemon 스레드가 종료를 붙잡는 문제 회피(선례: hourly_draw_sync.py)
