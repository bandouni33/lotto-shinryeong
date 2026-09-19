"""번개조합 "생일/행운수 관리" 이동 버튼 — 쿼리파라미터 보존 불변식.

2026-09-19 수정: 이 버튼 핸들러가 `st.query_params.clear()`로 gid(게스트 식별자)와
native(네이티브 앱 플래그)까지 지워버려, 누를 때마다 게스트 식별자가 끊기고
localStorage 복구 스크립트가 강제 재로딩을 걸어 "로그인이 풀리는" 원인이었다.
그 한 줄을 제거했고, 그 계약을 여기서 실제 Streamlit 런타임으로 확인한다.

불변식 (모든 파라미터 조합에 대해 성립해야 하는 성질):
  I1. 렌더 자체가 예외 없이 끝난다.
  I2. 버튼이 실제로 화면에 마운트되어 key로 찾을 수 있다.
  I3. 클릭 후 page == "birthday" (핸들러의 목적이 달성된다).
  I4. 클릭 전 존재하던 다른 모든 쿼리파라미터는 이름·값이 그대로 남는다(보존).
  I5. 클릭이 파라미터 집합을 늘리지도 줄이지도 않는다(보존/불변).
  I6. 두 번 눌러도 I3~I5가 유지된다(멱등).

pytest 없이도 돌아가도록 표준 assert와 __main__ 러너를 함께 둔다.
"""

from __future__ import annotations

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


def _assert_invariants(after: AppTest, params: dict[str, str], stage: str) -> None:
    # I1: 예외 없이 렌더
    assert len(after.exception) == 0, f"[{stage}] 앱이 예외로 죽었다: {after.exception}"
    # I3: 목적 달성
    assert _as_list(after.query_params.get("page")) == ["birthday"], (
        f"[{stage}] page가 birthday로 바뀌지 않았다: {dict(after.query_params)}"
    )
    # I4: 기존 파라미터 보존(이름·값 동일)
    for k, v in params.items():
        assert _as_list(after.query_params.get(k)) == [v], (
            f"[{stage}] 파라미터 {k!r}가 보존되지 않았다 "
            f"(기대 {v!r}, 실제 {after.query_params.get(k)!r}, 전체 {dict(after.query_params)})"
        )
    # I5: 키 집합이 늘지도 줄지도 않는다
    expected_keys = set(params) | {"page"}
    actual_keys = set(after.query_params)
    assert actual_keys == expected_keys, (
        f"[{stage}] 쿼리파라미터 키 집합이 변했다 (기대 {sorted(expected_keys)}, 실제 {sorted(actual_keys)})"
    )


def test_birthday_nav_preserves_query_params_for_every_case() -> None:
    """I1~I5 — 파라미터 조합마다: 렌더 → 클릭 → page 변경 + 나머지 전부 보존."""
    for params in CASES:
        at = _open_app(params)
        # I2: 버튼이 실제로 마운트되어 있어야 클릭이 가능하다(찾기 실패 시 여기서 예외).
        assert at.button(key=BUTTON_KEY) is not None, f"버튼이 없다: {params}"
        _assert_invariants(at, params, stage=f"클릭 전 {params}")

        _click_birthday_nav(at)
        _assert_invariants(at, params, stage=f"클릭 후 {params}")


def test_birthday_nav_is_idempotent_on_repeat_clicks() -> None:
    """I6 — 같은 화면에서 연속 클릭해도 보존 불변식이 계속 성립한다."""
    params = {"gid": "deadbeef", "native": "1"}
    at = _open_app(params)
    for i in (1, 2, 3):
        _click_birthday_nav(at)
        _assert_invariants(at, params, stage=f"{i}번째 클릭 {params}")


def _main() -> int:
    tests = [
        test_birthday_nav_preserves_query_params_for_every_case,
        test_birthday_nav_is_idempotent_on_repeat_clicks,
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
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
