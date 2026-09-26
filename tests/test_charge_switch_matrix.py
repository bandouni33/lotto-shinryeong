"""충전 화면 스위치 조합 전수 검증 (2026-09-27 심사 스위치 사고 대응).

주장(이번 조사에서 확인한 것)을 **모든 조합**에 대해 고정한다:
  · 앱(native=1)에서 "결제 연동 준비 중" 안내는 IAP off + 테스터충전 off 조합에서만 나온다.
  · 앱에서 IAP_CHARGE_ENABLED=True면 준비 중으로 대체되는 폴백 없이 구글플레이 버튼이 나온다.
    (= 심사 구성이 배포된 동안 앱이 어떤 화면을 보여주는지의 근거)
  · 앱에서는 토스 결제 버튼이 절대 나오지 않는다(Play 결제정책).
  · 웹(native 없음)은 PG 연동 시 토스, 미연동·Mock 미허용 시 준비 중.

조합을 손으로 몇 개만 찍어 보면 나머지 조합의 회귀를 못 잡으므로 (native × IAP × 테스터충전
× PG × Mock) 전수 표를 돌린다. DB는 isolated_db()만, 앱 코드 변경 없음.
"""

from __future__ import annotations

import sys
import uuid
from itertools import product
from pathlib import Path

from streamlit.testing.v1 import AppTest

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _path in (str(ROOT), str(TESTS_DIR), str(ROOT / "tarot")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import _db_isolation  # noqa: E402
import wallet_db as wdb  # noqa: E402
import wallet_ui  # noqa: E402

ENTRY = str(ROOT / "app.py")
TIMEOUT_SEC = 90
IAP_KEYS = ("iap_buy_points_1000", "iap_buy_points_3000")
MOCK_KEY = "test_charge_btn"
TOSS_KEY = "toss_checkout_btn"


def _safe(text: object) -> str:
    return str(text).encode("ascii", "replace").decode("ascii")


def _keys(at: AppTest) -> list[str]:
    return [b.key for b in at.button]


def _info_text(at: AppTest) -> str:
    return "\n".join(
        str(getattr(e, "value", "") or "") for e in list(at.info) + list(at.warning)
    )


def _member(handle: str, points: int = 5000) -> int:
    wdb.init_wallet_tables()
    mid, _new = wdb.get_or_create_member("kakao", handle)
    mid = int(mid)
    balance = int(wdb.get_balance(mid) or 0)
    if points > balance:
        wdb.charge_points(mid, points - balance, f"mtx:{mid}:{uuid.uuid4().hex[:8]}")
    return mid


def _render(native: bool, mid: int, gid: str) -> AppTest:
    at = AppTest.from_file(ENTRY, default_timeout=TIMEOUT_SEC)
    at.query_params["page"] = "main"
    at.query_params["gid"] = gid
    if native:
        at.query_params["native"] = "1"
    at.session_state["member_id"] = mid
    at.session_state["_guest_id"] = gid
    at.session_state["wallet_show_charge"] = True  # render_wallet_bar가 충전창을 띄운다
    at.run()
    assert not at.exception, f"충전창 렌더 예외: {at.exception}"
    return at


def _expect(at: AppTest, native: bool, iap: bool, tester: bool, pg: bool, mock: bool) -> None:
    keys = _keys(at)
    notice = wallet_ui.CHARGE_PENDING_NOTICE in _info_text(at)
    tag = f"native={native} IAP={iap} TESTER={tester} PG={pg} MOCK={mock}"

    if native and iap:
        for k in IAP_KEYS:
            assert k in keys, f"{tag}: 구글플레이 충전 버튼이 없다 {keys}"
        assert not notice, f"{tag}: IAP가 켜졌는데 '준비 중'이 함께 떴다(폴백 존재)"
        assert MOCK_KEY not in keys, f"{tag}: 앱 제출 구성인데 Mock 충전이 함께 떴다 {keys}"
    elif native and tester:
        assert MOCK_KEY in keys, f"{tag}: 앱 테스터 구성인데 Mock 충전 버튼이 없다 {keys}"
        assert not notice, f"{tag}: 테스터 충전이 켜졌는데 '준비 중'이 떴다"
        assert not any(k in keys for k in IAP_KEYS), f"{tag}: Mock과 IAP가 동시에 떴다 {keys}"
    elif native:
        assert notice, f"{tag}: 앱에서 충전 수단이 하나도 없는데 '준비 중' 안내도 없다 {keys}"
        assert not any(k in keys for k in IAP_KEYS), f"{tag}: 준비 중인데 IAP 버튼이 떴다"
        assert MOCK_KEY not in keys, f"{tag}: 준비 중인데 Mock 버튼이 떴다"
    elif pg:
        assert TOSS_KEY in keys, f"{tag}: 웹+PG인데 토스 결제 버튼이 없다 {keys}"
        assert not notice, f"{tag}: 웹+PG인데 '준비 중'이 떴다"
    elif mock:
        assert MOCK_KEY in keys, f"{tag}: 웹+Mock 허용인데 Mock 버튼이 없다 {keys}"
        assert not notice, f"{tag}: 웹+Mock 허용인데 '준비 중'이 떴다"
    else:
        assert notice, f"{tag}: 웹 미연동인데 '준비 중' 안내가 없다 {keys}"
        assert MOCK_KEY not in keys and TOSS_KEY not in keys, f"{tag}: 웹 미연동인데 결제 버튼이 떴다 {keys}"

    # 앱에서는 어떤 조합에서도 토스 버튼이 나오면 안 된다(Play 결제정책).
    if native:
        assert TOSS_KEY not in keys, f"{tag}: 앱인데 토스 결제 버튼이 그려졌다 {keys}"


def _main() -> int:
    originals = (
        wallet_ui.IAP_CHARGE_ENABLED,
        wallet_ui.TEST_CHARGE_ENABLED,
        wallet_ui.pg_configured,
        wallet_ui.mock_charge_enabled,
    )
    failures: list[str] = []
    checked = 0
    try:
        with _db_isolation.isolated_db():
            mid = _member("matrix_member")
            for native, iap, tester, pg, mock in product((True, False), repeat=5):
                wallet_ui.IAP_CHARGE_ENABLED = iap
                wallet_ui.TEST_CHARGE_ENABLED = tester
                wallet_ui.pg_configured = lambda pg=pg: pg
                wallet_ui.mock_charge_enabled = lambda mock=mock: mock
                gid = f"mtx{native}{iap}{tester}{pg}{mock}"
                try:
                    at = _render(native, mid, gid)
                    _expect(at, native, iap, tester, pg, mock)
                except AssertionError as exc:
                    failures.append(str(exc))
                checked += 1
                sys.stdout.flush()
    finally:
        (
            wallet_ui.IAP_CHARGE_ENABLED,
            wallet_ui.TEST_CHARGE_ENABLED,
            wallet_ui.pg_configured,
            wallet_ui.mock_charge_enabled,
        ) = originals

    print(f"조합 {checked}개 검사")
    for f in failures:
        print(_safe(f"FAIL {f}"))
    if failures:
        print(f"\n실패 {len(failures)}건 / {checked}조합")
        return 1
    print(f"\n{checked}/{checked} 조합 전부 성립 — 앱 '준비 중'은 IAP off + 테스터충전 off 조합 전용")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
