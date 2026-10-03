"""앱이 플랫폼을 서버에 알리는 계약 검증 — 2026-10-03 (iOS 게시 준비).

무엇을 잠그는가: 앱(streamlit-webview.tsx)이 native=1 과 **함께** native_platform 을
실어 보내고, 그 값이 ios/android 로 내려가야 서버(wallet_ui)가 "iOS 에는 결제 버튼을
띄우지 않는다"를 판단할 수 있다. 이 계약이 깨지면 서버는 플랫폼을 모른 채 안드로이드
기본 동작을 하게 되고, iOS 심사에서 결제 버튼이 그대로 노출된다.

  P1 buildUri 가 native_platform 을 Platform.OS 로 싣는다(상수 문자열이 아니라)
  P2 reloadWith 도 항상 다시 싣는다(로그인·결제 후 복귀 주소에서 플랫폼이 사라지지 않게)
  P3 기존 파라미터 계약이 그대로다 — native=1·page·gid 는 app 쪽에서 안 건드렸다
  P4 서버가 같은 이름을 읽는다(교차 계약 — 한쪽만 바꾸면 조용히 어긋난다)

런타임 없이 소스 계약으로 검사한다(tests/test_iap_dispatch_lock_timeout.py 와 같은 방식).
pytest 없이 돌도록 표준 assert + __main__ 러너를 둔다(AGENTS §3).
실행: venv312\\Scripts\\python.exe tests\\test_native_platform_param.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TSX_PATH = ROOT / "LottoShinryeong" / "components" / "streamlit-webview.tsx"
CONST_PATH = ROOT / "LottoShinryeong" / "constants" / "streamlit.ts"
WALLET = (ROOT / "wallet_ui.py").read_text(encoding="utf-8")

TSX = TSX_PATH.read_text(encoding="utf-8")
CONST = CONST_PATH.read_text(encoding="utf-8")

PARAM = "native_platform"


def _block(text: str, start_marker: str, end_marker: str) -> str:
    """start_marker 부터 end_marker 까지(둘 다 포함) — 선언 하나만 떼어 본다."""
    assert start_marker in text, f"구역 시작을 못 찾았다: {start_marker!r}"
    tail = text.split(start_marker, 1)[1]
    assert end_marker in tail, f"구역 끝을 못 찾았다: {end_marker!r}"
    return tail.split(end_marker, 1)[0]


BUILD_URI = _block(TSX, "const buildUri = useCallback(", "[page, guestId, extraParams]")
RELOAD_WITH = _block(TSX, "const reloadWith = useCallback(", "[buildUri]\n  );")


# ── P1 ───────────────────────────────────────────────────────
def test_P1_buildUri_sends_the_platform():
    assert f"{PARAM}: Platform.OS" in BUILD_URI, (
        f"buildUri 가 {PARAM} 을 Platform.OS 로 싣지 않는다 — 서버가 플랫폼을 모른다"
    )
    # 값이 상수 문자열이면 두 OS 모두 실린다는 보장이 없다(하나로 고정된다).
    assert not re.search(rf"{PARAM}\s*:\s*['\"]", BUILD_URI), (
        f"{PARAM} 값이 문자열 상수다 — Platform.OS 를 써야 ios/android 가 그대로 내려간다"
    )
    # getStreamlitPageUrl 에 넘기는 객체 '안'에 있어야 실제로 URL 에 붙는다.
    call = BUILD_URI.split("getStreamlitPageUrl(", 1)
    assert len(call) == 2, "buildUri 안에 getStreamlitPageUrl 호출이 없다"
    brace = call[1].index("{")
    assert call[1].index(f"{PARAM}: Platform.OS") > brace, (
        f"{PARAM} 이 인자 객체 밖에 있다 — URL 에 안 실린다"
    )


# ── P2 ───────────────────────────────────────────────────────
def test_P2_reloadWith_keeps_the_platform():
    assert f"{PARAM}: Platform.OS" in RELOAD_WITH, (
        f"reloadWith 가 {PARAM} 을 다시 싣지 않는다 — 로그인·결제 후 복귀 주소에서 "
        "플랫폼 정보가 사라져 그 화면에서만 iOS 분기가 풀린다"
    )
    # withParams 가 Map 기반이라 중복 파라미터가 안 생기는 것이 이 방식의 전제다.
    assert "new Map<string, string>()" in TSX, (
        "withParams 가 Map 기반이 아니다 — 같은 키를 두 번 넘기면 중복 파라미터가 생긴다"
    )
    assert "pairs.set(key, encodeURIComponent(value))" in TSX, (
        "withParams 가 기존 키를 덮어쓰지 않는다 — 중복 파라미터 위험"
    )


# ── P3 ───────────────────────────────────────────────────────
def test_P3_existing_parameters_are_untouched():
    # native=1(앱 여부)은 constants/streamlit.ts 의 정본 그대로여야 한다.
    assert "url += '&native=1';" in CONST, (
        "native=1 을 붙이는 정본이 바뀌었다 — 서버의 in_native_app() 이 무너진다"
    )
    assert f"&{PARAM}" not in CONST, (
        f"constants/streamlit.ts 에 {PARAM} 이 들어갔다 — 이번 작업 대상 파일이 아니고, "
        "붙이는 자리를 두 곳으로 늘리면 한쪽만 고쳐져 조용히 어긋난다"
    )
    assert "page=${encodeURIComponent(safePage)}" in CONST
    assert "&gid=${encodeURIComponent(guestId)}" in CONST
    # buildUri 의 기존 스프레드가 사라지지 않았는지(가격·extra 파라미터 유실 방지)
    assert "...(extraParams || {})" in BUILD_URI
    assert "...priceParamsRef.current" in BUILD_URI
    assert "...(overrides || {})" in BUILD_URI


# ── P4 ───────────────────────────────────────────────────────
# P4(서버가 같은 이름을 읽는지)는 ② 에서 서버 쪽 reader 를 만든 뒤 추가한다 —
# 그 전에 넣으면 이 파일이 깨진 채로 커밋된다.


def _main() -> int:
    import os

    tests = [
        test_P1_buildUri_sends_the_platform,
        test_P2_reloadWith_keeps_the_platform,
        test_P3_existing_parameters_are_untouched,
    ]
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
