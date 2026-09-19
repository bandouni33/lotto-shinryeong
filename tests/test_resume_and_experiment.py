"""두 작업 검증 — (1) 로그인 후 재개(resume) 유실 수정, (2) 반전/겹침 A/B 실험 스위치.

(1) 불변식:
  R1. state는 provider·page·guest_id 뿐 아니라 재개 의도(resume 이름 + 데이터)까지
      왕복에서 보존한다 — 모든 resume 종류·데이터 모양에 대해.
  R2. 재개 의도가 없는/예전 형식/외부에서 온 이상한 state도 예외 없이 안전한 기본값으로 풀린다.
  R3. 세션 리셋(완전 페이지 로드)을 거친 로그인 완료 시점에도 재개 의도가 되살아난다
      (콜백 state 경로 + 네이티브 앱용 서버 임시저장 경로 둘 다).
  R4. 재개 의도는 1회만 소비되고, 오래된(TTL 초과) 값은 실행되지 않는다.

(2) 불변식:
  E1. 기본값(스위치 꺼짐)에서는 아무것도 바뀌지 않는다(번호판 HTML·스크립트 3종 그대로).
  E2. no_board는 번호판 iframe만 빼고 상단 스크립트는 그대로 둔다.
  E3. no_scripts는 상단 스크립트만 빼고 번호판 iframe은 그대로 둔다.
  E4. both는 둘 다 뺀다.
  E5. 스위치는 환경변수 하나로만 바뀌고, 그 외 렌더 결과(요소·예외)는 동일하다.

DB는 건드리지 않는다 — app_settings/멤버 생성/게스트 연결을 테스트 안에서 스텁으로 바꾼다.
pytest 없이도 돌도록 표준 assert + __main__ 러너를 함께 둔다.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

THUNDER_PAGE = str(ROOT / "page_thunder.py")
ENTRY = str(ROOT / "app.py")
TIMEOUT_SEC = 60


def _ss(at: AppTest, key: str, default=None):
    try:
        return at.session_state[key]
    except KeyError:
        return default

RESUME_KINDS = [
    "open_thunder_dialog",
    "open_hedge_dialog",
    "open_hedge_qr_scan",
    "open_tarot_dialog",
    "my_info_dialog",
    "wallet_show_charge",
    "auto_show_points",
    "af_show_step1_points",
    "af_show_step2_points",
]

RESUME_DATA_SHAPES = [
    {},
    {"games": 20},
    {"count": 5, "lines": [[1, 2, 3, 4, 5, 6], [7, 8, 9, 10, 11, 12]]},
    {"label": "한글 값 ✓", "nested": {"a": [1, 2, {"b": None}]}},
]


# ── R2: 순수 함수 — 이상한 state도 안전하게 풀려야 한다 ──────────────────────
def test_decode_state_handles_legacy_and_hostile_input() -> None:
    import auth_providers as ap

    cases = [
        # (state 입력, 기대 provider, 기대 page, 기대 gid, 기대 resume)
        (None, "kakao", "main", None, None),
        ("", "kakao", "main", None, None),
        ("kakao:thunder:gid1", "kakao", "thunder", "gid1", None),          # 예전 형식(3필드)
        ("kakao:hedge:gid2:open_hedge_qr_scan:", "kakao", "hedge", "gid2", "open_hedge_qr_scan"),
        (":::::", "kakao", "main", None, None),                            # 빈 필드만
        ("kakao:thunder:gid3:resume_x:%7B%22a%22%3A1%7D", "kakao", "thunder", "gid3", "resume_x"),
        ("kakao:not-a-page:gid4", "kakao", "not-a-page", "gid4", None),
    ]
    for raw, exp_provider, exp_page, exp_gid, exp_resume in cases:
        provider, page, gid, resume, _data = ap._decode_oauth_state(raw)
        assert provider == exp_provider, f"provider: {raw!r} -> {provider!r}"
        assert page == exp_page, f"page: {raw!r} -> {page!r}"
        assert gid == exp_gid, f"gid: {raw!r} -> {gid!r}"
        assert resume == exp_resume, f"resume: {raw!r} -> {resume!r}"

    # 어떤 입력이든 예외를 내지 않아야 한다(경계·잘림·이모지·아주 긴 값)
    for weird in ["a" * 5000, ":" * 100, "kakao::", "🙂:🙂:🙂:🙂:🙂", "kakao:x:y:z:w:extra"]:
        assert isinstance(ap._decode_oauth_state(weird), tuple), f"crashed on {weird[:20]!r}"


# ── R1: state 왕복에서 재개 의도가 보존된다 ──────────────────────────────────
_ROUNDTRIP_APP = r"""
import json
import streamlit as st
import auth_providers as ap
from wallet_ui import AUTH_RESUME_DATA, AUTH_RESUME_FLAG

