"""검증 마지막 조각 — 앱에서 연 팝업이 sandbox를 벗어나 최상위에서 카카오를 여는가.

앞선 대조 실험 결과 이 헤드리스 도구는
  · window.open 으로 연 팝업은 본다 (대조 1: 반환 '열림', 새 페이지 1개 관측)
  · <a target="_blank"> 클릭으로 열린 팝업은 못 본다 (대조 3: 증가분 0)
이라, 배너의 카카오 링크를 **클릭**해서 나온 "새 탭 0"은 판정 불가였다.

그래서 같은 href 를 window.open 으로 열어, 되돌린 처방이 기대는 메커니즘
(sandbox 를 벗어난 최상위 새 탭에서 카카오 페이지가 뜬다)이 실제로 성립하는지 본다.
앵커의 target='_blank' 는 바로 이 경로와 같은 결과를 내는 것이 기대값이다.

동작: 배너를 열고 앵커의 href 를 읽어, 앱 iframe 안에서 window.open(href, '_blank')을
부른 뒤 새 페이지의 프레임 구조에서 카카오 문서가 is_top=True 인지 확인한다.
자격증명은 입력하지 않는다. 결제·충전·구독 버튼은 누르지 않는다.

실행: venv312\\Scripts\\python.exe -u -X utf8 scratch\\verify_kakao_popup_toplevel.py
"""

from __future__ import annotations

import sys
import time

BARE = "https://lotto-shinryeong.streamlit.app/"
WIDTH, HEIGHT = 430, 932
MY_INFO_BTN = ".st-key-my_info_trigger_btn button"

FRAME_INFO = """() => ({isTop: window.top === window, host: location.host,
                        href: location.href.split('?')[0]})"""


def evaluate(frame, js):
    try:
        return frame.evaluate(js)
    except Exception as exc:  # noqa: BLE001
        return {"__error__": f"{type(exc).__name__}: {str(exc)[:140]}"}


def app_frame(page):
    best, best_n = None, 0
    for frame in page.frames:
        try:
            n = frame.evaluate(
                "() => document.querySelectorAll('[class*=\"st-key-\"]').length")
        except Exception:  # noqa: BLE001
            continue
        if isinstance(n, int) and n > best_n:
            best, best_n = frame, n
    return best


def main() -> int:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": WIDTH, "height": HEIGHT})
        page = context.new_page()
        new_pages: list = []
        context.on("page", lambda pg: new_pages.append(pg))

        page.goto(BARE, timeout=120000, wait_until="domcontentloaded")
        time.sleep(3)
        frame = None
        deadline = time.time() + 150
        while time.time() < deadline:
            frame = app_frame(page)
            if frame is not None:
                break
            time.sleep(3)
        if frame is None:
            print("실패: 앱 문서를 못 찾았다")
            browser.close()
            return 1
        print(f"앱 문서 = {frame.url[:60]}")

        deadline = time.time() + 120
        while time.time() < deadline:
            if evaluate(frame, f"() => !!document.querySelector({MY_INFO_BTN!r})"):
                break
            time.sleep(2)
        frame.click(MY_INFO_BTN, timeout=20000)

        deadline = time.time() + 60
        info = None
        while time.time() < deadline:
            info = evaluate(frame, """() => {
              const a = document.querySelector('.st-key-auth_banner_kakao a');
              if (!a) return {found: false};
              return {found: true, target: a.getAttribute('target'),
                      href: a.getAttribute('href')};
            }""")
            if isinstance(info, dict) and info.get("found"):
                break
            time.sleep(2)
        if not isinstance(info, dict) or not info.get("found"):
            print(f"앵커를 못 찾았다: {info}")
            browser.close()
            return 1
        print(f"[1] 앵커 target={info['target']!r} (되돌림 후이므로 '_blank' 여야 함)")

        print("[2] 같은 href 를 앱 iframe 안에서 window.open(href, '_blank') 로 연다")
        returned = evaluate(
            frame,
            "() => { const a = document.querySelector('.st-key-auth_banner_kakao a');"
            " if (!a) return '앵커 없음';"
            " try { const w = window.open(a.href, '_blank');"
            "       return w ? '열림' : 'null(차단됨)'; }"
            " catch (e) { return '예외:' + e.name; } }")
        print(f"    window.open 반환값 = {returned}")
        time.sleep(12)

        print(f"[3] 새 페이지 수 = {len(new_pages)}  (전체 {len(context.pages)})")
        top_ok = False
        for i, pg in enumerate(new_pages):
            try:
                print(f"    새 탭[{i}] url = {pg.url.split('?')[0][:70]}")
            except Exception:  # noqa: BLE001
                print(f"    새 탭[{i}] url = (?)")
            for fr in pg.frames:
                got = evaluate(fr, FRAME_INFO)
                if isinstance(got, dict) and "isTop" in got:
                    print(f"        frame host={got['host'][:34]:<34} "
                          f"is_top={got['isTop']}  {got['href'][:42]}")
                    if got["isTop"] and "kakao" in got["host"]:
                        top_ok = True

        print("\n[판정]")
        print(f"  새 탭이 열렸다 = {bool(new_pages)}")
        print(f"  카카오가 최상위(is_top=True)에서 열렸다 = {top_ok}")
        if top_ok:
            print("  => 되돌린 처방이 기대는 메커니즘이 성립한다: 앱에서 연 팝업이")
            print("     sandbox 를 벗어나 최상위에서 카카오 로그인 페이지를 연다.")
        else:
            print("  => 메커니즘을 확인하지 못했다.")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
