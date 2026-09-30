"""렌더 1회당 DB 왕복 실측 계측 계약 (2026-09-27, "화면 이동 간 딜레이가 너무 심함" 대응).

배경: 지연의 원인 후보가 두 개다 — (a) 화면 이동이 전체 페이지 새로고침이라는 구조,
(b) 그 새로고침마다 원격 DB를 수십 번 순차 왕복하는 것. 어느 쪽이 얼마나 먹는지는
코드를 읽어서 정할 수 없어서 실측을 넣는다: 앱의 모든 DB 호출이 지나가는 db_turso
한 곳에서 횟수·소요만 세고, 화면 스크립트의 마지막 줄(user_page.db_trace_end_run)에서
한 줄로 찍는다.

불변식/계약:
  T1. begin → 호출 N건 → end 이면 정확히 한 줄이 찍히고, 호출 수·DB 소요·스크립트
      시간·비중이 그대로 나온다(호출별 SQL은 표 단위로 묶인다).
  T2. 세션(스레드)당 기본은 첫 2회 렌더만 기록한다 — 진단용 로그가 무한정 쌓이지 않는다.
  T3. LOTTO_DB_TRACE=0(off)이면 한 줄도 찍히지 않는다(운영에서 즉시 끌 수 있다).
  T4. 계측이 켜져 있어도 실제 쿼리 경로는 그대로 동작하고, 호출이 정확히 세어진다
      (배치는 한 번의 왕복이라 1건 — 서버에서 원자적으로 실행된다).
  T5. 조립(진입점): 진입점을 그대로 렌더하면 [dbtrace] 한 줄이 실제로 찍힌다
      (= user_page.py의 두 줄이 실제로 연결돼 있다).
  T6. 계측이 꺼져 있으면 기록 함수는 아무 것도 세지 않는다(운영 기본 경로 비용 0).

한계(T5): 이 하네스는 DB를 로컬 sqlite로 격리하면서 db_turso의 연결 래퍼 자체를
대역(_db_isolation._LocalConnection)으로 바꾼다 — 그래서 진입점 렌더에서는 호출 수가
0으로 찍힌다. 계측이 쿼리를 세는 부분은 T4가 실제 래퍼로 검증하고, T5는 "화면
스크립트의 두 줄이 실제로 연결돼 한 줄이 찍히는가"만 본다(user_page.py를 통째로
렌더하는 유일한 방법이 격리 하네스이기 때문이다).

pytest 없이도 돌도록 표준 assert + __main__ 러너를 함께 둔다.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _path in (str(ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import _db_isolation  # noqa: E402

import db_turso  # noqa: E402

TIMEOUT_SEC = 60
ENTRY = str(ROOT / "app.py")


def _reset_trace(mode: str | None = None) -> None:
    """계측 상태를 초기화한다 — 실측 상태는 세션(스레드)마다 따로라 테스트끼리 새는
    걸 여기서 끊는다. mode를 주면 이 프로세스의 모드 캐시도 함께 바꾼다(=환경변수를
    바꾼 것과 같은 효과, 모드는 프로세스당 1회만 판정해 캐시한다)."""
    state = db_turso._TRACE
    state.on = False
    state.runs = 0
    state.calls = 0
    state.db_ms = 0.0
    state.sql = {}
    state.page = ""
    state.t0 = 0.0
    if mode is not None:
        db_turso._TRACE_MODE_CACHE = mode


def _collect(fn) -> str:
    """fn() 동안 표준출력에 찍힌 내용을 모은다(_safe_log가 print로 찍는다)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn()
    return buf.getvalue()


def _summary_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("[dbtrace]")]


# ── T1: 한 줄 요약의 내용 ────────────────────────────────────────────────────
def test_t1_one_line_reports_calls_time_and_share() -> None:
    """T1 — 호출 3건(같은 표 2건 + 다른 표 1건)이 정확히 한 줄로 요약된다."""
    _reset_trace(mode="all")

    def _run_once():
        db_turso.db_trace_begin_run("main")
        db_turso.db_trace_note("SELECT balance FROM wallets WHERE member_id = ?", 12.0)
        db_turso.db_trace_note("SELECT balance FROM wallets WHERE member_id = ?", 8.0)
        db_turso.db_trace_note("INSERT INTO wallet_ledger (delta) VALUES (?)", 30.0)
        db_turso.db_trace_end_run()

    lines = _summary_lines(_collect(_run_once))
    assert len(lines) == 1, f"렌더 1회에 한 줄이어야 한다: {lines!r}"
    line = lines[0]
    assert line.startswith("[dbtrace] page=main"), line
    assert "calls=3" in line, line
    assert "db_ms=50" in line, f"호출 소요 합계가 틀렸다: {line}"
    assert "script_ms=" in line and "db_share=" in line, line
    assert "SELECT walletsx2(20ms)" in line, f"표 단위 묶음이 틀렸다: {line}"
    assert "INSERT wallet_ledgerx1(30ms)" in line, f"표 단위 묶음이 틀렸다: {line}"
    # 요약은 완료 후 초기화된다 — 같은 렌더를 한 번 더 끝내도 두 번째 줄이 없어야 한다.
    assert _summary_lines(_collect(lambda: db_turso.db_trace_end_run())) == [], "end를 두 번 불러도 한 줄만 나와야 한다"


