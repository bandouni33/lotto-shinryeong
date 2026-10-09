"""심사 제출(production) 직전 **강제 검사** — "사람이 기억해서 스위치를 내리는" 단계를 코드로 막는다.

배경(2026-09-26): 네이티브 앱에서 지금 상수(IAP_CHARGE_ENABLED=False,
TEST_CHARGE_ENABLED=True)는 "Mock 결제 (테스트) — 1,000P 충전" 버튼을 실제로
노출한다. 구글 리뷰어가 충전 화면만 눌러봐도 보이는 경로라 심사 반려 사유가 된다.
그런데 이건 사람이 제출 직전에 기억해서 꺼야 하는 값이라, 잊으면 그대로 나간다 —
이 스크립트가 그걸 대신 막는다(빌드/제출 전에 돌리면 exit 1).

사용법:
  venv312\\Scripts\\python.exe scripts\\preflight_review_build.py              # 심사용 검사
  ... --cloud-secrets-confirmed   # Cloud Secrets 를 직접 확인한 뒤(R6·R7)
  venv312\\Scripts\\python.exe scripts\\preflight_review_build.py --phase tester  # 테스터용 검사

exit 0 = 통과 / exit 1 = 실패(무엇을 어떻게 바꿔야 하는지 줄 단위로 출력).
검사는 상수(빠름)뿐 아니라 **실제 화면 렌더**(tests/_iap_probe.py + 운영과 같은
환경변수 + 격리 DB)로 확인한다 — 상수를 봐도 "그 화면에 뭐가 그려지는가"는 별개다.
"""

from __future__ import annotations

