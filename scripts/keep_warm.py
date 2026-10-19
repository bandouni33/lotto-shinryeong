"""서버 데워두기(2026-10-18 사용자 승인 ①) — 실제 브라우저로 앱을 한 번 열어 서버 화면 코드를 돌린다.

이용자가 거의 없으면 Streamlit Cloud 의 캐시·DB 연결이 식어 첫 방문이 2.8~11초 걸린다(10-08 실측).
주소만 찌르는 요청(UptimeRobot)은 껍데기 페이지만 받아 파이썬 화면 코드가 돌지 않으므로, 여기서는
헤드리스 브라우저로 끝까지 그려지게 한다. ?warm=1 표시는 render_timing 기록에서 구분용(로그인·결제 경로 무관).
잠든 앱이면 '다시 깨우기' 버튼을 누른다. 결과(걸린 초)는 실행 기록에만 남긴다(비밀 값 없음).
"""
from __future__ import annotations

import sys
import time

from playwright.sync_api import sync_playwright

URL = "https://lotto-shinryeong.streamlit.app/?warm=1"


def main() -> int:
    t0 = time.time()
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 390, "height": 844})
        pg.goto(URL, wait_until="domcontentloaded", timeout=90_000)
        deadline = time.time() + 150
        woke = False
        while time.time() < deadline:
            if not woke:
                btn = pg.get_by_role("button", name="Yes, get this app back up!")
                if btn.count():
                    btn.first.click()
                    woke = True
                    print("잠든 앱 깨우기 누름")
            for fr in pg.frames:
                try:
                    if fr.locator('[data-testid="stApp"]').count() and "조합" in fr.locator("body").inner_text(timeout=2000):
                        print(f"OK 화면 그려짐 {time.time() - t0:.1f}초 (깨우기={'예' if woke else '아니오'})")
                        b.close()
                        return 0
                except Exception:  # noqa: BLE001
                    pass
            time.sleep(1)
        print(f"시간 초과 {time.time() - t0:.1f}초")
        b.close()
        return 1


if __name__ == "__main__":
    sys.exit(main())
