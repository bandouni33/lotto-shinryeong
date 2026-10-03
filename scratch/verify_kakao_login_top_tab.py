"""긴급 완화 검증 — 카카오 로그인이 최상위 새 탭에서 열리는가 (읽기 전용).

배경: _force_kakao_link_same_tab() 호출을 제거했다(2026-10-03 긴급 완화). 그 함수가
target 을 지우면 카카오 인증 페이지가 앱 iframe(sandbox, allow-top-navigation 없음)
안에서 열려 로그인이 막혔다. target="_blank" 가 남으면
allow-popups-to-escape-sandbox 덕분에 sandbox 를 벗어난 최상위 탭에서 열린다.

확인할 것:
  1) 배너의 카카오 앵커에 target 이 실제로 남아 있는가(target='_blank')
  2) 클릭했을 때 **새 탭이 열리는가** (완화 전 실측은 "새로 열린 페이지 0")
  3) 그 새 탭의 카카오 문서가 최상위인가 (window.top === window 가 True)
  4) 기존 탭은 그대로 앱 화면으로 남아 있는가(앱 프레임이 카카오로 이동하지 않았는가)

로그인 완료까지는 확인하지 않는다(자격증명 입력 안 함). 결제·충전·구독 버튼도 누르지 않는다.

실행: venv312\\Scripts\\python.exe -u -X utf8 scratch\\verify_kakao_login_top_tab.py
"""

from __future__ import annotations

import sys
import time

BARE = "https://lotto-shinryeong.streamlit.app/"
WIDTH, HEIGHT = 430, 932
MY_INFO_BTN = ".st-key-my_info_trigger_btn button"
KAKAO_A = ".st-key-auth_banner_kakao a"

ANCHOR = """() => {
  const a = document.querySelector('.st-key-auth_banner_kakao a');
  if (!a) return {found: false};
  return {
    found: true,
    target: a.getAttribute('target'),
    host: (function () { try { return new URL(a.href, location.href).host; }
                          catch (e) { return ''; } })(),
  };
}"""

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

        deadline = time.time() + 120
        while time.time() < deadline:
            if evaluate(frame, f"() => !!document.querySelector({MY_INFO_BTN!r})"):
                break
            time.sleep(2)
        frame.click(MY_INFO_BTN, timeout=20000)

        deadline = time.time() + 60
        anchor = None
        while time.time() < deadline:
            anchor = evaluate(frame, ANCHOR)
            if isinstance(anchor, dict) and anchor.get("found"):
                break
            time.sleep(2)
        if not isinstance(anchor, dict) or not anchor.get("found"):
            print(f"카카오 앵커를 못 찾았다: {anchor}")
            browser.close()
            return 1

        print(f"[1] 앵커 target={anchor['target']!r}  host={anchor['host']}")
        target_ok = anchor["target"] == "_blank"
        print(f"    target 이 남아 있는가 = {target_ok}   "
              f"(완화 전 실측은 None — ②가 지운 상태였음)")

        print("[2] 카카오 링크 클릭")
        try:
            frame.click(KAKAO_A, timeout=20000)
        except Exception as exc:  # noqa: BLE001
            print(f"    클릭 예외: {str(exc).splitlines()[0][:90]}")
        time.sleep(10)

        print(f"[3] 새로 열린 페이지 수 = {len(new_pages)}  (전체 {len(context.pages)})")
        top_ok = False
        for i, pg in enumerate(new_pages):
            try:
                print(f"    새 탭[{i}] url = {pg.url.split('?')[0][:70]}")
            except Exception:  # noqa: BLE001
                print(f"    새 탭[{i}] url = (?)")
            for fr in pg.frames:
                info = evaluate(fr, FRAME_INFO)
                if isinstance(info, dict) and "isTop" in info:
                    print(f"        frame host={info['host'][:36]:<36} "
                          f"is_top={info['isTop']}  {info['href'][:44]}")
                    if info["isTop"] and "kakao" in info["host"]:
                        top_ok = True

        print("[4] 기존 탭(앱)이 그대로 남아 있는가")
        app_still = False
        for fr in page.frames:
            info = evaluate(fr, FRAME_INFO)
            if not isinstance(info, dict) or "isTop" not in info:
                continue
            if "lotto-shinryeong" in info["host"] and not info["isTop"] and "~/+/" in info["href"]:
                app_still = True
            print(f"    frame host={info['host'][:36]:<36} is_top={info['isTop']} "
                  f"{info['href'][:46]}")
        print(f"    앱 iframe 이 그대로인가 = {app_still}")

        print("\n[판정]")
        print(f"  target 유지 = {target_ok}")
        print(f"  최상위 새 탭에서 카카오 열림 = {top_ok}")
        print(f"  기존 탭 앱 화면 유지 = {app_still}")
        if not top_ok:
            print("  -> 완화가 아직 반영되지 않았거나(재배포 대기) 다른 원인이 있다.")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