kinds = json.loads(st.query_params.get("kinds"))
shapes = json.loads(st.query_params.get("shapes"))
page = st.query_params.get("target_page", "thunder")
results = []
for kind in kinds:
    for shape in shapes:
        st.session_state[AUTH_RESUME_FLAG] = kind
        st.session_state[AUTH_RESUME_DATA] = shape
        state = ap._encode_oauth_state("kakao", page)
        p, pg, gid, resume, data_raw = ap._decode_oauth_state(state)
        decoded = json.loads(data_raw) if data_raw else None
        results.append({"kind": kind, "shape": shape, "state": state, "provider": p,
                        "page": pg, "gid": gid, "resume": resume, "data": decoded})
st.session_state["roundtrip"] = results
"""


def test_state_roundtrip_preserves_resume_for_every_kind_and_shape() -> None:
    # 주의: gid를 쿼리파라미터로 못 박는다. AppTest의 st.context.cookies는 MagicMock이라
    # (항상 truthy) 쿠키 폴백 분기를 타면 guest_id가 Mock이 돼 quote()가 TypeError를 낸다 —
    # 실기기/실서버에서는 쿠키가 str|None이라 생기지 않는 하네스 특성이다(측정으로 확인).
    gid = "rt" + os.urandom(5).hex()
    at = AppTest.from_string(_ROUNDTRIP_APP, default_timeout=TIMEOUT_SEC)
    at.query_params["kinds"] = json.dumps(RESUME_KINDS)
    at.query_params["shapes"] = json.dumps(RESUME_DATA_SHAPES, ensure_ascii=False)
    at.query_params["target_page"] = "hedge"
    at.query_params["gid"] = gid
    at.run()
    assert len(at.exception) == 0, f"roundtrip app raised: {at.exception}"

    rows = at.session_state["roundtrip"]
    assert len(rows) == len(RESUME_KINDS) * len(RESUME_DATA_SHAPES), "케이스 수가 맞지 않는다"
    for row in rows:
        assert row["resume"] == row["kind"], f"resume 유실: {row['kind']} -> {row['resume']}"
        assert row["page"] == "hedge", f"page 유실: {row['page']}"
        assert row["gid"] == gid, f"gid 유실/변형: {row['gid']!r}"
        assert row["provider"] == "kakao"
        assert row["data"] == row["shape"], (
            f"데이터 유실/변형: {row['kind']} {row['shape']} -> {row['data']}"
        )
        assert len(row["state"]) < 1500, f"state가 비정상적으로 길다: {len(row['state'])}"


# ── R3/R4: 세션 리셋 후에도 재개된다(콜백 + 네이티브용 서버저장) ──────────────
_CALLBACK_APP = r"""
import json
import time
import streamlit as st
import app_settings as _as

# 라이브 DB를 건드리지 않도록 설정 저장소를 메모리 스텁으로 교체
_store = {}
_as.init_settings_table = lambda: None
_as.get_setting = lambda key, default="": _store.get(key, default)
_as.set_setting = lambda key, value: _store.__setitem__(key, value)

import auth_providers as ap

ap.init_wallet_tables = lambda: None                      # 콜백 진입 시 DB 초기화 차단
ap.login_member = lambda provider, uid: (424242, False, False)  # 회원 생성 스텁
ap._link_guest_to_member_safe = lambda *a, **k: None
ap.kakao_configured = lambda: True
ap._exchange_kakao_code = lambda code: ("uid_test", None)

gid = st.query_params.get("gid")
resume = st.query_params.get("resume")
data = json.loads(st.query_params.get("data") or "{}")

