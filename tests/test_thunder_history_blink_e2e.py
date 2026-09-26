"""번개조합 저장 직후 깜빡임이 실제 화면에서 보이는가 (2026-09-26 사용자 신고).

신고: "번개조합 창 — 조합저장 시 깜박임 없음".
공용 패널 쪽(H1)은 단독 렌더로 확인됐지만, **번개조합 화면이 실제로 밟는 경로**
(`th_save` → `thunder_history_blink` → 저장내역 버튼/패널)를 진입점에서 이어본 적이
없어서 여기서 확인한다. 스텁 없이 실제 저장 함수로 데이터를 심는다.

불변식: 진입점 `app.py?page=thunder` 에서
  T1. 저장 직후(blink) 저장내역 패널이 실제로 펼쳐진다.
  T2. 깜빡임 클래스가 **최신 배치 1개에만** 붙는다(예전 회차 배치는 안 붙는다).

DB는 _db_isolation.isolated_db()로만 만진다.
"""

from __future__ import annotations

import os
import sys
import time
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
NEEDLE = 'history-just-saved"'


def _marked(at: AppTest) -> list[str]:
    return [(m.value or "") for m in at.markdown if NEEDLE in (m.value or "")]


def test_T1_T2_thunder_save_blinks_the_newest_batch_in_the_real_entry_point():
    with _db_isolation.isolated_db():
        wdb.init_wallet_tables()
        mdb.init_marketing_tables()
        mid, _new = wdb.get_or_create_member("kakao", "thblink_t1")
        mid = int(mid)

        from auto_purchase_service import _next_draw_round

        gid = "thblink01"
        this_round = int(_next_draw_round())
        # 번개조합 저장 함수 그대로(계정 화면이 실제로 쓰는 경로).
        mdb.save_guest_generated_combos(gid, "thunder", this_round - 1, [[11, 12, 13, 14, 15, 16]])
        time.sleep(0.02)
        mdb.save_guest_generated_combos(gid, "thunder", this_round, [[1, 2, 3, 4, 5, 6]])

        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=TIMEOUT_SEC)
        at.query_params["page"] = "thunder"
        at.query_params["gid"] = gid
        at.query_params["native"] = "1"
        at.session_state["member_id"] = mid
        at.session_state["_guest_id"] = gid
        # 저장 직후 상태(th_save 경로가 세우는 것과 같은 플래그).
        at.session_state["thunder_history_blink"] = True
        at.run()
        assert not at.exception, f"번개조합 페이지 렌더 예외: {at.exception}"

        assert at.session_state["thunder_history_blink_panel_open"] is True, (
            "T1: 저장 직후인데 저장내역 패널이 안 펼쳐졌다(깜빡임이 보일 수 없다)"
        )
        marked = _marked(at)
        assert len(marked) == 1, (
            f"T2: 깜빡임 표시가 정확히 1개가 아니다: {len(marked)} / "
            f"캡션={[((c.value or '')[:40]) for c in at.caption]}"
        )
        assert ">01<" in marked[0], "T2: 최신 배치가 아니라 다른 카드가 깜빡인다"
        assert ">11<" not in marked[0], "T2: 예전 회차 배치가 깜빡였다"
        print("  (진입점 page=thunder · 실제 저장 데이터 → 저장내역 열림 · 최신 배치 1개만)")


def _main() -> int:
    tests = [test_T1_T2_thunder_save_blinks_the_newest_batch_in_the_real_entry_point]
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
