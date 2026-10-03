"""조사 3 — 폰 폭에서 × 자리를 눌렀을 때 사용자에게 실제로 무슨 일이 일어나는가.

앞선 두 조사에서 360/390/430px에서는 × 버튼의 다섯 지점 전부가 배너 밖 요소
(메인 화면의 "📖 사용설명서")로 갔고, 768/1280px에서는 정상이었다. 히트테스트는
"브라우저가 클릭을 어디로 보내는가"를 말해줄 뿐이라, 마지막으로 그 자리를
실제로 눌러 **무엇이 열리는지** 본다:

  - 클릭 전후의 본문 텍스트와 배너 컨테이너 개수를 비교해
    "배너가 닫혔는가"와 "다른 것이 열렸는가"를 가린다.

누르는 곳은 × 자리 하나뿐이다(결제·충전·구독 버튼 없음).

실행: venv312\\Scripts\\python.exe -u -X utf8 scratch\\probe_close_button_effect.py
"""

from __future__ import annotations

import re
import sys
import time

BARE = "https://lotto-shinryeong.streamlit.app/"
WIDTH, HEIGHT = 430, 932
MY_INFO_BTN = ".st-key-my_info_trigger_btn button"

STATE = """() => {
  const b = document.querySelector('.st-key-auth_banner_close_x button');
  const r = b ? b.getBoundingClientRect() : null;
  return {
    bannerWraps: document.querySelectorAll('.st-key-auth_banner_wrap').length,
    dialogs: document.querySelectorAll('[data-testid="stDialog"], [role="dialog"]').length,
    btn: r ? {x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2)} : null,
    text: (document.body.innerText || '').replace(/\\s+/g, ' ').slice(0, 260),
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

        try:
            frame.click(MY_INFO_BTN, timeout=30000)
        except Exception as exc:  # noqa: BLE001
            print(f"배너 열기 실패: {str(exc).splitlines()[0][:100]}")
            browser.close()
            return 1
        deadline = time.time() + 60
        while time.time() < deadline:
            before = evaluate(frame, STATE)
            if isinstance(before, dict) and before.get("bannerWraps", 0) > 0:
                break
            time.sleep(2)

        print(f"[클릭 전] 배너={before['bannerWraps']} 다이얼로그={before['dialogs']} "
              f"× 중심={before['btn']}")
        print(f"  본문: {before['text'][:180]}")

        bx, by = before["btn"]["x"], before["btn"]["y"]
        print(f"\n[× 자리를 실제로 누른다] 좌표 ({bx}, {by})")
        # 프레임 좌표 → 페이지 좌표로 옮겨 page.mouse로 진짜 클릭을 보낸다.
        box = frame.frame_element().bounding_box()
        page.mouse.click(box["x"] + bx, box["y"] + by)
        time.sleep(6)

        after = evaluate(frame, STATE)
        print(f"[클릭 후] 배너={after['bannerWraps']} 다이얼로그={after['dialogs']}")
        print(f"  본문: {after['text'][:180]}")

        print("\n[판정]")
        if after["bannerWraps"] == 0:
            print("  × 자리 클릭으로 배너가 닫혔다 — 이 폭에서는 정상 동작.")
        else:
            print("  × 자리 클릭으로 배너가 닫히지 않았다.")
        if after["dialogs"] != before["dialogs"]:
            print(f"  대신 다른 창이 열렸다(다이얼로그 {before['dialogs']} -> "
                  f"{after['dialogs']}) — 사용자는 ×를 눌렀는데 다른 것이 뜬다.")
        else:
            print("  새로 열린 다이얼로그는 없다.")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