# "배너를 열었던 순간"을 흉내: 네이티브 앱 경로용 서버 임시저장이 남아 있는 상태
_store[ap._PENDING_RESUME_PREFIX + gid] = json.dumps(
    {"resume": resume, "data": data, "ts": int(time.time())}
)

# 그 뒤 로그인창을 눌러 외부로 나갔다가 state를 들고 돌아온 상황
st.session_state["_guest_id"] = gid
state = ap._encode_oauth_state("kakao", "thunder")
st.session_state.clear_resume_probe = True

# 콜백 요청은 새 세션이다 — session_state에 재개 의도가 없는 상태를 만든다
st.session_state.pop("auth_resume_flag", None)
st.session_state.pop("auth_resume_data", None)

ok = ap.handle_oauth_callback()

# 재개 실행기(2번째 렌더)까지 확인
before = {
    "ok": bool(ok),
    "flag": st.session_state.get("auth_resume_flag"),
    "data": st.session_state.get("auth_resume_data"),
    "pending_after": _store.get(ap._PENDING_RESUME_PREFIX + gid, ""),
    "state_used": state,
}
from wallet_ui import _resume_after_auth

_resume_after_auth()
before["applied_dialog_flag"] = st.session_state.get("open_thunder_dialog")
before["applied_games"] = st.session_state.get("open_thunder_dialog_games")
st.session_state["out"] = before
"""


def test_resume_survives_full_reload_via_callback() -> None:
    at = AppTest.from_string(_CALLBACK_APP, default_timeout=TIMEOUT_SEC)
    gid = "cbgid" + os.urandom(4).hex()
    at.query_params["gid"] = gid
    at.query_params["resume"] = "open_thunder_dialog"
    at.query_params["data"] = json.dumps({"games": 20})
    at.query_params["code"] = "dummy_auth_code"
    at.run()
    assert len(at.exception) == 0, f"callback app raised: {at.exception}"

    out = at.session_state["out"]
    assert out["flag"] == "open_thunder_dialog", f"R3: state 경로로 재개 의도가 복원되지 않았다 {out}"
    assert out["data"] == {"games": 20}, f"R3: 재개 데이터가 복원되지 않았다 {out}"
    assert out["pending_after"] == "", "R4: 서버 임시저장이 1회 소비로 지워지지 않았다"
    assert out["applied_dialog_flag"] is True, f"재개 실행 실패 {out}"
    assert out["applied_games"] == 20, f"재개 데이터 반영 실패 {out}"


_PENDING_APP = r"""
import json
import time
import streamlit as st
import app_settings as _as

_store = {}
_as.init_settings_table = lambda: None
_as.get_setting = lambda key, default="": _store.get(key, default)
_as.set_setting = lambda key, value: _store.__setitem__(key, value)

import auth_providers as ap

gid = st.query_params.get("gid")
st.session_state["_guest_id"] = gid
ttl_age = int(st.query_params.get("age", "0"))

