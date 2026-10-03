"""실제 Cloud 주소에서 ①② 수정이 정말 먹는지 확인 — 2026-10-03.

배포본(https://lotto-shinryeong.streamlit.app/)에 수정이 올라간 것을 전제로,
실사용자가 겪는 경로 그대로 확인한다. 이 배너는 미로그인 상태에서 메인 화면의
"👤 내정보"를 누르면 열린다(wallet_ui.py _request_my_info_login). 결제·충전·구독
버튼은 누르지 않는다.

  (A) 프레임 구조 — 앱 문서가 정말 최상위가 아닌지(그래서 top이 틀렸는지)
  (B) 배너를 열고, components.html의 srcdoc에서 실행될 JS를 그대로 읽어
      배포된 코드가 새 버전인지 판정한다. srcdoc은 같은 출처라 읽을 수 있고,
      배너가 렌더돼야 두 함수가 주입되므로 (A)와 (B)의 순서가 중요하다.
      이 판정이 없으면 "수정이 안 먹었다"와 "아직 재배포가 안 끝났다"를 구분 못 한다.
  (C) 행동 — 카카오 링크의 target 속성이 실제로 지워졌는지(②),
      × 를 누른 뒤 잔재 컨테이너(wrap/box/close_x)가 0이 되는지(①).

성공 판정은 "봐야 할 것을 실제로 봤을 때"만 낸다 — 배너가 안 떴으면 통과가
아니라 "확인 불가"로 끝난다(0건이 우연히 0인 경우를 통과로 세지 않는다).

실행: venv312\\Scripts\\python.exe scratch\\verify_cloud_auth_banner_fix.py
"""

from __future__ import annotations

import re
import sys
import time

BARE = "https://lotto-shinryeong.streamlit.app/"
WAIT_APP = 180          # 앱 문서가 뜰 때까지(콜드 스타트·잠든 앱 깨우기 포함)
WAIT_BANNER = 60        # 배너가 뜰 때까지
WAIT_AFTER_CLICK = 30   # × 이후 잔재가 사라질 때까지
MY_INFO_BTN = ".st-key-my_info_trigger_btn button"
CLOSE_BTN = ".st-key-auth_banner_close_x button"

# × 버튼의 위치와, 그 한가운데 지점에서 실제로 "맨 위에 있는" 요소가 무엇인지 본다.
# Playwright가 클릭을 거부할 때 그 이유(다른 요소가 덮고 있는지)를 말해준다.
CLOSE_BTN_STATE = """() => {
  const b = document.querySelector('.st-key-auth_banner_close_x button');
  if (!b) return null;
  const r = b.getBoundingClientRect();
  const cx = r.x + r.width / 2, cy = r.y + r.height / 2;
  const el = document.elementFromPoint(cx, cy);
  return {
    found: true,
    x: Math.round(r.x), y: Math.round(r.y),
    w: Math.round(r.width), h: Math.round(r.height),
    top_at_center: el ? (el.tagName + '.' + String(el.className).slice(0, 50)) : null,
  };
}"""

TOPOLOGY = """() => ({
  is_top: window.top === window,
  parent_is_self: window.parent === window,
  st_keys: document.querySelectorAll('[class*="st-key-"]').length,
  wrap: document.querySelectorAll('.st-key-auth_banner_wrap').length,
  box: document.querySelectorAll('.st-key-auth_banner_box').length,
  close_x: document.querySelectorAll('.st-key-auth_banner_close_x').length,
  kakao_a: document.querySelectorAll('.st-key-auth_banner_kakao a').length,
  kakao_a_target: document.querySelectorAll('.st-key-auth_banner_kakao a[target]').length,
  body_len: document.body ? document.body.innerText.length : -1,
})"""

