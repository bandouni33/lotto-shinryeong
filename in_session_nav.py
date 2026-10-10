"""화면 이동을 '새로 불러오기' 대신 '같은 세션 안에서 바꿔 그리기'로 하는 시험판 (2026-10-10).

배경(사용자 신고·영상): 메뉴를 누를 때마다 브라우저가 페이지를 통째로 새로 불러와
(새 세션·새 웹소켓·로그인 복원·전체 스크립트) 2~6초 동안 흰 화면→빈 화면→조각조각 그려짐이
보였다. 여기서는 링크 클릭을 가로채 숨은 버튼을 눌러 같은 세션 안에서 page 값만 바꾼다.

· 링크(<a href>) 자체·위치·모양은 그대로 둔다 — 스위치를 끄거나 숨은 버튼이 없으면 예전처럼
  그냥 링크로 이동한다(안전한 쪽으로 실패).
· 적용 화면은 ENABLED_PAGES 에 있는 화면끼리만(시험판: 메인 ↔ 자동조합).
· 앱 뒤로가기: 이동할 때 history 에 한 칸을 쌓아(pushState) 웹뷰 canGoBack 이 그대로 참이 되고,
  뒤로가기(popstate) 때 같은 방식으로 이전 화면을 다시 그린다.
· 화면 전환은 본문을 잠깐 투명하게 했다가 새 화면이 다 그려지면 다시 보이게 한다
  (그리는 도중의 섞인 화면이 안 보이게).
"""

from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components

# 켜고 끄는 스위치 — False 면 아무것도 그리지 않아 예전 방식(새로 불러오기)으로 동작한다.
IN_SESSION_NAV_ENABLED = True
# 같은 세션 안에서 오갈 화면(시험판). 늘릴 때는 여기만 고친다.
ENABLED_PAGES = ("main", "auto")
# 2026-10-10(실기기 영상 11:13·서버 기록 대조): 지금 깔린 안드로이드 빌드는 주소만 바뀌어도(pushState)
# 웹뷰가 '로드 시작'으로 보고 "불러오는 중" 화면을 띄운 뒤, 문서 로드 끝 신호가 안 와서 안전장치(6초)까지
# 그대로 덮어 둔다 — 같은 세션 이동은 1.7초에 끝났는데 화면은 6초 가려졌다. 그래서 앱 안에서는 이 처리를
# 아는 빌드(이 표시를 주소에 싣는 빌드)에서만 켠다. 일반 브라우저는 그대로 켠다.
APP_CAPABILITY_PARAM = "spa_nav"
_BUTTON_KEY_PREFIX = "ln_nav_go_"
_WRAP_KEY = "ln_nav_hidden_wrap"


def button_key(page: str) -> str:
    return f"{_BUTTON_KEY_PREFIX}{page}"


def _go(page: str) -> None:
    st.query_params["page"] = page


def render(current_page: str) -> None:
    """현재 화면이 대상이면 숨은 이동 버튼들과 클릭 가로채기 스크립트를 그린다."""
    if not IN_SESSION_NAV_ENABLED or current_page not in ENABLED_PAGES:
        return
    if st.query_params.get("native") == "1" and st.query_params.get(APP_CAPABILITY_PARAM) != "1":
        return  # 옛 앱 빌드 — 예전처럼 새로 불러오기(위 APP_CAPABILITY_PARAM 설명)
    with st.container(key=_WRAP_KEY):
        # 이 컨테이너는 통째로 숨긴다. 1.64 는 컨테이너를 stLayoutWrapper 로 한 겹 더 감싸므로
        # 그 겉껍데기까지 숨겨야 요소 간격(16px)이 생기지 않는다(로컬 실측).
        st.markdown(
            f"<style>.st-key-{_WRAP_KEY},"
            f'div[data-testid="stLayoutWrapper"]:has(> .st-key-{_WRAP_KEY}){{display:none !important;}}</style>',
            unsafe_allow_html=True,
        )
        for page in ENABLED_PAGES:
            if page == current_page:
                continue
            st.button(page, key=button_key(page), on_click=_go, args=(page,))
        components.html(_installer_html(), height=0)