# ── T2: 세션(스레드)당 기록 횟수 상한 ─────────────────────────────────────────
def test_t2_only_the_first_runs_of_a_session_are_logged_by_default() -> None:
    """T2 — 기본(head) 설정: 세션당 첫 2회만, 3회째부터는 아무 것도 안 찍힌다."""
    _reset_trace(mode="head")
    outputs = []
    for _ in range(3):
        outputs.append(
            _collect(
                lambda: (
                    db_turso.db_trace_begin_run("main"),
                    db_turso.db_trace_note("SELECT 1 FROM members", 5.0),
                    db_turso.db_trace_end_run(),
                )
            )
        )
    assert _summary_lines(outputs[0]), "1회차 렌더가 기록되지 않았다"
    assert _summary_lines(outputs[1]), "2회차 렌더가 기록되지 않았다"
    assert _summary_lines(outputs[2]) == [], f"3회차까지 찍혔다(로그가 무한정 쌓인다): {outputs[2]!r}"
    assert db_turso._TRACE.calls == 0, "상한을 넘긴 렌더의 호출까지 세고 있다"


# ── T3/T6: 끄기 ─────────────────────────────────────────────────────────────
def test_t3_trace_off_prints_nothing() -> None:
    """T3 — LOTTO_DB_TRACE=0(off)이면 한 줄도 안 찍힌다."""
    before = os.environ.get("LOTTO_DB_TRACE")
    os.environ["LOTTO_DB_TRACE"] = "0"
    try:
        db_turso._TRACE_MODE_CACHE = None  # 환경변수를 다시 읽게 한다
        assert db_turso._trace_mode() == "off", "환경변수가 off로 해석되지 않았다"
        _reset_trace()

        def _run_once():
            db_turso.db_trace_begin_run("main")
            db_turso.db_trace_note("SELECT 1 FROM members", 100.0)
            db_turso.db_trace_end_run()

        assert _summary_lines(_collect(_run_once)) == [], "꺼져 있는데 기록됐다"
        assert db_turso._TRACE.calls == 0, "꺼져 있는데 호출을 세고 있다"
    finally:
        if before is None:
            os.environ.pop("LOTTO_DB_TRACE", None)
        else:
            os.environ["LOTTO_DB_TRACE"] = before
        db_turso._TRACE_MODE_CACHE = None
        _reset_trace()


def test_t6_note_is_free_when_not_started() -> None:
    """T6 — begin 없이(운영 기본 경로) 기록 함수를 불러도 아무 것도 세지 않는다."""
    _reset_trace()
    db_turso._TRACE.on = False
    db_turso.db_trace_note("SELECT 1 FROM members", 999.0)
    assert db_turso._TRACE.calls == 0 and db_turso._TRACE.db_ms == 0.0, "꺼진 상태에서 세고 있다"


# ── T4: 실제 쿼리 경로에서 세어지는가 ────────────────────────────────────────
class _FakeResultSet:
    def __init__(self, rows, columns=("n",)):
        self.columns = columns
        self.rows = rows
        self.last_insert_rowid = 0
        self.rows_affected = len(rows)


class _FakeClient:
    """execute/batch만 있는 가짜 Turso 클라이언트 — 계측이 진짜 쿼리 경로\n    (_ConnectionWrapper)에 걸려 있는지 보려는 최소 대역이다(네트워크는 안 쓴다)."""

    def __init__(self):
        self.executed: list[str] = []

    def execute(self, sql, params=()):
        self.executed.append(sql)
        return _FakeResultSet([(1,)])

    def batch(self, statements):
        self.executed.extend(sql for sql, _params in statements)
        return [_FakeResultSet([(1,)]) for _ in statements]


def test_t4_real_query_path_is_counted_and_still_works() -> None:
    """T4 — 계측이 켜져 있어도 쿼리 결과는 그대로이고, execute·batch가 1건씩 세어진다."""
    _reset_trace(mode="all")
    client = _FakeClient()
    conn = db_turso._ConnectionWrapper(client)
    batch = [
        ("UPDATE wallets SET balance = ?", (10,)),
        ("INSERT INTO wallet_ledger (delta) VALUES (?)", (10,)),
    ]

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        db_turso.db_trace_begin_run("main")
        fetched = conn.execute("SELECT n FROM members WHERE id = ?", (1,)).fetchone()
        conn.batch_execute(batch)
        db_turso.db_trace_end_run()

    assert fetched["n"] == 1, f"계측이 켜지면 쿼리 결과가 달라졌다: {fetched!r}"
    assert client.executed == [
        "SELECT n FROM members WHERE id = ?",
        "UPDATE wallets SET balance = ?",
        "INSERT INTO wallet_ledger (delta) VALUES (?)",
    ], f"실제 클라이언트까지 간 SQL이 이상하다: {client.executed!r}"
    lines = _summary_lines(buf.getvalue())
    assert len(lines) == 1, f"한 줄이어야 한다: {lines!r}"
    line = lines[0]
    assert "calls=2" in line, f"execute 1 + batch 1이어야 한다: {line}"
    assert "SELECT membersx1" in line and "UPDATE walletsx1" in line, line