# 앱 문서 안의 components.html iframe들이 실행할 JS를 그대로 들고 있다.
MARKER = """() => {
  const out = [];
  document.querySelectorAll('iframe').forEach(function(f, i) {
    const s = f.getAttribute('srcdoc') || '';
    if (!s) return;
    out.push({
      idx: i,
      uses_parent: s.indexOf('window.parent.document') >= 0,
      uses_top: s.indexOf('window.top.document') >= 0,
      kakao_fn: s.indexOf('[kakao_link]') >= 0,
      cleanup_fn: s.indexOf('[auth_banner]') >= 0,
      kakao_sel: s.indexOf('auth_banner_kakao') >= 0,
    });
  });
  return out;
}"""

KEY_COUNTS = ("wrap", "box", "close_x")


def evaluate(frame, js):
    try:
        return frame.evaluate(js)
    except Exception as exc:  # noqa: BLE001
        return {"__error__": f"{type(exc).__name__}: {str(exc)[:120]}"}


def wake_if_asleep(page) -> None:
    """Streamlit Cloud는 유휴 앱을 재운다 — 잠들어 있으면 깨우고 계속한다."""
    try:
        text = (page.inner_text("body") or "").lower()
    except Exception:  # noqa: BLE001
        return
    if "gone to sleep" not in text and "zzzz" not in text:
        return
    print("    (앱이 잠들어 있다 — 깨우기 버튼을 누른다)")
    for pattern in ("back up", "wake", "get this app"):
        try:
            page.get_by_role("button", name=re.compile(pattern, re.I)).first.click(
                timeout=5000)
            return
        except Exception:  # noqa: BLE001
            continue


def best_frame(page):
    """st-key-*를 가장 많이 가진 프레임 = 앱 문서."""
    best, best_info, best_n = None, None, -1
    for frame in page.frames:
        info = evaluate(frame, TOPOLOGY)
        if not isinstance(info, dict) or "st_keys" not in info:
            continue
        if info["st_keys"] > best_n:
            best, best_info, best_n = frame, info, info["st_keys"]
    return best, best_info


def request_banner(app) -> bool:
    """미로그인 상태에서 '👤 내정보'를 눌러 배너를 연다(결제 버튼 아님)."""
    for label, action in (
        (f"셀렉터 {MY_INFO_BTN}", lambda: app.click(MY_INFO_BTN, timeout=15000)),
        ("버튼 이름 '내정보'",
         lambda: app.get_by_role("button", name=re.compile("내정보")).first.click(
             timeout=10000)),
    ):
        try:
            action()
            print(f"  배너 열기 시도 성공: {label}")
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"  배너 열기 실패({label}): {type(exc).__name__}: {str(exc)[:120]}")
    return False


def dismiss_banner(app) -> str:
    """닫기(×)를 실제로 누른다.

    실패 원인을 잘라내지 않고 그대로 찍는다 — "버튼을 찾았는데 클릭이
    안 됐다"는 것과 "버튼이 없다"는 것은 다른 문제이고, 전자라면 그 자체가
    사용자에게도 영향을 주는 사실이다.
    """
    print(f"  버튼 상태: {app.evaluate(CLOSE_BTN_STATE)}")
    for label, kwargs, use_dispatch in (
        ("일반 클릭", {"timeout": 15000}, False),
        ("하단 지점 클릭(겹침 회피)", {"timeout": 15000, "position": {"x": 11, "y": 18}}, False),
        ("dispatch_event('click')", {}, True),
    ):
        try:
            if use_dispatch:
                app.locator(CLOSE_BTN).dispatch_event("click")
            else:
                app.click(CLOSE_BTN, **kwargs)
            print(f"  × 클릭 성공: {label}")
            return label
        except Exception as exc:  # noqa: BLE001
            print(f"  × 실패({label}): {str(exc)[:600]}")
    return ""


def wait_for(app, key, target, timeout):
    """counts[key]가 target과 같아질 때까지 기다린다. 마지막 관측값을 돌려준다."""
    deadline, info = time.time() + timeout, None
    while time.time() < deadline:
        info = evaluate(app, TOPOLOGY)
        if isinstance(info, dict) and info.get(key) == target:
            return info
        time.sleep(2)
    return info


