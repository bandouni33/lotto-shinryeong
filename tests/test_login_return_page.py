"""로그인 후 "보던 화면 그대로" — 서버 쪽 복귀 (2026-10-05 사용자 지시).

문제: 타로·자동·번개·번호검증(hedge) 화면에서 로그인하면 메인화면으로 튕겼다.
원인: 지금 설치된 앱 빌드는 카카오 로그인 성공 후 주소를 새로 조립해(buildUri) page가
      빠진 채 다시 로드한다(고친 reloadWith는 네이티브_빌드_대기목록 §2로 빌드 대기 중).
처방: 배너를 열 때 서버 임시저장(pending_resume)에 **보던 화면도** 남기고, 로그인 완료
      (finalize_login → _restore_pending_resume) 때 그 화면으로 page를 되돌린다.
      앱 빌드 없이 서버 배포만으로 적용된다.

리스크 점검(다른 기능에 영향이 없는가)을 테스트로 고정한다:
  P1 허용 목록(RETURN_PAGES)은 한 곳 — OAuth state 인코딩 결과가 예전과 같다.
  P2 저장: 앱(native=1)은 재개 동작이 없어도 화면을 남기고, 웹은 예전처럼 재개 동작이
     있을 때만 남긴다(웹 DB 쓰기 증가 없음). 저장 형식에 page가 추가될 뿐 나머지는 그대로.
  P3 복원: 4개 화면 각각 되돌아간다 / 허용 목록 밖 값·만료 값은 무시 / 1회 소비 /
     재개 동작(resume) 복원은 예전과 동일.
  E1 조립(앱): 진입점(app.py)에 page=main + native_kakao_token(지금 앱이 실제로 보내는
     모양)으로 들어와도, 4개 화면 각각 그 화면에서 끝난다.
  E2 조립(앱·다음 빌드): 이미 같은 화면으로 들어오면(reloadWith) 그대로 — 충돌 없음.
  E3 조립(웹): 카카오 콜백은 state의 화면이 우선 — 임시저장 값이 달라도 결과 불변.
  E4 ×로 배너를 닫으면 임시저장이 지워져, 이후 다른 화면 로그인이 엉뚱한 곳으로 안 간다.
  E5 계정삭제·관리자처럼 복귀 대상이 아닌 화면에서는 page를 건드리지 않는다.
  C1 로그인 버튼을 누른 순간의 화면으로 갱신(배너를 연 채 다른 화면으로 이동한 경우),
     재개 의도는 유지. C2 만료된 재개 의도는 클릭으로 되살리지 않는다.
  C3 앱 로그인 버튼이 로그인 신호 전에 화면을 저장한다.

DB는 _db_isolation.isolated_db()로만 만진다(진입점 테스트 포함). 실행:
  venv312\\Scripts\\python.exe -X utf8 tests\\test_login_return_page.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _path in (str(ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import _db_isolation  # noqa: E402

TIMEOUT_SEC = 90
ENTRY = str(ROOT / "app.py")
FOUR_PAGES = ("tarot", "auto", "thunder", "hedge")  # 사용자 지시의 4개 화면


def _qp(at: AppTest, key: str):
    value = at.query_params.get(key)
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    return value


def _ss(at: AppTest, key: str):
    return at.session_state[key] if key in at.session_state else None


class _Stubbed:
    """설정 저장소(메모리)·회원 생성·카카오 검증을 스텁으로 바꿨다가 되돌린다."""

    def __init__(self):
        import app_settings
        import auth_providers as ap
        import wallet_ui as wu

        self.store: dict[str, str] = {}
        self._patched = {
            (app_settings, "init_settings_table"): lambda: None,
            (app_settings, "get_setting"): lambda key, default="": self.store.get(key, default),
            (app_settings, "set_setting"): lambda key, value: self.store.__setitem__(key, value),
            # 메인 화면 렌더가 부르는 업데이트 공지 조회 — 설정 테이블 초기화를 스텁으로
            # 막았으므로 이것도 막는다(안 막으면 빈 격리 DB에서 "no such table" 로그가 남는다).
            (app_settings, "get_update_notice"): lambda: {"version": "", "url": "", "message": ""},
            (ap, "init_wallet_tables"): lambda: None,
            (ap, "login_member"): lambda provider, uid: (424242, False, False),
            (ap, "_link_guest_to_member_safe"): lambda *a, **k: None,
            (ap, "_fetch_kakao_uid_with_token"): lambda token: ("uid_native", None),
            (ap, "kakao_configured"): lambda: True,
            (ap, "_exchange_kakao_code"): lambda code: ("uid_web", None),
            (wu, "get_balance"): lambda mid: 100000,
        }
        self._saved = {}
        self.ap = ap

    def __enter__(self):
        for (mod, name), fn in self._patched.items():
            self._saved[(mod, name)] = getattr(mod, name)
            setattr(mod, name, fn)
        return self

    def __exit__(self, *exc):
        for (mod, name), fn in self._saved.items():
            setattr(mod, name, fn)
        return False

    def put_pending(self, gid: str, page, resume: str = "", data=None, age: int = 0):
        self.store[self.ap._PENDING_RESUME_PREFIX + gid] = json.dumps(
            {"resume": resume, "data": data or {}, "page": page, "ts": int(time.time()) - age}
        )

    def pending(self, gid: str) -> str:
        return self.store.get(self.ap._PENDING_RESUME_PREFIX + gid, "")


class ReferencePointTests(unittest.TestCase):
    def test_P1_single_allowed_list_and_state_encoding_unchanged(self):
        import auth_providers as ap

        self.assertEqual(
            ap.RETURN_PAGES,
            ("main", "thunder", "auto", "stats", "birthday", "advanced", "tarot", "hedge"),
        )
        for page in FOUR_PAGES:
            self.assertIn(page, ap.RETURN_PAGES)
        src = (ROOT / "auth_providers.py").read_text(encoding="utf-8")
        self.assertEqual(src.count('"tarot", "hedge")'), 1, "허용 목록 사본이 생겼다")
        for raw, expected in (("thunder", "thunder"), (" hedge ", "hedge"), ("", "main"),
                              (None, "main"), ("delete_account", "main"), ("admin", "main"),
                              (["auto"], "auto")):
            self.assertEqual(ap._valid_return_page(raw) or "main", expected, repr(raw))


_REMEMBER_APP = r"""
import json
import streamlit as st
import app_settings as _as

