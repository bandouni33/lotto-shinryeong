"""카카오 앱(네이티브) 로그인 경로 진단 계약 — 2026-09-27 "눌러도 다음 단계로 안 넘어간다" 대응.

배경: 앱(안드로이드 웹뷰)의 카카오 로그인은 세 단계로 이어진다.
  (1) 배너 버튼 → 서버가 앱에 "네이티브 SDK로 로그인해달라"는 신호를 보낸다
      (wallet_ui._fire_kakao_native_login_trigger — postMessage 또는 URL 파라미터).
  (2) 앱이 카카오 SDK로 로그인해 받은 access_token을 주소에 실어 웹뷰를 다시 띄운다.
  (3) 서버가 그 토큰을 카카오에 직접 검증해 로그인을 완료한다
      (auth_providers.finalize_login_with_native_token).
어느 단계에서 끊겨도 예전에는 서버에 흔적이 하나도 남지 않았다 — 테스터 전원이
로그인을 못 하는데 "앱이 신호를 못 받은 것"인지 "서버가 토큰을 거절한 것"인지
사후에 구분할 방법이 없었다. 그래서 세 단계가 각각 이름 있는 기록으로 남고, 실패가
사용자 화면을 죽이지 않는지를 여기서 고정한다.

불변식/계약:
  N1. 토큰 검증 실패 → None 반환(예외 없음) + 실패 이유가 [kakao_native_login_fail]
      경고 로그와 대시보드 계측 이벤트에 남고, 토큰 원문은 남지 않는다.
  N2. 토큰 검증 성공 → finalize_login("kakao", uid)을 그대로 호출하고 그 결과를
      그대로 돌려준다(성공 흐름은 이전과 동일) + 완료 계측 1건.
  N3. 로그인 처리 중 예외 → None 반환(페이지가 죽지 않는다) + 이유가 기록된다.
  N4. 새 계측 이벤트 3종은 대시보드 라벨이 있고 '침입 시도' 경보 집계에서 빠진다.
  N5. 조립(진입점): native_kakao_token이 실려 와 검증이 실패해도 화면은 살아 있고
      로그인되지 않으며, 주소의 토큰 파라미터가 지워진다.
  N6. 조립(배너): 앱 배너의 카카오 버튼을 실제로 누르면 (1)단계 신호 기록이 남는다 —
      이 기록이 없는데 이후 이벤트도 없으면 "앱이 응답을 안 했다"는 뜻이다.

pytest 없이도 돌도록 표준 assert + __main__ 러너를 함께 둔다.
"""

from __future__ import annotations

