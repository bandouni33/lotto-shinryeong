"""조사 4 — × 버튼이 왜 가려지는지, 원인 규칙까지 특정한다 (읽기 전용).

앞선 조사에서 폰 폭(360/390/430px)에서는 × 버튼의 다섯 지점 전부가 배너 '밖'
요소로 갔고, 768/1280px에서는 정상이었다. 히트테스트는 증상만 알려줄 뿐
어느 규칙이 지는지는 말해주지 않으므로, 여기서 계산된 스타일과 조상 체인을
그대로 덤프한다.

확인하려는 것:
  Q1 × 버튼의 중심점이 배너 랩(.st-key-auth_banner_wrap)의 테두리 상자 안인가?
     (transform: translateX(12px)로 밖으로 밀려 있으면 그 자체가 원인 후보다)
  Q2 그 지점에 실제로 겹쳐 있는 요소들이 무엇이고, 각각 position/z-index가 얼마인가
  Q3 배너 쪽 조상과 덮는 쪽 조상 중 어디에서 쌓임 맥락(stacking context)이
     갈리는가 — transform/filter/opacity/isolation 중 무엇이 원인인가
  Q4 같은 덤프를 1280px에서도 떠서 두 폭의 차이가 무엇인지 본다

배너를 열기만 한다(×를 누르지 않는다 — 이번엔 가림 상태만 본다).

실행: venv312\\Scripts\\python.exe -u -X utf8 scratch\\probe_close_button_stack.py
"""

from __future__ import annotations

import re
import sys
import time

BARE = "https://lotto-shinryeong.streamlit.app/"
WIDTHS = [(430, 932), (1280, 900)]
MY_INFO_BTN = ".st-key-my_info_trigger_btn button"

DUMP = """() => {
  const cls = (el) => String(el.className || '').split(' ')
    .filter(c => c.indexOf('st-key-') === 0 || c.indexOf('st-') === 0).join('.');
  const name = (el) => el.tagName.toLowerCase() + (cls(el) ? '.' + cls(el) : '');
  const rect = (el) => {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {l: Math.round(r.left), r: Math.round(r.right),
            t: Math.round(r.top), b: Math.round(r.bottom),
            w: Math.round(r.width), h: Math.round(r.height)};
  };
  const styleOf = (el) => {
    const cs = getComputedStyle(el);
    return {pos: cs.position, z: cs.zIndex,
            transform: cs.transform === 'none' ? 'none' : cs.transform,
            overflow: cs.overflow, isolation: cs.isolation,
            opacity: cs.opacity, filter: cs.filter === 'none' ? 'none' : 'filter',
            maxWidth: cs.maxWidth, margin: cs.margin, willChange: cs.willChange};
  };
  const chain = (el, limit) => {
    const out = [];
    let n = el;
    while (n && n !== document.documentElement && out.length < limit) {
      out.push({name: name(n), style: styleOf(n), rect: rect(n)});
      n = n.parentElement;
    }
    return out;
  };

  const b = document.querySelector('.st-key-auth_banner_close_x button');
  const wrap = document.querySelector('.st-key-auth_banner_wrap');
  const closeWrap = document.querySelector('.st-key-auth_banner_close_x');
  if (!b) return {found: false};

  const br = b.getBoundingClientRect();
  const cx = br.left + br.width / 2, cy = br.top + br.height / 2;
  const wr = wrap ? wrap.getBoundingClientRect() : null;
  const stack = document.elementsFromPoint(cx, cy).map(el => ({
    name: name(el),
    isTarget: el === b,
    inBanner: !!(el.closest && el.closest('.st-key-auth_banner_wrap')),
    style: styleOf(el),
  }));

  return {
    found: true,
    viewport: {w: window.innerWidth, h: window.innerHeight},
    scrollY: Math.round(window.scrollY),
    // Q1: 버튼 중심이 배너 랩의 테두리 상자 안인가
    centerInsideWrap: wr ? (cx >= wr.left && cx <= wr.right && cy >= wr.top && cy <= wr.bottom) : null,
    centerInsideWrapDetail: wr ? {
      dxRight: Math.round(cx - wr.right), dyTop: Math.round(cy - wr.top),
      dxLeft: Math.round(cx - wr.left), dyBottom: Math.round(cy - wr.bottom),
    } : null,
    btnRect: rect(b), btnStyle: styleOf(b),
    closeWrapRect: rect(closeWrap), closeWrapStyle: closeWrap ? styleOf(closeWrap) : null,
    wrapRect: rect(wrap), wrapStyle: wrap ? styleOf(wrap) : null,
    // Q2: 그 지점의 쌓임 순서 (위 → 아래)
    stack: stack,
    // Q3: 덮는 요소와 버튼의 조상 체인
    coverChain: stack.length > 1 ? chain(document.elementsFromPoint(cx, cy)[0], 8) : [],
    buttonChain: chain(b, 8),
  };
}"""


