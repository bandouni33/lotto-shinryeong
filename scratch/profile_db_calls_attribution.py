"""렌더당 DB 왕복을 **누가** 내는지 귀속시켜 센다 (2026-10-04 조사 2번: 캐시 레버 찾기).

무엇을 답하는가:
  "웜 렌더마다 DB로 나가는 10건"이 대체 무엇인가 — 어느 앱 모듈에서, 어느 테이블에, 읽기인지
  쓰기인지, 어떤 SQL 템플릿인지. 캐시 후보는 **매 렌더 반복되는 읽기**이므로 그 목록이 곧
  다음 작업 목록이다(반복되는 쓰기는 캐시 대상이 아니다 — 무효화 문제).

어떻게 재는가:
  격리 sqlite(운영 Turso 무접촉)에서 **앱을 그대로 렌더**하고(streamlit AppTest),
  sqlite 실행 지점을 감싸 호출마다 ① 앱 쪽 호출 모듈(스택에서 저장소 안 프레임) ② SQL에서
  읽은 테이블 ③ 읽기/쓰기 ④ 정규화한 SQL 템플릿을 기록한다. 앱 코드는 한 줄도 바꾸지 않는다.

읽을 때 주의:
  · 여기서 나온 왕복 수는 Turso 왕복(쿼리당 약 75ms)과 곱해야 시간이 된다.
  · 쓰기(INSERT/UPDATE)는 캐시로 줄일 수 없다 — 조회를 캐시하거나 호출 자체를 줄여야 한다.
  · 같은 렌더 안에서 같은 템플릿이 여러 번 나오면 그건 **한 렌더 중복**이다(가장 안전한 후보).

실행: venv312\\Scripts\\python.exe -X utf8 scratch\\profile_db_calls_attribution.py
"""

from __future__ import annotations

import re
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from env_loader import load_dotenv_file  # noqa: E402

load_dotenv_file()

import _db_isolation as iso  # noqa: E402

SKIP_DIRS = ("scratch", "tests", "scripts", "venv312", "Claude outputs")
_TABLE_RE = re.compile(r"\b(?:from|into|update|join)\s+([A-Za-z_][A-Za-z0-9_]*)", re.I)
_WS_RE = re.compile(r"\s+")

CALLS: Counter = Counter()          # (모듈, 테이블, kind, 템플릿) -> 건수
ORDER: list[tuple] = []             # 등장 순서(같은 템플릿이 렌더 안에서 몇 번 나왔는지)


def _caller_module() -> str:
    """저장소 앱 코드 중 이 호출을 낸 프레임의 파일 이름(계측·테스트 프레임은 건너뛴다)."""
    import traceback

    me = Path(__file__).name
    for frame in reversed(traceback.extract_stack()[:-1]):
        path = Path(frame.filename)
        if path.name == me:
            continue
        try:
            rel = path.resolve().relative_to(ROOT)
        except Exception:
            continue
        if rel.parts and rel.parts[0] in SKIP_DIRS:
            continue
        if path.suffix != ".py":
            continue
        return f"{rel.as_posix()}:{frame.lineno}"
    return "(unknown)"


def _template(sql: str) -> str:
    """값을 지운 SQL 뼈대 — 같은 모양의 반복을 한 줄로 묶기 위함."""
    return _WS_RE.sub(" ", sql).strip()[:110]


def _classify(sql: str) -> tuple[str, str]:
    head = sql.lstrip().split(" ", 1)[0].upper()
    kind = "read" if head in ("SELECT", "PRAGMA", "WITH", "EXPLAIN") else "write"
    m = _TABLE_RE.search(sql)
    return kind, (m.group(1) if m else "-")


def _record(sql: str) -> None:
    kind, table = _classify(sql)
    tmpl = _template(sql)
    module = _caller_module()
    CALLS[(module, table, kind, tmpl)] += 1
    ORDER.append((module, table, kind, tmpl))


def _instrument() -> None:
    original_execute = iso._LocalConnection.execute
    original_batch = iso._LocalConnection.batch_execute
    original_many = iso._LocalConnection.executemany

    def execute(self, sql, params=()):
        _record(sql)
        return original_execute(self, sql, params)

    def batch(self, statements):
        for sql, _params in statements:
            _record(sql)
        return original_batch(self, statements)

    def executemany(self, sql, params_list):
        _record(sql)  # 왕복은 1회다(행 수와 무관)
        return original_many(self, sql, params_list)

    iso._LocalConnection.execute = execute
    iso._LocalConnection.batch_execute = batch
    iso._LocalConnection.executemany = executemany


def _seed_and_render(label: str, rounds: int = 1) -> list[tuple]:
    from streamlit.testing.v1 import AppTest

    per_render = []
    for i in range(rounds):
        CALLS.clear()
        ORDER.clear()
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
        at.query_params["page"] = "main"
        at.query_params["gid"] = f"prof_{label}_{i}"
        t0 = time.perf_counter()
        at.run()
        ms = (time.perf_counter() - t0) * 1000
        total = sum(CALLS.values())
        print(f"  {label}{i}: 왕복 {total}건 · 렌더 {ms:.0f}ms · 예외 {len(at.exception)}건",
              flush=True)
        per_render.append(list(ORDER))
    return per_render


def _print_breakdown(rows: list[tuple], title: str) -> None:
    print(f"\n[{title}]")
    counts = Counter(rows)
    for (module, table, kind, tmpl), n in counts.most_common(18):
        print(f"  {n:>2}회 {kind:<5} {table:<22} {module}")
        print(f"       {tmpl}")


def main() -> int:
    _instrument()
    with iso.isolated_db() as db_path:
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

        print("[렌더당 DB 왕복 귀속 — 메인화면]")
        cold = _seed_and_render("cold")[0]
        warm_rows = []
        for label in ("warm1", "warm2"):
            warm_rows.extend(_seed_and_render(label)[0])

        _print_breakdown(cold, "콜드 렌더 1회")
        _print_breakdown(warm_rows, "웜 렌더 2회 합계(= 매 렌더 반복되는 것들)")

        print("\n[웜 렌더에서 매번 반복되는 항목 — 캐시 후보]")
        warm_counts = Counter(warm_rows)
        for (module, table, kind, tmpl), n in warm_counts.most_common():
            if n >= 2:  # 두 번의 웜 렌더에서 모두 나온 것 = 매 렌더 반복
                print(f"  {kind:<5} {table:<22} {module}")
                print(f"        {tmpl}")
        reads = sum(n for (_m, _t, kind, _s), n in warm_counts.items() if kind == "read")
        writes = sum(n for (_m, _t, kind, _s), n in warm_counts.items() if kind == "write")
        print(f"\n  웜 2회 합계: 읽기 {reads}건 · 쓰기 {writes}건 "
              f"(= 렌더당 읽기 {reads/2:.1f} · 쓰기 {writes/2:.1f})")
        print(f"\n격리 DB {db_path}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