import contextlib
import logging
import os
import sqlite3
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _path in (str(ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import _db_isolation  # noqa: E402

TIMEOUT_SEC = 60
ENTRY = str(ROOT / "app.py")
NATIVE_BTN = "auth_banner_kakao_native"

TRIGGER_EVENT = "kakao_native_trigger"
OK_EVENT = "kakao_native_login_ok"
FAIL_EVENT = "kakao_native_login_fail"
INSTRUMENTED_EVENTS = (TRIGGER_EVENT, OK_EVENT, FAIL_EVENT)


# ── 공용 도우미 ──────────────────────────────────────────────────────────────
def _rows(sql: str, params=()) -> list[tuple]:
    path = _db_isolation.current_path()
    assert path, "테스트 DB 경로를 얻지 못했다(격리 밖에서 조회할 뻔했다)"
    conn = sqlite3.connect(path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _events(event_type: str) -> list[str]:
    return [r[0] for r in _rows("SELECT detail FROM security_events WHERE event_type = ?", (event_type,))]


class _LogCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record):  # noqa: D102
        try:
            self.messages.append(record.getMessage())
        except Exception:
            pass


@contextlib.contextmanager
def _log_lines():
    """루트 로거에 임시 핸들러를 붙여 경고/오류 줄을 그대로 모은다 — "Cloud 로그에
    남는다"는 이 변경의 요점이라, 실제로 방출되는지를 확인해야 한다."""
    handler = _LogCapture()
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(handler)
    if root.level == logging.NOTSET or root.level > logging.WARNING:
        root.setLevel(logging.WARNING)
    try:
        yield handler.messages
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)


@contextlib.contextmanager
def _patched(targets: dict):
    """{(모듈, 이름): 대역 함수}로 잠깐 바꿔치기한다. 카카오 서버·DB 쓰기를 스텁으로
    대신해 "서버가 토큰을 거절했다"는 상황만 정확히 만든다."""
    saved = {(mod, name): getattr(mod, name) for (mod, name) in targets}
    try:
        for (mod, name), fn in targets.items():
            setattr(mod, name, fn)
        yield
    finally:
        for (mod, name), fn in saved.items():
            setattr(mod, name, fn)


@contextlib.contextmanager
def _kakao_configured_env():
    before_key = os.environ.get("KAKAO_REST_API_KEY")
    before_mock = os.environ.get("LOTTO_DEV_MOCK_AUTH")
    os.environ["KAKAO_REST_API_KEY"] = "test-rest-key"
    os.environ["LOTTO_DEV_MOCK_AUTH"] = "0"
    try:
        yield
    finally:
        for name, before in (("KAKAO_REST_API_KEY", before_key), ("LOTTO_DEV_MOCK_AUTH", before_mock)):
            if before is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = before


# ── N1~N3: 토큰 검증 단계(순수 함수) ────────────────────────────────────────
def test_n1_failed_token_returns_none_and_records_the_reason() -> None:
    """N1 — 거절된 토큰: 예외 없이 None, 이유는 로그와 기록에 남고 토큰 원문은 안 남는다."""
    import auth_providers as ap

    reason = '카카오 사용자 조회 오류 (401): {"msg":"this access token does not exist"}'
    token = "expired_token_value_should_not_be_stored"
    with _db_isolation.isolated_db():
        with _patched({(ap, "_fetch_kakao_uid_with_token"): lambda tok: (None, reason)}):
            with _log_lines() as lines:
                result = ap.finalize_login_with_native_token(token)

        assert result is None, "실패했는데 성공 값을 돌려줬다"
        assert any("[kakao_native_login_fail]" in line and "401" in line for line in lines), (
            f"Cloud 로그에 실패 이유가 남지 않았다: {lines!r}"
        )
        recorded = _events(FAIL_EVENT)
        assert len(recorded) == 1, f"실패 기록이 정확히 1건이 아니다: {recorded!r}"
        assert "401" in recorded[0], f"실패 이유가 기록에 없다: {recorded[0]!r}"
        assert token not in recorded[0], "토큰 원문이 기록에 남았다(개인정보·비밀값 유출)"


def test_n2_success_path_is_unchanged_and_recorded() -> None:
    """N2 — 성공 흐름은 이전과 완전히 동일하다(카카오 uid로 그대로 로그인 처리)."""
    import auth_providers as ap

    calls: list[tuple[str, str]] = []
    with _db_isolation.isolated_db():
        with _patched(
            {
                (ap, "_fetch_kakao_uid_with_token"): lambda tok: ("kakao_uid_1", None),
                (ap, "finalize_login"): lambda provider, uid: (
                    calls.append((provider, uid)) or (77, True, True)
                ),
            }
        ):
            result = ap.finalize_login_with_native_token("good_token")

        assert result == (77, True, True), f"성공 결과가 그대로 돌아오지 않았다: {result!r}"
        assert calls == [("kakao", "kakao_uid_1")], f"로그인 처리가 다른 인자로 불렸다: {calls!r}"
        assert len(_events(OK_EVENT)) == 1, "완료 기록이 남지 않았다"
        assert _events(FAIL_EVENT) == [], "성공인데 실패 기록이 남았다"


def test_n3_login_exception_never_kills_the_page() -> None:
    """N3 — 로그인 처리 중 DB 예외 등이 나도 예외가 밖으로 나가지 않고 기록만 남는다."""
    import auth_providers as ap

    def _boom(provider, uid):
        raise RuntimeError("wallets 갱신 실패")

    with _db_isolation.isolated_db():
        with _patched(
            {
                (ap, "_fetch_kakao_uid_with_token"): lambda tok: ("kakao_uid_1", None),
                (ap, "finalize_login"): _boom,
            }
        ):
            with _log_lines() as lines:
                result = ap.finalize_login_with_native_token("good_token")

        assert result is None, "예외를 삼키는 대신 성공 값을 만들었다"
        assert any("[kakao_native_login_fail]" in line for line in lines), (
            f"예외가 Cloud 로그에 남지 않았다: {lines!r}"
        )
        recorded = _events(FAIL_EVENT)
        assert len(recorded) == 1 and "RuntimeError" in recorded[0], f"예외 이유가 기록에 없다: {recorded!r}"


# ── N4: 계측 이벤트가 경보를 울리지 않아야 한다 ──────────────────────────────
def test_n4_instrumentation_events_are_labelled_and_not_alerts() -> None:
    """N4 — 라벨이 있고, 침입 경보 집계에는 안 들어간다(정상적인 로그인 실패로 배지가 켜지면 안 된다)."""
    import security_log

    with _db_isolation.isolated_db():
        for event_type in INSTRUMENTED_EVENTS:
            security_log.log_event(event_type, "probe")
        total = _rows("SELECT COUNT(*) FROM security_events")[0][0]
        assert total == len(INSTRUMENTED_EVENTS), f"계측 이벤트가 기록되지 않았다: {total}"
        assert security_log.count_recent_events(hours=24) == 0, "계측 이벤트가 '침입 시도 의심'으로 집계됐다"
        for event_type in INSTRUMENTED_EVENTS:
            assert event_type in security_log.EVENT_LABELS, f"대시보드 라벨이 없다: {event_type}"


# ── N5: 실제 진입점에서 실패해도 화면이 살아 있는가 ───────────────────────────
def test_n5_failed_native_token_keeps_the_real_entry_alive() -> None:
    """N5(조립) — 앱이 만료된 토큰을 실어 보낸 상황을 진입점(app.py) 그대로 렌더한다."""
    import auth_providers as ap

    with _kakao_configured_env():
        with _db_isolation.isolated_db():
            with _patched(
                {(ap, "_fetch_kakao_uid_with_token"): lambda tok: (None, "카카오 사용자 조회 오류 (401)")}
            ):
                gid = "natfail" + os.urandom(4).hex()
                at = AppTest.from_file(ENTRY, default_timeout=TIMEOUT_SEC)
                at.query_params["page"] = "main"
                at.query_params["gid"] = gid
                at.query_params["native"] = "1"
                at.query_params["native_kakao_token"] = "expired_token"
                at.run()

            assert len(at.exception) == 0, f"진입점이 예외로 죽었다: {at.exception}"
            body = "\n".join((m.value or "") for m in at.markdown)
            assert "점검 중" not in body, "로그인 실패가 화면 전체를 죽여 '준비 중' 안내로 대체됐다"
            member_id = None
            try:
                member_id = at.session_state["member_id"]
            except KeyError:
                pass
            assert not member_id, f"로그인되지 않았는데 회원 세션이 생겼다: {member_id!r}"
            assert at.query_params.get("native_kakao_token") in (None, []), (
                "실패한 토큰이 주소에 남았다(재시도/재로드 때 같은 실패를 반복한다)"
            )
            recorded = _events(FAIL_EVENT)
            assert len(recorded) == 1, f"실패가 계측에 남지 않았다: {recorded!r}"


# ── N6: (1)단계 신호가 실제로 기록되는가 ─────────────────────────────────────
_BANNER_APP = """
import streamlit as st
from wallet_ui import open_auth_banner, render_auth_banner

open_auth_banner()
render_auth_banner()
"""


def test_n6_banner_click_records_the_native_signal() -> None:
    """N6(조립) — 앱 배너의 카카오 버튼을 누르면 "앱에 신호를 보냈다" 기록이 1건 남는다."""
    with _kakao_configured_env():
        with _db_isolation.isolated_db():
            at = AppTest.from_string(_BANNER_APP, default_timeout=TIMEOUT_SEC)
            at.query_params["page"] = "main"
            at.query_params["gid"] = "gidtrigger1"
            at.query_params["native"] = "1"
            at.run()
            keys = [b.key for b in at.button]
            assert NATIVE_BTN in keys, f"native=1인데 앱 전용 카카오 버튼이 없다: {keys}"

            at.button(key=NATIVE_BTN).click().run()

            assert len(at.exception) == 0, f"버튼 클릭이 예외로 죽었다: {at.exception}"
            assert len(_events(TRIGGER_EVENT)) == 1, (
                f"앱에 신호를 보낸 기록이 없으면 어디서 끊겼는지 알 수 없다: {_events(TRIGGER_EVENT)!r}"
            )


def _main() -> int:
    tests = [
        test_n1_failed_token_returns_none_and_records_the_reason,
        test_n2_success_path_is_unchanged_and_recorded,
        test_n3_login_exception_never_kills_the_page,
        test_n4_instrumentation_events_are_labelled_and_not_alerts,
        test_n5_failed_native_token_keeps_the_real_entry_alive,
        test_n6_banner_click_records_the_native_signal,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"ERROR {t.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"PASS {t.__name__}")
        sys.stdout.flush()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
