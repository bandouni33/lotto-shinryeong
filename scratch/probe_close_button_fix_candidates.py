"""조사 5 — × 가림을 실제로 뒤집는 규칙을 실험으로 찾는다 (읽기 전용, 저장소 무변경).

앞선 덤프에서 확인된 사실:
  - 배너 랩(.st-key-auth_banner_wrap)은 position:sticky, z-index:100 인데도
    폰 폭에서 × 지점의 쌓임 막대기 맨 아래로 밀린다.
  - 그 지점을 덮는 것은 메인 화면의 div.st-key-manual_trigger_btn
    (position:relative, z-index:auto) — × 와 좌표가 실제로 겹친다.
  - × 버튼 자신은 transform:translateX(12px) 로 배너 랩 오른쪽 끝보다 1px 밖에 있다.
  - .st-key-auth_banner_close_x 는 CSS에 z-index:5 !important 가 있는데
    position:static 이라 그 z-index 가 아예 적용되지 않는다.

그래서 후보 CSS를 **운영 페이지 안에 하나씩 주입해** 그 지점의 최상단 요소가
× 버튼으로 바뀌는지 본다. 페이지 DOM에 <style> 하나를 넣었다 빼는 실험이며
저장소 파일은 건드리지 않는다. 마지막으로 가장 유력한 후보에 대해 실제 클릭까지
해본다(히트테스트는 통과했는데 실제 클릭이 막히는 경우가 앞서 있었으므로).

배너를 열고 × 를 누르는 것뿐이다(결제·충전·구독 버튼 없음).

실행: venv312\\Scripts\\python.exe -u -X utf8 scratch\\probe_close_button_fix_candidates.py
"""

from __future__ import annotations

import re
import sys
import time

BARE = "https://lotto-shinryeong.streamlit.app/"
WIDTH, HEIGHT = 430, 932
MY_INFO_BTN = ".st-key-my_info_trigger_btn button"
CLOSE_BTN = ".st-key-auth_banner_close_x button"

# (설명, 주입할 CSS) — 각각을 단독으로 시험한다.
CANDIDATES = [
    ("대조군(주입 없음)", ""),
    ("랩 z-index 를 더 올림 (100 -> 99999)",
     ".st-key-auth_banner_wrap{z-index:99999 !important}"),
    ("랩을 position:relative 로 (sticky 해제)",
     ".st-key-auth_banner_wrap{position:relative !important}"),
    ("close_x 를 position:relative 로 (기존 z-index:5 활성화)",
     ".st-key-auth_banner_close_x{position:relative !important}"),
    ("close_x 를 relative + z-index 99999",
     ".st-key-auth_banner_close_x{position:relative !important;z-index:99999 !important}"),
    ("manual 트리거의 position 을 static 으로 제거",
     ".st-key-manual_trigger_btn{position:static !important}"),
    ("랩에 isolation:isolate 추가",
     ".st-key-auth_banner_wrap{isolation:isolate !important;z-index:99999 !important}"),
]

HIT = """() => {
  const b = document.querySelector('.st-key-auth_banner_close_x button');
  if (!b) return {found: false};
  const r = b.getBoundingClientRect();
  const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  const stack = document.elementsFromPoint(cx, cy);
  const top = stack[0] || null;
  const desc = (el) => {
    if (!el) return null;
    const t = (el.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 12);
    const c = String(el.className || '').split(' ')
      .filter(x => x.indexOf('st-key-') === 0 || x.indexOf('st-') === 0).join('.');
    return el.tagName.toLowerCase() + (c ? '.' + c : '') + (t ? ' [' + t + ']' : '');
  };
  return {
    found: true,
    isButtonTop: top === b,
    topIsButton: desc(top),
    btnRect: {l: Math.round(r.left), r: Math.round(r.right),
              t: Math.round(r.top), b: Math.round(r.bottom)},
    wrapTop: (function () {
      const w = document.querySelector('.st-key-auth_banner_wrap');
      return w ? Math.round(w.getBoundingClientRect().top) : null;
    })(),
  };
}"""

SET_CSS = """(css) => {
  let el = document.getElementById('__probe_css');
  if (!el) {
    el = document.createElement('style');
    el.id = '__probe_css';
    document.head.appendChild(el);
  }
  el.textContent = css;
  return true;
}"""


def evaluate(frame, js, arg=None):
    try:
        return frame.evaluate(js, arg) if arg is not None else frame.evaluate(js)
    except Exception as exc:  # noqa: BLE001
        return {"__error__": f"{type(exc).__name__}: {str(exc)[:150]}"}


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
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
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
        try:
            frame.click(MY_INFO_BTN, timeout=20000)
        except Exception as exc:  # noqa: BLE001
            print(f"배너 열기 실패: {str(exc).splitlines()[0][:100]}")
            browser.close()
            return 1

        deadline = time.time() + 60
        while time.time() < deadline:
            got = evaluate(frame, HIT)
            if isinstance(got, dict) and got.get("found"):
                break
            time.sleep(2)
        print(f"뷰포트 {WIDTH}x{HEIGHT}  버튼 {got['btnRect']}  랩 top={got['wrapTop']}")

        results = []
        for label, css in CANDIDATES:
            evaluate(frame, SET_CSS, css)
            time.sleep(1.2)
            got = evaluate(frame, HIT)
            if not isinstance(got, dict) or not got.get("found"):
                print(f"  {label:<46} 측정 실패 {got}")
                results.append((label, css, None, None))
                continue
            print(f"  {label:<46} 버튼이 맨위={got['isButtonTop']}  "
                  f"현재 맨위={got['topIsButton']}  랩top={got['wrapTop']}")
            results.append((label, css, got["isButtonTop"], got["wrapTop"]))

        # 마지막으로 실제 클릭까지: 가장 유력한 후보를 넣고 진짜 클릭을 보낸다.
        winner = next((r for r in results if r[0].startswith("close_x 를 relative + z")), None)
        if winner:
            print(f"\n[실제 클릭 확인] 후보: {winner[0]}")
            evaluate(frame, SET_CSS, winner[1])
            time.sleep(1.2)
            before = evaluate(frame, HIT)
            print(f"  클릭 전 버튼이 맨위={before['isButtonTop']}")
            try:
                frame.click(CLOSE_BTN, timeout=8000)
                print("  실제 클릭 = 성공")
            except Exception as exc:  # noqa: BLE001
                print(f"  실제 클릭 = 실패({str(exc).splitlines()[0][:90]})")
            time.sleep(4)
            left = frame.evaluate(
                "() => document.querySelectorAll('.st-key-auth_banner_wrap').length")
            print(f"  클릭 후 배너 개수 = {left} (0이면 닫혔다)")

        evaluate(frame, SET_CSS, "")
        browser.close()

    print("\n=== 뒤집힌 후보 ===")
    for label, _css, ok, _wt in results:
        if ok:
            print(f"  {label}")
    print("=== 안 뒤집힌 후보 ===")
    for label, _css, ok, _wt in results:
        if ok is False:
            print(f"  {label}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
