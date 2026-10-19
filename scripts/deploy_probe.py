"""운영(Streamlit Cloud)에 최신 코드가 반영됐는지 확인 — 화면 HTML 에 들어간 표식만 찾는다(로그인·결제 무관).

결과는 weekly_content/checks/deploy_probe_result.txt 로 커밋된다(값만, 비밀 없음)."""
from __future__ import annotations

import sys
import time

from playwright.sync_api import sync_playwright

URL = "https://lotto-shinryeong.streamlit.app/?page=auto&warm=1"
MARKS = {"확인창 즉시 감춤(wallet_ui)": "ln-pn-fast-close", "빛 연출(page_auto)": "-fx-halo",
         "미리 싣기(page_auto)": "data-ln-preload"}


def main() -> int:
    out = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 390, "height": 844})
        pg.goto(URL, wait_until="domcontentloaded", timeout=90_000)
        t0 = time.time()
        html = ""
        while time.time() - t0 < 120:
            parts = []
            for fr in pg.frames:
                try:
                    parts.append(fr.content())
                except Exception:  # noqa: BLE001
                    pass
            html = "\n".join(parts)
            if "조합시작" in html and "ln-pn-fast-close" in html:
                break
            time.sleep(2)
        out.append(f"화면 그려짐: {'조합시작' in html} ({time.time() - t0:.0f}초)")
        for name, mark in MARKS.items():
            out.append(f"{name}: {'있음' if mark in html else '없음'}")
        b.close()
    print("\n".join(out))
    with open("weekly_content/checks/deploy_probe_result.txt", "w", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime()) + "\n" + "\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
