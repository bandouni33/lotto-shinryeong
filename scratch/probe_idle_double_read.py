"""웜 렌더에서 같은 행을 두 번 읽는 원인 확정 (2026-10-04 조사).

관측: 웜 렌더 1회에 `guest_member_links` 조회가 두 종류 각각 2번씩 나간다
      (`wallet_db.guest_idle_seconds` = last_seen_at, `wallet_db.get_member_and_ua_for_guest`).
      다른 조회(users·combo_round_stats·app_settings·draw_results)는 각 1번이다 — 즉
      스크립트가 통째로 두 번 돈 게 아니라 **이 두 함수만** 두 번 불렸다는 뜻이다.

가설:
  A) `auth_providers.restore_member_from_guest()` 가 한 렌더 안에서 두 번 불린다.
  B) 각 함수가 한 번 불렸는데 그 안에서 쿼리가 두 번 실행된다.
  C) 스크립트가 두 번 돌았는데 두 번째 실행은 앞부분만 지나간다(다른 조회는 캐시).

이 프로브는 A/B/C를 가른다 — 함수 호출을 감싸 세고, DB 호출 순서에 표식을 끼워 찍는다.
앱 코드는 건드리지 않는다(감싸기만 한다).

실행: venv312\\Scripts\\python.exe -X utf8 scratch\\probe_idle_double_read.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from env_loader import load_dotenv_file  # noqa: E402

load_dotenv_file()

import _db_isolation as iso  # noqa: E402

TRACE: list[str] = []


def _wrap_functions() -> None:
    import auth_providers
    import wallet_db

    def wrap_restore(original):
        def inner(*a, **kw):
            TRACE.append("CALL restore_member_from_guest")
            try:
                return original(*a, **kw)
            finally:
                TRACE.append("RET  restore_member_from_guest")
        return inner

    def wrap(name, original, marker):
        def inner(*a, **kw):
            TRACE.append(f"CALL {marker}")
            try:
                return original(*a, **kw)
            finally:
                TRACE.append(f"RET  {marker}")
        return inner

    auth_providers.restore_member_from_guest = wrap_restore(
        auth_providers.restore_member_from_guest)
    wallet_db.guest_idle_seconds = wrap(
        "guest_idle_seconds", wallet_db.guest_idle_seconds, "wallet_db.guest_idle_seconds")
    wallet_db.get_member_and_ua_for_guest = wrap(
        "get_member_and_ua_for_guest", wallet_db.get_member_and_ua_for_guest,
        "wallet_db.get_member_and_ua_for_guest")


DL = ROOT / "user_page.py"


def _count_script_runs() -> None:
    """스크립트가 한 렌더에 몇 번 돌았는지 — app.py 맨 위의 check_admission()을 세면 된다."""
    import admission_control

    original = admission_control.check_admission

    def inner(*a, **kw):
        TRACE.append("CALL check_admission  (스크립트 1회 실행)")
        return original(*a, **kw)

    admission_control.check_admission = inner


def _instrument_sql() -> None:
    """어느 SQL이 나갔는지 순서대로 표식만 남긴다(값은 안 본다)."""
    original_execute = iso._LocalConnection.execute

    def execute(self, sql, params=()):
        head = " ".join(sql.split())[:60]
        if "guest_member_links" in sql or "security_events" in sql:
            TRACE.append(f"SQL  {head}")
        return original_execute(self, sql, params)

    iso._LocalConnection.execute = execute


def main() -> int:
    _wrap_functions()
    _count_script_runs()
    _instrument_sql()
    with iso.isolated_db():
        import combo_gen_trigger
        import draw_results_db
        import marketing_db as mdb

        draw_results_db.init_draw_results_table()
        for draw_round in range(1, 1246):
            draw_results_db.upsert_draw_result(draw_round, [3, 11, 19, 27, 35, 44], 7)
        mdb.init_marketing_tables()
        mdb.set_reference_ranks(1245, (0, 0, 0, 5, 12))
        mdb.snapshot_round_stats(1245, 6465)
        mdb.finalize_round_stats(1245)
        draw_results_db.sync_latest_from_dhlottery = lambda: None
        combo_gen_trigger.maybe_trigger_weekly_generation = lambda: None

        from streamlit.testing.v1 import AppTest

        for label in ("cold", "warm"):
            TRACE.clear()
            at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
            at.query_params["page"] = "main"
            at.query_params["gid"] = f"probe_double_{label}"
            at.run()
            print(f"\n===== {label} 렌더 · 추적 {len(TRACE)}줄 =====")
            for line in TRACE:
                print("  " + line)
            calls = sum(1 for t in TRACE if t.startswith("CALL restore"))
            idle = sum(1 for t in TRACE if t.startswith("CALL wallet_db.guest_idle"))
            runs = sum(1 for t in TRACE if t.startswith("CALL check_admission"))
            print(f"  → 스크립트 실행 {runs}회 · restore_member_from_guest 호출 {calls}회 · "
                  f"guest_idle_seconds 호출 {idle}회")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
