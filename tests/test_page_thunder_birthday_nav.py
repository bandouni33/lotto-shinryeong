"""번개조합 "생일/행운수 관리" 이동 버튼 — 쿼리파라미터 보존 불변식.

2026-09-19 수정: 이 버튼 핸들러가 `st.query_params.clear()`로 gid(게스트 식별자)와
native(네이티브 앱 플래그)까지 지워버려, 누를 때마다 게스트 식별자가 끊기고
localStorage 복구 스크립트가 강제 재로딩을 걸어 "로그인이 풀리는" 원인이었다.
그 한 줄을 제거했고, 그 계약을 여기서 실제 Streamlit 런타임(AppTest)으로 확인한다.

불변식 (모든 파라미터 조합에 대해 성립해야 하는 성질):
  I1. 렌더가 예외 없이 끝난다 (클릭 전/후 모두).
  I2. 버튼이 실제로 화면에 마운트되어 key로 찾을 수 있다.
  I3. 클릭 후 page == "birthday" (핸들러의 목적이 달성된다).
  I4. 클릭 전 존재하던 다른 모든 쿼리파라미터는 이름·값이 그대로 남는다(보존).
  I5. 클릭이 파라미터 키 집합을 늘리지도 줄이지도 않는다
      (클릭 전 = 입력 그대로, 클릭 후 = 입력 + {"page"}).
  I6. 연속 클릭해도 I1·I3~I5가 유지된다(멱등).

pytest 없이도 돌아가도록 표준 assert와 __main__ 러너를 함께 둔다.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

# AppTest는 상대경로를 "이 파일을 부른 파일" 기준으로 풀어서, tests/ 안에 있으면
# tests/page_thunder.py를 찾다가 FileNotFoundError가 난다 — 저장소 루트 기준
# 절대경로로 고정한다(테스트가 이 함정을 실제로 잡아냈다).
APP = str(Path(__file__).resolve().parent.parent / "page_thunder.py")
BUTTON_KEY = "th_nav_bday_6n36s5"
TIMEOUT_SEC = 60

# 파라미터 조합(입력) — 값은 문자열로 넣고, AppTest는 parse_qs 의미론에 따라
# 리스트로 돌려준다. 그래서 출력 비교는 _as_list()로 정규화한다.
# 빈 문자열 값("")은 일부러 넣지 않는다 — parse_qs가 빈 값을 버리는 표준 동작이라
# "보존되어야 한다"고 주장할 수 없는 입력이기 때문(경계는 '없음'으로 커버).
CASES: list[dict[str, str]] = [
    {},  # 경계: page 외에 아무 파라미터도 없음
    {"gid": "a" * 32, "native": "1"},  # 네이티브 앱이 실어보내는 통상 조합
    {  # 여러 개 + 유니코드 값 + 숫자형 값
        "gid": "b2c3d4e5f6",
        "native": "1",
        "_cb": "1726700000000",
        "q": "한글 값",
    },
]


def _as_list(v) -> list[str]:
    """AppTest가 돌려주는 파라미터 값(리스트)과 우리가 넣은 값(문자열)을 같은 모양으로."""
    if isinstance(v, list):
        return [str(x) for x in v]
    return [] if v is None else [str(v)]


def _open_app(params: dict[str, str]) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=TIMEOUT_SEC)
    for k, v in params.items():
        at.query_params[k] = v
    at.run()
    return at


def _click_birthday_nav(at: AppTest) -> None:
    at.button(key=BUTTON_KEY).click().run()


def _assert_rendered(at: AppTest, stage: str) -> None:
    assert len(at.exception) == 0, f"[{stage}] 앱이 예외로 죽었다: {at.exception}"


def _assert_params_preserved(at: AppTest, params: dict[str, str], *, clicked: bool, stage: str) -> None:
    """I4·I5 — 기존 파라미터의 이름·값이 그대로이고, 키 집합도 의도한 만큼만 변한다."""
    for k, v in params.items():
        assert _as_list(at.query_params.get(k)) == [v], (
            f"[{stage}] 파라미터 {k!r}가 보존되지 않았다 "
            f"(기대 {v!r}, 실제 {at.query_params.get(k)!r}, 전체 {dict(at.query_params)})"
        )
    expected_keys = set(params) | ({"page"} if clicked else set())
    actual_keys = set(at.query_params)
    assert actual_keys == expected_keys, (
        f"[{stage}] 쿼리파라미터 키 집합이 변했다 "
        f"(기대 {sorted(expected_keys)}, 실제 {sorted(actual_keys)})"
    )


def _assert_nav_happened(at: AppTest, stage: str) -> None:
    """I3 — 버튼을 누른 뒤에는 page가 birthday여야 한다."""
    assert _as_list(at.query_params.get("page")) == ["birthday"], (
        f"[{stage}] page가 birthday로 바뀌지 않았다: {dict(at.query_params)}"
    )


def test_birthday_nav_preserves_query_params_for_every_case() -> None:
    """I1~I5 — 파라미터 조합마다: 렌더 → 클릭 → page 변경 + 나머지 전부 보존."""
    for params in CASES:
        at = _open_app(params)
        _assert_rendered(at, f"클릭 전 {params}")
        # I2: 버튼이 실제로 마운트되어 있어야 클릭이 가능하다(찾기 실패 시 여기서 예외).
        assert at.button(key=BUTTON_KEY) is not None, f"버튼이 없다: {params}"
        _assert_params_preserved(at, params, clicked=False, stage=f"클릭 전 {params}")

        _click_birthday_nav(at)
        _assert_rendered(at, f"클릭 후 {params}")
        _assert_nav_happened(at, f"클릭 후 {params}")
        _assert_params_preserved(at, params, clicked=True, stage=f"클릭 후 {params}")


def test_birthday_nav_is_idempotent_on_repeat_clicks() -> None:
    """I6 — 같은 화면에서 연속 클릭해도 보존 불변식이 계속 성립한다."""
    params = {"gid": "deadbeef", "native": "1"}
    at = _open_app(params)
    for i in (1, 2, 3):
        _click_birthday_nav(at)
        _assert_rendered(at, f"{i}번째 클릭 {params}")
        _assert_nav_happened(at, f"{i}번째 클릭 {params}")
        _assert_params_preserved(at, params, clicked=True, stage=f"{i}번째 클릭 {params}")


# 수정 전 코드(한 줄 제거 전) — 이 핸들러를 그대로 흉내 낸 앱에서 위 불변식이
# 실제로 깨져야 한다. 깨지지 않으면 이 테스트는 아무것도 검사하지 않는 것이다
# (통과만 하는 테스트 방지).
_OLD_HANDLER_APP = """
import streamlit as st

