"""조사 — 인증 배너의 닫기(×)를 실제 마우스 클릭으로 누를 수 있는가 (읽기 전용).

배경: ①② 검증 중, 헤드리스 브라우저(430x900)에서 Playwright의 실제 클릭이
두 번 다 막혔다. 그 지점에서 맨 위에 있는 요소가 × 버튼이 아니라 메인 화면의
`<p>📖 사용설명서</p>`였다. 이건 ①② 수정(JS가 조회하는 문서)과 무관한
CSS/레이아웃 문제로 보이지만, 실사용자도 ×를 못 누르는 상황인지 확인이 필요하다.

그래서 실사용자가 쓰는 화면 폭에서 각각:
  1) × 버튼의 위치와 그 위에 실제로 올라와 있는 요소가 무엇인지(히트테스트)
  2) 그 요소가 배너 '안'인지 '밖'인지 — 밖이면 실사용자 클릭이 그쪽으로 샌다
  3) 진짜 마우스 클릭(Playwright의 액션 가능성 검사 포함)이 되는지
를 본다. 클릭은 배너를 열고 ×를 누르는 것뿐이다(결제·충전·구독 버튼 없음).

실행: venv312\\Scripts\\python.exe -u -X utf8 scratch\\probe_close_button_hit.py
"""

from __future__ import annotations

import re
import sys
import time

BARE = "https://lotto-shinryeong.streamlit.app/"
WIDTHS = [
    (360, 780, "안드로이드 소형 폰 폭"),
    (390, 844, "아이폰 표준 폭"),
    (430, 932, "아이폰 대형 폭(앞서 실패한 값)"),
    (768, 1024, "태블릿"),
    (1280, 900, "PC"),
]
MY_INFO_BTN = ".st-key-my_info_trigger_btn button"
CLOSE_BTN = ".st-key-auth_banner_close_x button"

# × 버튼 위/가운데/아래와 좌우를 각각 찍어, 버튼의 어느 부분이 가려지는지 본다.
HIT_TEST = """() => {
  const b = document.querySelector('.st-key-auth_banner_close_x button');
  if (!b) return {found: false};
  const r = b.getBoundingClientRect();
  const describe = (el) => {
    if (!el) return null;
    const cls = String(el.className || '').split(' ')[0];
    const txt = (el.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 16);
    return el.tagName.toLowerCase() + (cls ? '.' + cls : '') +
           (txt ? ' [' + txt + ']' : '');
  };
  const points = [
    ['center', r.x + r.width / 2, r.y + r.height / 2],
    ['top', r.x + r.width / 2, r.y + 3],
    ['bottom', r.x + r.width / 2, r.y + r.height - 3],
    ['left', r.x + 3, r.y + r.height / 2],
    ['right', r.x + r.width - 3, r.y + r.height / 2],
  ].map(([name, x, y]) => {
    const stack = document.elementsFromPoint(x, y);
    const top = stack[0];
    return {
      name: name,
      topIsButton: top === b,
      withinBanner: !!(top && top.closest && top.closest('.st-key-auth_banner_wrap')),
      top: describe(top),
      depth: stack.length,
    };
  });
  const wrap = document.querySelector('.st-key-auth_banner_wrap');
  const cs = wrap ? getComputedStyle(wrap) : null;
  const wr = wrap ? wrap.getBoundingClientRect() : null;
  return {
    found: true,
    viewport: {w: window.innerWidth, h: window.innerHeight},
    btn: {x: Math.round(r.x), y: Math.round(r.y),
          w: Math.round(r.width), h: Math.round(r.height)},
    wrap: wr ? {top: Math.round(wr.top), bottom: Math.round(wr.bottom),
                h: Math.round(wr.height), position: cs.position,
                zIndex: cs.zIndex, overflow: cs.overflow} : null,
    points: points,
    clickablePoints: points.filter(p => p.topIsButton).map(p => p.name),
  };
}"""


def evaluate(frame, js):
    try:
        return frame.evaluate(js)
    except Exception as exc:  # noqa: BLE001
        return {"__error__": f"{type(exc).__name__}: {str(exc)[:140]}"}


def wake_if_asleep(page) -> None:
    try:
        text = (page.inner_text("body") or "").lower()
    except Exception:  # noqa: BLE001
        return
    if "gone to sleep" not in text and "zzzz" not in text:
        return
    for pattern in ("back up", "wake", "get this app"):
        try:
            page.get_by_role("button", name=re.compile(pattern, re.I)).first.click(
                timeout=5000)
            return
        except Exception:  # noqa: BLE001
            continue