_store = {}
_as.init_settings_table = lambda: None
_as.get_setting = lambda key, default="": _store.get(key, default)
_as.set_setting = lambda key, value: _store.__setitem__(key, value)

import auth_providers as ap

st.session_state["_guest_id"] = "rmgid"
resume = st.query_params.get("resume") or None
ap._remember_pending_resume(resume, {"games": 5} if resume else None)
raw = _store.get(ap._PENDING_RESUME_PREFIX + "rmgid", "")
st.session_state["out"] = json.loads(raw) if raw else None
"""


class RememberTests(unittest.TestCase):
    def _run(self, **params):
        at = AppTest.from_string(_REMEMBER_APP, default_timeout=TIMEOUT_SEC)
        for k, v in params.items():
            at.query_params[k] = v
        at.run()
        self.assertFalse(at.exception, f"예외: {at.exception}")
        return _ss(at, "out")

    def test_P2_native_without_resume_stores_page(self):
        for page in FOUR_PAGES:
            out = self._run(page=page, native="1")
            self.assertIsNotNone(out, f"{page}: 앱인데 화면이 저장되지 않았다")
            self.assertEqual(out["page"], page)
            self.assertEqual(out["resume"], "")

    def test_P2_native_on_main_also_overwrites(self):
        # 메인에서 배너를 열 때도 덮어써야 이전 화면이 묵지 않는다.
        out = self._run(page="main", native="1")
        self.assertEqual(out["page"], "main")

    def test_P2_web_without_resume_stores_nothing(self):
        self.assertIsNone(self._run(page="tarot"), "웹에서 불필요한 DB 쓰기가 늘었다")

    def test_P2_web_with_resume_keeps_old_shape_plus_page(self):
        out = self._run(page="thunder", resume="open_thunder_dialog")
        self.assertEqual(out["resume"], "open_thunder_dialog")
        self.assertEqual(out["data"], {"games": 5})
        self.assertEqual(out["page"], "thunder")
        self.assertIn("ts", out)

    def test_P2_non_return_page_is_stored_as_main(self):
        out = self._run(page="delete_account", native="1")
        self.assertEqual(out["page"], "main")


_RESTORE_APP = r"""
import json
import time
import streamlit as st
import app_settings as _as

