"""고급필터 세팅 회원별 영구 저장 검증 (2026-10-10 사용자 승인).

  P1. '세팅완료 저장'을 안 눌러도, 바꾼 1단계 세팅이 새 세션(재접속)에서 그대로 채워진다.
  P2. 서버 파일이 지워져도(Cloud 재부팅 흉내) DB 에서 되살아난다.
  P3. '세팅완료 저장'을 누르면 재접속 뒤에도 '저장됨'으로 이어진다(1단계 실행 안내가 사라진 상태).
  P4. 다른 회원에게는 내 세팅이 보이지 않는다(공용 폴더 대체 읽기 제거).
  P5. 계정 삭제 때 세팅 행이 지워진다.

DB 는 _db_isolation.isolated_db() 로만 만진다.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _p in (str(ROOT), str(TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import _db_isolation  # noqa: E402

TIMEOUT = 120
WAIT_TEXT = "세팅완료 저장]을 눌러야"


def _open(mid: int, gid: str) -> AppTest:
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=TIMEOUT)
    at.query_params["page"] = "advanced"
    at.query_params["gid"] = gid
    at.session_state["member_id"] = mid
    at.session_state["_guest_id"] = gid
    return at.run()


def _num(at: AppTest, key: str):
    return at.number_input(key=key).value


def _wipe_files(mid: int) -> None:
    shutil.rmtree(ROOT / "data" / "users" / f"member_{mid}", ignore_errors=True)


def _md(at: AppTest) -> str:
    return " ".join((m.value or "") for m in at.markdown)


def test_P1_to_P5():
    with _db_isolation.isolated_db():
        import wallet_db as wdb

        wdb.init_wallet_tables()
        mid, _ = wdb.get_or_create_member("kakao", "af_persist_p1")
        mid = int(mid)
        other, _ = wdb.get_or_create_member("kakao", "af_persist_other")
        other = int(other)
        for m in (mid, other):
            _wipe_files(m)

        at = _open(mid, "afp1")
        assert not at.exception, at.exception
        assert _num(at, "최소총합") == 70
        at.number_input(key="최소총합").set_value(100).run()
        at.checkbox(key="홀짝 비율_3:3").check().run()
        assert not at.exception, at.exception

        # P1·P2: 새 세션 + 서버 파일 삭제(재부팅 흉내)
        _wipe_files(mid)
        at2 = _open(mid, "afp1b")
        assert not at2.exception, at2.exception
        assert _num(at2, "최소총합") == 100, f"P1: 저장 안 누른 세팅이 재접속 뒤 사라졌다: {_num(at2, '최소총합')}"
        assert at2.checkbox(key="홀짝 비율_3:3").value is True, "P1: 체크 세팅이 사라졌다"
        assert WAIT_TEXT in _md(at2), "P1: 저장 버튼을 안 눌렀는데 '저장됨'으로 표시됐다"

        # P3: 세팅완료 저장 → 재접속 → 저장됨 유지
        at2.button(key="save_settings_btn_6n36s5").click().run()
        assert not at2.exception, at2.exception
        _wipe_files(mid)
        at3 = _open(mid, "afp1c")
        assert _num(at3, "최소총합") == 100
        assert WAIT_TEXT not in _md(at3), "P3: 저장했는데 재접속 뒤 '저장 필요' 안내가 다시 뜬다"

        # P4: 다른 회원은 기본값
        at4 = _open(other, "afp4")
        assert _num(at4, "최소총합") == 70, "P4: 다른 회원에게 내 세팅이 보인다"

        # P5: 계정 삭제 시 파기
        import af_settings_db
        import account_deletion
        import birthday_db
        import feedback_db
        import marketing_db

        feedback_db.init_feedback_tables()
        marketing_db.init_marketing_tables()
        if hasattr(birthday_db, "init_birthday_tables"):
            birthday_db.init_birthday_tables()

        assert af_settings_db.get_member_settings(mid)["draft"] is not None
        account_deletion.delete_account(mid)
        row = af_settings_db.get_member_settings(mid)
        assert row == {"draft": None, "saved": None, "k295": None}, f"P5: 탈퇴 뒤 세팅이 남았다: {row}"
        for m in (mid, other):
            _wipe_files(m)
        print("  (저장 안 눌러도 유지 · 파일 삭제 뒤 DB 복원 · 저장됨 유지 · 회원 분리 · 탈퇴 파기)")


def _main() -> int:
    tests = [test_P1_to_P5]
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
