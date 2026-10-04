"""이벤트 배너 창의 **실제 DOM 계측** — CSS가 정말 걸렸는지 요소 단위로 확인한다.

왜 필요한가(2026-10-04): AppTest에는 DOM이 없어서 "CSS를 썼다"까지만 확인됐고,
구름님 실기기에서는 제목 정렬·버튼 한 줄·빈 공간이 그대로였다. 이 계측은 추측을 지우고
  · 다이얼로그의 실제 구조(testid/class/좌표)
  · .st-key-win_event_banner_body 가 정말 존재하는지, 어느 요소인지
  · 제목(h2 계열)의 computed text-align
  · 두 버튼의 좌표(같은 줄인가)
  · iframe 높이 vs 내용 높이(빈 공간)
를 숫자로 돌려준다.

실행: venv312\\Scripts\\python.exe -u -X utf8 scratch\\probe_win_banner_dom.py [URL]
"""

from __future__ import annotations

import json
import sys
import time

DEFAULT_URL = "http://127.0.0.1:8599/?page=main"
WIDTH, HEIGHT = 390, 844

JS = r"""() => {
  const R = (el) => { const r = el.getBoundingClientRect();
    return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)}; };
  const rect = [];
  const dialogs = document.querySelectorAll('div[data-testid="stDialog"]');
  const out = {dialogs: dialogs.length, nodes: [], keys: [], titles: [], buttons: [],
               frames: [], docH: document.documentElement.scrollHeight,
               inner: {w: window.innerWidth, h: window.innerHeight}};
  if (!dialogs.length) return out;
  const dlg = dialogs[0];
  out.dialogRect = R(dlg);
  const cls = (el) => { try { return String(el.className || ''); } catch (e) { return ''; } };
  (function walk(el, depth) {
    if (depth > 5) return;
    const c = cls(el);
    out.nodes.push({d: depth, tag: el.tagName.toLowerCase(),
                    testid: el.getAttribute('data-testid') || '',
                    role: el.getAttribute('role') || '',
                    keycls: (c.match(/st-key-[A-Za-z0-9_\-]+/g) || []).join(','),
                    rect: R(el)});
    if (c.indexOf('st-key-') >= 0) {
      const k = (c.match(/st-key-[A-Za-z0-9_\-]+/g) || []).join(',');
      out.keys.push({depth: depth, tag: el.tagName.toLowerCase(), key: k,
                     testid: el.getAttribute('data-testid') || '', rect: R(el)});
    }
    for (const ch of el.children) walk(ch, depth + 1);
  })(dlg, 0);

  dlg.querySelectorAll('h1,h2,h3,h4').forEach(function (h) {
    const st = getComputedStyle(h);
    out.titles.push({tag: h.tagName.toLowerCase(), text: (h.innerText || '').trim(),
                     align: st.textAlign, width: st.width, fontWeight: st.fontWeight,
                     fontSize: st.fontSize, pad: st.padding, rect: R(h)});
  });
  dlg.querySelectorAll('button').forEach(function (b) {
    const st = getComputedStyle(b);
    out.buttons.push({text: (b.innerText || '').trim().slice(0, 30), rect: R(b),
                      fontSize: st.fontSize, parentRect: R(b.closest('div[data-testid="stColumn"]') || b.parentElement)});
  });
  dlg.querySelectorAll('iframe').forEach(function (f) {
    const st = getComputedStyle(f);
    let contentH = null;
    try {
      const doc = f.contentDocument;
      contentH = doc ? Math.max(doc.body.scrollHeight, doc.documentElement.scrollHeight) : null;
      if (doc) {
        const shine = doc.querySelector('.wev-shine');
        const ps = Array.from(doc.querySelectorAll('.wev-p'));
        out.anim = {
          shineDur: shine ? getComputedStyle(shine).animationDuration : null,
          shineIter: shine ? getComputedStyle(shine).animationIterationCount : null,
          particles: ps.length,
          distinctX: new Set(ps.map(function (p) { return p.style.getPropertyValue('--x'); })).size,
          pDur: ps.slice(0, 4).map(function (p) { return getComputedStyle(p).animationDuration; }),
          pDurVar: ps.slice(0, 6).map(function (p) { return p.style.getPropertyValue('--dur'); }),
          pSway: ps.slice(0, 6).map(function (p) { return p.style.getPropertyValue('--sx'); }),
        };
      }
    } catch (e) { contentH = 'unreadable'; }
    out.frames.push({rect: R(f), cssHeight: st.height, attrHeight: f.getAttribute('height'),
                     title: f.getAttribute('title') || '', contentH: contentH});
  });
  out.supports = {has: CSS.supports('selector(:has(*))'),
                  nowrap: CSS.supports('flex-wrap: nowrap')};
  out.keyed = Array.from(document.querySelectorAll('[class*="st-key-"]')).map(function (el) {
    const c = cls(el);
    return {key: (c.match(/st-key-[A-Za-z0-9_\-]+/g) || []).join(','),
            testid: el.getAttribute('data-testid') || '',
            inDialog: !!el.closest('div[data-testid="stDialog"]'), rect: R(el)};
  });
  out.styleTags = Array.from(document.querySelectorAll('style')).map(function (s) {
    const t = s.textContent || '';
    return {len: t.length, hasWev: t.indexOf('wev') >= 0,
            hasKey: t.indexOf('win_event_banner') >= 0,
            parent: s.parentElement ? s.parentElement.tagName : '-',
            sample: t.slice(0, 160)};
  }).filter(function (s) { return s.hasWev || s.hasKey; });
  out.dialogHtml = dlg.outerHTML.slice(0, 2600);
  out.hasProbe = {
    matchesHas: dlg.matches('div[data-testid="stDialog"]:has(.st-key-win_event_banner_body)'),
    closedBtnDisplay: (function () { const b = document.querySelector('.st-key-win_event_banner_closed_btn');
      return b ? getComputedStyle(b).display : 'missing'; })(),
    colStyle: (function () { const c = dlg.querySelector('div[data-testid="stColumn"]');
      const cs = getComputedStyle(c);
      return {minWidth: cs.minWidth, flex: cs.flex, width: cs.width}; })(),
    ourSheets: Array.from(document.querySelectorAll('style'))
      .filter(function (s) { return (s.textContent || '').indexOf('win_event_banner_body') >= 0; })
      .map(function (s) {
        let n = -1, first = [];
        try { n = s.sheet ? s.sheet.cssRules.length : -1;
              first = s.sheet ? Array.from(s.sheet.cssRules).slice(0, 4).map(function (r) {
                return (r.selectorText || r.cssText || '').slice(0, 110); }) : []; } catch (e) { n = 'err'; }
        return {rules: n, first: first};
      }),
    allSheetCount: document.styleSheets.length
  };
  const cols = dlg.querySelectorAll('div[data-testid="stColumn"]');
  out.columns = Array.from(cols).map(function (c) { const st = getComputedStyle(c);
    return {rect: R(c), width: st.width, minWidth: st.minWidth, flex: st.flex, order: st.order}; });
  const hblocks = dlg.querySelectorAll('div[data-testid="stHorizontalBlock"]');
  out.hblocks = Array.from(hblocks).map(function (h) { const st = getComputedStyle(h);
    return {rect: R(h), display: st.display, flexWrap: st.flexWrap, flexDirection: st.flexDirection}; });
  return out;
}"""


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT},
                                device_scale_factor=1)
        page.goto(url, timeout=120000, wait_until="domcontentloaded")
        deadline = time.time() + 180
        data = None
        while time.time() < deadline:
            try:
                data = page.evaluate(JS)
            except Exception as exc:  # noqa: BLE001
                print(f"  (평가 대기) {type(exc).__name__}: {str(exc)[:80]}")
                data = None
            if data and data.get("dialogs", 0) > 0:
                break
            time.sleep(3)

        if not data or not data.get("dialogs"):
            print("실패: 다이얼로그가 뜨지 않았다")
            print(json.dumps({"docH": (data or {}).get("docH")}, ensure_ascii=False))
            page.screenshot(path="scratch/win_banner_dom.png", full_page=False)
            browser.close()
            return 1

        time.sleep(2)
        data = page.evaluate(JS)
        page.screenshot(path="scratch/win_banner_dom.png", full_page=False)

        print(f"뷰포트 {data['inner']['w']}x{data['inner']['h']}  다이얼로그 {data['dialogs']}개")
        print(f"창 좌표 {data['dialogRect']}")
        print("\n[제목]")
        for h in data["titles"]:
            print(f"  {h['tag']} '{h['text']}' align={h['align']} width={h['width']} "
                  f"font={h['fontSize']} rect={h['rect']}")
        print("\n[st-key-* 요소 — CSS 기준점이 실제로 있는가]")
        for k in data["keys"]:
            print(f"  depth{k['depth']} {k['tag']} .{k['key']} testid={k['testid']} rect={k['rect']}")
        print("\n[버튼 — 같은 줄인가]")
        for b in data["buttons"]:
            print(f"  '{b['text']}' rect={b['rect']} font={b['fontSize']} col={b['parentRect']}")
        print("\n[컬럼]")
        for c in data.get("columns", []):
            print(f"  {c}")
        print("\n[가로블록]")
        for h in data.get("hblocks", []):
            print(f"  {h}")
        print("\n[iframe — 빈 공간]")
        for f in data["frames"]:
            print(f"  rect={f['rect']} cssHeight={f['cssHeight']} attr={f['attrHeight']} "
                  f"내용높이={f['contentH']}")
        print(f"\n[:has() 지원] {data.get('supports')}")
        print("\n[문서 전체 st-key-* (다이얼로그 포함 여부)]")
        for k in data.get("keyed", []):
            print(f"  .{k['key']} testid={k['testid']} inDialog={k['inDialog']} rect={k['rect']}")
        print("\n[우리 CSS가 DOM에 들어갔는가]")
        for s in data.get("styleTags", []):
            print(f"  parent={s['parent']} len={s['len']} wev={s['hasWev']} key={s['hasKey']}")
            print(f"    {s['sample']!r}")
        print("\n[카드 iframe 안쪽 애니메이션 실측]")
        print(json.dumps(data.get("anim", {}), ensure_ascii=False))
        print("\n[우리 CSS 적용 여부 직접 확인]")
        print(json.dumps(data.get("hasProbe", {}), ensure_ascii=False, indent=2))
        print("\n[다이얼로그 outerHTML 앞부분]")
        print(data.get("dialogHtml", ""))
        print("\n[구조 트리]")
        for n in data["nodes"]:
            print(f"  {'  ' * n['d']}{n['tag']} testid={n['testid'] or '-'} key={n['keycls'] or '-'} {n['rect']}")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