_store = {}
_as.init_settings_table = lambda: None
_as.get_setting = lambda key, default="": _store.get(key, default)
_as.set_setting = lambda key, value: _store.__setitem__(key, value)

import auth_providers as ap

st.session_state["_guest_id"] = "rsgid"
payload = json.loads(st.query_params.get("payload"))
payload["ts"] = int(time.time()) - int(payload.pop("age", 0))
_store[ap._PENDING_RESUME_PREFIX + "rsgid"] = json.dumps(payload)
first = ap._restore_pending_resume()
page_after_first = st.query_params.get("page")
st.query_params["page"] = "main"
second = ap._restore_pending_resume()
st.session_state["out"] = {
    "first": first,
    "page_after_first": page_after_first,
    "flag": st.session_state.get("auth_resume_flag"),
    "second": second,
    "page_after_second": st.query_params.get("page"),
    "pending_after": _store.get(ap._PENDING_RESUME_PREFIX + "rsgid", ""),
}
"""


class RestoreTests(unittest.TestCase):
    def _run(self, start_page: str, payload: dict):
        at = AppTest.from_string(_RESTORE_APP, default_timeout=TIMEOUT_SEC)
        at.query_params["page"] = start_page
        at.query_params["payload"] = json.dumps(payload)
        at.run()
        self.assertFalse(at.exception, f"예외: {at.exception}")
        return _ss(at, "out")

    def test_P3_each_of_four_pages_is_restored_and_consumed_once(self):
        for page in FOUR_PAGES:
            out = self._run("main", {"resume": "", "data": {}, "page": page})
            self.assertEqual(out["page_after_first"], page, f"{page}: 화면이 복원되지 않았다")
            self.assertFalse(out["first"], "resume이 없는데 True를 돌려줬다(반환값 계약 변경)")
            self.assertEqual(out["page_after_second"], "main", f"{page}: 두 번 소비됐다")
            self.assertEqual(out["pending_after"], "")

    def test_P3_resume_restore_is_unchanged(self):
        out = self._run("main", {"resume": "open_tarot_dialog", "data": {}, "page": "tarot"})
        self.assertTrue(out["first"])
        self.assertEqual(out["flag"], "open_tarot_dialog")
        self.assertEqual(out["page_after_first"], "tarot")
        self.assertFalse(out["second"])

    def test_P3_invalid_or_expired_page_is_ignored(self):
        for bad in ("delete_account", "admin", "toss_test_login", "", None, 123):
            out = self._run("auto", {"resume": "", "data": {}, "page": bad})
            self.assertEqual(out["page_after_first"], "auto", f"{bad!r}: page를 건드렸다")
        out = self._run("main", {"resume": "", "data": {}, "page": "tarot", "age": 100000})
        self.assertEqual(out["page_after_first"], "main", "만료된 화면으로 이동했다")

    def test_P3_old_payload_without_page_still_works(self):
        # 배포 직전에 저장된 예전 형식(page 없음)이 와도 재개는 그대로, 화면은 그대로.
        out = self._run("auto", {"resume": "auto_show_points", "data": {}})
        self.assertTrue(out["first"])
        self.assertEqual(out["page_after_first"], "auto")


class EntryPointTests(unittest.TestCase):
    """진입점(app.py) 조립 — 앱·웹이 실제로 밟는 순서."""

    def _native_login(self, stub: _Stubbed, gid: str, arrive_page: str):
        at = AppTest.from_file(ENTRY, default_timeout=TIMEOUT_SEC)
        at.query_params["page"] = arrive_page
        at.query_params["gid"] = gid
        at.query_params["native"] = "1"
        at.query_params["native_kakao_token"] = "dummy_access_token"
        at.run()
        self.assertFalse(at.exception, f"진입점 예외: {at.exception}")
        self.assertEqual(_ss(at, "member_id"), 424242, "네이티브 로그인이 완료되지 않았다")
        self.assertIsNone(_qp(at, "native_kakao_token"), "토큰 파라미터가 남았다")
        self.assertEqual(_qp(at, "native"), "1", "native=1이 사라졌다(앱 판정이 깨진다)")
        self.assertEqual(_qp(at, "gid"), gid, "gid가 바뀌었다(로그인 연결이 끊긴다)")
        return at

    def test_E1_native_login_lands_back_on_each_of_four_pages(self):
        for page in FOUR_PAGES:
            with _db_isolation.isolated_db(), _Stubbed() as stub:
                gid = f"e1{page}" + os.urandom(3).hex()
                stub.put_pending(gid, page)
                at = self._native_login(stub, gid, arrive_page="main")  # 지금 앱의 실제 모양
                self.assertEqual(_qp(at, "page"), page, f"{page}: 로그인 후 메인으로 튕겼다")
                self.assertEqual(stub.pending(gid), "", f"{page}: 임시저장이 소비되지 않았다")

    def test_E1_native_login_with_resume_runs_it_on_the_right_page(self):
        with _db_isolation.isolated_db(), _Stubbed() as stub:
            gid = "e1r" + os.urandom(3).hex()
            stub.put_pending(gid, "thunder", resume="open_thunder_dialog", data={"games": 20})
            at = self._native_login(stub, gid, arrive_page="main")
            self.assertEqual(_qp(at, "page"), "thunder")
            self.assertIs(_ss(at, "open_thunder_dialog"), True, "재개 동작이 실행되지 않았다")
            self.assertEqual(_ss(at, "open_thunder_dialog_games"), 20)

    def test_E2_next_build_arriving_on_same_page_is_untouched(self):
        with _db_isolation.isolated_db(), _Stubbed() as stub:
            gid = "e2" + os.urandom(3).hex()
            stub.put_pending(gid, "tarot")
            at = self._native_login(stub, gid, arrive_page="tarot")
            self.assertEqual(_qp(at, "page"), "tarot")

    def test_E2_main_banner_login_stays_on_main(self):
        with _db_isolation.isolated_db(), _Stubbed() as stub:
            gid = "e2m" + os.urandom(3).hex()
            stub.put_pending(gid, "main")
            at = self._native_login(stub, gid, arrive_page="main")
            self.assertEqual(_qp(at, "page"), "main")

    def test_E3_web_callback_state_page_wins(self):
        import urllib.parse

        with _db_isolation.isolated_db(), _Stubbed() as stub:
            gid = "e3" + os.urandom(3).hex()
            stub.put_pending(gid, "tarot", resume="open_thunder_dialog")  # 일부러 다르게
            state = ":".join(["kakao", "thunder", urllib.parse.quote(gid, safe="")])
            at = AppTest.from_file(ENTRY, default_timeout=TIMEOUT_SEC)
            at.query_params["page"] = "main"
            at.query_params["gid"] = gid
            at.query_params["code"] = "dummy_code"
            at.query_params["state"] = state
            at.run()
            self.assertFalse(at.exception, f"진입점 예외: {at.exception}")
            self.assertEqual(_ss(at, "member_id"), 424242)
            self.assertEqual(_qp(at, "page"), "thunder", "웹 콜백의 state 화면이 덮였다")

    def test_E4_dismiss_clears_saved_page(self):
        app = r"""