def app_frame(page):
    """st-key-*를 가장 많이 가진 프레임 = 앱 문서. **0개인 프레임은 반환하지 않는다.**

    초기값을 -1로 두면 st-key-*가 하나도 없는 (아직 렌더 전인) 프레임도
    "최댓값"으로 뽑혀 반환된다 — 그러면 호출부는 앱이 떴다고 착각하고 곷바로
    클릭을 시도해 대기 시간을 다 쓰고 실패한다(실제로 이 실수로 5개 폭이 전부
    "배너를 못 열었다"로 나왔다). 0보다 클 때만 후보로 삼아야 한다.
    """
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


def wait_for_selector(frame, selector: str, timeout: float) -> bool:
    """그 셀렉터가 문서에 실제로 나타날 때까지 기다린다.

    앱 프레임이 뜬 직후에는 메인 화면이 아직 렌더되기 전이다(콜드 스타트면
    수십 초). 그 상태에서 바로 클릭하면 대기 시간을 다 쓰고 "배너를 못 열었다"로
    끝나는데, 그건 앱 문제가 아니라 기다리지 않은 쪽의 문제다.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if frame.evaluate(f"() => !!document.querySelector({selector!r})"):
                return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2)
    return False


def open_banner(frame) -> bool:
    if not wait_for_selector(frame, MY_INFO_BTN, 120):
        print("  (내정보 버튼이 끝내 안 나타났다 — 화면이 렌더되지 않았다)")
        return False
    for label, action in (
        ("셀렉터", lambda: frame.click(MY_INFO_BTN, timeout=20000)),
        ("버튼 이름", lambda: frame.get_by_role(
            "button", name=re.compile("내정보")).first.click(timeout=15000)),
    ):
        try:
            action()
            print(f"  내정보 클릭 성공({label})")
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"  내정보 클릭 실패({label}): {str(exc).splitlines()[0][:90]}")
    return False


def main() -> int:
    from playwright.sync_api import sync_playwright

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for width, height, label in WIDTHS:
            print(f"\n=== {width}x{height} ({label}) ===")
            page = browser.new_page(viewport={"width": width, "height": height})
            try:
                page.goto(BARE, timeout=120000, wait_until="domcontentloaded")
                wake_if_asleep(page)
                frame = None
                deadline = time.time() + 150
                while time.time() < deadline:
                    frame = app_frame(page)
                    if frame is not None:
                        break
                    time.sleep(3)
                if frame is None:
                    print("  실패: 앱 문서를 못 찾았다")
                    results.append((width, None, "앱 문서 없음", None))
                    continue

                if not open_banner(frame):
                    print("  실패: 배너를 못 열었다")
                    results.append((width, None, "배너 안 열림", None))
                    continue

                deadline = time.time() + 60
                hit = None
                while time.time() < deadline:
                    hit = evaluate(frame, HIT_TEST)
                    if isinstance(hit, dict) and hit.get("found"):
                        break
                    time.sleep(2)
                if not isinstance(hit, dict) or not hit.get("found"):
                    print(f"  실패: × 버튼을 못 찾았다 {hit}")
                    results.append((width, None, "× 없음", None))
                    continue

                print(f"  뷰포트 {hit['viewport']}  버튼 {hit['btn']}")
                print(f"  배너 랩 {hit['wrap']}")
                for pt in hit["points"]:
                    print(f"    {pt['name']:<7} topIsButton={str(pt['topIsButton']):<5} "
                          f"배너안={str(pt['withinBanner']):<5} top={pt['top']}")
                print(f"  버튼이 맨 위인 지점 = {hit['clickablePoints'] or '없음'}")

                # 진짜 마우스 클릭 (Playwright의 액션 가능성 검사 포함)
                click_result = ""
                try:
                    frame.click(CLOSE_BTN, timeout=8000)
                    click_result = "성공"
                except Exception as exc:  # noqa: BLE001
                    first = str(exc).split("\n")[0][:90]
                    intercepted = ""
                    for line in str(exc).splitlines():
                        if line.strip().startswith("- <"):
                            intercepted = line.strip()[2:120]
                            break
                    click_result = f"실패({first})"
                    if intercepted:
                        click_result += f" 가로챈 요소={intercepted}"
                print(f"  실제 클릭 = {click_result}")
                results.append((width, hit["clickablePoints"], click_result, hit["btn"]))
            finally:
                page.close()
        browser.close()

    print("\n=== 요약 ===")
    print(f"{'폭':>6} | {'버튼이 맨 위인 지점':<20} | 실제 클릭")
    for width, points, click_result, _btn in results:
        shown = ",".join(points) if points else "-"
        print(f"{width:>6} | {shown:<20} | {click_result}")
    bad = [r for r in results if not str(r[2]).startswith("성공")]
    print(f"\n실제 클릭이 막힌 폭 = {[r[0] for r in bad] or '없음'}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
