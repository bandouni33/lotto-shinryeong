"""대조 실험 — 이 헤드리스 환경이 팝업(새 탭)을 볼 수 있기는 한가.

왜 필요한가: 긴급 완화 후 카카오 링크 클릭에서 "새로 열린 페이지 0"이 나왔다.
그 숫자가 "팝업이 정말 안 열렸다"인지 "이 도구가 팝업을 못 본다"인지 구분하지
않으면 아무 결론도 못 낸다. 그래서 확실히 팝업이 열리는 조건을 만들어 본다:

  대조 1) 앱 iframe 안에서 window.open('about:blank')
  대조 2) 최상위 문서에서 window.open('about:blank')
  대조 3) 앱 iframe 안에 target="_blank" 앵커를 심고 클릭

각각에 대해 context.on("page") 와 page.on("popup") 둘 다로 관찰한다.

읽기 전용이다(about:blank 만 연다). 결제·충전·구독 버튼은 누르지 않는다.

실행: venv312\\Scripts\\python.exe -u -X utf8 scratch\\probe_popup_observable.py
"""

from __future__ import annotations

import sys
import time

BARE = "https://lotto-shinryeong.streamlit.app/"


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
        context = browser.new_context(viewport={"width": 430, "height": 932})
        page = context.new_page()
        via_context: list[str] = []
        via_popup: list[str] = []
        context.on("page", lambda pg: via_context.append(pg.url[:40]))
        page.on("popup", lambda pg: via_popup.append(pg.url[:40]))

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

        def report(label: str) -> None:
            print(f"\n[{label}]")
            print(f"  context 'page' 이벤트로 본 새 페이지 = {len(via_context)} {via_context}")
            print(f"  page 'popup' 이벤트로 본 팝업    = {len(via_popup)} {via_popup}")
            print(f"  context.pages 총 {len(context.pages)}개")
            opened = len(via_context) + len(via_popup)
            print(f"  => 이 도구가 팝업을 보는가 = {opened > 0}")

        # 대조 1 — 앱 iframe 안에서 window.open
        print("\n[대조 1] 앱 iframe 안에서 window.open('about:blank')")
        print("  반환값 =", evaluate(
            frame, "() => { try { const w = window.open('about:blank');"
                   " return w ? '열림' : 'null(차단됨)'; } catch (e) { return '예외:' + e.name; } }"))
        time.sleep(3)
        report("대조 1 결과")
        before = len(via_context) + len(via_popup)

        # 대조 2 — 최상위 문서에서 window.open
        print("\n[대조 2] 최상위 문서에서 window.open('about:blank')")
        print("  반환값 =", evaluate(
            page.main_frame, "() => { try { const w = window.open('about:blank');"
                             " return w ? '열림' : 'null(차단됨)'; } catch (e) { return '예외:' + e.name; } }"))
        time.sleep(3)
        report("대조 2 결과")
        after2 = len(via_context) + len(via_popup)
        print(f"  대조 1 이후 증가분 = {after2 - before}")

        # 대조 3 — 앱 iframe 에 target=_blank 앵커를 심고 클릭
        print("\n[대조 3] 앱 iframe 에 target='_blank' 앵커를 심고 클릭")
        evaluate(frame, """() => {
          const a = document.createElement('a');
          a.id = '__probe_anchor';
          a.href = 'about:blank';
          a.target = '_blank';
          a.textContent = 'probe';
          a.style.cssText = 'position:fixed;left:6px;bottom:6px;z-index:99999';
          document.body.appendChild(a);
          return a.getAttribute('target');
        }""")
        time.sleep(1)
        try:
            frame.click("#__probe_anchor", timeout=8000)
            print("  클릭 성공")
        except Exception as exc:  # noqa: BLE001
            print(f"  클릭 예외: {str(exc).splitlines()[0][:80]}")
        time.sleep(4)
        report("대조 3 결과")
        after3 = len(via_context) + len(via_popup)
        print(f"  대조 3 증가분 = {after3 - after2}")

        browser.close()

    print("\n[결론 재료] 위 세 대조 중 하나라도 '이 도구가 팝업을 보는가 = True' 면 "
          "이 도구는 팝업을 볼 수 있다.")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
