"""조사 2 — 폰 폭에서 × 버튼이 '실제로 보이게' 가려지는가 (읽기 전용).

앞선 히트테스트(scratch/probe_close_button_hit.py)에서 360/390/430px에서는
× 버튼의 다섯 지점 전부가 배너 밖 요소(메인 화면의 "📖 사용설명서")로 갔고,
768/1280px에서는 정상이었다. 히트테스트는 브라우저가 클릭을 어디로 보내는지를
알려주지만 "사용자 눈에 가려져 보이는지"는 말해주지 않는다. 그래서:

  1) 스크롤 0에서 화면을 그대로 캡처해 둔다(눈으로 확인할 근거)
  2) 스크롤을 내린 뒤 같은 히트테스트를 다시 한다 — 가림이 스크롤에 따라
     변하면 "레이아웃이 겹친 것"이 아니라 특정 위치에서만 생기는 현상이다
  3) 스크롤 뒤에는 클릭이 되는지 본다(실사용자는 대개 스크롤한 상태로 ×를 누른다)

배너를 열고 ×를 누르는 것뿐이다(결제·충전·구독 버튼 없음).

실행: venv312\\Scripts\\python.exe -u -X utf8 scratch\\probe_close_button_visual.py
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BARE = "https://lotto-shinryeong.streamlit.app/"
WIDTH, HEIGHT = 430, 932
MY_INFO_BTN = ".st-key-my_info_trigger_btn button"
CLOSE_BTN = ".st-key-auth_banner_close_x button"

HIT = """() => {
  const b = document.querySelector('.st-key-auth_banner_close_x button');
  if (!b) return {found: false};
  const r = b.getBoundingClientRect();
  const at = (x, y) => {
    const st = document.elementsFromPoint(x, y);
    const top = st[0] || null;
    const txt = top ? (top.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 14) : '';
    return {
      isButton: top === b,
      withinBanner: !!(top && top.closest && top.closest('.st-key-auth_banner_wrap')),
      top: top ? (top.tagName.toLowerCase() + (txt ? ' [' + txt + ']' : '')) : null,
    };
  };
  return {
    found: true,
    scrollY: Math.round(window.scrollY),
    btn: {x: Math.round(r.x), y: Math.round(r.y), h: Math.round(r.height)},
    center: at(r.x + r.width / 2, r.y + r.height / 2),
    isTop: b.getBoundingClientRect().top >= 0,
  };
}"""


def evaluate(frame, js):
    try:
        return frame.evaluate(js)
    except Exception as exc:  # noqa: BLE001
        return {"__error__": f"{type(exc).__name__}: {str(exc)[:120]}"}


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

    shots = []
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
        print(f"앱 문서 = {frame.url[:70]}")

        try:
            frame.click(MY_INFO_BTN, timeout=30000)
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

        def snap(tag: str) -> dict:
            got = evaluate(frame, HIT)
            path = ROOT / "scratch" / f"shot_close_{tag}.png"
            page.screenshot(path=str(path))
            shots.append(path.name)
            print(f"  [{tag}] scrollY={got.get('scrollY')} 버튼={got.get('btn')}")
            print(f"         가운데 클릭 대상: isButton={got['center']['isButton']} "
                  f"배너안={got['center']['withinBanner']} top={got['center']['top']}")
            return got

        print("\n[스크롤 0]")
        snap("scroll0")

        print("\n[스크롤 350 내린 뒤]")
        frame.evaluate("() => { window.scrollTo(0, 350); "
                       "const el = document.querySelector('[data-testid=\"stAppViewContainer\"]'); "
                       "if (el && el.scrollTo) el.scrollTo(0, 350); }")
        time.sleep(2)
        got = snap("scrolled")
        try:
            frame.click(CLOSE_BTN, timeout=8000)
            print("  스크롤 뒤 실제 클릭 = 성공")
        except Exception as exc:  # noqa: BLE001
            line = str(exc).splitlines()[0][:80]
            inter = ""
            for ln in str(exc).splitlines():
                if ln.strip().startswith("- <"):
                    inter = ln.strip()[2:100]
                    break
            print(f"  스크롤 뒤 실제 클릭 = 실패({line}) 가로챈 요소={inter}")

        print(f"\n캡처 저장 = {', '.join(shots)} (scratch/)")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