import argparse
import os
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _path in (str(ROOT), str(ROOT / "tests")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from streamlit.testing.v1 import AppTest  # noqa: E402

import _db_isolation  # noqa: E402
import wallet_db as wdb  # noqa: E402

PROBE = str(ROOT / "tests" / "_iap_probe.py")
TIMEOUT_SEC = 60
TOSS_KEY = "toss_checkout_btn"

# 운영(Streamlit Cloud)과 같은 판정이 나오게 하는 최소 환경 — 이게 없으면
# _testing_period_active()가 켜져 검사 결과가 실제 배포 상태와 달라진다.
_ENV_KEYS = ("KAKAO_REST_API_KEY", "TOSS_CLIENT_KEY", "TOSS_SECRET_KEY", "LOTTO_DEV_MOCK_AUTH")

results: list[tuple[bool, str]] = []
CLOUD_SECRETS_CONFIRMED = False


def _out(text: str) -> None:
    """cmd.exe(cp949)에서 못 찍는 문자(-, 화살표 등) 때문에 스크립트가 죽는 것을 막는다.
    이 프로젝트 테스트에서 실제로 여러 번 났던 사고다."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(str(text).encode("ascii", "replace").decode("ascii"))


def check(ok: bool, label: str, fix: str = "") -> None:
    results.append((bool(ok), label if ok else f"{label} / {fix}" if fix else label))


@contextmanager
def _prod_like_env():
    before = {key: os.environ.get(key) for key in _ENV_KEYS}
    os.environ["KAKAO_REST_API_KEY"] = "preflight_kakao"
    os.environ["TOSS_CLIENT_KEY"] = "preflight_client"
    os.environ["TOSS_SECRET_KEY"] = "preflight_secret"
    os.environ["LOTTO_DEV_MOCK_AUTH"] = "0"
    try:
        yield
    finally:
        for key, value in before.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _member(handle: str) -> int:
    wdb.init_wallet_tables()
    mid, _new = wdb.get_or_create_member("kakao", handle)
    return int(mid)


def _render(mode: str, mid: int) -> AppTest:
    at = AppTest.from_file(PROBE, default_timeout=TIMEOUT_SEC)
    at.query_params["probe"] = mode
    at.query_params["native"] = "1"
    at.session_state["member_id"] = mid
    at.run()
    return at


def _labels(at: AppTest) -> list[str]:
    return [(b.label or "") for b in at.button]


def _keys(at: AppTest) -> list[str]:
    return [k for k in (b.key for b in at.button) if k]


def run_review_checks() -> None:
    import wallet_ui

    check(
        wallet_ui.IAP_CHARGE_ENABLED is True,
        "R1 네이티브 충전 = 구글플레이 결제 노출(IAP_CHARGE_ENABLED=True)",
        "wallet_ui.py에서 IAP_CHARGE_ENABLED를 True로",
    )
    check(
        wallet_ui.IAP_SUBSCRIPTION_ENABLED is True,
        "R2 네이티브 구독 = 구글플레이 정기결제 노출(IAP_SUBSCRIPTION_ENABLED=True)",
        "wallet_ui.py에서 IAP_SUBSCRIPTION_ENABLED를 True로",
    )
    check(
        wallet_ui.TEST_CHARGE_ENABLED is False,
        "R3 테스터용 Mock 결제 버튼 제거(TEST_CHARGE_ENABLED=False)",
        "wallet_ui.py에서 TEST_CHARGE_ENABLED를 False로",
    )

    with _db_isolation.isolated_db():
        mid = _member("preflight_charge")
        at = _render("charge", mid)
        check(not at.exception, "R4a 네이티브 충전창이 예외 없이 렌더된다", str(at.exception))
        labels = _labels(at)
        keys = _keys(at)
        check(
            not any("Mock 결제" in label for label in labels),
            "R4b 네이티브 충전창에 'Mock 결제' 버튼이 없다(심사 반려 사유)",
            f"지금 그려진 버튼: {labels}",
        )
        check(
            any(key.startswith("iap_buy_") for key in keys),
            "R4c 구글플레이 충전 버튼이 실제로 그려진다(리뷰어가 결제를 시험할 수 있다)",
            f"그려진 키: {keys}",
        )
        check(
            TOSS_KEY not in keys,
            "R4d 네이티브에 토스(카드) 결제 버튼이 없다(디지털 재화는 Play 결제만)",
            f"그려진 키: {keys}",
        )

        # 구독 화면 — 첫 구독 무료 프로모가 켜져 있으면 무료 안내가, 아니면 요금제 버튼이 나온다.
        at_sub = _render("sub", mid)
        check(not at_sub.exception, "R5a 네이티브 구독창이 예외 없이 렌더된다", str(at_sub.exception))
        sub_labels = _labels(at_sub)
        sub_keys = _keys(at_sub)
        check(
            not any("Mock" in label for label in sub_labels),
            "R5b 구독창에 테스트/Mock 결제가 없다",
            f"그려진 버튼: {sub_labels}",
        )
        check(
            TOSS_KEY not in sub_keys,
            "R5c 구독창에 토스 결제가 없다",
            f"그려진 키: {sub_keys}",
        )
        if any(key.startswith("iap_sub_") for key in sub_keys):
            check(True, "R5d 구글플레이 정기결제 요금제 버튼이 그려진다")
        elif "iap_free_sub_confirm" in sub_keys:
            check(
                True,
                "R5d 첫 구독 무료 프로모 경로다(결제 없음 - 요금제 버튼은 프로모 소진 후 노출)",
            )
        else:
            check(
                False,
                "R5d 구독창에 구글플레이 요금제 버튼도 무료 프로모 버튼도 없다(리뷰어가 구독을 시험할 수 없다)",
                f"그려진 키: {sub_keys}",
            )

    # R6·R7: 운영 서버(Streamlit Cloud) 비밀값은 이 PC에서 볼 수 없다.
    # 2026-10-09: 예전 R6 은 위 _prod_like_env 가 직접 넣은 값을 다시 읽어 항상 통과했다(자기충족 검사).
    # 이제는 사람이 Cloud Secrets 화면에서 직접 확인했다는 표시(--cloud-secrets-confirmed)를 요구한다.
    check(
        CLOUD_SECRETS_CONFIRMED,
        "R6 Cloud Secrets 에 KAKAO_REST_API_KEY 가 있다(무료 우회 차단 조건) - 사람이 확인함",
        "Streamlit Cloud > Settings > Secrets 에서 확인 후 --cloud-secrets-confirmed 로 다시 실행",
    )
    check(
        CLOUD_SECRETS_CONFIRMED,
        "R7 Cloud Secrets 에 GOOGLE_PLAY_SERVICE_ACCOUNT_JSON 이 있다(없으면 모든 구글 결제가 '확인 실패') - 사람이 확인함",
        "Streamlit Cloud > Settings > Secrets 에서 확인 후 --cloud-secrets-confirmed 로 다시 실행",
    )

    # R8: 결제 "이후" 수명주기(갱신·해지·보류·환불·승인 재시도·가격 위조) — 2026-10-09 점검에서
    # 첫 결제만 보던 검사가 놓친 구멍들이다. 테스트가 하나라도 실패하면 제출하지 않는다.
    import subprocess

    lifecycle = subprocess.run(
        [sys.executable, "-X", "utf8", str(ROOT / "tests" / "test_gplay_lifecycle.py")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    tail = (lifecycle.stdout or "").strip().splitlines()[-1:] or ["(출력 없음)"]
    check(
        lifecycle.returncode == 0,
        f"R8 구글 결제 수명주기 테스트 통과(tests/test_gplay_lifecycle.py: {tail[0]})",
        "tests/test_gplay_lifecycle.py 를 직접 실행해 FAIL 항목을 고칠 것",
    )


def run_tester_checks() -> None:
    import wallet_ui

    check(
        wallet_ui.IAP_CHARGE_ENABLED is False,
        "T1 IAP 수신부 없는 빌드에 죽은 구글플레이 버튼을 내지 않는다(IAP_CHARGE_ENABLED=False)",
        "테스터용이면 IAP_CHARGE_ENABLED를 False로",
    )
    check(
        wallet_ui.TEST_CHARGE_ENABLED is True,
        "T2 테스터가 앱에서 충전할 수 있다(TEST_CHARGE_ENABLED=True)",
        "테스터용이면 TEST_CHARGE_ENABLED를 True로",
    )

    with _db_isolation.isolated_db():
        mid = _member("preflight_tester")
        at = _render("charge", mid)
        check(not at.exception, "T3a 네이티브 충전창이 예외 없이 렌더된다", str(at.exception))
        labels = _labels(at)
        keys = _keys(at)
        check(
            any("Mock 결제" in label for label in labels),
            "T3b 테스터용 Mock 결제 버튼이 실제로 그려진다",
            f"그려진 버튼: {labels}",
        )
        check(
            not any(key.startswith("iap_buy_") for key in keys),
            "T3c 죽은 구글플레이 버튼이 함께 그려지지 않는다",
            f"그려진 키: {keys}",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="심사/테스터 빌드 전 스위치 검사")
    parser.add_argument("--phase", choices=("review", "tester"), default="review")
    parser.add_argument(
        "--cloud-secrets-confirmed",
        action="store_true",
        help="Streamlit Cloud Secrets 에 KAKAO_REST_API_KEY·GOOGLE_PLAY_SERVICE_ACCOUNT_JSON 이 있음을 직접 확인했다",
    )
    args = parser.parse_args()
    global CLOUD_SECRETS_CONFIRMED
    CLOUD_SECRETS_CONFIRMED = bool(args.cloud_secrets_confirmed)

    phase = "심사 제출용" if args.phase == "review" else "테스터용"
    _out(f"[preflight] {phase} 빌드 설정 검사 (phase={args.phase})")
    with _prod_like_env():
        if args.phase == "review":
            run_review_checks()
        else:
            run_tester_checks()

    failed = 0
    for ok, message in results:
        if ok:
            _out(f"  OK   {message}")
        else:
            failed += 1
            _out(f"  FAIL {message}")
    _out(f"\n{len(results) - failed}/{len(results)} 통과")
    if failed:
        _out("이 상태로 빌드/제출하면 안 된다 - 위 FAIL 항목을 먼저 고칠 것.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
