"""긴급 조사 — 카카오 로그인 페이지가 최상위 창이 아니라 중첩 iframe 안에서 열리는가.

신고: ②(카카오 링크 target 제거) 배포 후, 카카오 로그인에서 비밀번호 입력 후
"로그인" 버튼이 반응하지 않는다(제자리).

가설: ②는 .st-key-auth_banner_kakao a[target] 의 target 을 지운다. target 이 없으면
그 앵커가 있는 **문서 안에서** 이동한다. 실사용자 주소에서는 앱이 Streamlit Cloud
껍데기 문서 안의 iframe(~/+/)에서 돌므로, 카카오 인증 페이지가 그 iframe **안에서**
열린다 — 최상위가 아니다. (개발 중처럼 앱이 최상위일 때는 차이가 안 보인다.)

② 이전에는 target="_blank" 가 그대로 남아 있어 새 탭(최상위)에서 열렸다.
그래서 이 스크립트는 두 경우를 **같은 세션에서 대조**한다:

  A) 현재(② 적용: target 없음)  -> 클릭 후 카카오 페이지가 어디에 열리는가
  B) ② 이전 복원(target=_blank) -> 클릭 후 새 탭(최상위)에서 열리는가

각 경우에 대해: 새 탭이 열렸는지 / 앱 iframe 이 그 URL 로 이동했는지 /
그 문서에서 window.top === window 인지 / 카카오 응답 헤더(X-Frame-Options,
Content-Security-Policy)가 무엇인지 본다.

로그인 자격증명은 입력하지 않는다. 링크를 눌러 페이지가 어디에 뜨는지만 본다.
결제·충전·구독 버튼은 누르지 않는다.

실행: venv312\\Scripts\\python.exe -u -X utf8 scratch\\probe_kakao_login_frame.py
"""

from __future__ import annotations

import re
import sys
import time

BARE = "https://lotto-shinryeong.streamlit.app/"
WIDTH, HEIGHT = 430, 932
MY_INFO_BTN = ".st-key-my_info_trigger_btn button"
KAKAO_A = ".st-key-auth_banner_kakao a"

ANCHOR = """() => {
  const a = document.querySelector('.st-key-auth_banner_kakao a');
  if (!a) return {found: false};
  let host = '', path = '';
  try { const u = new URL(a.href, location.href); host = u.host; path = u.pathname; } catch (e) {}
  return {
    found: true,
    target: a.getAttribute('target'),
    rel: a.getAttribute('rel'),
    tag: a.tagName.toLowerCase(),
    host: host,
    path: path,
    params: (function () {
      try { return Array.from(new URL(a.href, location.href).searchParams.keys()); }
      catch (e) { return []; }
    })(),
    thisDocIsTop: window.top === window,
  };
}"""

FRAME_INFO = """() => ({
  isTop: window.top === window,
  href: location.href.split('?')[0],
  host: location.host,
})"""


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


def run_case(browser, label: str, restore_blank: bool) -> None:
    print(f"\n{'=' * 72}\n=== {label}\n{'=' * 72}")
    context = browser.new_context(viewport={"width": WIDTH, "height": HEIGHT})
    page = context.new_page()
    opened: list[str] = []
    context.on("page", lambda p: opened.append("(새 페이지)"))
    kakao_headers: dict[str, dict] = {}
    console: list[str] = []

    def on_response(resp):
        if "kakao" not in resp.url:
            return
        h = resp.headers
        kakao_headers[resp.url.split("?")[0][:70]] = {
            "status": resp.status,
            "x_frame_options": h.get("x-frame-options"),
            "csp": (h.get("content-security-policy") or "")[:110],
            "location": (h.get("location") or "")[:60],
        }

    page.on("response", on_response)
    page.on("console", lambda m: console.append(f"{m.type}: {m.text[:120]}"))
    page.on("pageerror", lambda e: console.append(f"pageerror: {str(e)[:120]}"))

    try:
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
            print("  실패: 앱 문서를 못 찾았다")
            return

        deadline = time.time() + 120
        while time.time() < deadline:
            if evaluate(frame, f"() => !!document.querySelector({MY_INFO_BTN!r})"):
                break
            time.sleep(2)
        try:
            frame.click(MY_INFO_BTN, timeout=20000)
        except Exception as exc:  # noqa: BLE001
            print(f"  배너 열기 실패: {str(exc).splitlines()[0][:90]}")
            return

        deadline = time.time() + 60
        info = None
        while time.time() < deadline:
            info = evaluate(frame, ANCHOR)
            if isinstance(info, dict) and info.get("found"):
                break
            time.sleep(2)
        if not isinstance(info, dict) or not info.get("found"):
            print(f"  카카오 앵커를 못 찾았다: {info}")
            return
        print(f"  앵커: tag={info['tag']} target={info['target']!r} rel={info['rel']!r}")
        print(f"        host={info['host']} path={info['path']}")
        print(f"        쿼리 파라미터 이름={info['params']}")
        print(f"        이 문서가 최상위인가(window.top===window) = {info['thisDocIsTop']}")

        if restore_blank:
            frame.evaluate(
                "() => { const a = document.querySelector('.st-key-auth_banner_kakao a');"
                " if (a) a.setAttribute('target', '_blank');"
                " return a ? a.getAttribute('target') : null; }")
            time.sleep(0.5)
            back = evaluate(frame, ANCHOR)
            print(f"  target 을 '_blank' 로 복원 = {back.get('target')!r}")

        print("  [카카오 링크를 누른다]")
        try:
            frame.click(KAKAO_A, timeout=20000)
        except Exception as exc:  # noqa: BLE001
            print(f"    클릭 실패: {str(exc).splitlines()[0][:90]}")
        time.sleep(9)

        print("  --- 클릭 후 ---")
        print(f"    새로 열린 페이지 수 = {len(opened)}  (전체 페이지 {len(context.pages)})")
        for i, pg in enumerate(context.pages):
            try:
                url = pg.url.split("?")[0][:70]
            except Exception:  # noqa: BLE001
                url = "(?)"
            print(f"    page[{i}] url={url}")
            for fr in pg.frames:
                got = evaluate(fr, FRAME_INFO)
                if isinstance(got, dict) and "isTop" in got:
                    print(f"        frame host={got['host'][:40]:<40} "
                          f"is_top={got['isTop']}  {got['href'][:50]}")

        print("  --- 카카오 응답 헤더 ---")
        if not kakao_headers:
            print("    (카카오 요청이 없었다)")
        for url, h in list(kakao_headers.items())[:6]:
            print(f"    {url}")
            print(f"      status={h['status']} x-frame-options={h['x_frame_options']!r}")
            print(f"      csp={h['csp']!r}")
            if h["location"]:
                print(f"      location={h['location']!r}")

        if console:
            print("  --- 콘솔 ---")
            for line in console[-6:]:
                print(f"    {line}")
    finally:
        context.close()


def main() -> int:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        run_case(browser, "A) 현재 상태 (② 적용: target 제거됨)", restore_blank=False)
        run_case(browser, "B) ② 이전 복원 (target='_blank' 로 되돌림)", restore_blank=True)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
