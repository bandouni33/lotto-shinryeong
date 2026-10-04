"""CSS 후보 실험 — 어떤 규칙이 **실제로 먹는지** 하나씩 주입해 computed 값으로 판정한다.

배경(2026-10-04): 앞선 계측에서 `:has()` 선택자가 주입된 상태에서도 제목 정렬·컬럼 폭이
그대로였다(matches()는 True, 우리 스타일시트의 규칙 9개도 파싱됨). 그래서 "왜 안 먹는가"를
추측으로 넘기지 않고, 후보를 하나씩 넣고 지우며 **계산된 값**을 읽어 확정한다.

실행: venv312\\Scripts\\python.exe -u -X utf8 scratch\\probe_win_banner_css_test.py [URL]
"""

from __future__ import annotations

import json
import sys
import time

DEFAULT_URL = "http://127.0.0.1:8599/?page=main"
WIDTH, HEIGHT = 390, 844

MEASURE = r"""() => {
  const dlg = document.querySelector('div[data-testid="stDialog"]');
  if (!dlg) return {dialog: false};
  const h2 = dlg.querySelector('h2');
  const wrap = dlg.firstElementChild;
  const hb = dlg.querySelector('[data-testid="stHorizontalBlock"]');
  const col = dlg.querySelector('[data-testid="stColumn"]');
  const btns = Array.from(dlg.querySelectorAll('button'))
    .filter(b => (b.innerText || '').trim().length > 1)
    .map(b => { const r = b.getBoundingClientRect();
      return {t: (b.innerText || '').trim().slice(0, 12), x: Math.round(r.x), y: Math.round(r.y),
              w: Math.round(r.width), h: Math.round(r.height)}; });
  return {
    dialog: true,
    h2Align: h2 ? getComputedStyle(h2).textAlign : 'none',
    wrapPad: wrap ? getComputedStyle(wrap).padding : 'none',
    hbWrap: hb ? getComputedStyle(hb).flexWrap : 'none',
    colMin: col ? getComputedStyle(col).minWidth : 'none',
    colWidth: col ? getComputedStyle(col).width : 'none',
    btns: btns,
    sameRow: btns.length >= 2 && Math.abs(btns[0].y - btns[1].y) < 6,
    dialogH: Math.round(dlg.getBoundingClientRect().height),
    sectionH: Math.round((dlg.querySelector('section') || dlg).getBoundingClientRect().height),
  };
}"""

DIALOG = '[data-testid="stDialog"]'
BODY = ':has(.st-key-win_event_banner_body)'

CANDIDATES: list[tuple[str, str]] = [
    ("A  :has() 스코프 h2 가운데",
     f'{DIALOG}{BODY} h2 {{ text-align: center !important; }}'),
    ("B  :has() 없이 h2 가운데",
     f'{DIALOG} h2 {{ text-align: center !important; }}'),
    ("C  :has() 스코프 패딩 축소",
     f'{DIALOG}{BODY} > div {{ padding: 6px 10px 4px !important; }}'),
    ("D  :has() 스코프 가로블록 nowrap",
     f'{DIALOG}{BODY} [data-testid="stHorizontalBlock"] {{ flex-wrap: nowrap !important; }}'),
    ("E  :has() 스코프 컬럼 min-width:0 + 50%",
     f'{DIALOG}{BODY} [data-testid="stColumn"] {{ min-width: 0 !important; width: 50% !important; flex: 1 1 0 !important; }}'),
    ("F  스코프 없이 컬럼 min-width:0",
     f'{DIALOG} [data-testid="stColumn"] {{ min-width: 0 !important; }}'),
    ("G  JS로 붙인 속성[data-wev] 스코프 h2",
     f'{DIALOG}[data-wev="1"] h2 {{ text-align: center !important; }}'),
]


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
        page.goto(url, timeout=120000, wait_until="domcontentloaded")
        deadline = time.time() + 180
        base = None
        while time.time() < deadline:
            try:
                base = page.evaluate(MEASURE)
            except Exception:  # noqa: BLE001
                base = None
            if base and base.get("dialog"):
                break
            time.sleep(3)
        if not base or not base.get("dialog"):
            print("실패: 다이얼로그가 안 떴다")
            browser.close()
            return 1

        print("기준 상태:", json.dumps(base, ensure_ascii=False))

        # G 후보용 마커 속성(JS로 붙이는 방식이 되는지)
        page.evaluate("() => { const d = document.querySelector('div[data-testid=\"stDialog\"]');"
                      " if (d) d.setAttribute('data-wev', '1'); }")

        for name, css in CANDIDATES:
            handle = page.add_style_tag(content=css)
            time.sleep(0.7)
            after = page.evaluate(MEASURE)
            changed = []
            for k in ("h2Align", "wrapPad", "hbWrap", "colMin", "colWidth", "sameRow", "sectionH"):
                if k in after and base.get(k) != after.get(k):
                    changed.append(f"{k}: {base.get(k)} -> {after.get(k)}")
            verdict = "적용됨" if changed else "효과 없음"
            print(f"\n[{name}] {verdict}")
            for c in changed:
                print("   " + c)
            print("   버튼 y: " + ", ".join(f"{b['t']}={b['y']}" for b in after.get("btns", [])))
            handle.evaluate("el => el.remove()")
            time.sleep(0.4)

        # 마지막: 후보 D+E+B 를 한꺼번에 → 실제 목표 상태가 되는지
        combo = (f'{DIALOG} h2 {{ text-align: center !important; }}'
                 f'{DIALOG}{BODY} > div {{ padding: 6px 10px 4px !important; }}'
                 f'{DIALOG}{BODY} [data-testid="stHorizontalBlock"] {{ flex-wrap: nowrap !important; }}'
                 f'{DIALOG}{BODY} [data-testid="stColumn"] {{ min-width: 0 !important; width: 50% !important; flex: 0 1 50% !important; }}')
        handle = page.add_style_tag(content=combo)
        time.sleep(0.8)
        final = page.evaluate(MEASURE)
        print("\n[합본] " + json.dumps(final, ensure_ascii=False))
        page.screenshot(path="scratch/win_banner_css_test.png")
        handle.evaluate("el => el.remove()")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
