"""카카오 로그인 배너 분기 보존 계약 — 2026-09-21 "로그인 버튼이 눌러도 먹통" 수정 검증.

배경: 네이티브 앱은 URL의 `native=1` 하나로만 "앱 전용 카카오 SDK 버튼"과 "일반 웹
링크"를 가른다(wallet_ui._render_auth_banner_form). 그런데 상세페이지 좌상단
로또신령 아이콘(shared_ui_styles.brand_home_link_html)의 기본 href가 `"?"`라, 그
아이콘을 한 번 누르면 쿼리스트링이 통째로 비워져 native=1(과 gid)이 사라졌다 —
그 뒤 앱에서 로그인 배너를 누르면 카카오 로그인 페이지가 앱 웹뷰 안에서 열리고,
리다이렉트 주소는 개발 PC IP(`http://210.99.230.83:8501`)로 잡혀 로그인이 끝나지
않았다(사용자 신고: "카카오 로그인창은 클릭해도 먹통").

불변식(모든 유효 입력에 대해 성립해야 하는 성질):
  K1. native=1이 있는 요청에서 만든 내부이동 링크는 **임의의** gid(공백·예약문자·
      한글·초장문 포함)에 대해 그 gid를 손실 없이 되돌려주고(왕복 보존) native를
      그대로 실어 보낸다. 파라미터는 {page, gid, native} 밖으로 늘어나지 않는다.
  K2. native가 없는 요청(일반 브라우저)에서는 native를 만들지 않는다.
  K3. 같은 입력에 대해 몇 번을 만들어도 같은 href가 나온다(결정적).
  K4. redirect_uri: 설정값이 비어 있지 않으면 그 값 그대로, 비어 있으면 요청 호스트
      에서 만든 origin, 그것도 없으면 로컬 기본값 — 어떤 헤더 조합에서도 예외 없이
      이 셋 중 하나이고, 인가 URL이 쓰는 값과 토큰교환이 쓰는 값이 항상 같다.
  K5. 배너 분기: native=1이면 앱 전용 버튼, 없으면 아니다. 계측은 세션당 1회만,
      첫 판정 그대로 남고, '침입 시도' 경보 집계에는 들어가지 않는다.
  K6. security_log.log_event는 ip 값이 문자열이 아니어도(모의 컨텍스트 등) 기록을
      통째로 잃지 않는다 — 참고용 값 때문에 이벤트가 사라지면 안 된다.

한계: AppTest는 <a href>를 "클릭"해 실제 브라우저 이동을 일으킬 수 없다(마크다운
HTML이다). 그래서 브라우저가 그대로 따라갈 href를 실제 렌더 출력에서 꺼내 검증한다.
user_page.py의 클릭 패치 JS는 이 환경에서 실행할 수 없어(JS 런타임 없음) 소스 수준의
구조 검사로만 고정한다 — 그 한계는 해당 테스트 독스트링에 명시했다.

pytest 없이도 돌도록 표준 assert + __main__ 러너를 함께 둔다.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import urllib.parse
from pathlib import Path
from unittest import mock

from streamlit.testing.v1 import AppTest

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _path in (str(ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import _db_isolation  # noqa: E402

TIMEOUT_SEC = 60

# ── 내부이동 링크 불변식(K1~K3) ───────────────────────────────────────────────
# gid는 값의 종류를 가리지 않고 보존돼야 한다 — 공백, 예약문자, 한글, 미리 인코딩된
# 것처럼 보이는 값, 부호, 초장문, 그리고 빈 값(빈 값일 때는 서버가 새 id를 발급하므로
# "비어있지 않은 gid"만 요구한다).
GID_CASES = (
    "abc123",
    "한글아이디",
    "a b&c=d?e",
    "%2Fslash",
    "+plus",
    "0",
    "x" * 300,
    "",
)

_LINKS_APP = """
import streamlit as st
from shared_ui_styles import brand_home_link_html, main_nav_button_html

GIDS = ["abc123", "한글아이디", "a b&c=d?e", "%2Fslash", "+plus", "0", "x" * 300, ""]


def _href(html):
    return html.split('href="', 1)[1].split('"', 1)[0]