import streamlit as st
import app_settings as _as
_store = st.session_state.setdefault("_store", {})
_as.init_settings_table = lambda: None
_as.get_setting = lambda key, default="": _store.get(key, default)
_as.set_setting = lambda key, value: _store.__setitem__(key, value)
import auth_providers as ap
import wallet_ui as wu
st.session_state["_guest_id"] = "e4gid"
wu.open_auth_banner(reason="t")
st.session_state["saved"] = _store.get(ap._PENDING_RESUME_PREFIX + "e4gid", "")
wu.close_auth_banner()
st.session_state["after_close"] = _store.get(ap._PENDING_RESUME_PREFIX + "e4gid", "")
"""
        at = AppTest.from_string(app, default_timeout=TIMEOUT_SEC)
        at.query_params["page"] = "hedge"
        at.query_params["native"] = "1"
        at.run()
        self.assertFalse(at.exception, f"예외: {at.exception}")
        self.assertEqual(json.loads(_ss(at, "saved"))["page"], "hedge",
                         "배너를 열 때 화면이 저장되지 않았다")
        self.assertEqual(_ss(at, "after_close"), "", "×로 닫았는데 저장된 화면이 남았다")

    def test_E5_non_return_page_is_never_redirected(self):
        # 계정삭제·관리자·심사용처럼 복귀 대상이 아닌 화면에서는 저장값이 무엇이든 그대로.
        for special in ("delete_account", "admin", "toss_test_login"):
            app = r"""
