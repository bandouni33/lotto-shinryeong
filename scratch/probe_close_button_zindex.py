"""조사 7 — 배너 z-index 를 999(사용설명서 버튼) 위로 올리면 실제로 풀리는가.

앞선 조사에서 원인이 확인됐다:
  div.st-key-manual_trigger_wrap  position:fixed  z-index:999   (사용설명서 버튼)
  div.st-key-auth_banner_wrap     position:sticky z-index:100   (인증 배너)
같은 쌓임 맥락이라 999가 100을 이기고, 폰 폭에서 그 둘이 같은 좌표에 겹쳐
× 버튼이 사용설명서 버튼 아래로 들어간다. 1280px에서는 두 요소가 겹치지 않아
문제가 안 보인다.

스타일시트 주입은 앱 규칙과 specificity·!important가 같아 계속 져서(계산값이
100 그대로) 검증이 안 됐다. 그래서 여기서는 **인라인 스타일에 !important**로
직접 넣는다(인라인 !important는 어떤 스타일시트보다 세다) — 이것이 z-index
경쟁이 진짜 원인인지, 그리고 몇 이상이면 되는지를 확정한다.

배너를 열고 마지막에 × 를 한 번 누른다(결제·충전·구독 버튼 없음).

실행: venv312\\Scripts\\python.exe -u -X utf8 scratch\\probe_close_button_zindex.py
"""

from __future__ import annotations

import sys
import time

BARE = "https://lotto-shinryeong.streamlit.app/"
WIDTH, HEIGHT = 430, 932
MY_INFO_BTN = ".st-key-my_info_trigger_btn button"
CLOSE_BTN = ".st-key-auth_banner_close_x button"

VALUES = [100, 500, 999, 1000, 9999]

SET_INLINE = """(z) => {
  const w = document.querySelector('.st-key-auth_banner_wrap');
  if (!w) return {ok: false};
  w.style.setProperty('z-index', String(z), 'important');
  return {ok: true, computed: String(getComputedStyle(w).zIndex)};
}"""

HIT = """() => {
  const b = document.querySelector('.st-key-auth_banner_close_x button');
  const w = document.querySelector('.st-key-auth_banner_wrap');
  if (!b) return {found: false};
  const r = b.getBoundingClientRect();
  const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  const stack = document.elementsFromPoint(cx, cy);
  const top = stack[0] || null;
  const desc = (el) => {
    if (!el) return null;
    const t = (el.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 12);
    return el.tagName.toLowerCase() + (t ? ' [' + t + ']' : '');
  };
  return {
    found: true,
    isButtonTop: top === b,
    top: desc(top),
    stackSize: stack.length,
    manual: (function () {
      const m = document.querySelector('.st-key-manual_trigger_wrap');
      if (!m) return null;
      const cs = getComputedStyle(m);
      const mr = m.getBoundingClientRect();
      return {pos: cs.position, z: cs.zIndex,
              rect: {l: Math.round(mr.left), r: Math.round(mr.right),
                     t: Math.round(mr.top), b: Math.round(mr.bottom)}};
    })(),
    banner: w ? {z: getComputedStyle(w).zIndex,
                 rect: (function (x) { return {l: Math.round(x.left), r: Math.round(x.right),
                        t: Math.round(x.top), b: Math.round(x.bottom)}; })(
                   w.getBoundingClientRect())} : null,
  };
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
        print(f"뷰포트 {WIDTH}x{HEIGHT}")
        print(f"  배너   {got['banner']}")
        print(f"  사용설명서 {got['manual']}")

        print("\n=== 배너 z-index 를 인라인 !important 로 바꿔가며 ===")
        winner = None
        for value in VALUES:
            res = evaluate(frame, SET_INLINE, value)
            time.sleep(1.0)
            hit = evaluate(frame, HIT)
            if not isinstance(hit, dict) or not hit.get("found"):
                print(f"  z-index {value:<6} 측정 실패 {hit}")
                continue
            print(f"  z-index {value:<6} (적용={res.get('computed')})  "
                  f"버튼이맨위={hit['isButtonTop']}  현재맨위={hit['top']}  "
                  f"쌓임깊이={hit['stackSize']}")
            if hit["isButtonTop"] and winner is None:
                winner = value

        print(f"\n[판정] 999를 넘겨야 풀리는가: 최초로 뒤집힌 값 = {winner}")
        if winner is not None:
            print(f"[실제 클릭 확인] z-index {winner} 로 두고 × 를 누른다")
            evaluate(frame, SET_INLINE, winner)
            time.sleep(1.0)
            try:
                frame.click(CLOSE_BTN, timeout=8000)
                print("  실제 클릭 = 성공")
            except Exception as exc:  # noqa: BLE001
                print(f"  실제 클릭 = 실패({str(exc).splitlines()[0][:90]})")
            time.sleep(4)
            print("  클릭 후 배너 개수 =",
                  frame.evaluate(
                      "() => document.querySelectorAll('.st-key-auth_banner_wrap').length"))
        else:
            print("  뒤집히지 않았다 — z-index 경쟁만으로는 설명되지 않는다.")

        browser.close()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
