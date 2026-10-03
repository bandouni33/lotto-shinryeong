"""두 UI 버그의 공통 원인 후보를 실측으로 확정한다 (일회성 진단).

가설: wallet_ui의 두 JS 수정 함수가 `window.top.document`를 조회하는데,
실사용자가 여는 주소(https://lotto-shinryeong.streamlit.app/)에서는 앱이
Streamlit Cloud 껍데기 문서 안의 iframe(/~/+/)에서 돈다. 그러면 이 함수들이
지우려는 앱 DOM이 `window.top.document`에는 아예 없어서 조용히 무동작이 된다
(둘 다 try/catch로 감싸여 있어 오류도 안 난다).

  - _cleanup_stale_auth_banner_dom()  → .st-key-auth_banner_wrap 제거
  - _force_kakao_link_same_tab()      → .st-key-auth_banner_kakao a[target] 제거

확인할 것:
  1) 최상위 문서에 앱 DOM(.st-key-*, stAppViewContainer)이 있는가
  2) 앱 프레임 안에 그것이 있는가
  3) 앱 프레임에서 window.top === window 인가(= 중첩돼 있는가)
  4) /~/+/ 로 직접 들어가면 달라지는가(= 개발 중에는 정상으로 보이는 이유)

실행: venv312\\Scripts\\python.exe scratch\\probe_iframe_top_document.py
"""

from __future__ import annotations

import sys
import time

BARE = "https://lotto-shinryeong.streamlit.app/"
APP = BARE + "~/+/"

PROBE = """
() => ({
  is_top: window.top === window,
  parent_is_self: window.parent === window,
  st_keys: document.querySelectorAll('[class*="st-key-"]').length,
  banner_wrap: document.querySelectorAll('.st-key-auth_banner_wrap').length,
  app_view: !!document.querySelector('[data-testid="stAppViewContainer"]'),
  body_len: document.body ? document.body.innerText.length : -1,
})
"""


def show(label: str, info: dict) -> None:
    print(f"  {label:<26} is_top={info['is_top']} parent_self={info['parent_is_self']} "
          f"st_keys={info['st_keys']:<4} banner_wrap={info['banner_wrap']} "
          f"app_view={info['app_view']} len={info['body_len']}")


def main() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # (A) 실사용자가 여는 주소 그대로
        page = browser.new_page()
        page.goto(BARE, timeout=90000, wait_until="domcontentloaded")
        time.sleep(10)
        print(f"\n[사용자 주소] {BARE}")
        print(f"  프레임 {len(page.frames)}개")
        print("  [최상위 문서]")
        show("top(document)", page.evaluate(PROBE))
        for frame in page.frames[1:]:
            try:
                info = frame.evaluate(PROBE)
            except Exception as exc:  # noqa: BLE001
                print(f"  [{frame.url[:60]}] 평가 불가: {type(exc).__name__}")
                continue
            print(f"  [frame] {frame.url[:60]}")
            show("frame(document)", info)
        page.close()

        # (B) 앱 프레임으로 직접 진입 (개발·직접 테스트에서 보이는 상태)
        page = browser.new_page()
        page.goto(APP, timeout=90000, wait_until="domcontentloaded")
        time.sleep(10)
        print(f"\n[직접 진입] {APP}")
        print(f"  프레임 {len(page.frames)}개")
        show("top(document)", page.evaluate(PROBE))
        page.close()

        browser.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
    sys.stdout.flush()