# ── T5: 진입점에 실제로 연결돼 있는가 ────────────────────────────────────────
def test_t5_real_entry_prints_the_summary_line() -> None:
    """T5(조립) — 진입점(app.py → user_page.py)을 그대로 렌더하면 요약 한 줄이 찍힌다."""
    before_key = os.environ.get("KAKAO_REST_API_KEY")
    before_mock = os.environ.get("LOTTO_DEV_MOCK_AUTH")
    os.environ["KAKAO_REST_API_KEY"] = "test-rest-key"
    os.environ["LOTTO_DEV_MOCK_AUTH"] = "0"
    try:
        with _db_isolation.isolated_db():
            db_turso._TRACE_MODE_CACHE = "all"
            at = AppTest.from_file(ENTRY, default_timeout=TIMEOUT_SEC)
            at.query_params["page"] = "main"
            at.query_params["gid"] = "gidtrace1"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                at.run()
            assert len(at.exception) == 0, f"진입점이 예외로 죽었다: {at.exception}"
            lines = _summary_lines(buf.getvalue())
            assert len(lines) == 1, f"진입점 렌더가 요약 줄을 남기지 않았다: {lines!r}"
            assert "page=main" in lines[0], lines[0]
            assert "calls=" in lines[0] and "script_ms=" in lines[0], lines[0]
    finally:
        db_turso._TRACE_MODE_CACHE = None
        _reset_trace()
        for name, saved in (("KAKAO_REST_API_KEY", before_key), ("LOTTO_DEV_MOCK_AUTH", before_mock)):
            if saved is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = saved


# ── T7: 계측이 사용자 화면을 죽이지 않는다(배포 직후 "점검 중" 사고) ───────────
class _StaleModule:
    """배포 직후 실제로 벌어지는 상태를 흉내낸다: 프로세스는 살아 있는데
    db_turso는 **이전 배포본이 sys.modules에 캐시된 채**라 새로 추가한 심볼이 없다.
    화면 스크립트(user_page.py)는 디스크에서 새로 읽히므로 이 상황에서
    `from db_turso import db_trace_begin_run`은 ImportError가 된다."""


def test_t7_entry_survives_a_stale_db_turso_without_the_trace_symbols() -> None:
    """T7(조립) — 계측 심볼이 없는 옛 db_turso가 캐시돼 있어도 진입점은 살아서 그려진다.

    2026-09-30 실사고: 이 심볼을 화면 스크립트 최상단에서 `from db_turso import`로
    가져오게 만든 뒤, 배포 직후 실행 중이던 옛 프로세스가 새 user_page.py를 읽어
    ImportError를 냈고 app.py의 공용 예외 화면("일시적으로 서비스 점검 중입니다")만
    떴다 — 사용자 화면이 계측 때문에 죽었다. 계측은 어떤 경우에도 화면을 죽이면 안 된다."""
    import db_turso

    saved = (db_turso.db_trace_begin_run, db_turso.db_trace_end_run)
    before_key = os.environ.get("KAKAO_REST_API_KEY")
    before_mock = os.environ.get("LOTTO_DEV_MOCK_AUTH")
    os.environ["KAKAO_REST_API_KEY"] = "test-rest-key"
    os.environ["LOTTO_DEV_MOCK_AUTH"] = "0"
    try:
        del db_turso.db_trace_begin_run
        del db_turso.db_trace_end_run
        with _db_isolation.isolated_db():
            at = AppTest.from_file(ENTRY, default_timeout=TIMEOUT_SEC)
            at.query_params["page"] = "main"
            at.query_params["gid"] = "gidstale1"
            at.run()
            body = "\n".join((m.value or "") for m in at.markdown)
            assert "\uc810\uac80 \uc911" not in body, (
                "옛 db_turso가 캐시된 상태에서 진입점이 예외 화면('점검 중')으로 바뀌었다 "
                f"/ 계측 때문에 사용자 화면이 죽었다: {at.exception}"
            )
            assert len(at.exception) == 0, f"진입점이 예외로 죽었다: {at.exception}"
            assert [b.key for b in at.button], "화면이 그려지지 않았다"
    finally:
        db_turso.db_trace_begin_run, db_turso.db_trace_end_run = saved
        for name, value in (("KAKAO_REST_API_KEY", before_key), ("LOTTO_DEV_MOCK_AUTH", before_mock)):
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _main() -> int:
    tests = [
        test_t1_one_line_reports_calls_time_and_share,
        test_t2_only_the_first_runs_of_a_session_are_logged_by_default,
        test_t3_trace_off_prints_nothing,
        test_t4_real_query_path_is_counted_and_still_works,
        test_t5_real_entry_prints_the_summary_line,
        test_t6_note_is_free_when_not_started,
        test_t7_entry_survives_a_stale_db_turso_without_the_trace_symbols,
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
