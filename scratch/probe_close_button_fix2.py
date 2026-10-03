"""조사 6 — × 가림을 뒤집는 규칙을, 이번엔 '적용됐는지 확인하면서' 찾는다.

앞선 실험(probe_close_button_fix_candidates.py)은 무효였다. 앱 자체 규칙이
  div[data-testid="stVerticalBlock"].st-key-auth_banner_wrap { z-index:100 !important }
처럼 클래스+속성 선택자라 specificity가 높은데, 주입한 후보는 `.st-key-auth_banner_wrap`
뿐이라 **둘 다 !important라서 더 구체적인 앱 규칙이 이겼다** — 즉 후보가 적용조차
안 됐고, "안 뒤집힌다"는 결론은 실험 설계 결함의 산물이었다.

그래서 이번엔:
  (A) 주입한 값이 계산 스타일에 실제로 반영됐는지 한 줄씩 되읽는다(적용 여부 증명)
  (B) 후보 선택자를 앱 규칙과 같은 specificity로 쓴다
  (C) 조상 체인을 html까지 전부 덤프하고, 각 조상이 쌓임 맥락을 만드는지 계산한다
      (position+z-index / sticky / transform / filter / opacity<1 / isolation /
       will-change / contain / mix-blend-mode)

배너를 열고 필요할 때 × 를 누르는 것뿐이다(결제·충전·구독 버튼 없음).

실행: venv312\\Scripts\\python.exe -u -X utf8 scratch\\probe_close_button_fix2.py
"""

from __future__ import annotations

import sys
import time

BARE = "https://lotto-shinryeong.streamlit.app/"
WIDTH, HEIGHT = 430, 932
MY_INFO_BTN = ".st-key-my_info_trigger_btn button"
CLOSE_BTN = ".st-key-auth_banner_close_x button"
WRAP = 'div[data-testid="stVerticalBlock"].st-key-auth_banner_wrap'
CLOSE = 'div[data-testid="stVerticalBlock"].st-key-auth_banner_close_x'

# (설명, 주입할 CSS, 되읽을 대상 셀렉터, 되읽을 속성) — 앱 규칙과 같은 specificity로 쓴다.
CANDIDATES = [
    ("대조군(주입 없음)", "", WRAP, "zIndex"),
    (f"랩 z-index 99999 (specificity 동일)",
     f"{WRAP}{{z-index:99999 !important}}", WRAP, "zIndex"),
    ("랩 position:relative (sticky 해제, specificity 동일)",
     f"{WRAP}{{position:relative !important}}", WRAP, "position"),
    ("랩 relative + z-index 99999",
     f"{WRAP}{{position:relative !important;z-index:99999 !important}}", WRAP, "position"),
    ("close_x relative + z-index 99999",
     f"{CLOSE}{{position:relative !important;z-index:99999 !important}}", CLOSE, "zIndex"),
    ("랩에 transform:translateZ(0) (새 쌓임 맥락)",
     f"{WRAP}{{transform:translateZ(0) !important;z-index:99999 !important}}", WRAP, "transform"),
    ("랩 바깥 래퍼(18kf3ut 상당) 를 relative + z-index 99999",
     'div[data-testid="stVerticalBlock"]:has(> div > .st-key-auth_banner_wrap)'
     '{position:relative !important;z-index:99999 !important}', WRAP, "zIndex"),
]

CHAIN_JS = """() => {
  const CONTEXT_REASON = (el) => {
    const cs = getComputedStyle(el);
    const why = [];
    if (cs.position === 'sticky' || cs.position === 'fixed') why.push('pos=' + cs.position);
    if (cs.position !== 'static' && cs.zIndex !== 'auto') why.push('pos+z=' + cs.zIndex);
    if (cs.transform !== 'none') why.push('transform');
    if (cs.filter !== 'none') why.push('filter');
    if (cs.backdropFilter && cs.backdropFilter !== 'none') why.push('backdrop-filter');
    if (parseFloat(cs.opacity) < 1) why.push('opacity<1');
    if (cs.isolation === 'isolate') why.push('isolation');
    if (cs.willChange && cs.willChange !== 'auto') why.push('will-change=' + cs.willChange);
    if (cs.contain && cs.contain !== 'none') why.push('contain=' + cs.contain);
    if (cs.mixBlendMode && cs.mixBlendMode !== 'normal') why.push('blend');
    return why;
  };
  const desc = (el) => {
    const c = String(el.className || '').split(' ')
      .filter(x => x.indexOf('st-key-') === 0 || x.indexOf('st-') === 0).join('.');
    return el.tagName.toLowerCase() + (c ? '.' + c : '') + (el.id ? '#' + el.id : '');
  };
  const chain = (el) => {
    const out = [];
    let n = el;
    while (n && n !== document.documentElement) {
      const cs = getComputedStyle(n);
      const r = n.getBoundingClientRect();
      out.push({
        name: desc(n), z: cs.zIndex, pos: cs.position,
        rect: {l: Math.round(r.left), r: Math.round(r.right),
               t: Math.round(r.top), b: Math.round(r.bottom)},
        why: CONTEXT_REASON(n),
      });
      n = n.parentElement;
    }
    return out;
  };

  const b = document.querySelector('.st-key-auth_banner_close_x button');
  const wrap = document.querySelector('.st-key-auth_banner_wrap');
  if (!b) return {found: false};
  const r = b.getBoundingClientRect();
  const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  const stack = document.elementsFromPoint(cx, cy);
  const top = stack[0];
  return {
    found: true,
    trigger: {x: Math.round(cx), y: Math.round(cy)},
    wrapClosedOffsets: wrap ? {
      wrapRight: Math.round(wrap.getBoundingClientRect().right),
      cx: Math.round(cx),
    } : null,
    topElement: top ? desc(top) : null,
    coverChain: top ? chain(top) : [],
    btnChain: chain(b),
  };
}"""