if st.button("bday", key="probe_bday"):
    st.query_params.clear()
    st.query_params["page"] = "birthday"
    st.rerun()
"""


def test_harness_detects_param_dropping() -> None:
    """이 테스트 자체의 검출력 확인 — clear()를 하는 예전 동작에서는 I4가 깨진다."""
    params = {"gid": "deadbeef", "native": "1"}
    at = AppTest.from_string(_OLD_HANDLER_APP, default_timeout=TIMEOUT_SEC)
    at.query_params.update(params)
    at.run()
    at.button(key="probe_bday").click().run()
    assert len(at.exception) == 0, f"대조군 앱이 예외로 죽었다: {at.exception}"
    try:
        _assert_params_preserved(at, params, clicked=True, stage="대조군(수정 전 코드)")
    except AssertionError:
        return  # 기대대로 예전 동작을 잡아냈다
    raise AssertionError(
        "수정 전 코드(clear 포함)를 잡아내지 못했다 — 이 테스트는 검출력이 없다: "
        f"{dict(at.query_params)}"
    )


def _main() -> int:
    tests = [
        test_birthday_nav_preserves_query_params_for_every_case,
        test_birthday_nav_is_idempotent_on_repeat_clicks,
        test_harness_detects_param_dropping,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001 — 러너이므로 무엇이든 보고하고 계속
            failed += 1
            print(f"ERROR {t.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"PASS {t.__name__}")
        sys.stdout.flush()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.stdout.flush()
    # db_turso.py가 모듈 import 시점에 만드는 ThreadPoolExecutor(비데몬 스레드)가
    # 살아있어 프로세스가 스스로 끝나지 않는다(첫 실행에서 실제로 요약을 찍고도
    # 120초 제한에 걸려 죽었다) — 결과를 다 낸 뒤에는 즉시 종료한다.
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