for i, g in enumerate(GIDS):
    if "gid" in st.query_params:
        del st.query_params["gid"]
    st.session_state["_guest_id"] = g
    st.session_state["_guest_id_confirmed"] = True
    # 두 번 만들어 값이 항상 같아야 한다(K3).
    st.write("brand|" + str(i) + "|" + _href(brand_home_link_html()) + "|" + _href(brand_home_link_html()))
    st.write("mainnav|" + str(i) + "|" + _href(main_nav_button_html()) + "|" + _href(main_nav_button_html()))
"""


def _render_link_matrix(with_native: bool) -> dict[str, dict[int, tuple[str, str]]]:
    at = AppTest.from_string(_LINKS_APP, default_timeout=TIMEOUT_SEC)
    at.query_params["page"] = "hedge"
    if with_native:
        at.query_params["native"] = "1"
    at.run()
    assert len(at.exception) == 0, f"링크 앱이 예외를 냈다: {at.exception}"

    rows: dict[str, dict[int, tuple[str, str]]] = {}
    for m in at.markdown:
        value = m.value or ""
        if not (value.startswith("brand|") or value.startswith("mainnav|")):
            continue
        tag, index, href, href_again = value.split("|", 3)
        rows.setdefault(tag, {})[int(index)] = (href, href_again)
    for tag in ("brand", "mainnav"):
        assert len(rows.get(tag, {})) == len(GID_CASES), f"{tag} 링크가 {len(GID_CASES)}건 모두 렌더되지 않았다"
    return rows


def _assert_link_invariants(rows, with_native: bool) -> None:
    for tag, per_case in rows.items():
        for index, (href, href_again) in per_case.items():
            gid_in = GID_CASES[index]
            where = f"{tag} gid={gid_in!r} → {href!r}"

            # K3: 결정적
            assert href == href_again, f"같은 입력인데 href가 달라졌다: {where} vs {href_again!r}"

            assert href.startswith("?"), f"내부이동 링크가 ?로 시작하지 않는다: {where}"
            assert "None" not in href, f"href에 None이 섞였다(파라미터 생성 실패): {where}"

            query = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            assert query.get("page") == ["main"], f"page가 main이 아니다: {where}"
            assert set(query) <= {"page", "gid", "native"}, (
                f"내부이동 링크에 예상 밖 파라미터가 붙었다: {set(query)} ({where})"
            )

            # K1: gid 왕복 보존 (빈 값으로 나가면 게스트 식별자가 끊기므로 그것만 막으면 된다)
            assert len(query.get("gid", [])) == 1, f"gid 파라미터가 없다: {where}"
            got_gid = query["gid"][0]
            if gid_in:
                assert got_gid == gid_in, f"gid가 손실/변형됐다: 기대 {gid_in!r}, 실제 {got_gid!r} ({where})"
            else:
                # 입력이 빈 값일 때 채워지는 실제 값은 get_or_create_guest_id()의 폴백
                # 사슬(쿠키 등)이 정한다 — 여기서 고정할 수 있는 불변식은 "빈 값으로는
                # 절대 나가지 않는다"까지다(쿠키 폴백은 이 하네스에서 모의 객체를 돌려준다).
                assert got_gid.strip(), f"gid가 빈 값으로 나갔다: {where}"

            # K1/K2: native는 있으면 그대로, 없으면 만들지 않는다
            if with_native:
                assert query.get("native") == ["1"], f"native=1이 유실됐다(앱이 웹 분기로 떨어진다): {where}"
            else:
                assert "native" not in query, f"브라우저 요청에 native를 지어냈다: {where}"


def test_internal_links_keep_gid_and_native_for_every_input() -> None:
    """K1~K3 — native가 있는 앱 요청: 모든 gid 종류에서 손실 없이 보존된다."""
    _assert_link_invariants(_render_link_matrix(with_native=True), with_native=True)


def test_internal_links_do_not_invent_native_for_every_input() -> None:
    """K2/K3 — native가 없는 브라우저 요청: 모든 gid 종류에서 native를 만들지 않는다."""
    _assert_link_invariants(_render_link_matrix(with_native=False), with_native=False)


def test_click_patch_carries_both_params() -> None:
    """K1(구조) — user_page.py 클릭 패치가 gid만이 아니라 native도 이어붙이는지.

    이 JS는 이 환경에서 실행할 수 없다(JS 런타임 없음) — 그래서 "두 파라미터를 모두
    읽고, 각각 빠져 있을 때만 덧붙이며, 예전처럼 gid가 있으면 조기 return하지 않는다"는
    구조만 소스 수준에서 고정한다. 동작 자체는 위의 href 불변식이 담당한다.
    """
    src = (ROOT / "user_page.py").read_text(encoding="utf-8")
    block_start = src.find("function currentParam(name)")
    assert block_start != -1, "클릭 패치(currentParam)를 찾지 못했다"
    block = src[block_start : block_start + 2000]

    assert "currentParam('gid')" in block and "currentParam('native')" in block, (
        "클릭 패치가 gid와 native를 모두 읽지 않는다"
    )
    assert "href.indexOf('gid=') === -1" in block and "href.indexOf('native=') === -1" in block, (
        "빠져 있는 파라미터만 덧붙이는 형태가 아니다"
    )
    assert "indexOf('gid=') !== -1) return" not in block, (
        "gid가 있으면 조기 return해 native를 놓치는 예전 형태가 남아 있다"
    )


# ── redirect_uri 불변식(K4) ──────────────────────────────────────────────────
HEADER_CASES = (
    ({"Host": "lotto-shinryeong.streamlit.app", "X-Forwarded-Proto": "https"}, "https://lotto-shinryeong.streamlit.app"),
    ({"Host": "lotto-shinryeong.streamlit.app"}, "https://lotto-shinryeong.streamlit.app"),
    ({"Host": "a.example", "X-Forwarded-Proto": "http"}, "http://a.example"),
    ({"Host": "a.example", "X-Forwarded-Proto": "https, http"}, "https://a.example"),
    ({"Host": "a.example", "X-Forwarded-Proto": "HTTPS"}, "https://a.example"),
    ({"Host": "a.example", "X-Forwarded-Proto": "  https  "}, "https://a.example"),
    ({"Host": "a.example", "X-Forwarded-Proto": "garbage"}, "https://a.example"),
    ({"host": "a.example"}, "https://a.example"),
    ({"Host": "  a.example  "}, "https://a.example"),
    ({"Host": "localhost:8501"}, "http://localhost:8501"),
    ({"Host": "127.0.0.1:8501"}, "http://127.0.0.1:8501"),
    ({"Host": "0.0.0.0:8501"}, "http://0.0.0.0:8501"),
    ({"Host": "192.168.0.5:8501"}, "https://192.168.0.5:8501"),
    ({}, None),
    ({"Host": ""}, None),
    ({"Host": "   "}, None),
    ({"X-Forwarded-Proto": "https"}, None),
    (None, None),
    (["no", "get"], None),
)


def test_origin_from_headers_table() -> None:
    """K4 — 어떤 헤더 조합이든 origin 또는 None, 스킴 규칙은 항상 같다."""
    import auth_providers

    for headers, expected in HEADER_CASES:
        got = auth_providers._origin_from_headers(headers)
        assert got == expected, f"{headers!r} → 기대 {expected!r}, 실제 {got!r}"
        if got is not None:
            host = (headers.get("Host") or headers.get("host") or "").strip()
            assert got in (f"http://{host}", f"https://{host}"), (
                f"헤더의 호스트와 다른 주소를 만들었다: {got!r} (Host={host!r})"
            )
            assert got.startswith(("http://", "https://")), got
            assert " " not in got, f"origin에 공백이 남았다: {got!r}"


def test_redirect_uri_invariants() -> None:
    """K4 — 설정값 우선, 비면 요청 호스트, 그것도 없으면 로컬 기본값. 결정적이다."""
    import auth_providers

    before = os.environ.get("KAKAO_REDIRECT_URI")
    saved_origin = auth_providers._request_origin
    try:
        # 설정값은 (앞뒤 공백을 뺀) 그대로 — 값의 종류를 가리지 않는다.
        for configured in ("http://210.99.230.83:8501", "https://x.example/oauth/kakao", "  https://y.example  "):
            os.environ["KAKAO_REDIRECT_URI"] = configured
            assert auth_providers._redirect_uri() == configured.strip(), configured
            assert auth_providers._redirect_uri() == auth_providers._redirect_uri(), "결정적이지 않다"

        # 설정이 비거나 공백뿐이면 요청 호스트로 대체(예전엔 localhost 고정 → 배포 서버에서 로그인 불가).
        auth_providers._request_origin = lambda: "https://lotto-shinryeong.streamlit.app"
        for blank in ("", "   "):
            os.environ["KAKAO_REDIRECT_URI"] = blank
            assert auth_providers._redirect_uri() == "https://lotto-shinryeong.streamlit.app", repr(blank)
        os.environ.pop("KAKAO_REDIRECT_URI", None)
        assert auth_providers._redirect_uri() == "https://lotto-shinryeong.streamlit.app"

        # 호스트도 못 얻으면 로컬 개발 기본값(기존 동작 유지).
        auth_providers._request_origin = lambda: None
        assert auth_providers._redirect_uri() == "http://localhost:8501"
    finally:
        auth_providers._request_origin = saved_origin
        if before is None:
            os.environ.pop("KAKAO_REDIRECT_URI", None)
        else:
            os.environ["KAKAO_REDIRECT_URI"] = before


_AUTH_URL_APP = """
import urllib.parse as up