# 네이티브 앱 경로: state를 거치지 않으므로 서버 임시저장만이 유일한 전달 수단
_store[ap._PENDING_RESUME_PREFIX + gid] = json.dumps(
    {"resume": "open_hedge_qr_scan", "data": {"count": 5}, "ts": int(time.time()) - ttl_age}
)
first = ap._restore_pending_resume()
mid = {
    "first": first,
    "flag": st.session_state.get("auth_resume_flag"),
    "pending_after": _store.get(ap._PENDING_RESUME_PREFIX + gid, ""),
}
st.session_state.pop("auth_resume_flag", None)
st.session_state.pop("auth_resume_data", None)
second = ap._restore_pending_resume()
st.session_state["out"] = {"mid": mid, "second": second, "flag_after_second": st.session_state.get("auth_resume_flag")}
"""


def test_pending_resume_is_consumed_once_and_expires() -> None:
    # 정상(TTL 안쪽): 1회 소비되고 두 번째 호출은 아무것도 하지 않는다
    at = AppTest.from_string(_PENDING_APP, default_timeout=TIMEOUT_SEC)
    gid = "pngid" + os.urandom(4).hex()
    at.query_params["gid"] = gid
    at.query_params["age"] = "0"
    at.run()
    assert len(at.exception) == 0, f"pending app raised: {at.exception}"
    out = at.session_state["out"]
    assert out["mid"]["first"] is True, f"R3: 네이티브 경로 재개가 복원되지 않았다 {out}"
    assert out["mid"]["flag"] == "open_hedge_qr_scan", out
    assert out["mid"]["pending_after"] == "", "R4: 서버 임시저장이 지워지지 않았다"
    assert out["second"] is False, f"R4: 같은 의도가 두 번 소비됐다 {out}"
    assert out["flag_after_second"] is None, f"R4: 두 번째 호출이 값을 되살렸다 {out}"

    # TTL 초과: 실행되지 않고 소비만 된다(묵은 의도가 뒤늦게 실행되는 사고 방지)
    at2 = AppTest.from_string(_PENDING_APP, default_timeout=TIMEOUT_SEC)
    gid2 = "pngid" + os.urandom(4).hex()
    at2.query_params["gid"] = gid2
    at2.query_params["age"] = "100000"  # 15분 TTL 초과
    at2.run()
    assert len(at2.exception) == 0, f"pending app raised: {at2.exception}"
    out2 = at2.session_state["out"]
    assert out2["mid"]["first"] is False, f"R4: 만료된 의도가 실행됐다 {out2}"
    assert out2["mid"]["flag"] is None, f"R4: 만료된 의도가 플래그를 세웠다 {out2}"


# ── E1~E4: A/B 스위치가 주장하는 것만 바꾼다 ─────────────────────────────────
BOARD_MARK = "numberGrid"          # 번호판 iframe 안에만 있는 문자열
# 주의: 'safeVibrate'는 번호판 iframe 안에도 들어있어 마커로 쓸 수 없다(첫 실행에서
# 거짓 양성이 나왔다) — 최상위 문서용 진동 바인더에만 있는 dataset 플래그를 쓴다.
SCRIPT_MARKS = {
    "vibrate": "thVibrateBound",
    "poller": "thVisibilitySyncBound",
}


def _component_htmls(experiment: str | None):
    """page_thunder를 실제로 렌더하면서 components.html에 넘어간 HTML을 수집한다."""
    import streamlit.components.v1 as c1

    seen: list[str] = []
    original = c1.html
    c1.html = lambda html, **kw: (seen.append(html or ""), original(html, **kw))[1]
    before = os.environ.get("LOTTO_EXPERIMENT")
    if experiment is None:
        os.environ.pop("LOTTO_EXPERIMENT", None)
    else:
        os.environ["LOTTO_EXPERIMENT"] = experiment
    try:
        at = AppTest.from_file(THUNDER_PAGE, default_timeout=TIMEOUT_SEC)
        at.run()
        return at, seen
    finally:
        c1.html = original
        if before is None:
            os.environ.pop("LOTTO_EXPERIMENT", None)
        else:
            os.environ["LOTTO_EXPERIMENT"] = before


def test_experiment_switches_isolate_board_vs_scripts() -> None:
    # 첫 앱 실행에서는 스파이가 안 잡히는 하네스 특성이 있어(측정으로 확인) 예열 1회
    AppTest.from_file(THUNDER_PAGE, default_timeout=TIMEOUT_SEC).run()

    def measure(experiment: str | None) -> dict:
        at, seen = _component_htmls(experiment)
        assert len(at.exception) == 0, f"[{experiment}] page raised: {at.exception}"
        assert seen, f"[{experiment}] components.html 호출이 하나도 잡히지 않았다(계측 실패)"
        return {
            "has_board": any(BOARD_MARK in h for h in seen),
            "board_chars": max((len(h) for h in seen), default=0),
            "marks": {k: any(v in h for h in seen) for k, v in SCRIPT_MARKS.items()},
            "components": len(seen),
        }

    default = measure(None)
    no_board = measure("no_board")
    no_scripts = measure("no_scripts")
    both = measure("both")

    # E1: 기본값은 원래 그대로
    assert default["has_board"], f"E1: 기본값에서 번호판 HTML이 없다 {default}"
    assert default["board_chars"] > 20000, f"E1: 번호판 HTML이 너무 작다 {default}"
    assert all(default["marks"].values()), f"E1: 기본값에서 스크립트가 빠졌다 {default}"

    # E2: 번호판만 제거, 스크립트는 유지
    assert not no_board["has_board"], f"E2: no_board인데 번호판이 남아 있다 {no_board}"
    assert no_board["board_chars"] < 20000, f"E2: 번호판이 안 빠졌다 {no_board}"
    assert all(no_board["marks"].values()), f"E2: no_board가 스크립트까지 건드렸다 {no_board}"

    # E3: 스크립트만 제거, 번호판은 유지
    assert no_scripts["has_board"], f"E3: no_scripts가 번호판까지 없앴다 {no_scripts}"
    assert no_scripts["board_chars"] > 20000, f"E3: no_scripts에서 번호판이 작아졌다 {no_scripts}"
    assert not any(no_scripts["marks"].values()), (
        f"E3: no_scripts인데 스크립트가 남아 있다 {no_scripts}"
    )

    # E4: 둘 다
    assert not both["has_board"], f"E4: both인데 번호판이 남아 있다 {both}"
    assert not any(both["marks"].values()), f"E4: both인데 스크립트가 남아 있다 {both}"


# ── R3(조립): 실제 진입점(app.py)에서 완전 리로드를 거친 로그인이 재개되는가 ──
def test_resume_survives_full_reload_in_real_entry() -> None:
    """가짜 state를 들고 앱을 띄워, 콜백 → 재개 실행까지를 조립된 상태로 한 번 돌린다.
    라이브 DB 쓰기를 막기 위해 멤버 생성·게스트 연결·설정 저장을 스텁으로 바꾼다."""
    import app_settings
    import auth_providers as ap
    import wallet_ui as wu

    store: dict[str, str] = {}
    app_settings.init_settings_table = lambda: None
    app_settings.get_setting = lambda key, default="": store.get(key, default)
    app_settings.set_setting = lambda key, value: store.__setitem__(key, value)
    patched = {
        (ap, "init_wallet_tables"): lambda: None,
        (ap, "login_member"): lambda provider, uid: (424242, False, False),
        (ap, "_link_guest_to_member_safe"): lambda *a, **k: None,
        (ap, "kakao_configured"): lambda: True,
        (ap, "_exchange_kakao_code"): lambda code: ("uid_entry", None),
        (wu, "get_balance"): lambda mid: 100000,
    }
    saved = {(mod, name): getattr(mod, name) for (mod, name) in patched}
    for (mod, name), fn in patched.items():
        setattr(mod, name, fn)
    try:
        gid = "entgid" + os.urandom(4).hex()
        data = json.dumps({"games": 20}, separators=(",", ":"))
        state = ":".join(
            [
                "kakao",
                urllib.parse.quote("thunder", safe=""),
                urllib.parse.quote(gid, safe=""),
                urllib.parse.quote("open_thunder_dialog", safe=""),
                urllib.parse.quote(data, safe=""),
            ]
        )
        at = AppTest.from_file(ENTRY, default_timeout=TIMEOUT_SEC)
        at.query_params["page"] = "thunder"
        at.query_params["gid"] = gid
        at.query_params["code"] = "dummy_code"
        at.query_params["state"] = state
        at.run()
        assert len(at.exception) == 0, f"진입점이 예외로 죽었다: {at.exception}"
        assert _ss(at, "open_thunder_dialog") is True, "R3(조립): 로그인 후 확정창이 재개되지 않았다"
        assert _ss(at, "open_thunder_dialog_games") == 20, "R3(조립): 재개 데이터(games)가 반영되지 않았다"
        assert _ss(at, "auth_resume_flag") is None, "재개 의도는 실행 후 소비돼야 한다"
        assert at.query_params.get("code") in (None, []), "콜백 파라미터가 남아 있다"
    finally:
        for (mod, name), fn in saved.items():
            setattr(mod, name, fn)


def _main() -> int:
    tests = [
        test_decode_state_handles_legacy_and_hostile_input,
        test_state_roundtrip_preserves_resume_for_every_kind_and_shape,
        test_resume_survives_full_reload_via_callback,
        test_pending_resume_is_consumed_once_and_expires,
        test_resume_survives_full_reload_in_real_entry,
        test_experiment_switches_isolate_board_vs_scripts,
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
