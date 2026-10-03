"""조사 8 — 배너 z-index 를 999 위로 올리는 것이 정답인지 확정한다.

앞선 실행에서 판정 기준에 결함이 있었다: elementsFromPoint()[0] 은 가장 안쪽
요소를 돌려주므로, × 버튼의 라벨 <p> 가 맨 위면 `top === button` 이 False 가 된다.
그래서 "뒤집히지 않았다"로 잘못 결론냈다. 실제 관측은 이미 뒤집힘을 보여줬다:
  z-index 100/500/999 -> 맨 위 = p [📖 사용설명서]
  z-index 1000/9999   -> 맨 위 = p [✕]      (× 버튼 안쪽 라벨)

이번엔 판정을 `top === button || button.contains(top)` 로 고치고,
(1) 임계값이 정말 999/1000 경계인지
(2) 스타일시트로(인라인이 아니라) specificity를 앱 규칙보다 높여 넣어도 같은지
    — 실제 수정은 앱 규칙의 값 자체를 바꾸는 것이라 이 조건과 동등하다
(3) 그 상태에서 실제 클릭이 되고 배너가 닫히는지
(4) 배너 위치·크기가 그대로인지(수정이 레이아웃을 깨지 않는지)
를 확인한다.

배너를 열고 × 를 누르는 것뿐이다(결제·충전·구독 버튼 없음).

실행: venv312\\Scripts\\python.exe -u -X utf8 scratch\\probe_close_button_zindex2.py
"""

from __future__ import annotations

import sys
import time

BARE = "https://lotto-shinryeong.streamlit.app/"
WIDTH, HEIGHT = 430, 932
MY_INFO_BTN = ".st-key-my_info_trigger_btn button"
CLOSE_BTN = ".st-key-auth_banner_close_x button"
WRAP = 'div[data-testid="stVerticalBlock"].st-key-auth_banner_wrap'

SET_INLINE = """(z) => {
  const w = document.querySelector('.st-key-auth_banner_wrap');
  if (!w) return {ok: false};
  w.style.setProperty('z-index', String(z), 'important');
  return {ok: true, computed: String(getComputedStyle(w).zIndex)};
}"""

# 앱 규칙과 같은 선택자 + 감정 클래스 하나를 더 붙여 specificity 를 앱 규칙보다 높인다.
# (실제 수정은 앱 규칙의 값 자체를 바꾸는 것이라 어떤 specificity 경쟁도 없다.)
SET_SHEET = """(css) => {
  let el = document.getElementById('__probe_sheet');
  if (!el) { el = document.createElement('style'); el.id = '__probe_sheet';
             document.head.appendChild(el); }
  el.textContent = css;
  return true;
}"""

HIT = """() => {
  const b = document.querySelector('.st-key-auth_banner_close_x button');
  const w = document.querySelector('.st-key-auth_banner_wrap');
  if (!b) return {found: false};
  const r = b.getBoundingClientRect();
  const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  const stack = document.elementsFromPoint(cx, cy);
  const top = stack[0] || null;
  const owned = !!top && (top === b || b.contains(top));
  const desc = (el) => {
    if (!el) return null;
    const t = (el.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 12);
    return el.tagName.toLowerCase() + (t ? ' [' + t + ']' : '');
  };
  const wr = w ? w.getBoundingClientRect() : null;
  return {
    found: true,
    buttonOwnsPoint: owned,
    top: desc(top),
    bannerDesc: desc(top) && top && top.closest
      ? desc(top.closest('.st-key-auth_banner_wrap')) : null,
    bannerZ: w ? String(getComputedStyle(w).zIndex) : null,
    bannerRect: wr ? {l: Math.round(wr.left), r: Math.round(wr.right),
                      t: Math.round(wr.top), b: Math.round(wr.bottom)} : null,
    bannerPos: w ? getComputedStyle(w).position : null,
    btnRect: {l: Math.round(r.left), r: Math.round(r.right),
              t: Math.round(r.top), b: Math.round(r.bottom)},
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
            base = evaluate(frame, HIT)
            if isinstance(base, dict) and base.get("found"):
                break
            time.sleep(2)
        print(f"뷰포트 {WIDTH}x{HEIGHT}  배너 z={base['bannerZ']} pos={base['bannerPos']} "
              f"rect={base['bannerRect']}")
        print(f"  × rect={base['btnRect']}  기준 상태: 버튼이 그 픽셀을 가짐="
              f"{base['buttonOwnsPoint']} 맨위={base['top']}")

        print("\n=== (1) 판정 기준을 고쳐 다시: 임계값 경계 ===")
        flipped = []
        for z in (100, 999, 1000):
            evaluate(frame, SET_INLINE, z)
            time.sleep(1.0)
            got = evaluate(frame, HIT)
            print(f"  z-index {z:<5} 적용={got['bannerZ']:<5} "
                  f"버튼이 픽셀을 가짐={got['buttonOwnsPoint']}  맨위={got['top']}  "
                  f"배너위치={got['bannerRect']}")
            if got["buttonOwnsPoint"]:
                flipped.append(z)

        print("\n=== (2) 스타일시트로 넣어도 같은가 (specificity 로 앱 규칙을 이김) ===")
        evaluate(frame, SET_INLINE, 100)  # 인라인 먼저 되돌리고
        evaluate(frame, SET_SHEET,
                 f"{WRAP}.st-emotion-cache-q25c8l{{z-index:1000 !important}}")
        time.sleep(1.2)
        sheet = evaluate(frame, HIT)
        print(f"  주입 후 z={sheet['bannerZ']}  버튼이 픽셀을 가짐={sheet['buttonOwnsPoint']}  "
              f"맨위={sheet['top']}  배너위치={sheet['bannerRect']}")

        print("\n=== (3)(4) 실제 클릭 + 레이아웃 무변화 확인 ===")
        if sheet.get("buttonOwnsPoint"):
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
            print("  버튼이 픽셀을 가지지 못해 클릭 확인을 건너뛴다")

        evaluate(frame, SET_SHEET, "")
        browser.close()

    print(f"\n[판정] 버튼이 픽셀을 가진 z-index 값 = {flipped or '없음'}")
    print("  999까지는 사용설명서 버튼이, 1000부터는 × 가 그 픽셀을 가진다."
          if flipped == [1000] else "")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
