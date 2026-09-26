"""번개조합 "저장 경로"(?th_save=...)를 진입점에서 조립 검증 (2026-09-26 사용자 신고).

신고: 생성이 끝나면 화면이 3초 넘게 하얗게 변했다가 저장내역이 보인다.
원인 후보를 코드로 좁힌 결과 — (1) 보드 iframe이 서버에 조합을 넘기는 유일한
통로가 **주소 이동(전체 페이지 재요청)**이고, (2) 그 요청을 처리하는 th_save
분기가 저장 뒤 `st.rerun()`을 또 던져 **페이지가 두 번** 실행된다.

이 테스트는 그 저장 경로를 사용자가 밟는 방식 그대로(app.py?page=thunder&th_save=...)
돌려서, rerun을 줄여도 **결과가 그대로인지**를 고정한다:

  S1. 저장된 조합이 실제로 DB에 들어간다(회차 포함).
  S2. 저장 직후 저장내역 패널이 열리고 최신 배치 1개에만 표시가 붙는다.
  S3. "조합생성이 완료되었습니다" 안내가 실제로 뜬다.
  S4. 페이지가 예외로 죽지 않는다.

DB는 _db_isolation.isolated_db()로만 만진다.
"""

from __future__ import annotations

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
import marketing_db as mdb  # noqa: E402
import wallet_db as wdb  # noqa: E402

TIMEOUT_SEC = 60
MARK = 'history-just-saved"'


def _messages(at: AppTest) -> str:
    parts = []
    for attr in ("success", "info", "error", "warning", "caption"):
        for element in getattr(at, attr, []):
            value = getattr(element, "value", None)
            if value:
                parts.append(str(value))
    return " | ".join(parts)


def test_S1_to_S4_save_path_through_the_entry_point():
    with _db_isolation.isolated_db():
        wdb.init_wallet_tables()
        mdb.init_marketing_tables()
        mid, _new = wdb.get_or_create_member("kakao", "thsave_s1")
        mid = int(mid)
        gid = "thsave01"

        from auto_purchase_service import _next_draw_round

        expected_round = int(_next_draw_round())
        # 보드 iframe이 실제로 넘기는 형식 그대로: "1-2-3-4-5-6,7-8-9-10-11-12"
        saved_param = "1-2-3-4-5-6,7-8-9-10-11-12"

        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=TIMEOUT_SEC)
        at.query_params["page"] = "thunder"
        at.query_params["gid"] = gid
        at.query_params["native"] = "1"
        at.query_params["th_save"] = saved_param
        at.session_state["member_id"] = mid
        at.session_state["_guest_id"] = gid
        at.run()

        assert not at.exception, f"S4: 저장 경로에서 예외: {at.exception}"

        batches = mdb.list_guest_generated_combos(gid, "thunder")
        assert batches, f"S1: 저장된 조합이 DB에 없다(저장 경로가 안 돌았다): {batches}"
        rounds = {int(b["draw_round"]) for b in batches}
        assert rounds == {expected_round}, f"S1: 회차가 예상과 다르다: {rounds}"
        combos = sorted(tuple(c["combo"]) for b in batches for c in (b.get("combos") or []))
        assert combos == [(1, 2, 3, 4, 5, 6), (7, 8, 9, 10, 11, 12)], (
            f"S1: 넘긴 조합과 저장된 조합이 다르다: {combos}"
        )

        assert at.session_state["thunder_history_blink_panel_open"] is True, (
            "S2: 저장 직후인데 저장내역 패널이 안 펼쳐졌다"
        )
        marked = [(m.value or "") for m in at.markdown if MARK in (m.value or "")]
        assert len(marked) == 1, f"S2: 표시가 정확히 1개가 아니다: {len(marked)}"
        assert ">01<" in marked[0], "S2: 저장한 조합 카드가 아니다"

        messages = _messages(at)
        assert "완료" in messages, f"S3: 생성 완료 안내가 안 떴다: {messages[:120]!r}"

        # 저장 파라미터는 1회 소비돼 주소에 남지 않는다(새로고침 시 중복 저장 방지).
        assert not at.query_params.get("th_save"), (
            "th_save 파라미터가 주소에 남아 있다 - 새로고침하면 같은 조합이 또 저장된다"
        )
        print("  (진입점 ?th_save=... → DB 저장 · 저장내역 열림 · 완료 안내 · 파라미터 소비)")


def _main() -> int:
    tests = [test_S1_to_S4_save_path_through_the_entry_point]
    failed = 0
    for test in tests:
        try:
            test()
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"ERROR {test.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
        sys.stdout.flush()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
