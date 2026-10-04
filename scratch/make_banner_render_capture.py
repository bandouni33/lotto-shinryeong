"""배너 실제 렌더 캡처 — 앱이 실제로 내려보낸 iframe 문서를 그대로 저장한다.

카드가 components.html(iframe)로 나가므로, 이 파일은 **앱이 브라우저로 보낸 그 문서**와
바이트 단위로 같다(브라우저로 열면 실제 모달과 동일하게 보인다). 대상 회차도 운영 DB의
실제 대상(1244회차) 값이다. 운영 DB는 건드리지 않는다(tests/_db_isolation).

산출물: 배너_실제렌더_캡처.html (프로젝트 루트 + 내PC 다운로드 폴더)
실행: venv312\\Scripts\\python.exe -X utf8 scratch\\make_banner_render_capture.py
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = ROOT / "tests"
for _path in (str(ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from env_loader import load_dotenv_file  # noqa: E402

load_dotenv_file()

import _db_isolation  # noqa: E402

GUEST = "capture-guest"
TARGET = 1244  # 운영에서 실제 대상이 되는 회차
RANKS = (0, 1, 18, 169, 1157)
STAGE4 = 1_025_190
DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")


def main() -> int:
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(("  PASS  " if ok else "  FAIL  ") + label + (f"  [{detail}]" if detail else ""))
        if not ok:
            failures.append(label)

    with _db_isolation.isolated_db() as db_path:
        import combo_gen_trigger
        import draw_results_db
        import marketing_db as mdb
        import user_scope
        import streamlit.components.v1 as c1
        from streamlit.testing.v1 import AppTest

        draw_results_db.init_draw_results_table()
        for draw_round in range(1241, TARGET):
            draw_results_db.upsert_draw_result(draw_round, [2, 11, 25, 33, 41, 45], 7)
        mdb.init_marketing_tables()
        mdb.set_reference_ranks(TARGET, RANKS)
        mdb.snapshot_round_stats(TARGET, 6465)
        mdb.finalize_round_stats(TARGET)
        mdb.record_draw_generation_stats(TARGET, 2_000_000, STAGE4, (34, 14, 45, 33, 40))
        info = mdb.get_latest_win_event_round()
        check("운영과 같은 대상 회차(1244)", bool(info) and info["draw_round"] == TARGET)
        if not info:
            return 1

        user_scope.get_or_create_guest_id = lambda: GUEST
        draw_results_db.sync_latest_from_dhlottery = lambda: None
        combo_gen_trigger.maybe_trigger_weekly_generation = lambda: None

        def run_once(suffix: str) -> tuple[list[str], str, list[str]]:
            payloads: list[str] = []
            original = c1.html
            c1.html = lambda html, **kw: (payloads.append(html or ""), original(html, **kw))[1]
            try:
                at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90)
                at.query_params["page"] = "main"
                at.query_params["gid"] = GUEST + suffix
                at.run()
            finally:
                c1.html = original
            markdown = "\n".join((m.value or "") for m in at.markdown)
            return payloads, markdown, [str(e) for e in at.exception]

        run_once("warm")  # 예열(첫 실행에서는 components.html 스파이가 안 잡히는 하네스 특성)
        payloads, markdown, errors = run_once("cap")
        check("렌더 예외 없음", not errors, f"{errors[:1]}")

        cards = [p for p in payloads if "wev-card" in p]
        check("iframe 페이로드에 카드가 있다", bool(cards), f"후보 {len(cards)}개")
        check(
            "markdown 쪽으로 태그가 새지 않았다(신고 증상)",
            "wev-title" not in markdown and 'class="wev-card"' not in markdown,
        )
        if not cards:
            return 1
        payload = max(cards, key=len)

        check("제목(2등 배출)", f"{TARGET}회차 결과 — 2등 배출" in payload)
        check("기준선(조합수량 없음)", "필터 통과 조합 기준" in payload)
        check("등수만 표기", "2등 1개 · 3등 18개" in payload)
        check("조합수량 숫자 없음", "1,025,190" not in payload)
        check("배경 투명", "background: transparent" in payload)

        path = ROOT / "배너_실제렌더_캡처.html"
        path.write_text(payload, encoding="utf-8")
        target = os.path.join(DOWNLOADS, path.name)
        shutil.copy2(path, target)
        check("다운로드 사본 동일", path.read_bytes() == open(target, "rb").read())
        print(f"  캡처: {path.name} ({path.stat().st_size} bytes) / 격리 DB {db_path}")

    print(f"\n결과: {'전부 통과' if not failures else str(len(failures)) + '건 실패'}")
    for item in failures:
        print("  - " + item)
    return 1 if failures else 0


if __name__ == "__main__":
    code = main()
    try:
        import db_turso

        db_turso.close_all_clients()
    except Exception:
        pass
    raise SystemExit(code)
