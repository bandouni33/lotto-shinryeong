"""렌더 1회당 DB 왕복(쿼리) 수 실측 — "다음 병목이 DB인가" 판단용 (2026-10-04 조사 2·4번).

왜 필요한가:
  Streamlit 인스턴스의 여유는 실측으로 확인했다(150세션 763MB·CPU 1%대). 남은 후보는
  원격 DB(Turso) 처리량이다 — 과거 세션 기록에 "95~99 qps, 렌더당 15~20왕복"이 있었지만
  지금 코드로 다시 세어 확인해야 한다. 여기서는 앱을 그대로 렌더하면서 **앱이 실제로 낸
  쿼리 수**를 센다(운영 Turso 대신 임시 sqlite — 코드 경로는 동일하다).

  cold = 첫 렌더(공유 캐시가 비어 있음), warm = 같은 세션의 두 번째 렌더(@st.cache_data가
  살아 있는 상태). 실사용자의 반복 조작은 대부분 warm에 해당한다.

실행: venv312\\Scripts\\python.exe -X utf8 scratch\\count_db_calls_per_render.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from env_loader import load_dotenv_file  # noqa: E402

load_dotenv_file()

import _db_isolation as iso  # noqa: E402

COUNTS = {"exec": 0, "batch": 0, "execmany": 0}


def _instrument() -> None:
    """임시 sqlite 연결의 실행 지점을 감싸 쿼리 수를 센다(앱 코드는 그대로 둔다)."""
    original_execute = iso._LocalConnection.execute
    original_batch = iso._LocalConnection.batch_execute
    original_many = iso._LocalConnection.executemany

    def execute(self, sql, params=()):
        COUNTS["exec"] += 1
        return original_execute(self, sql, params)

    def batch(self, statements):
        COUNTS["batch"] += len(list(statements))
        return original_batch(self, statements)

    def executemany(self, sql, params_list):
        n = len(list(params_list))
        COUNTS["execmany"] += max(1, n)
        return original_many(self, sql, params_list)

    iso._LocalConnection.execute = execute
    iso._LocalConnection.batch_execute = batch
    iso._LocalConnection.executemany = executemany


def main() -> int:
    _instrument()
    totals: list[tuple[str, int, float]] = []

    with iso.isolated_db() as db_path:
        import combo_gen_trigger
        import draw_results_db
        import marketing_db as mdb
        import streamlit.components.v1 as c1
        from streamlit.testing.v1 import AppTest

        draw_results_db.init_draw_results_table()
        for draw_round in range(1, 1246):
            draw_results_db.upsert_draw_result(draw_round, [3, 11, 19, 27, 35, 44], 7)
        mdb.init_marketing_tables()
        mdb.set_reference_ranks(1245, (0, 0, 0, 5, 12))
        mdb.snapshot_round_stats(1245, 6465)
        mdb.finalize_round_stats(1245)

        draw_results_db.sync_latest_from_dhlottery = lambda: None
        combo_gen_trigger.maybe_trigger_weekly_generation = lambda: None

        def render(label: str) -> None:
            COUNTS["exec"] = COUNTS["batch"] = COUNTS["execmany"] = 0
            at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90)
            at.query_params["page"] = "main"
            at.query_params["gid"] = "dbcnt_" + label
            t0 = time.perf_counter()
            at.run()
            ms = (time.perf_counter() - t0) * 1000
            total = COUNTS["exec"] + COUNTS["batch"] + COUNTS["execmany"]
            totals.append((label, total, ms))
            print(f"  {label:>4}: 쿼리 {total}건 (execute {COUNTS['exec']} · "
                  f"batch {COUNTS['batch']} · executemany {COUNTS['execmany']}) · "
                  f"렌더 {ms:.0f}ms · 예외 {len(at.exception)}건", flush=True)

        print("[렌더당 DB 왕복 수 — 메인화면]")
        render("cold")   # 첫 렌더(공유 캐시 비어 있음)
        render("warm1")  # 같은 데이터로 다시(캐시 살아 있음)
        render("warm2")
        print(f"\n격리 DB {db_path}")

    print("\n[요약]")
    for label, total, ms in totals:
        print(f"  {label:>4} {total:>4}건 / {ms:.0f}ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
