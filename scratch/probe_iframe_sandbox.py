"""조사 — 앱 iframe 이 최상위 이동(top-navigation)을 허용하는가 (읽기 전용).

배경: 카카오 로그인 페이지가 앱 iframe 안에서 열리는 것이 확인됐다(그래서 최상위가
아니다). 처방으로 "target 제거 대신 window.top.location.href 로 최상위까지 빠져나가기"가
거론되는데, 그게 가능하려면 앱 문서가 sandbox 없이(= allow-top-navigation 없이도)
돌고 있어야 한다. user_scope.py 주석에는 components.html iframe sandbox엔
allow-top-navigation이 없어 top 이동이 막힌다고 적혀 있다 — 그게 앱 프레임에도
해당하는지, 아니면 components.html 안에만 해당하는지 구분해야 처방을 정할 수 있다.

그래서 최상위 문서의 iframe 들을 src/sandbox/allow 와 함께 나열한다.

실행: venv312\\Scripts\\python.exe -u -X utf8 scratch\\probe_iframe_sandbox.py
"""

from __future__ import annotations

import sys
import time

BARE = "https://lotto-shinryeong.streamlit.app/"

IFRAMES = """() => Array.from(document.querySelectorAll('iframe')).map(function (f) {
  const r = f.getBoundingClientRect();
  return {
    src: (f.getAttribute('src') || '').split('?')[0].slice(0, 60),
    sid: (f.getAttribute('srcdoc') || '').length,
    sandbox: f.getAttribute('sandbox'),
    allow: f.getAttribute('allow'),
    title: f.getAttribute('title'),
    w: Math.round(r.width),
    h: Math.round(r.height),
  };
})"""


def evaluate(frame, js):
    try:
        return frame.evaluate(js)
    except Exception as exc:  # noqa: BLE001
        return [{"__error__": f"{type(exc).__name__}: {str(exc)[:120]}"}]


def main() -> int:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 430, "height": 932})
        page.goto(BARE, timeout=120000, wait_until="domcontentloaded")
        time.sleep(12)
        print(f"[최상위 문서] {BARE}")
        frames = evaluate(page.main_frame, IFRAMES)
        for f in frames:
            if "__error__" in f:
                print(f"  평가 불가: {f['__error__']}")
                continue
            print(f"  src={f['src'] or '(없음)'!r:<62} srcdoc={f['sid']}자 "
                  f"크기={f['w']}x{f['h']}")
            print(f"      sandbox={f['sandbox']!r}")
            print(f"      allow={f['allow']!r} title={f['title']!r}")

        # 앱 프레임 안에서 components.html iframe 들도 같은 방식으로 본다.
        app = None
        for fr in page.frames:
            try:
                n = fr.evaluate(
                    "() => document.querySelectorAll('[class*=\"st-key-\"]').length")
            except Exception:  # noqa: BLE001
                continue
            if isinstance(n, int) and n > 0:
                app = fr
                break
        if app is not None:
            print(f"\n[앱 문서] {app.url[:70]}")
            for f in evaluate(app, IFRAMES):
                if "__error__" in f:
                    print(f"  평가 불가: {f['__error__']}")
                    continue
                print(f"  src={f['src'] or '(srcdoc)'!r:<24} srcdoc={f['sid']}자")
                print(f"      sandbox={f['sandbox']!r}")
        else:
            print("\n앱 문서를 못 찾았다")

        browser.close()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