import streamlit as st

from auth_providers import _redirect_uri, get_kakao_authorize_url

parsed = up.parse_qs(up.urlparse(get_kakao_authorize_url("main")).query)
st.write("url_redirect|" + (parsed.get("redirect_uri") or [""])[0])
st.write("direct|" + _redirect_uri())
st.write("has_client_id|" + ("1" if (parsed.get("client_id") or [""])[0] else "0"))
"""


def test_authorize_url_and_token_exchange_share_one_redirect_uri() -> None:
    """K4 — 인가 URL과 토큰교환이 같은 값을 써야 한다(어긋나면 로그인이 깨진다)."""
    before = os.environ.get("KAKAO_REDIRECT_URI")
    before_key = os.environ.get("KAKAO_REST_API_KEY")
    try:
        os.environ.pop("KAKAO_REDIRECT_URI", None)
        os.environ["KAKAO_REST_API_KEY"] = "test-rest-key"
        at = AppTest.from_string(_AUTH_URL_APP, default_timeout=TIMEOUT_SEC)
        # 실제 앱에서도 이 화면은 항상 gid와 함께 열린다 — 넣어주지 않으면 쿠키 폴백이
        # 이 하네스의 모의 객체를 돌려줘 state 생성이 깨진다(그 경로는 제품 코드가 아니라
        # 테스트 대역의 한계다).
        at.query_params["gid"] = "gidauthtest"
        at.run()
        assert len(at.exception) == 0, f"인가 URL 앱이 예외를 냈다: {at.exception}"
        values = {}
        for m in at.markdown:
            value = m.value or ""
            if "|" in value:
                key, _, rest = value.partition("|")
                values[key] = rest
        assert values.get("has_client_id") == "1", "인가 URL에 client_id가 없다"
        assert values.get("url_redirect") == values.get("direct"), (
            f"인가 URL의 redirect_uri({values.get('url_redirect')!r})와 "
            f"토큰교환이 쓸 값({values.get('direct')!r})이 다르다"
        )
        assert values.get("url_redirect"), "redirect_uri가 비어 있다"
    finally:
        if before is None:
            os.environ.pop("KAKAO_REDIRECT_URI", None)
        else:
            os.environ["KAKAO_REDIRECT_URI"] = before
        if before_key is None:
            os.environ.pop("KAKAO_REST_API_KEY", None)
        else:
            os.environ["KAKAO_REST_API_KEY"] = before_key


# ── 배너 분기와 계측(K5) ─────────────────────────────────────────────────────
_BANNER_APP = """
import streamlit as st
from wallet_ui import _log_login_branch_once, open_auth_banner, render_auth_banner