HIT = """() => {
  const b = document.querySelector('.st-key-auth_banner_close_x button');
  if (!b) return {found: false};
  const r = b.getBoundingClientRect();
  const top = document.elementsFromPoint(r.left + r.width / 2, r.top + r.height / 2)[0];
  return {found: true, isButtonTop: top === b,
          top: top ? top.tagName.toLowerCase() : null};
}"""

SET = """(css) => {
  let el = document.getElementById('__probe_css');
  if (!el) { el = document.createElement('style'); el.id = '__probe_css';
             document.head.appendChild(el); }
  el.textContent = css;
  return true;
}"""

READ = """([sel, prop]) => {
  const el = document.querySelector(sel);
  return el ? String(getComputedStyle(el)[prop]) : '(요소 없음)';
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
            got = evaluate(frame, CHAIN_JS)
            if isinstance(got, dict) and got.get("found"):
                break
            time.sleep(2)
        if not isinstance(got, dict) or not got.get("found"):
            print(f"× 버튼을 못 찾았다: {got}")
            browser.close()
            return 1

        print(f"뷰포트 {WIDTH}x{HEIGHT}  클릭 기준점 {got['trigger']}  "
              f"{got['wrapClosedOffsets']}")
        print(f"그 지점 최상단 요소 = {got['topElement']}")

        print("\n=== (C) 덮는 요소의 조상 체인 (html 근처까지) ===")
        for i, row in enumerate(got["coverChain"]):
            flag = ("  <-- 쌓임 맥락: " + ",".join(row["why"])) if row["why"] else ""
            print(f"  {i:>2}. {row['name'][:60]:<60} pos={row['pos']:<8} z={row['z']:<6} "
                  f"rect={row['rect']['l']},{row['rect']['t']}~{row['rect']['r']},{row['rect']['b']}{flag}")

        print("\n=== × 버튼의 조상 체인 (html 근처까지) ===")
        for i, row in enumerate(got["btnChain"]):
            flag = ("  <-- 쌓임 맥락: " + ",".join(row["why"])) if row["why"] else ""
            print(f"  {i:>2}. {row['name'][:60]:<60} pos={row['pos']:<8} z={row['z']:<6} "
                  f"rect={row['rect']['l']},{row['rect']['t']}~{row['rect']['r']},{row['rect']['b']}{flag}")

        print("\n=== (A)(B) 후보 실험 — 주입이 실제로 적용됐는지 되읽으면서 ===")
        for label, css, sel, prop in CANDIDATES:
            evaluate(frame, SET, css)
            time.sleep(1.2)
            applied = evaluate(frame, READ, [sel, prop])
            hit = evaluate(frame, HIT)
            ok = hit.get("isButtonTop") if isinstance(hit, dict) else None
            print(f"  {label[:48]:<48} 적용된 {prop}={str(applied)[:28]:<28} "
                  f"버튼이맨위={ok} 맨위={hit.get('top') if isinstance(hit, dict) else '?'}")

        print("\n[실제 클릭 확인] 랩 relative + z-index 99999")
        evaluate(frame, SET, CANDIDATES[3][1])
        time.sleep(1.2)
        print(f"  적용 확인 position={evaluate(frame, READ, [WRAP, 'position'])}")
        try:
            frame.click(CLOSE_BTN, timeout=8000)
            print("  실제 클릭 = 성공")
        except Exception as exc:  # noqa: BLE001
            print(f"  실제 클릭 = 실패({str(exc).splitlines()[0][:90]})")
        time.sleep(4)
        print("  클릭 후 배너 개수 =",
              frame.evaluate("() => document.querySelectorAll('.st-key-auth_banner_wrap').length"))

        evaluate(frame, SET, "")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