def evaluate(frame, js):
    try:
        return frame.evaluate(js)
    except Exception as exc:  # noqa: BLE001
        return {"__error__": f"{type(exc).__name__}: {str(exc)[:160]}"}


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


def show_chain(title: str, chain: list) -> None:
    print(f"    {title}:")
    for level, row in enumerate(chain):
        st = row["style"]
        rc = row["rect"] or {}
        print(f"      {level}. {row['name'][:52]:<52} pos={st['pos']:<8} z={st['z']:<5} "
              f"ov={st['overflow']:<8} iso={st['isolation']:<8} op={st['opacity']}")
        if st["transform"] != "none":
            print(f"         transform={st['transform'][:70]}")
        if st["filter"] != "none" or st["willChange"] != "auto":
            print(f"         filter={st['filter'][:40]} willChange={st['willChange']}")
        print(f"         rect l={rc.get('l')} r={rc.get('r')} t={rc.get('t')} b={rc.get('b')}")


def main() -> int:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for width, height in WIDTHS:
            print(f"\n{'=' * 70}\n=== {width}x{height} ===\n{'=' * 70}")
            page = browser.new_page(viewport={"width": width, "height": height})
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
                    continue

                deadline = time.time() + 120
                while time.time() < deadline:
                    try:
                        if frame.evaluate(
                                f"() => !!document.querySelector({MY_INFO_BTN!r})"):
                            break
                    except Exception:  # noqa: BLE001
                        pass
                    time.sleep(2)
                try:
                    frame.click(MY_INFO_BTN, timeout=20000)
                except Exception as exc:  # noqa: BLE001
                    print(f"  배너 열기 실패: {str(exc).splitlines()[0][:100]}")
                    continue

                deadline = time.time() + 60
                dump = None
                while time.time() < deadline:
                    dump = evaluate(frame, DUMP)
                    if isinstance(dump, dict) and dump.get("found"):
                        break
                    time.sleep(2)
                if not isinstance(dump, dict) or not dump.get("found"):
                    print(f"  × 버튼을 못 찾았다: {dump}")
                    continue

                print(f"  뷰포트 {dump['viewport']} scrollY={dump['scrollY']}")
                print(f"  Q1 버튼 중심이 배너 랩 안인가 = {dump['centerInsideWrap']} "
                      f"{dump['centerInsideWrapDetail']}")
                print(f"  버튼  {dump['btnRect']}  {dump['btnStyle']['transform'][:40]}")
                print(f"  close {dump['closeWrapRect']}  pos={dump['closeWrapStyle']['pos']} "
                      f"z={dump['closeWrapStyle']['z']}")
                print(f"  랩    {dump['wrapRect']}  pos={dump['wrapStyle']['pos']} "
                      f"z={dump['wrapStyle']['z']} maxW={dump['wrapStyle']['maxWidth']}")
                print("  Q2 그 지점의 쌓임 순서(위->아래):")
                for i, row in enumerate(dump["stack"][:6]):
                    print(f"    {i}. {row['name'][:56]:<56} isTarget={row['isTarget']} "
                          f"배너안={row['inBanner']} pos={row['style']['pos']} "
                          f"z={row['style']['z']}")
                print("  Q3 조상 체인")
                show_chain("덮는 요소", dump["coverChain"])
                show_chain("× 버튼", dump["buttonChain"])
            finally:
                page.close()
        browser.close()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