def _installer_html() -> str:
    pages = json.dumps(list(ENABLED_PAGES))
    prefix = json.dumps(_BUTTON_KEY_PREFIX)
    # 스크립트는 앱 문서(window.parent)에 직접 심는다 — 이 iframe 은 화면이 바뀌면 사라지므로
    # 여기서 만든 리스너는 함께 죽는다. 앱 문서에 심은 스크립트는 페이지를 새로 불러오기 전까지 산다.
    body = """
(function(){
  if (window.__lnInSessionNav) return;
  window.__lnInSessionNav = true;
  var PAGES = __PAGES__, PREFIX = __PREFIX__;
  var doc = document;
  var st = doc.createElement('style');
  st.textContent =
    '[data-testid="stMain"]{transition:opacity .16s ease;}' +
    'html.ln-nav-leaving [data-testid="stMain"]{opacity:0 !important;}' +
    '#ln-nav-spinner{position:fixed;left:50%;top:42%;width:34px;height:34px;margin:-17px 0 0 -17px;' +
    'border-radius:50%;border:3px solid rgba(249,168,37,.25);border-top-color:#f9a825;z-index:99999;' +
    'opacity:0;pointer-events:none;transition:opacity .2s ease;animation:lnNavSpin .8s linear infinite;}' +
    'html.ln-nav-slow #ln-nav-spinner{opacity:1;}' +
    '@keyframes lnNavSpin{to{transform:rotate(360deg);}}';
  doc.head.appendChild(st);
  var sp = doc.createElement('div'); sp.id = 'ln-nav-spinner'; doc.body.appendChild(sp);

  function pageOf(search) {
    try { return new URLSearchParams(search).get('page') || 'main'; } catch (e) { return null; }
  }
  function btnFor(page) {
    return doc.querySelector('.st-key-' + PREFIX + page + ' button');
  }
  function appState() {
    var app = doc.querySelector('[data-testid="stApp"]');
    return app ? app.getAttribute('data-test-script-state') : null;
  }
  var pending = null;
  function finish() {
    if (!pending) return;
    clearTimeout(pending.slowTimer); clearTimeout(pending.failTimer);
    if (pending.obs) pending.obs.disconnect();
    pending = null;
    // 이 앱의 실제 스크롤 칸은 stMain 이다(로컬 실측) — 창과 함께 맨 위로 되돌린다.
    try { window.scrollTo(0, 0); } catch (e) {}
    try { var m = doc.querySelector('[data-testid="stMain"]'); if (m) m.scrollTop = 0; } catch (e) {}
    doc.documentElement.classList.remove('ln-nav-slow');
    requestAnimationFrame(function(){ doc.documentElement.classList.remove('ln-nav-leaving'); });
  }
  function go(page) {
    var b = btnFor(page);
    if (!b) return false;
    if (pending) finish();
    var root = doc.documentElement;
    root.classList.add('ln-nav-leaving');
    pending = { sawRunning: false };
    pending.slowTimer = setTimeout(function(){ root.classList.add('ln-nav-slow'); }, 350);
    // 안전장치: 끝 신호를 못 받아도 12초 뒤엔 화면을 다시 보이게 한다.
    pending.failTimer = setTimeout(finish, 12000);
    var app = doc.querySelector('[data-testid="stApp"]');
    if (app) {
      pending.obs = new MutationObserver(function(){
        if (!pending) return;
        var s = appState();
        if (s === 'running') pending.sawRunning = true;
        else if (pending.sawRunning && s === 'notRunning') finish();
      });
      pending.obs.observe(app, { attributes: true, attributeFilter: ['data-test-script-state'] });
    }
    b.click();
    return true;
  }
  doc.addEventListener('click', function(e){
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey) return;
    var a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
    if (!a || (a.target && a.target !== '_self')) return;
    var u;
    try { u = new URL(a.getAttribute('href'), window.location.href); } catch (err) { return; }
    if (u.origin !== window.location.origin || u.pathname !== window.location.pathname) return;
    var target = pageOf(u.search), here = pageOf(window.location.search);
    if (PAGES.indexOf(target) < 0 || PAGES.indexOf(here) < 0 || target === here) return;
    if (!btnFor(target)) return;
    e.preventDefault();
    try { history.pushState({ lnNav: target }, '', u.pathname + u.search); } catch (err) {}
    go(target);
  }, false);
  window.addEventListener('popstate', function(){
    var target = pageOf(window.location.search);
    if (PAGES.indexOf(target) < 0) { window.location.reload(); return; }
    if (!go(target)) window.location.reload();
  });
})();
"""
    body = body.replace("__PAGES__", pages).replace("__PREFIX__", prefix)
    return (
        "<script>(function(){try{var d=window.parent.document;"
        "if(d.__lnInSessionNavInjected)return;d.__lnInSessionNavInjected=true;"
        "var s=d.createElement('script');s.textContent="
        + json.dumps(body)
        + ";d.head.appendChild(s);}catch(e){try{console.error('[in_session_nav] '+(e&&e.message||e));}catch(e2){}}})();</script>"
    )