native = st.query_params.get("native") == "1"
# 같은 세션에서 두 번 불러도 계측은 1건이고, 첫 판정 그대로여야 한다(K5).
_log_login_branch_once(native)
_log_login_branch_once(not native)
open_auth_banner()
render_auth_banner()
"""

NATIVE_BTN = "auth_banner_kakao_native"


def _rows(sql: str, params=()) -> list[tuple]:
    path = _db_isolation.current_path()
    assert path, "테스트 DB 경로를 얻지 못했다"
    conn = sqlite3.connect(path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _branch_details() -> list[str]:
    return [r[0] for r in _rows("SELECT detail FROM security_events WHERE event_type = 'kakao_login_branch'")]


def _render_banner(with_native: bool) -> AppTest:
    before_key = os.environ.get("KAKAO_REST_API_KEY")
    before_mock = os.environ.get("LOTTO_DEV_MOCK_AUTH")
    os.environ["KAKAO_REST_API_KEY"] = "test-rest-key"
    os.environ["LOTTO_DEV_MOCK_AUTH"] = "0"
    try:
        at = AppTest.from_string(_BANNER_APP, default_timeout=TIMEOUT_SEC)
        at.query_params["page"] = "main"
        at.query_params["gid"] = "gidbanner1"
        if with_native:
            at.query_params["native"] = "1"
        at.run()
        return at
    finally:
        if before_key is None:
            os.environ.pop("KAKAO_REST_API_KEY", None)
        else:
            os.environ["KAKAO_REST_API_KEY"] = before_key
        if before_mock is None:
            os.environ.pop("LOTTO_DEV_MOCK_AUTH", None)
        else:
            os.environ["LOTTO_DEV_MOCK_AUTH"] = before_mock


def _assert_banner_branch(with_native: bool, expect_detail: str, absent_detail: str) -> None:
    import security_log

    at = _render_banner(with_native=with_native)
    assert len(at.exception) == 0, f"배너 렌더가 예외를 냈다: {at.exception}"
    keys = [b.key for b in at.button]
    if with_native:
        assert NATIVE_BTN in keys, f"native=1인데 앱 전용 버튼이 없다: {keys}"
    else:
        assert NATIVE_BTN not in keys, f"native가 없는데 앱 전용 버튼이 떴다: {keys}"

    details = _branch_details()
    assert len(details) == 1, f"계측이 세션당 1건이 아니다: {details}"
    assert expect_detail in details[0], f"첫 판정이 기록되지 않았다: {details}"
    assert absent_detail not in details[0], f"두 번째 호출이 첫 판정을 덮어썼다: {details}"

    # 계측 이벤트는 '침입 시도' 경보 집계에 들어가면 안 된다(정상 트래픽으로 배지가 켜짐).
    assert security_log.count_recent_events(hours=24) == 0, "순수 계측 이벤트가 침입 경보로 집계됐다"
    assert "kakao_login_branch" in security_log.EVENT_LABELS, "대시보드에 표시할 라벨이 없다"


def test_banner_uses_native_branch_when_native_param_present() -> None:
    """K5 — native=1이면 앱 버튼, 계측은 native로 1건."""
    _assert_banner_branch(with_native=True, expect_detail="branch=native", absent_detail="branch=web")


def test_banner_uses_web_branch_without_native_param() -> None:
    """K5 — native가 없으면 앱 버튼 없음, 계측은 web으로 1건."""
    _assert_banner_branch(with_native=False, expect_detail="branch=web", absent_detail="branch=native")


# ── 계측이 이벤트를 잃지 않는 조건(K6) ───────────────────────────────────────
class _FakeContext:
    def __init__(self, ip_address):
        self.ip_address = ip_address
        self.headers = {"User-Agent": "probe"}


def test_log_event_survives_non_string_ip() -> None:
    """K6 — ip가 문자열이 아니어도 이벤트 기록이 통째로 사라지지 않는다."""
    import security_log
    import streamlit

    cases = (
        ("1.2.3.4", "1.2.3.4"),
        (None, None),
        ("", None),
        ("   ", None),
        (12345, None),
        (b"bytes", None),
        (object(), None),
    )
    for raw_ip, expected in cases:
        with _db_isolation.isolated_db():
            with mock.patch.object(streamlit, "context", _FakeContext(raw_ip)):
                security_log.log_event("ip_probe", f"raw={type(raw_ip).__name__}")
            stored = _rows("SELECT ip_address FROM security_events WHERE event_type = 'ip_probe'")
            assert len(stored) == 1, f"ip={raw_ip!r}일 때 이벤트가 기록되지 않았다: {stored}"
            assert stored[0][0] == expected, (
                f"ip={raw_ip!r} → 기대 {expected!r}, 실제 {stored[0][0]!r}"
            )


# ── 조립 검증(실제 진입점) ──────────────────────────────────────────────
ENTRY = str(ROOT / "app.py")


def test_entry_point_renders_home_link_with_native_preserved() -> None:
    """조립 검증 — 사용자가 실제로 여는 진입점(app.py)을 그대로 렌더해서, 상세페이지
    화면에 "메인으로" 아이콘 링크가 정말 실려 나가고 그 href가 gid·native를 지키는지
    본다(단위 함수 호출이 아니라 조립된 화면의 실제 출력으로 판정).

    app.py는 페이지 예외를 잡아 "점검 중" 안내 화면으로 바꿔버리므로(사용자 화면 보호),
    예외 목록만 보면 안 되고 화면에 그려진 내용까지 확인해야 한다."""
    before_key = os.environ.get("KAKAO_REST_API_KEY")
    before_mock = os.environ.get("LOTTO_DEV_MOCK_AUTH")
    os.environ["KAKAO_REST_API_KEY"] = "test-rest-key"
    os.environ["LOTTO_DEV_MOCK_AUTH"] = "0"
    gid = "entry" + os.urandom(6).hex()
    try:
        at = AppTest.from_file(ENTRY, default_timeout=TIMEOUT_SEC)
        at.query_params["page"] = "hedge"
        at.query_params["gid"] = gid
        at.query_params["native"] = "1"
        at.run()
    finally:
        if before_key is None:
            os.environ.pop("KAKAO_REST_API_KEY", None)
        else:
            os.environ["KAKAO_REST_API_KEY"] = before_key
        if before_mock is None:
            os.environ.pop("LOTTO_DEV_MOCK_AUTH", None)
        else:
            os.environ["LOTTO_DEV_MOCK_AUTH"] = before_mock

    assert len(at.exception) == 0, f"진입점 렌더가 예외를 냈다: {at.exception}"

    body = "\n".join((m.value or "") for m in at.markdown)
    assert "점검 중" not in body, "진입점이 페이지 렌더 실패로 안내 화면을 대신 보여줬다"
    assert any(b.key.startswith("hedge_qr") for b in at.button), (
        f"안티·액땜 화면의 버튼이 없다 — 라우팅/조립이 실패했다: {[b.key for b in at.button]}"
    )

    hrefs = []
    for m in at.markdown:
        value = m.value or ""
        if 'class="brand-home-link"' not in value:
            continue
        hrefs.append(value.split('href="', 1)[1].split('"', 1)[0])
    assert hrefs, "상세페이지 화면에 메인 이동 아이콘 링크가 실려 나가지 않았다"

    for href in hrefs:
        query = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        assert query.get("page") == ["main"], f"조립된 화면의 메인 링크가 page=main이 아니다: {href!r}"
        assert query.get("gid") == [gid], f"조립된 화면에서 gid가 유실됐다: {gid!r} → {href!r}"
        assert query.get("native") == ["1"], (
            f"조립된 화면에서 native=1이 유실됐다(앱이 웹 로그인 분기로 떨어진다): {href!r}"
        )
    print(f"  (진입점 page=hedge 렌더 → 메인 아이콘 href={hrefs[0]!r})")


def _main() -> int:
    tests = [
        test_internal_links_keep_gid_and_native_for_every_input,
        test_internal_links_do_not_invent_native_for_every_input,
        test_click_patch_carries_both_params,
        test_origin_from_headers_table,
        test_redirect_uri_invariants,
        test_authorize_url_and_token_exchange_share_one_redirect_uri,
        test_banner_uses_native_branch_when_native_param_present,
        test_banner_uses_web_branch_without_native_param,
        test_log_event_survives_non_string_ip,
        test_entry_point_renders_home_link_with_native_preserved,
    ]
    failed = 0
    for t in tests:
        try:
            # 앱을 AppTest로 렌더하므로 운영 DB로 나가지 않게 격리한다(다른 테스트와 동일).
            with _db_isolation.isolated_db():
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