import streamlit as st
import auth_providers as ap
ap._apply_pending_return_page("tarot")
"""
            at = AppTest.from_string(app, default_timeout=TIMEOUT_SEC)
            at.query_params["page"] = special
            at.run()
            self.assertFalse(at.exception, f"예외: {at.exception}")
            self.assertEqual(_qp(at, "page"), special, f"{special}: page를 바꿨다")
        with _db_isolation.isolated_db(), _Stubbed() as stub:
            gid = "e5" + os.urandom(3).hex()
            stub.put_pending(gid, "tarot")
            at = self._native_login(stub, gid, arrive_page="delete_account")
            self.assertEqual(_qp(at, "page"), "delete_account")


_CLICK_APP = r"""
import json
import time
import streamlit as st
import app_settings as _as

_store = {}
_as.init_settings_table = lambda: None
_as.get_setting = lambda key, default="": _store.get(key, default)
_as.set_setting = lambda key, value: _store.__setitem__(key, value)

import auth_providers as ap

st.session_state["_guest_id"] = "ckgid"
seed = st.query_params.get("seed")
if seed:
    payload = json.loads(seed)
    payload["ts"] = int(time.time()) - int(payload.pop("age", 0))
    _store[ap._PENDING_RESUME_PREFIX + "ckgid"] = json.dumps(payload)
ap.remember_return_page_at_login_click()
st.session_state["out"] = json.loads(_store[ap._PENDING_RESUME_PREFIX + "ckgid"])
"""


class LoginClickTests(unittest.TestCase):
    """C1·C2 — 로그인 버튼을 누른 순간의 화면으로 갱신(배너를 연 화면과 다를 수 있다)."""

    def _run(self, page: str, seed: dict | None):
        at = AppTest.from_string(_CLICK_APP, default_timeout=TIMEOUT_SEC)
        at.query_params["page"] = page
        if seed is not None:
            at.query_params["seed"] = json.dumps(seed)
        at.run()
        self.assertFalse(at.exception, f"예외: {at.exception}")
        return _ss(at, "out")

    def test_C1_click_page_replaces_banner_open_page_and_keeps_resume(self):
        # 타로에서 배너를 연 채 자동조합으로 이동해 로그인 → 자동조합으로 돌아와야 한다.
        out = self._run("auto", {"resume": "auto_show_points", "data": {"n": 5}, "page": "tarot"})
        self.assertEqual(out["page"], "auto", "버튼을 누른 화면이 아니라 배너를 연 화면이 남았다")
        self.assertEqual(out["resume"], "auto_show_points", "재개 의도가 지워졌다")
        self.assertEqual(out["data"], {"n": 5})

    def test_C1_click_without_prior_save_creates_page_only(self):
        out = self._run("hedge", None)
        self.assertEqual(out, {**out, "resume": "", "data": {}, "page": "hedge"})

    def test_C2_expired_resume_is_not_revived_by_click(self):
        out = self._run("thunder", {"resume": "open_thunder_dialog", "data": {}, "page": "thunder",
                                    "age": 100000})
        self.assertEqual(out["resume"], "", "만료된 재개 의도가 클릭으로 되살아났다")
        self.assertEqual(out["page"], "thunder")

    def test_C3_native_button_calls_it_before_the_trigger(self):
        src = (ROOT / "wallet_ui.py").read_text(encoding="utf-8")
        body = src.split('key="auth_banner_kakao_native"', 1)[1].split("else:", 1)[0]
        self.assertIn("remember_return_page_at_login_click()", body)
        self.assertLess(body.index("remember_return_page_at_login_click()"),
                        body.index("_fire_kakao_native_login_trigger()"),
                        "화면 저장이 로그인 신호보다 늦다")


def _main() -> int:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (ReferencePointTests, RememberTests, RestoreTests, EntryPointTests,
                LoginClickTests):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    tests = list(suite)
    failed = 0
    for test in tests:
        result = unittest.TestResult()
        test.run(result)  # 결과 객체로 판정한다(TestCase를 직접 호출하면 실패를 삼킨다)
        problems = [("FAIL", tb) for _t, tb in result.failures] + \
                   [("ERROR", tb) for _t, tb in result.errors]
        if problems:
            failed += 1
            for kind, tb in problems:
                print(f"{kind} {test._testMethodName}:\n{tb.strip().splitlines()[-1]}")
        else:
            print(f"PASS {test._testMethodName}")
        sys.stdout.flush()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
