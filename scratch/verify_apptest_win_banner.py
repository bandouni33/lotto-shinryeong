"""조립 검증 — 메인화면(app.py)에서 1·2등 배출 배너가 실제로 뜨는지 (iframe 방식 반영판).

2026-10-04 실기기 신고 대응: 카드를 st.markdown HTML로 그리면 환경에 따라 태그가 글자로
보였다 → components.html(iframe)로 바꿨다. 그래서 이 검증은
  · iframe 페이로드(앱이 실제로 내려보낸 HTML 문서)에 카드·확정 문구가 들어 있는지
  · **markdown 쪽으로 태그가 새지 않았는지**(신고 증상 그대로) 
  · 창이 뜨고, 닫히면 다시 안 뜨고, 비히트 회차면 안 뜨는지
를 본다. 운영 DB는 건드리지 않는다(tests/_db_isolation).

실행: venv312\\Scripts\\python.exe -X utf8 scratch\\verify_apptest_win_banner.py
"""

from __future__ import annotations

import os
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

import win_event_banner as web  # noqa: E402

GUEST = "winbannerguest"
HIT_ROUND = 1245
STAGE4 = 939_330
RANKS = (0, 1, 18, 169, 1157)


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
        for draw_round in range(1241, HIT_ROUND):
            draw_results_db.upsert_draw_result(draw_round, [2, 11, 25, 33, 41, 45], 7)
        mdb.init_marketing_tables()
        mdb.set_reference_ranks(HIT_ROUND, RANKS)
        mdb.snapshot_round_stats(HIT_ROUND, 6465)
        mdb.finalize_round_stats(HIT_ROUND)
        mdb.record_draw_generation_stats(HIT_ROUND, 2_000_000, STAGE4, (34, 14, 45, 33, 40))
        info = mdb.get_latest_win_event_round()
        check("임시 DB에 히트 회차 준비", bool(info) and info["draw_round"] == HIT_ROUND)

        user_scope.get_or_create_guest_id = lambda: GUEST
        draw_results_db.sync_latest_from_dhlottery = lambda: None
        combo_gen_trigger.maybe_trigger_weekly_generation = lambda: None

        payloads: list[str] = []
        original_html = c1.html

        def spy(html, **kwargs):
            payloads.append(html or "")
            return original_html(html, **kwargs)

        def render(suffix: str) -> tuple[str, str, str, list[str]]:
            payloads.clear()
            at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90)
            at.query_params["page"] = "main"
            at.query_params["gid"] = GUEST + suffix
            at.run()
            markdown = "\n".join((m.value or "") for m in at.markdown)
            labels = "\n".join((b.label or "") for b in at.button)
            return "\n".join(payloads), markdown, labels, [str(e) for e in at.exception]

        # 예열 1회 — 이 하네스는 첫 실행에서 components.html 스파이가 잡히지 않는다.
        render("0")
        c1.html = spy
        try:
            card, markdown, labels, errors = render("1")
            check("메인 렌더가 예외로 죽지 않았다", not errors, f"{errors[:1]}")
            check("iframe 페이로드에 카드가 있다", "wev-card" in card, f"페이로드 {len(card)}자")
            check(
                "markdown 쪽으로 태그가 새지 않았다(신고 증상)",
                "wev-title" not in markdown and 'class="wev-card"' not in markdown,
            )
            check("배너 제목이 있다", f"{HIT_ROUND}회차 결과 — 2등 배출" in card)
            check("기준선이 있다", "필터 통과 조합 기준" in card)
            check("배출 등수만 표기", "2등 1개 · 3등 18개" in card)
            check("조합수량이 없다", "939,330" not in card)
            check("iframe 배경이 투명", "background: transparent" in card)
            check(
                "닫기 버튼 2개가 화면에 있다",
                web.BTN_NEVER in labels and web.BTN_OK in labels,
                labels.replace("\n", "|")[:60],
            )
            check("아직 닫힘 기록이 없다", not mdb.was_win_event_banner_closed(GUEST, HIT_ROUND))

            mdb.mark_win_event_banner_closed(GUEST, HIT_ROUND)
            card2, markdown2, labels2, errors2 = render("2")
            check("닫은 뒤 재렌더가 예외 없음", not errors2, f"{errors2[:1]}")
            check(
                "닫은 뒤에는 배너가 안 뜬다",
                "wev-card" not in card2 and web.BTN_NEVER not in labels2,
            )
            check("메인화면 자체는 그대로 그려진다", "회차별" in markdown2 or "당첨번호" in markdown2)

            clean = HIT_ROUND + 1
            mdb.set_reference_ranks(clean, (0, 0, 0, 5, 12))
            mdb.snapshot_round_stats(clean, 6465)
            mdb.finalize_round_stats(clean)
            card3, _, labels3, errors3 = render("3")
            check("비히트 최신 회차 렌더 예외 없음", not errors3, f"{errors3[:1]}")
            check(
                "지난 히트가 뒤늦게 뜨지 않는다",
                "wev-card" not in card3 and web.BTN_NEVER not in labels3,
            )
        finally:
            c1.html = original_html
        print(f"  (격리 DB {db_path})")

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