def main() -> int:
    from playwright.sync_api import sync_playwright

    console: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 430, "height": 900})
        page.on("console", lambda m: console.append(f"{m.type}: {m.text[:200]}"))
        page.on("pageerror", lambda e: console.append(f"pageerror: {str(e)[:200]}"))

        print(f"[1] 접속: {BARE}")
        page.goto(BARE, timeout=120000, wait_until="domcontentloaded")
        wake_if_asleep(page)

        print(f"[2] 앱 문서를 기다린다 (최대 {WAIT_APP}s)")
        deadline, app, info = time.time() + WAIT_APP, None, None
        while time.time() < deadline:
            app, info = best_frame(page)
            if app is not None and info.get("st_keys", 0) > 0:
                break
            time.sleep(3)
        if app is None or info.get("st_keys", 0) <= 0:
            print("  실패: st-key-*를 가진 프레임이 없다.")
            try:
                print("    body:", (page.inner_text("body") or "")[:400].replace("\n", " / "))
            except Exception:  # noqa: BLE001
                pass
            browser.close()
            return 1
        print(f"  앱 문서 = {app.url[:80]}")

        print("\n[3] 프레임 구조 (window.top이 왜 틀린지)")
        wanted = []
        for frame in page.frames:
            got = evaluate(frame, TOPOLOGY)
            if isinstance(got, dict) and "is_top" in got:
                print(f"  {frame.url[:50]:<50} is_top={got['is_top']} "
                      f"parent_self={got['parent_is_self']} st_keys={got['st_keys']}")
                wanted.append(got)
        print(f"  -> 앱 문서에서 is_top={info['is_top']}, parent_self={info['parent_is_self']}")

        print("\n[4] 배너를 연다 (미로그인 상태에서 '내정보')")
        opened = request_banner(app)
        before = wait_for(app, "wrap", 1, WAIT_BANNER) if opened else None
        banner_shown = isinstance(before, dict) and before.get("wrap", 0) > 0
        print(f"  배너 표시 = {banner_shown}")

        if not banner_shown:
            after_state = evaluate(app, TOPOLOGY)
            print(f"  현재 상태 = {after_state}")
            try:
                print("    body:", (app.evaluate("() => document.body.innerText") or "")
                      [:300].replace("\n", " / "))
            except Exception:  # noqa: BLE001
                pass
        else:
            print(f"  배너 상태 = {before}")

        print("\n[5] 배포된 코드 판정 (components.html srcdoc에서 직접 읽음)")
        markers = evaluate(app, MARKER) if banner_shown else []
        deployed_parent = deployed_top = False
        saw_kakao_fn = saw_cleanup_fn = False
        if isinstance(markers, list):
            for m in markers:
                flags = []
                if m["uses_parent"]:
                    flags.append("parent")
                    deployed_parent = True
                if m["uses_top"]:
                    flags.append("top")
                    deployed_top = True
                if m["kakao_fn"]:
                    flags.append("kakao_fn(새 로그)")
                    saw_kakao_fn = True
                if m["cleanup_fn"]:
                    flags.append("cleanup_fn(새 로그)")
                    saw_cleanup_fn = True
                if m["kakao_sel"]:
                    flags.append("kakao_셀렉터")
                print(f"  iframe[{m['idx']}] {', '.join(flags) or '(해당 없음)'}")
        else:
            print(f"  srcdoc을 못 읽었다: {markers}")

        after = None
        samples: list[tuple] = []
        if banner_shown:
            print("\n[6] 닫기(×) 클릭 -> 잔재 DOM 확인 (①)")
            method = dismiss_banner(app)
            t_click = time.time()
            # 짧은 간격으로 샘플링한다 — 잔재가 잠깐 생겼다가 사라지는지 보면
            # "원래 안 생긴 것"과 "정리 스크립트가 지운 것"을 구분하는 데 도움이 된다.
            deadline = time.time() + WAIT_AFTER_CLICK
            while time.time() < deadline:
                after = evaluate(app, TOPOLOGY)
                if isinstance(after, dict):
                    samples.append((round(time.time() - t_click, 1),
                                    after.get("wrap"), after.get("box"),
                                    after.get("close_x"), after.get("st_keys")))
                    if all(after.get(k) == 0 for k in KEY_COUNTS):
                        break
                time.sleep(0.3)
            print(f"  클릭 후 = {after}")
            if method:
                print(f"  사용한 클릭 방식 = {method}")
            print("  시각(s) / wrap / box / close_x / st_keys 변화:")
            last = None
            for row in samples:
                if row[1:] != last:
                    print(f"    {row}")
                    last = row[1:]

            # ①의 핵심 증거: 정리 스크립트 자체가 주입됐는가. 잔재가 0인 것이
            # "우연히 0"인지 "주입된 JS가 지운 것"인지는 이걸로 갈린다.
            print("\n[6b] 닫은 직후 주입된 컴포넌트 재확인 (정리 스크립트가 실제로 심겼는가)")
            post = evaluate(app, MARKER)
            if isinstance(post, list):
                for m in post:
                    flags = []
                    if m["uses_parent"]:
                        flags.append("parent")
                    if m["uses_top"]:
                        flags.append("top")
                    if m["cleanup_fn"]:
                        flags.append("cleanup_fn(정리 스크립트)")
                    if m["kakao_sel"]:
                        flags.append("kakao_셀렉터")
                    print(f"    iframe[{m['idx']}] {', '.join(flags) or '(해당 없음)'}")
                injected_cleanup = any(m["cleanup_fn"] and m["uses_parent"] for m in post)
                print(f"  정리 스크립트가 부모 문서를 대상으로 주입됨 = {injected_cleanup}")
            else:
                print(f"    srcdoc을 못 읽었다: {post}")

        print("\n[7] 콘솔 메시지 (수정으로 추가한 진단 로그 포함)")
        hits = [c for c in console if "auth_banner" in c or "kakao_link" in c]
        for line in (hits or ["(없음)"]):
            print(f"  {line}")

        browser.close()

    print("\n[8] 판정")
    ok = True
    if saw_kakao_fn or saw_cleanup_fn:
        print("  OK: 배포본에 새 코드가 있다(srcdoc에 새 진단 로그 문자열이 보인다).")
    elif deployed_top and not deployed_parent:
        ok = False
        print("  NG: 배포본이 아직 옛 코드다(window.top) — 재배포가 안 끝났거나 실패했다.")
    else:
        print("  ?: 배포본 코드 판정 불가 — 아래 결과만 참고.")

    if not banner_shown:
        ok = False
        print("  NG: 배너가 안 떠서 ①·②를 확인하지 못했다(0건을 통과로 세지 않는다).")
    else:
        if isinstance(before, dict) and before.get("kakao_a", 0) > 0:
            if before.get("kakao_a_target", 0) == 0:
                print(f"  OK ②: 카카오 링크 target 제거됨 "
                      f"(a={before['kakao_a']}, target붙은것={before['kakao_a_target']})")
            else:
                ok = False
                print(f"  NG ②: target이 남아 있다 "
                      f"(a={before['kakao_a']}, target붙은것={before['kakao_a_target']})")
        else:
            print("  ? ②: 카카오 <a>가 없어 확인 불가(웹 분기·kakao_configured 확인 필요)")

        if isinstance(after, dict):
            left = {k: after.get(k) for k in KEY_COUNTS}
            if sum(v for v in left.values() if isinstance(v, int)) == 0:
                print(f"  OK ①: × 이후 잔재 0 {left}")
            else:
                ok = False
                print(f"  NG ①: × 이후에도 잔재가 남아 있다 {left} (클릭 전 {before})")

    print(f"\n최종 = {'확인 완료' if ok else '미확인 / 실패'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
