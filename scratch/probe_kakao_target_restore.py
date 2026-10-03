"""조사 — ②가 원인인지 확정하는 대조 실험 (관찰자 종료 후 target 복원).

앞선 probe_kakao_login_frame.py 의 B 케이스는 무효였다: target 을 되돌린 직후
클릭했는데, ②의 MutationObserver 가 배너 랜더 후 5초 동안 target 을 계속 지우므로
제가 넣은 _blank 가 다시 제거됐을 가능성이 크다(그 경우 카카오 요청이 한 건도 안
갔던 것과 일치).

그래서 이번엔 순서를 바꾼다:
  1) 배너를 열고 앵커를 확인한다(② 적용 상태 = target 없음)
  2) **6.5초 기다린다** — ②의 관찰자는 setTimeout(..., 5000) 뒤 스스로 disconnect 한다
  3) 그 뒤 target='_blank' 를 넣고, 실제로 남아 있는지 되읽는다
  4) 클릭해서 새 탭(최상위)이 열리는지 본다

이것으로 "②가 target 을 지워서 로그인 페이지가 iframe 안에서 열리게 됐다"는 인과가
확정된다. 로그인 자격증명은 입력하지 않는다. 결제·충전·구독 버튼도 누르지 않는다.

실행: venv312\\Scripts\\python.exe -u -X utf8 scratch\\probe_kakao_target_restore.py
"""

from __future__ import annotations

import sys
import time

BARE = "https://lotto-shinryeong.streamlit.app/"
WIDTH, HEIGHT = 430, 932
MY_INFO_BTN = ".st-key-my_info_trigger_btn button"
KAKAO_A = ".st-key-auth_banner_kakao a"

READ = """() => {
  const a = document.querySelector('.st-key-auth_banner_kakao a');
  return a ? {target: a.getAttribute('target'), href: a.getAttribute('href')} : null;
}"""

SET_BLANK = """() => {
  const a = document.querySelector('.st-key-auth_banner_kakao a');
  if (!a) return null;
  a.setAttribute('target', '_blank');
  return a.getAttribute('target');
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
        got = None
        while time.time() < deadline:
            got = evaluate(frame, READ)
            if isinstance(got, dict):
                break
            time.sleep(2)
        print(f"[1] 배너 열림 — 앵커 target={got.get('target')!r}  (② 적용 상태)")

        print("[2] 6.5초 대기 — ②의 MutationObserver(setTimeout 5000)가 스스로 꺼지길 기다린다")
        time.sleep(6.5)
        still = evaluate(frame, READ)
        print(f"    대기 후 target={still.get('target')!r} (여전히 없으면 ②가 지운 상태)")

        print("[3] target='_blank' 복원")
        set_to = evaluate(frame, SET_BLANK)
        time.sleep(1.5)
        after = evaluate(frame, READ)
        print(f"    설정 직후={set_to!r}  1.5초 뒤 실제 값={after.get('target')!r}")
        if after.get("target") != "_blank":
            print("    복원이 유지되지 않았다(관찰자가 아직 살아있다) — 실험 무효")
        else:
            print("    복원 유지됨 — 이제 클릭해서 어디로 열리는지 본다")

        print("[4] 카카오 링크 클릭")
        try:
            frame.click(KAKAO_A, timeout=20000)
        except Exception as exc:  # noqa: BLE001
            print(f"    클릭 예외: {str(exc).splitlines()[0][:90]}")
        time.sleep(10)

        print(f"    새로 열린 페이지 수 = {len(new_pages)}  (전체 {len(context.pages)})")
        for pg in new_pages:
            try:
                print(f"      새 페이지 url = {pg.url.split('?')[0][:70]}")
            except Exception:  # noqa: BLE001
                print("      새 페이지 url = (?)")
            for fr in pg.frames:
                info = evaluate(fr, FRAME_INFO)
                if isinstance(info, dict) and "isTop" in info:
                    print(f"        frame host={info['host'][:36]:<36} is_top={info['isTop']}")
        print("    기존 페이지 프레임:")
        for fr in page.frames:
            info = evaluate(fr, FRAME_INFO)
            if isinstance(info, dict) and "isTop" in info:
                print(f"      frame host={info['host'][:36]:<36} is_top={info['isTop']} "
                      f"{info['href'][:46]}")

        context.close()
        browser.close()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
