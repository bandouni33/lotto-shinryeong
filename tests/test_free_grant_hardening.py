"""무료 지급 우회 차단(하드닝) 검증 — 2026-09-27.

왜 필요한가: `_dev_mock_enabled()`의 기본값이 "1"(켜짐)이었고 `kakao_configured()`가
os.environ만 봤다. 그래서 **환경변수가 빠진 배포**(시크릿 누락·오타, secrets로만 넣은
구성)에서는 `wallet_ui._testing_period_active()`가 True로 돌아가 ① 구독 안내창을
건너뛰고 3650일 무료 구독 지급 ② 안내 없는 조용한 자동 로그인이 켜졌다 —
기본값이 "돈이 새는 방향"이었다.

  H1 _dev_mock_enabled()는 명시적으로 켤 때만 True (입력값 전수 — 경계 포함)
  H2 kakao_configured()가 env → st.secrets 순으로 읽는다(secrets가 없거나 깨져도 죽지 않는다)
  H3 _testing_period_active() == (mock and not kakao) — 네 조합 전수
  H4 기본값(둘 다 비어있음)에서는 무료 우회가 켜지지 않고, 구독 안내창을 실제로
     렌더해도 지급이 일어나지 않는다(조립 검증)
  H5 명시적으로 켜면 개발 편의 경로는 그대로 살아있고, 카카오가 실연동되면 자동으로 꺼진다

DB는 _db_isolation.isolated_db()로만 만진다(운영 Turso 접촉 0).
pytest 없이 돌도록 표준 assert + __main__ 러너를 둔다.
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path

from streamlit.testing.v1 import AppTest

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _path in (str(ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import _db_isolation  # noqa: E402
import wallet_db as wdb  # noqa: E402

PROBE = str(TESTS_DIR / "_iap_probe.py")
TIMEOUT_SEC = 60
_ENV_KEYS = ("LOTTO_DEV_MOCK_AUTH", "KAKAO_REST_API_KEY")


@contextmanager
def _env(**values: str):
    """환경변수를 **명시적으로** 세팅한다.

    '값 없음'을 pop이 아니라 빈 문자열로 재현한다 — app.py가 import되면 .env가
    os.environ에 채워지므로(load_dotenv, override=False) pop만 하면 .env 값이 다시
    들어와 판정이 달라진다. 빈 문자열은 두 함수 모두 없는 것과 결과가 같다
    (os.environ.get(name, "")).
    """
    before = {key: os.environ.get(key) for key in _ENV_KEYS}
    for key, value in values.items():
        os.environ[key] = value
    try:
        yield
    finally:
        for key, value in before.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class _FakeSecrets:
    """st.secrets 대역 — AppTest도 st.secrets를 통째로 바꿔치기한다(같은 방식)."""

    def __init__(self, data: dict):
        self._data = dict(data)

    def get(self, key, default=None):
        return self._data.get(key, default)


class _BrokenSecrets:
    """secrets 파일이 아예 없을 때처럼 읽기 자체가 실패하는 경우."""

    def get(self, *_args, **_kwargs):
        raise FileNotFoundError("no secrets.toml")


def _rows(sql: str, *params):
    import sqlite3

    conn = sqlite3.connect(_db_isolation.current_path())
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _member(handle: str) -> int:
    wdb.init_wallet_tables()
    mid, _is_new = wdb.get_or_create_member("kakao", handle)
    return int(mid)


def _ss(at: AppTest, key: str, default=None):
    try:
        return at.session_state[key]
    except KeyError:
        return default


# ── H1 ────────────────────────────────────────────────────────
# 값 → 기대값. 예전 구현(`not in ("0","false","False")`)에서는 "on"·"2"·"truee"까지
# 켜졌다 — 알 수 없는 값은 꺼지는 쪽이 안전하다(fail-closed).
_MOCK_CASES = (
    ("1", True),
    ("true", True),
    ("TRUE", True),
    ("yes", True),
    (" 1 ", True),
    ("0", False),
    ("false", False),
    ("False", False),
    ("no", False),
    ("", False),
    ("2", False),
    ("on", False),
    ("truee", False),
    ("  ", False),
)


def test_H1_mock_auth_is_on_only_when_explicitly_enabled():
    import auth_providers

    for raw, expected in _MOCK_CASES:
        with _env(LOTTO_DEV_MOCK_AUTH=raw):
            actual = auth_providers._dev_mock_enabled()
            assert actual is expected, f"LOTTO_DEV_MOCK_AUTH={raw!r} → {actual} (기대 {expected})"


# ── H2 ────────────────────────────────────────────────────────
def test_H2_kakao_key_is_read_from_env_then_secrets():
    import auth_providers
    import streamlit as st

    original = st.secrets
    try:
        with _env(KAKAO_REST_API_KEY=""):
            st.secrets = _FakeSecrets({})
            assert auth_providers.kakao_configured() is False, "키가 없는데 configured=True"

            st.secrets = _FakeSecrets({"KAKAO_REST_API_KEY": "from-secrets"})
            assert auth_providers.kakao_configured() is True, (
                "secrets에만 있는 카카오 키를 못 읽는다 — 무료 우회가 켜지는 취약 고리"
            )

            st.secrets = _FakeSecrets({"KAKAO_REST_API_KEY": "   "})
            assert auth_providers.kakao_configured() is False, "공백만 있는 키를 유효로 본다"

            st.secrets = _BrokenSecrets()
            assert auth_providers.kakao_configured() is False, "secrets 읽기 실패가 예외로 샜다"

        with _env(KAKAO_REST_API_KEY="from-env"):
            st.secrets = _FakeSecrets({"KAKAO_REST_API_KEY": "from-secrets"})
            assert auth_providers.kakao_configured() is True
            assert auth_providers._env_or_secret("KAKAO_REST_API_KEY") == "from-env", (
                "env가 secrets보다 우선하지 않는다"
            )

        with _env(KAKAO_REST_API_KEY="  padded  "):
            st.secrets = _BrokenSecrets()
            assert auth_providers._env_or_secret("KAKAO_REST_API_KEY") == "padded", (
                "env 값의 앞뒤 공백을 제거하지 않는다"
            )
    finally:
        st.secrets = original


# ── H3 ────────────────────────────────────────────────────────
# (mock, kakao, 기대) — 네 조합 전수
_PERIOD_CASES = (
    ("", "", False),
    ("1", "", True),
    ("", "kakao-key", False),
    ("1", "kakao-key", False),
)


def test_H3_testing_period_is_mock_and_not_kakao_for_every_combination():
    import wallet_ui

    for raw_mock, raw_kakao, expected in _PERIOD_CASES:
        with _env(LOTTO_DEV_MOCK_AUTH=raw_mock, KAKAO_REST_API_KEY=raw_kakao):
            actual = wallet_ui._testing_period_active()
            assert actual is expected, (
                f"mock={raw_mock!r} kakao={raw_kakao!r} → {actual} (기대 {expected})"
            )


# ── H4 (조립: 실제 렌더에서 지급이 일어나지 않는가) ────────────
def test_H4_default_env_does_not_grant_free_subscription():
    with _env(LOTTO_DEV_MOCK_AUTH="", KAKAO_REST_API_KEY=""), _db_isolation.isolated_db():
        import wallet_ui

        assert wallet_ui._testing_period_active() is False, "기본값에서 무료 우회가 켜져 있다"
        mid = _member("hardening_h4")

        at = AppTest.from_file(PROBE, default_timeout=TIMEOUT_SEC)
        at.query_params["probe"] = "sub"
        at.session_state["member_id"] = mid
        at.run()
        assert not at.exception, f"구독 안내창 렌더 예외: {at.exception}"

        rows = _rows("SELECT expires_at, starts_at FROM subscriptions WHERE member_id = ?", mid)
        assert rows == [], f"구독 안내창을 여는 것만으로 구독이 지급됐다: {rows}"


# ── H5 (개발 편의 경로는 살아있다) ────────────────────────────
def test_H5_explicit_dev_switch_still_works_and_turns_off_when_kakao_is_live():
    import wallet_ui

    with _env(LOTTO_DEV_MOCK_AUTH="1", KAKAO_REST_API_KEY=""):
        assert wallet_ui._testing_period_active() is True, (
            "명시적으로 켠 개발용 Mock 인증 경로가 죽었다(.env·run_server.ps1 경로 확인)"
        )
    with _env(LOTTO_DEV_MOCK_AUTH="1", KAKAO_REST_API_KEY="live-key"):
        assert wallet_ui._testing_period_active() is False, (
            "카카오가 실연동돼도 테스트 기간 우회가 안 꺼진다"
        )


def _main() -> int:
    tests = [
        test_H1_mock_auth_is_on_only_when_explicitly_enabled,
        test_H2_kakao_key_is_read_from_env_then_secrets,
        test_H3_testing_period_is_mock_and_not_kakao_for_every_combination,
        test_H4_default_env_does_not_grant_free_subscription,
        test_H5_explicit_dev_switch_still_works_and_turns_off_when_kakao_is_live,
    ]
    failed = 0
    for test in tests:
        try:
            test()
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {str(exc).encode('ascii', 'replace').decode('ascii')}")
        except Exception as exc:  # noqa: BLE001 — 러너이므로 무엇이든 보고하고 계속
            failed += 1
            print(
                f"ERROR {test.__name__}: {type(exc).__name__}: "
                f"{str(exc).encode('ascii', 'replace').decode('ascii')}"
            )
        else:
            print(f"PASS {test.__name__}")
        sys.stdout.flush()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.stdout.flush()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
