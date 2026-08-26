
import streamlit as st
import streamlit.components.v1 as components
import base64
import os

if st.session_state.get("is_admin", False):
    with st.sidebar:
        st.markdown("## ⚙️ 관리자 제어 센터")
        if st.button("📊 대시보드로 바로가기", key="admin_sidebar_dash_6n36s5"):
            st.switch_page("admin_dashboard.py")

# ==========================================
# 1. 페이지 초기 설정 및 상태 관리
# ==========================================
st.set_page_config(page_title="로\u200b또신령", page_icon="K-325.jpg", layout="centered", initial_sidebar_state="collapsed")

from wallet_db import init_wallet_tables
from zero_phone_db import init_zero_phone_tables
from birthday_db import init_birthday_table
from auth_providers import handle_oauth_callback, restore_member_from_guest
from user_scope import init_guest_scope

init_wallet_tables()
init_zero_phone_tables()
init_birthday_table()
if handle_oauth_callback():
    st.rerun()
init_guest_scope()

# 네이티브 앱이 콜드 스타트(=완전히 껐다 다시 켬) 직후 최초 로드에만 ?fresh_start=1을
# 실어보낸다(LottoShinryeong/utils/fresh-start.ts 참고 — 백그라운드 전환/앱 내
# 화면 이동에서는 안 붙는다). 그 신호가 오면 이 기기의 자동 로그인 연결을 끊어서,
# 다음 줄의 restore_member_from_guest()가 조용히 다시 로그인시키지 않게 한다 —
# "앱 완전 종료 시 자동 로그아웃"이 되게 해달라는 요청. 다만 지금 비공개 테스트
# 중인 테스터들한테 매번 재로그인을 강제하면 번거로우니, 실제 카카오 인증이
# 붙는 정식 출시 전까지는 이 파라미터가 와도 무시한다(_testing_period_active
# 참고 — kakao_configured()가 켜지는 순간 자동으로 적용되기 시작함).
if st.query_params.get("fresh_start") == "1":
    del st.query_params["fresh_start"]
    from wallet_ui import _testing_period_active

    if not _testing_period_active():
        from user_scope import get_or_create_guest_id
        from wallet_db import unlink_guest_from_member

        unlink_guest_from_member(get_or_create_guest_id())

# 세션이 끊겼다 재연결되면(모바일 백그라운드 전환·네트워크 끊김 등) member_id가
# 사라져서 기능을 쓸 때마다 간편인증 배너가 다시 뜨는 문제가 있었다 — 이 기기
# (guest_id)가 이미 로그인한 적 있으면 인증 절차 없이 조용히 다시 로그인시킨다.
# (fresh_start로 방금 연결을 끊은 경우엔 이 호출이 찾을 게 없어 그냥 통과한다.)
restore_member_from_guest()

current_page = st.query_params.get("page", "main")

st.markdown(
    f'<style>:root{{--app-build:"{base64.b64encode(b"lotto-shinryeong|com.bandouni.lottoshinryeong").decode()}"}}</style>',
    unsafe_allow_html=True,
)

if current_page in ("main", "thunder", "auto", "stats", "birthday", "advanced", "tarot", "hedge"):
    # 자체 JS 핀치줌(frontend/components/pinch_zoom.py)은 여러 차례 시도했으나 실기기에서
    # 계속 문제가 있었다 — 타로 부채꼴 스프레드(iframe 안에서 렌더링됨) 페이지에서는
    # 이 커스텀 스크립트가 닿지 못해 네이티브 WebView 줌이 방해 없이 그대로 동작했는데,
    # 거기서 오히려 가장 잘 됐다는 피드백을 받았다. 즉 커스텀 스크립트가 메인 문서에서
    # 네이티브 줌을 가로채 더 나쁘게 만들고 있었을 가능성이 높아 제거하고 네이티브 줌
    # (streamlit-webview.tsx의 scalesPageToFit / setBuiltInZoomControls)에 맡긴다.
    #
    # 그런데도 실기기에서 핀치줌이 전혀 동작하지 않는다는 재현 확인 후 실제 배포된
    # 페이지(lotto-shinryeong.streamlit.app)의 DOM을 직접 열어 확인해보니, Streamlit이
    # 자체 번들 index.html에 <meta name="viewport" content="...,user-scalable=no">를
    # 하드코딩하고 있었다 — 우리 코드가 아니라 Streamlit 프레임워크 자체가 심어둔
    # 태그다. 이 속성은 브라우저 렌더링 엔진 단에서 핀치 제스처 자체를 인식하지 않게
    # 만들어서, WebView 쪽 setBuiltInZoomControls를 아무리 켜도 무시된다. Streamlit이
    # 만든 정적 태그라 파이썬 쪽에서 직접 고칠 수 없으니, 페이지 로드 시 JS로 그
    # meta 태그의 user-scalable=no/maximum-scale 제약을 지워 네이티브 핀치줌이
    # 실제로 동작하게 한다.
    components.html(
        """
        <script>
        (function() {
            const doc = window.parent.document;
            const meta = doc.querySelector('meta[name="viewport"]');
            if (meta) {
                meta.setAttribute('content', 'width=device-width, initial-scale=1, shrink-to-fit=no');
            }

            // 안티조합·액땜조합 페이지처럼 iframe 없이 순수 네이티브 Streamlit 위젯만으로
            // 만든 화면에서, 안드로이드 웹뷰/크롬이 "번개조합"·"액땜조합" 같은 신조어를
            // 자동번역 대상으로 오인해 영어로 번역했다가 다시 이상한 한국어로 표시하는
            // 현상이 있었다(예: "액땜조합"→"액용조합", "조합 생성"→"구성성분 생성").
            // 번역 자체를 아예 걸지 않도록 막는다.
            doc.documentElement.setAttribute('lang', 'ko');
            doc.documentElement.setAttribute('translate', 'no');
            if (!doc.querySelector('meta[name="google"]')) {
                const noTranslate = doc.createElement('meta');
                noTranslate.setAttribute('name', 'google');
                noTranslate.setAttribute('content', 'notranslate');
                doc.head.appendChild(noTranslate);
            }

            // 안드로이드 웹뷰의 강제 다크모드가 색을 직접 지정 안 한 요소(흰 배경
            // 버튼·셀렉트박스 등)를 임의로 반전시켜, 실기기에서 페이지 일부가
            // 텍스트/배경이 뒤섞여 안 보이거나 빈 공간처럼 보이는 문제가 있었다
            // (page_thunder.py 안 iframe에는 이미 적용했지만, 안티/액땜조합처럼
            // iframe 없이 순수 Streamlit 위젯으로만 만든 화면은 이 최상위 문서
            // 자체에 걸어야 한다). 앱 전체를 항상 라이트 배색으로 고정한다.
            doc.documentElement.style.colorScheme = 'light';
            if (!doc.querySelector('meta[name="color-scheme"]')) {
                const colorScheme = doc.createElement('meta');
                colorScheme.setAttribute('name', 'color-scheme');
                colorScheme.setAttribute('content', 'light');
                doc.head.appendChild(colorScheme);
            }

            // 네이티브 앱이 최초 로드 때 URL에 실어준 ?gid=...(AsyncStorage에 저장된
            // 게스트 식별자)는, 화면 안의 "메인으로"/메뉴 링크(page_auto.py의
            // href="?", user_page.py의 href="?page=auto" 등 순수 HTML <a> 태그)를
            // 누르는 순간 사라진다 — 그 링크들은 애초에 gid를 몰라서 못 붙여준다.
            // 그러면 다음 페이지는 gid 없이 렌더링되고, 구매내역/타로 제한이
            // (네이티브 앱이 아직 안 보내던 시절과 똑같이) 쿠키 폴백으로 되돌아가
            // 버린다. 클릭 시점에 현재 URL의 gid를 읽어 그 링크의 href에 실시간으로
            // 붙여줘서, 앱 안에서 어떤 링크를 눌러도 게스트 식별자가 계속 이어지게 한다.
            function currentGid() {
                const m = doc.location.search.match(/[?&]gid=([^&]*)/);
                return m ? m[1] : null;
            }
            // 이 컴포넌트는 st.rerun()마다 다시 렌더링되는데, 매번 새 리스너를 doc에
            // 계속 쌓지 않도록 한 세션(같은 top-level document)에는 한 번만 붙인다.
            if (!doc.__gidLinkPatchBound) {
                doc.__gidLinkPatchBound = true;
                doc.addEventListener('click', function(e) {
                    const gid = currentGid();
                    if (!gid) return;
                    const a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
                    if (!a) return;
                    const href = a.getAttribute('href') || '';
                    if (!href || /^https?:\\/\\//i.test(href) || href.indexOf('gid=') !== -1) return;
                    const sep = href.endsWith('?') ? '' : (href.indexOf('?') === -1 ? '?' : '&');
                    a.setAttribute('href', href + sep + 'gid=' + encodeURIComponent(gid));
                }, true);
            }
        })();
        </script>
        """,
        height=0,
    )

    from wallet_ui import render_wallet_bar

    render_wallet_bar(show_my_info_trigger=(current_page == "main"))

    from app_settings import get_update_notice
    import html as _html

    _update_notice = get_update_notice()
    # 메인화면에서만 노출한다 — 예전엔 이 블록이 모든 페이지 공통 영역에 있어서
    # 화면을 옮길 때마다(자동구매→메인→자동구매 등) 계속 다시 떴다.
    if current_page == "main" and _update_notice["version"]:
        _un_version = _update_notice["version"]
        _un_message = _html.escape(_update_notice["message"])
        _un_url = _update_notice["url"]

        # "오늘 이미 봤는지"를 서버 DB에서 guest_id 기준으로 먼저 확인한다 — 예전엔
        # 클라이언트 쿠키/localStorage로만 판단했는데, 이 앱은 화면마다 안드로이드
        # 웹뷰가 통째로 새로 생성되는 구조라 방금 쓴 쿠키가 디스크에 저장되기 전에
        # 다음 화면으로 넘어가버리면 유실돼서 "몇 번을 눌러도 또 뜨는" 문제로
        # 이어졌다. 구매내역·타로 제한과 동일한 guest_id+DB 방식으로 바꿔 그 타이밍
        # 문제 자체를 없앤다.
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from user_scope import get_or_create_guest_id
        from marketing_db import (
            init_marketing_tables,
            mark_guest_update_notice_shown,
            was_guest_update_notice_shown_today,
        )

        init_marketing_tables()
        _un_guest_id = get_or_create_guest_id()
        _un_today = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")
        _un_already_shown = was_guest_update_notice_shown_today(_un_guest_id, _un_version, _un_today)

        if not _un_already_shown:
          mark_guest_update_notice_shown(_un_guest_id, _un_version, _un_today)

          # TODO(update-banner-link): 앱(React Native WebView)에서 target="_blank"가 새 탭이
          # 아니라 이 웹뷰 안에서 그대로 열림 — LottoShinryeong/components/streamlit-webview.tsx
          # 참고. update_url에 APK 직링크를 넣으면 다운로드가 안 될 수 있음.
          # 두 조각으로 나뉜 알약 모양 배지 — 왼쪽(메시지)을 누르면 "다음에"(닫기)와
          # 동일하게 동작하고, 오른쪽(금색 버튼)만 실제 업데이트 링크로 이동한다.
          if _un_url:
            _un_btn_html = (
                f'<a class="update-toast-btn-seg" id="update-toast-now-6n36s5" '
                f'href="{_html.escape(_un_url, quote=True)}" target="_blank" rel="noopener">'
                f'업데이트<span class="update-toast-chevron">›</span></a>'
            )
          else:
            _un_btn_html = (
                '<span class="update-toast-btn-seg update-toast-btn-seg-disabled">'
                '업데이트<span class="update-toast-chevron">›</span></span>'
            )

          st.markdown(
            f"""
            <div class="update-toast" id="update-toast-6n36s5">
                <button type="button" class="update-toast-msg-seg" id="update-toast-later-6n36s5">{_un_message}</button>
                {_un_btn_html}
            </div>
            """,
            unsafe_allow_html=True,
          )

          components.html(
            f"""
            <script>
            (function() {{
                const doc = window.parent.document;
                const version = {_un_version!r};

                // 이 iframe의 스크립트는 옆의 배너 <div>(별도의 st.markdown 호출로 그려짐)보다
                // 먼저 실행될 수 있다 — React가 그 div를 아직 DOM에 붙이기 전이면
                // getElementById가 null을 반환하는데, 예전엔 그러면 그냥 조용히 포기하고
                // 다시 시도하지 않아서 배너가 아예 안 뜨는(그리고 "확인함" 기록도 못 남기는)
                // 경우가 있었다 — haptic.py와 같은 재시도 패턴으로 고친다.
                let tries = 0;
                const MAX_TRIES = 15;
                const timer0 = window.setInterval(function() {{
                    tries += 1;
                    const ok = boot();
                    if (ok || tries >= MAX_TRIES) window.clearInterval(timer0);
                }}, 300);
                boot();

                function boot() {{
                const toast = doc.getElementById('update-toast-6n36s5');
                if (!toast || toast.dataset.toastInit === '1') return !!toast;
                toast.dataset.toastInit = '1';

                if (!doc.getElementById('update-toast-style')) {{
                    const style = doc.createElement('style');
                    style.id = 'update-toast-style';
                    style.textContent = `
                        .update-toast {{
                            position: fixed;
                            top: 14px;
                            left: 50%;
                            z-index: 9999;
                            display: flex;
                            width: max-content;
                            max-width: min(92vw, 320px);
                            border-radius: 999px;
                            overflow: hidden;
                            box-shadow: 0 14px 32px rgba(0, 0, 0, 0.35);
                            opacity: 0;
                            visibility: hidden;
                            pointer-events: none;
                            transform: translate(-50%, -10px) scale(0.96);
                            transition: opacity 0.35s cubic-bezier(.2,.8,.3,1.15),
                                        transform 0.35s cubic-bezier(.2,.8,.3,1.15),
                                        visibility 0.35s;
                        }}
                        .update-toast.show {{
                            opacity: 1;
                            visibility: visible;
                            pointer-events: auto;
                            transform: translate(-50%, 0) scale(1);
                        }}
                        .update-toast-msg-seg {{
                            display: flex;
                            align-items: center;
                            padding: 10px 16px;
                            background: #efe1bd;
                            color: #1c2540;
                            font-size: 13px;
                            font-weight: 800;
                            letter-spacing: -0.01em;
                            white-space: nowrap;
                            border: none;
                            cursor: pointer;
                        }}
                        .update-toast-btn-seg {{
                            display: flex;
                            align-items: center;
                            gap: 1px;
                            padding: 10px 16px;
                            background: linear-gradient(180deg, #e8c470 0%, #d9a94f 100%);
                            color: #1c2540;
                            font-size: 13px;
                            font-weight: 800;
                            white-space: nowrap;
                            text-decoration: none;
                            cursor: pointer;
                        }}
                        .update-toast-btn-seg-disabled {{
                            opacity: 0.5;
                            pointer-events: none;
                        }}
                        .update-toast-chevron {{
                            font-size: 14px;
                        }}
                    `;
                    doc.head.appendChild(style);
                }}

                // "오늘 이미 봤는지"는 렌더링 전에 서버(guest_id+DB)에서 이미 걸러졌으니,
                // 여기서는 "업데이트"를 눌러 완전히 끝낸 사람만 이 버전에 대해 다시 안
                // 뜨도록 최소한으로 기록한다(최선 노력 — 외부 링크로 바로 이동하는
                // 클릭이라 100% 보장은 못 하지만, 매번 뜨던 예전보다는 훨씬 낫다).
                function getCookie(name) {{
                    const m = doc.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
                    return m ? decodeURIComponent(m[1]) : null;
                }}
                function setCookie(name, value) {{
                    doc.cookie = name + '=' + encodeURIComponent(value) + '; max-age=31536000; path=/';
                }}
                const foreverKey = 'update_ack_forever';
                if (getCookie(foreverKey) === version) return true;

                function dismiss() {{
                    toast.classList.remove('show');
                }}

                toast.classList.add('show');
                const timer = window.setTimeout(dismiss, 6000);

                const laterBtn = doc.getElementById('update-toast-later-6n36s5');
                if (laterBtn) {{
                    laterBtn.addEventListener('click', function() {{
                        window.clearTimeout(timer);
                        dismiss();
                    }});
                }}
                const nowBtn = doc.getElementById('update-toast-now-6n36s5');
                if (nowBtn) {{
                    nowBtn.addEventListener('click', function() {{
                        setCookie(foreverKey, version);
                    }});
                }}
                return true;
                }}
            }})();
            </script>
            """,
            height=0,
        )

# ===============================================================================
# ⚠️⚠️⚠️ [관리자 필수 확인] 매주 이 숫자 6개를 직접 수정하세요 ⚠️⚠️⚠️
# 앞 번호일수록 유력한 순서로 입력 (예: 44가 가장 유력, 7이 가장 약함)
# ⚠️⚠️⚠️ 다른 코드는 건드리지 말고 이 줄의 숫자만 바꾸세요 ⚠️⚠️⚠️
lucky_display = [41, 26, 17, 33, 32, 5]
# ===============================================================================

def get_image_base64(file_path):
    if os.path.exists(file_path):
        with open(file_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    return ""

icon_base64 = get_image_base64("K-325.jpg")


# ==========================================
# 📺 화면 1: 메인 페이지 (Main View) - 🎨 모바일 앱 고급 UI 적용 완료
# ==========================================
if current_page == "main":
    st.markdown("""
    <style>
        .stApp { background-color: #12182b; color: white; }
        html, body, #root, .stApp, [data-testid="stAppViewContainer"],
        [data-testid="stAppViewContainer"] > section.main {
            overflow-x: hidden !important;
        }
        .block-container { padding-top: 5px !important; padding-bottom: 0px !important; padding-left: 12px !important; padding-right: 12px !important; max-width: 600px; }
        section[data-testid="stSidebar"] { display: none; }
        header[data-testid="stHeader"] { display: none; }
        div[data-testid="stVerticalBlock"] { gap: 0.35rem !important; }

        div[data-columns="true"] {
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            align-items: center !important;
            gap: 6px !important;
            width: 100% !important;
        }
        div[data-testid="stColumn"] { padding: 0px !important; margin: 0px !important; }

        .st-key-main_rank_row_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] {
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            align-items: center !important;
            justify-content: flex-start !important;
            gap: 10px !important;
            width: 100% !important;
            box-sizing: border-box !important;
        }
        .st-key-main_rank_row_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:nth-child(1) {
            flex: 1 1 0 !important;
            min-width: 0 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: flex-start !important;
        }
        .st-key-main_rank_row_6n36s5 > div[data-testid="stLayoutWrapper"] > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:nth-child(2) {
            flex: 0 0 auto !important;
            min-width: 0 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: flex-end !important;
        }
    </style>
    """, unsafe_allow_html=True)

    # 엑셀에서 데이터 가져오기
    try:
        from lotto_stats import load_lotto_data

        df = load_lotto_data()
        row = df.iloc[0].tolist()
        draw_no = str(row[1]).replace(".0", "") + "회" 
        numbers = sorted([int(x) for x in row[3:9]])
        import re
        bonus_val = int(re.sub(r'[^0-9]', '', str(row[9])))
    except Exception as e:
        draw_no = "오류"
        numbers = [3, 8, 9, 22, 28, 42]
        bonus_val = 45

    # 상단 로고 + 회전 볼 오버레이

    def get_ball_color(n):
        if 1 <= n <= 10: return "#f9a825"
        if 11 <= n <= 20: return "#1976d2"
        if 21 <= n <= 30: return "#e53935"
        if 31 <= n <= 40: return "#757575"
        return "#388e3c"

    balls_css = ""
    for i, num in enumerate(lucky_display):
        angle = i * 30
        color = get_ball_color(num)
        balls_css += f"""
        .orbit-ball-{i} {{
            position: absolute; width: 30px; height: 30px; border-radius: 50%;
            background: radial-gradient(circle at 35% 35%, {color}, #000);
            display: flex; align-items: center; justify-content: center;
            color: white; font-weight: 900; font-size: 15px;
            text-shadow: 1px 1px 2px rgba(0,0,0,0.8);
            box-shadow: 2px 3px 5px rgba(0,0,0,0.6), inset 2px 2px 4px rgba(255,255,255,0.4);
            top: 50%; left: 50%;
            margin-top: -11px; margin-left: -11px;
            animation: orbit{i} 6s linear infinite;
        }}
        @keyframes orbit{i} {{
            from {{ transform: rotate({angle}deg) translateX(82px) rotate(-{angle}deg); }}
            to {{ transform: rotate({angle + 360}deg) translateX(82px) rotate(-{angle + 360}deg); }}
        }}
        """


    st.markdown(f"""
    <style>
        @keyframes orbitSpin {{
            0% {{ transform: rotate({0}deg) translateY(-52px) rotate(-{0}deg); opacity: 0.7; }}
            50% {{ opacity: 1; transform: rotate(180deg) translateY(-52px) rotate(-180deg); }}
            100% {{ transform: rotate(360deg) translateY(-52px) rotate(-360deg); opacity: 0.7; }}
        }}
        @keyframes glowPulse {{
            0%, 100% {{ box-shadow: 0 0 15px rgba(255,179,0,0.8), 0 0 30px rgba(255,179,0,0.4); }}
            50% {{ box-shadow: 0 0 25px rgba(255,179,0,1), 0 0 50px rgba(255,179,0,0.6); }}
        }}
        .logo-wrapper {{
            position: relative; width: 175px; height: 175px; margin: 0 auto;
            z-index: 1;
        }}
        /* HERO_BRAND_ANIM: butterfly-fly — 롤백: user_page.py.bak-hero-spirit-mirage 복사 */
        .hero-with-brand {{
            position: relative;
            text-align: center;
            min-height: 198px;
            padding: 16px 0 20px 0;
            margin-top: -5px;
            margin-left: auto;
            margin-right: auto;
            max-width: 360px;
            overflow: hidden;
            box-sizing: border-box;
        }}
        .app-name-fly {{
            position: absolute;
            left: 50%;
            top: 30px;
            width: max-content;
            margin: 0;
            padding: 0;
            z-index: 4;
            pointer-events: none;
            font-size: 26px;
            font-weight: 800;
            line-height: 1;
            letter-spacing: 0.14em;
            white-space: nowrap;
            display: flex;
            flex-direction: row;
            align-items: center;
            gap: 5px;
            will-change: transform, opacity, filter;
            animation: spiritButterflyPath 20s ease-in-out infinite;
        }}
        .app-name-fly span {{
            display: inline-block;
            transform-origin: center center;
            opacity: 0;
            background: linear-gradient(180deg, rgba(255,255,255,0.45) 0%, rgba(255,255,255,0.92) 42%, rgba(200,225,255,0.85) 58%, rgba(255,255,255,0.4) 100%);
            background-size: 100% 220%;
            -webkit-background-clip: text;
            background-clip: text;
            -webkit-text-fill-color: transparent;
            animation: spiritCharShimmer 3.6s ease-in-out infinite,
                       spiritCharCycle 20s ease-in-out infinite,
                       spiritWingFlutter 1.1s ease-in-out infinite;
        }}
        .app-name-fly span:nth-child(1) {{ animation-delay: 0s, 0s, 0s; }}
        .app-name-fly span:nth-child(2) {{ animation-delay: 0.12s, 0.2s, 0.06s; }}
        .app-name-fly span:nth-child(3) {{ animation-delay: 0.24s, 0.4s, 0.12s; }}
        .app-name-fly span:nth-child(4) {{ animation-delay: 0.36s, 0.6s, 0.18s; }}
        @keyframes spiritButterflyPath {{
            0%, 100% {{
                transform: translate(calc(-50% - 150px), 0px) rotate(-3deg);
            }}
            8% {{
                transform: translate(calc(-50% - 118px), -7px) rotate(2deg);
            }}
            14% {{
                transform: translate(calc(-50% - 88px), 5px) rotate(-2deg);
            }}
            20% {{
                transform: translate(calc(-50% - 58px), -11px) rotate(3deg);
            }}
            26% {{
                transform: translate(calc(-50% - 28px), 10px) rotate(-3deg);
            }}
            32% {{
                transform: translate(calc(-50% + 2px), -12px) rotate(2deg);
            }}
            38% {{
                transform: translate(calc(-50% + 32px), 9px) rotate(-2deg);
            }}
            44% {{
                transform: translate(calc(-50% + 62px), -11px) rotate(3deg);
            }}
            50% {{
                transform: translate(calc(-50% + 92px), 8px) rotate(-2deg);
            }}
            56% {{
                transform: translate(calc(-50% + 118px), -9px) rotate(2deg);
            }}
            62% {{
                transform: translate(calc(-50% + 138px), 5px) rotate(-1deg);
            }}
            68% {{
                transform: translate(calc(-50% + 152px), -4px) rotate(1deg);
            }}
            76% {{
                transform: translate(calc(-50% + 158px), 0px) rotate(0deg);
            }}
            84% {{
                transform: translate(calc(-50% + 158px), 0px) rotate(0deg);
            }}
            90%, 100% {{
                transform: translate(calc(-50% - 150px), 0px) rotate(-3deg);
            }}
        }}
        @keyframes spiritCharCycle {{
            /* ── 등장 ── */
            0%, 100% {{
                opacity: 0;
                filter: blur(2.5px);
            }}
            4% {{
                opacity: 0.4;
                filter: blur(1.2px);
            }}
            8% {{
                opacity: 1;
                filter: blur(0);
            }}
            /* ── 비행 중 아지랭이 (희미 ↔ 선명 반복) ── */
            12% {{ opacity: 0.95; filter: blur(0); }}
            15% {{ opacity: 0.1; filter: blur(2.2px); }}
            18% {{ opacity: 0.92; filter: blur(0.2px); }}
            22% {{ opacity: 0.14; filter: blur(2px); }}
            25% {{ opacity: 1; filter: blur(0); }}
            29% {{ opacity: 0.08; filter: blur(2.4px); }}
            32% {{ opacity: 0.88; filter: blur(0.3px); }}
            36% {{ opacity: 0.16; filter: blur(1.9px); }}
            39% {{ opacity: 0.98; filter: blur(0); }}
            43% {{ opacity: 0.11; filter: blur(2.1px); }}
            46% {{ opacity: 0.9; filter: blur(0.25px); }}
            50% {{ opacity: 0.18; filter: blur(1.7px); }}
            53% {{ opacity: 1; filter: blur(0); }}
            57% {{ opacity: 0.12; filter: blur(2px); }}
            60% {{ opacity: 0.93; filter: blur(0.15px); }}
            64% {{ opacity: 0.2; filter: blur(1.5px); }}
            67% {{ opacity: 0.82; filter: blur(0.4px); }}
            /* ── 소멸 ── */
            71% {{ opacity: 0.6; filter: blur(0.7px); }}
            75% {{ opacity: 0.28; filter: blur(1.5px); }}
            79% {{ opacity: 0.08; filter: blur(2.4px); }}
            83% {{ opacity: 0; filter: blur(2.8px); }}
            /* ── 쉼 (재등장 전) ── */
            90%, 98% {{
                opacity: 0;
                filter: blur(2.5px);
            }}
        }}
        @keyframes spiritWingFlutter {{
            0%, 100% {{ transform: translateY(0px); }}
            50% {{ transform: translateY(-2px); }}
        }}
        @keyframes spiritCharShimmer {{
            0%, 100% {{ background-position: 0% 22%; }}
            50% {{ background-position: 0% 82%; }}
        }}
        .logo-img {{
            width: 105px; height: 105px; border-radius: 50%; border: 3px solid #ffb300;
            position: absolute; top: calc(50% - 1px); left: calc(50% - 1px); transform: translate(-50%, -50%);
            object-fit: cover; animation: glowPulse 2s infinite;
        }}
        {balls_css}
    </style>
    <div class="hero-with-brand">
        <div class="logo-wrapper">
            <img class="logo-img" src="data:image/jpeg;base64,{icon_base64}">
            <div class="orbit-ball-0">{lucky_display[0]}</div>
            <div class="orbit-ball-1">{lucky_display[1]}</div>
            <div class="orbit-ball-2">{lucky_display[2]}</div>
            <div class="orbit-ball-3">{lucky_display[3]}</div>
            <div class="orbit-ball-4">{lucky_display[4]}</div>
            <div class="orbit-ball-5">{lucky_display[5]}</div>
        </div>
        <p class="app-name-fly" aria-label="로또신령">
            <span>로</span><span>또</span><span>신</span><span>령</span>
        </p>
    </div>
    """, unsafe_allow_html=True)

    # 🟢 1. 로또볼 디자인 (3D 입체감 & 크기 확대)
    col1 = st.columns([1])[0]
    with col1:
        def get_ball_style(n):
            if 1 <= n <= 10: return "background: radial-gradient(circle at 35% 35%, #ffeb3b, #f9a825, #f57f17);"
            if 11 <= n <= 20: return "background: radial-gradient(circle at 35% 35%, #4fc3f7, #1976d2, #0d47a1);"
            if 21 <= n <= 30: return "background: radial-gradient(circle at 35% 35%, #ef5350, #e53935, #b71c1c);"
            if 31 <= n <= 40: return "background: radial-gradient(circle at 35% 35%, #bdbdbd, #757575, #424242);"
            return "background: radial-gradient(circle at 35% 35%, #81c784, #388e3c, #1b5e20);"

        # 34px 공 6개 + 보너스공 + 라벨을 고정폭으로 한 줄에 다 넣으면 합계가
        # 약 475px에 달해, 실제 폰 화면(보통 360~412dp)에서는 항상 넘쳐서
        # "+ 보너스공"이 화면 밖으로 잘려 안 보이는 문제가 있었다(overflow-x:hidden을
        # 상위에 걸어둔 뒤로는 스크롤도 안 돼서 아예 안 보이기만 했다). 공 크기를
        # 좁혀도 라벨과 한 줄로 나란히 두면 폭 계산이 미묘하게 계속 빠듯했어서,
        # 아예 라벨을 위 줄로 올리고 공들만 따로 한 줄로 뺐다 — 공 6개+보너스공만
        # 합쳐도 ~210px이라 어떤 폰 폭에도 넉넉히 들어간다. 그래도 만약을 대비해
        # 이 줄만 별도로 가로 스크롤 가능하게 해서 최소한 잘려서 안 보이는 일은 없게 한다.
        _ball_css = (
            "width:26px; height:26px; border-radius:50%; display:flex; align-items:center; "
            "justify-content:center; color:white; font-weight:900; font-size:12px; "
            "flex-shrink:0; box-shadow: 2px 3px 5px rgba(0,0,0,0.5), inset -3px -3px 5px rgba(0,0,0,0.4), "
            "inset 2px 2px 4px rgba(255,255,255,0.6); text-shadow: 1px 1px 2px rgba(0,0,0,0.8);"
        )
        balls_html = "".join([f'<div style="{get_ball_style(n)} {_ball_css} margin-right:4px;">{n}</div>' for n in numbers])

        st.markdown(f"""
        <div style="background: linear-gradient(145deg, #1c2645, #12182b); border-radius:16px; padding:10px 12px; border: 1px solid #2a3a60; box-shadow: 0 6px 12px rgba(0,0,0,0.5); margin-bottom: 12px; max-width: 100%; box-sizing: border-box;">
            <div style="color:#ffb300; font-size:12.5px; font-weight:900; line-height:1; letter-spacing:-0.3px; margin-bottom: 8px; text-align:center;">최근당첨번호 <span style="color:#fff;">{draw_no}</span></div>
            <div style="display:flex; align-items:center; justify-content:center; max-width: 100%; overflow-x: auto;">
                {balls_html}
                <span style="color:#aaa; font-weight:900; font-size:16px; margin: 0 4px; flex-shrink:0;">+</span>
                <div style="{get_ball_style(bonus_val)} {_ball_css}">{bonus_val}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # 🟢 2. 하단 4버튼 메뉴 (모바일 앱 스타일, 강한 햅틱 진동 추가)
    st.markdown("""
    <style>
    .menu-grid { display: grid; grid-template-columns: 1fr 1fr; grid-auto-rows: 1fr; gap: 10px; margin-top: 7px; }
    .menu-grid > a { display: flex; min-height: 0; }
    
    .menu-box { 
        background: linear-gradient(145deg, #1c2645, #101628); 
        border-radius: 20px; 
        padding: 18px 10px; 
        min-height: 118px;
        width: 100%;
        flex: 1;
        box-sizing: border-box;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        text-align: center; 
        box-shadow: 6px 8px 16px rgba(0,0,0,0.6), inset 1px 1px 2px rgba(255,255,255,0.1); 
        cursor: pointer; 
        transition: all 0.1s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
    }
    
    /* ⚡ 터치 시 강하게 눌리는 입체 효과 */
    .menu-box:active { 
        transform: scale(0.93) translateY(4px); 
        box-shadow: 2px 3px 6px rgba(0,0,0,0.6), inset 4px 6px 12px rgba(0,0,0,0.8), inset -2px -2px 6px rgba(255,255,255,0.05); 
    }
    
    /* 3D 느낌의 크고 선명한 이모티콘 */
    .menu-icon { font-size: 36px; margin-bottom: 8px; line-height: 1; filter: drop-shadow(2px 4px 6px rgba(0,0,0,0.5)); }
    /* "안티조합 · 액땜조합"처럼 긴 제목이 좁은 카드 폭에서 "안티조/합"처럼 글자
       중간에서 줄바꿈되던 버그(2026-08-22 실기기 스크린샷 확인) — 한글은 기본
       word-break 규칙상 아무 글자 사이에서나 끊길 수 있어서, 단어(어절) 경계
       에서만 끊기도록 명시한다. nowrap은 이 제목엔 너무 길어 오히려 잘려
       보일 수 있어 쓰지 않는다. */
    .menu-title { color: #ffffff; font-weight: 900; font-size: 16px; margin-bottom: 2px; letter-spacing: 0.5px; word-break: keep-all; }
    .menu-sub { color: #9aa5b1; font-size: 13px; font-weight: 600; min-height: 18px; line-height: 18px; }
    
    /* 테두리 글로우 효과 */
    .gold { border: 2px solid rgba(255, 179, 0, 0.7); }
    .blue { border: 2px solid rgba(41, 182, 246, 0.7); }
    .green { border: 2px solid rgba(102, 187, 106, 0.7); }
    .purple { border: 2px solid rgba(171, 71, 188, 0.7); }
    /* 안티조합·액땜조합 — 방패 아이콘에 은은한 금빛 광채를 더해 고급스러운 느낌 */
    .shield { border: 2px solid rgba(226, 194, 120, 0.75); }
    .menu-box.shield .menu-icon {
        filter: drop-shadow(0 0 7px rgba(255, 221, 150, 0.65)) drop-shadow(2px 4px 6px rgba(0,0,0,0.5));
    }

    /* 통계센터 — 4박스 그리드에서 빼서 타로 배너와 같은 폭의 알약형 단독 줄로 */
    .stats-unit { width: 88%; max-width: 88%; margin: 12px auto 0; }
    .stats-box {
        background: linear-gradient(145deg, #142a22, #0f1c22);
        border: 2px solid rgba(102, 187, 106, 0.6);
        border-radius: 20px;
        padding: 9px 8px;
        min-height: 48px;
        width: 100%;
        max-width: 100%;
        box-sizing: border-box;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        text-align: center;
        box-shadow: 6px 8px 16px rgba(0,0,0,0.6), inset 1px 1px 2px rgba(255,255,255,0.1);
        cursor: pointer;
        transition: all 0.1s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .stats-box:active {
        transform: scale(0.93) translateY(4px);
        box-shadow: 2px 3px 6px rgba(0,0,0,0.6), inset 4px 6px 12px rgba(0,0,0,0.8), inset -2px -2px 6px rgba(255,255,255,0.05);
    }
    .stats-icon { font-size: 21px; line-height: 1; filter: drop-shadow(2px 4px 6px rgba(0,0,0,0.5)); }
    .stats-title { color: #ffffff; font-weight: 900; font-size: 13px; letter-spacing: 0.5px; }

    .tarot-unit {
        width: 88%;
        max-width: 88%;
        margin: 35px auto 35px;
        transform: translateX(-2%) translateX(-12px);
    }
    .tarot-box {
        position: relative;
        background: linear-gradient(145deg, #2a1c45, #161028);
        border: 2px solid rgba(186, 104, 200, 0.7);
        border-radius: 20px;
        padding: 9px 8px;
        min-height: 48px;
        width: 100%;
        max-width: 100%;
        box-sizing: border-box;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        text-align: center;
        box-shadow: 6px 8px 16px rgba(0,0,0,0.6), inset 1px 1px 2px rgba(255,255,255,0.1);
        cursor: pointer;
        transition: all 0.1s cubic-bezier(0.4, 0, 0.2, 1);
        margin-top: 0px;
    }
    .tarot-box:active {
        transform: scale(0.93) translateY(4px);
        box-shadow: 2px 3px 6px rgba(0,0,0,0.6), inset 4px 6px 12px rgba(0,0,0,0.8), inset -2px -2px 6px rgba(255,255,255,0.05);
    }
    .tarot-icon { font-size: 21px; line-height: 1; filter: drop-shadow(2px 4px 6px rgba(0,0,0,0.5)); }
    .tarot-title { color: #ffffff; font-weight: 900; font-size: 13px; letter-spacing: 0.5px; }
    </style>

<div class="tarot-unit">
    <a href="?page=tarot" target="_self" class="tarot-link" style="text-decoration:none; display:block;">
        <div class="tarot-box" id="tarot-box-6n36s5">
            <div class="tarot-icon">🔮</div>
            <div class="tarot-title">삶이 지치고 힘들 때 신비로운 타로 점</div>
        </div>
    </a>
</div>
<div class="menu-grid">
    <a href="?page=auto" target="_self" style="text-decoration:none; display:block;">
        <div class="menu-box purple">
            <div class="menu-icon">💎</div>
            <div class="menu-title">자동구매</div>
            <div class="menu-sub">자동 발송</div>
        </div>
    </a>
    <a href="?page=thunder&fresh=1" target="_self" style="text-decoration:none; display:block;">
        <div class="menu-box gold">
            <div class="menu-icon">⚡</div>
            <div class="menu-title">번\u200b\u200b개조합</div>
            <div class="menu-sub">빠른 조합</div>
        </div>
    </a>
    <a href="?page=hedge" target="_self" style="text-decoration:none; display:block;">
        <div class="menu-box shield">
            <div class="menu-icon">🛡️</div>
            <div class="menu-title">안티조합 · 액땜조합</div>
            <div class="menu-sub">안 겹치는 조합</div>
        </div>
    </a>
    <a href="?page=advanced" target="_self" style="text-decoration:none; display:block;">
        <div class="menu-box blue">
            <div class="menu-icon">👑</div>
            <div class="menu-title">고급필터</div>
            <div class="menu-sub">전문가 분석용</div>
        </div>
    </a>
</div>
<div class="stats-unit">
    <a href="?page=stats" target="_self" class="stats-link" style="text-decoration:none; display:block;">
        <div class="stats-box">
            <div class="stats-icon">📊</div>
            <div class="stats-title">통계센터 · 데이터분석</div>
        </div>
    </a>
</div>
    """, unsafe_allow_html=True)

    components.html("""
    <script>
    (function() {
        function safeVibrate() {
            if (typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function') {
                try { navigator.vibrate(70); } catch (e) {}
            }
        }
        const doc = window.parent.document;

        doc.querySelectorAll('.menu-grid a, .tarot-link, .stats-link').forEach(function(el) {
            if (el.dataset.mainVibrateBound) return;
            el.dataset.mainVibrateBound = '1';
            el.addEventListener('click', safeVibrate, { passive: true });
        });
    })();
    </script>
    """, height=0)

    # 타로 카드 장식 이미지 (버튼 밖으로 살짝 삐져나오는 고정 데코레이션)
    tarot_card_deco_base64 = get_image_base64(os.path.join("tarot", "images", "major_17.jpg"))
    if tarot_card_deco_base64:
        components.html(f"""
        <script>
        (function() {{
            const doc = window.parent.document;
            if (!doc.getElementById('tarot-card-deco-style')) {{
                const style = doc.createElement('style');
                style.id = 'tarot-card-deco-style';
                style.textContent = `
                    .tarot-card-deco {{
                        position: absolute;
                        top: 50%;
                        right: -28px;
                        width: 36px;
                        height: auto;
                        border-radius: 6px;
                        border: 1px solid rgba(255, 193, 7, 0.4);
                        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
                        transform: translateY(-50%) rotate(13deg);
                        z-index: 5;
                        pointer-events: none;
                    }}
                `;
                doc.head.appendChild(style);
            }}
            const box = doc.getElementById('tarot-box-6n36s5');
            if (box && !box.querySelector('.tarot-card-deco')) {{
                const img = doc.createElement('img');
                img.className = 'tarot-card-deco';
                img.src = 'data:image/jpeg;base64,{tarot_card_deco_base64}';
                img.alt = '';
                box.appendChild(img);
            }}
        }})();
        </script>
        """, height=0)

    # 역대 최고 당첨금 (좌: 순위+금액 박스 / 우: 더보러가기 박스, 분리)
    # — 메인화면 첫인상이 어수선해 보인다는 피드백으로, 상단(최근당첨번호 바로 아래)에서
    # 버튼 그리드(자동구매 등) 아래로 옮겼다. 다른 레이아웃·버튼 기능은 그대로다.
    main_rank_row = st.container(key="main_rank_row_6n36s5")
    col_info, col_btn = main_rank_row.columns([2, 1])
    with col_info:
        st.markdown("""
        <div id="rank-top1-trigger-6n36s5" style="height:32px; box-sizing:border-box; display:flex; align-items:center; justify-content:space-between; gap:8px; width:100%; padding:0 10px; background: linear-gradient(145deg, #1c2645, #12182b); border-radius:10px; border:1px solid #2a3a60; box-shadow: 0 3px 6px rgba(0,0,0,0.35);">
            <span style="color:#b0bec5; font-size:13px; font-weight:bold; letter-spacing:-0.3px; line-height:1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">🏆 역대 최고 당첨 금액 순위</span>
            <div style="display:flex; align-items:center; gap:6px; white-space:nowrap; flex-shrink:0;">
                <div style="background: radial-gradient(circle at 35% 35%, #ef5350, #e53935, #b71c1c); width:18px; height:18px; border-radius:50%; text-align:center; line-height:18px; color:white; font-weight:bold; font-size:11px; box-shadow: 1px 2px 3px rgba(0,0,0,0.5); flex-shrink:0;">1</div>
                <span style="color:#fff; font-weight:900; font-size:16px; letter-spacing:-0.5px; line-height:1;">407억 원</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    with col_btn:
        st.markdown("""
        <div class="rank-more-wrap">
            <button type="button" id="rank-more-btn-6n36s5" class="rank-more-btn">더 보러가기</button>
            <div id="rank-more-toast-6n36s5" class="rank-more-toast">
                <div class="rank-more-toast-title">🏆 역대 당첨금 TOP 5</div>
                <div class="rank-more-toast-body">
                    1위: 407억 (1회)<br>
                    2위: 369억 (51회)<br>
                    3위: 346억 (100회)<br>
                    4위: 300억 (132회)
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    components.html("""
    <script>
    (function() {
        const doc = window.parent.document;
        if (!doc.getElementById('rank-more-toast-style')) {
            const style = doc.createElement('style');
            style.id = 'rank-more-toast-style';
            style.textContent = `
                @keyframes rankToastFade {
                    0% { opacity: 0; transform: translateY(-6px); }
                    100% { opacity: 1; transform: translateY(0); }
                }
                .rank-more-wrap {
                    position: relative;
                    display: inline-block;
                }
                .rank-more-btn {
                    background: linear-gradient(145deg, #1e88e5, #1565c0) !important;
                    background-color: #1976d2 !important;
                    color: #ffffff !important;
                    border: 1px solid #0d47a1 !important;
                    border-radius: 8px !important;
                    height: 32px !important;
                    box-sizing: border-box !important;
                    padding: 0 14px !important;
                    font-weight: 700 !important;
                    font-size: 13px !important;
                    line-height: 1.4 !important;
                    display: flex !important;
                    align-items: center !important;
                    justify-content: center !important;
                    cursor: pointer !important;
                    /* "더 보러가기"의 공백에서 줄바꿈되면서 height:32px 고정 박스 안에
                       2줄이 눌려 찌그러져 보이던 버그(실기기 스크린샷 확인,
                       2026-08-22) — 줄바꿈 자체를 막는다. */
                    white-space: nowrap !important;
                }
                .rank-more-toast {
                    position: absolute;
                    top: calc(100% + 8px);
                    right: 0;
                    z-index: 60;
                    width: max-content;
                    max-width: min(80vw, 260px);
                    padding: 13px 16px;
                    border-radius: 14px;
                    border: 1px solid rgba(255, 193, 7, 0.4);
                    background: rgba(24, 17, 9, 0.88);
                    backdrop-filter: blur(8px);
                    -webkit-backdrop-filter: blur(8px);
                    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
                    opacity: 0;
                    visibility: hidden;
                    pointer-events: none;
                    transform: translateY(-6px);
                    transition: opacity 0.25s ease, transform 0.25s ease, visibility 0.25s;
                    text-align: left;
                }
                .rank-more-toast.show {
                    opacity: 1;
                    visibility: visible;
                    pointer-events: auto;
                    transform: translateY(0);
                    animation: rankToastFade 0.25s ease;
                }
                .rank-more-toast-title {
                    color: #ffe082;
                    font-weight: 900;
                    font-size: 14px;
                    margin-bottom: 8px;
                }
                .rank-more-toast-body {
                    color: #ffffff;
                    font-size: 13px;
                    line-height: 1.9;
                    font-weight: 600;
                }
            `;
            doc.head.appendChild(style);
        }

        function safeVibrate() {
            if (typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function') {
                try { navigator.vibrate(70); } catch (e) {}
            }
        }

        const btn = doc.getElementById('rank-more-btn-6n36s5');
        const toast = doc.getElementById('rank-more-toast-6n36s5');
        if (btn && toast && !btn.dataset.rankToastBound) {
            btn.dataset.rankToastBound = '1';
            let hideTimer = null;
            btn.addEventListener('click', function() {
                safeVibrate();
                if (hideTimer) {
                    clearTimeout(hideTimer);
                    hideTimer = null;
                }
                const isOpen = toast.classList.contains('show');
                if (isOpen) {
                    toast.classList.remove('show');
                } else {
                    toast.classList.add('show');
                    hideTimer = setTimeout(function() {
                        toast.classList.remove('show');
                        hideTimer = null;
                    }, 5000);
                }
            });
        }

        // "역대 최고 당첨 금액 순위 1위" 배지는 실제 데이터를 보여주는 동시에
        // 관리자 전용 숨은 진입점이다 — 일반 사용자는 그냥 순위 표시로 보이지만,
        // 클릭하면 메인 화면 관리자 메뉴가 나타난다(위 CSS의 body.admin-menu-revealed
        // 규칙 참고). Streamlit 재실행 없이 순수 CSS 클래스 토글이라 즉시 반영된다.
        // (2026-08-27: "더 보러가기" 토스트 안 가짜 4위 줄이 트리거였는데, 모바일에서
        // 화면 우측이라 눌리지 않는 위치라는 지적 — 항상 보이는 1위 배지로 옮김.)
        const secretEntry = doc.getElementById('rank-top1-trigger-6n36s5');
        if (secretEntry && !secretEntry.dataset.adminRevealBound) {
            secretEntry.dataset.adminRevealBound = '1';
            secretEntry.addEventListener('click', function(e) {
                e.stopPropagation();
                doc.body.classList.add('admin-menu-revealed');
                if (toast) toast.classList.remove('show');
            });
        }
    })();
    </script>
    """, height=0)

# ==========================================================
# 👑 관리자 메뉴 (역대 최고 당첨금 순위 토스트 바로 아래)
# ==========================================================
# 이 블록은 항상 렌더링되지만 기본적으로 display:none으로 숨겨져 있다 — "역대
# 최고 당첨 금액 순위 1위" 배지를 클릭해야만 document.body에 admin-menu-revealed
# 클래스가 붙으면서 나타난다(바로 위 토스트 스크립트 참고). 일반 사용자 화면에는
# "시스템 관리자 메뉴"라는 문구 자체가 노출되지 않는다. 서버 왕복(Streamlit
# 재실행) 없이 순수 CSS/JS로 즉시 토글되는 방식이라, 안 보이는 상태에서도
# password 위젯 자체는 이미 DOM에 존재한다 — 하지만 관리자 비밀번호 값 자체는
# 서버에서만 비교하므로(환경변수 ADMIN_MENU_PASSWORD) 노출 위험은 없다.
# 원래 메인 화면 맨 아래(개선 요구사항·약관보다도 아래)에 있었는데, 트리거와
# 너무 멀리 떨어져 있어 모바일에서 열어도 스크롤을 한참 내려야만 보이는
# 위치였다(2026-08-23 사용자 지적) — 트리거 바로 다음으로 옮겼다.
# 2026-08-27: 트리거 자체도 "더 보러가기" 토스트 안 가짜 4위 줄(화면 우측,
# 모바일에서 눌리지 않는 위치)에서 항상 보이는 "1위" 배지로 옮겼다.
if current_page == "main":
    with st.container(key="admin_menu_reveal_wrap"):
        st.markdown("""
        <div class="main-admin-menu-marker" aria-hidden="true"></div>
        <style>
        .main-admin-menu-marker { display: none !important; }
        /* 숨김/노출은 이 컨테이너 자체(.st-key-admin_menu_reveal_wrap)로 정확히
           타겟팅한다 — 처음엔 아래처럼 :has(.main-admin-menu-marker)로 잡은
           stVerticalBlock에 display:none을 걸었었는데, Streamlit의 중첩 레이아웃
           구조상 :has()가 마커를 포함한 "모든 조상" 블록에 다 매치돼서(가장
           바깥쪽 루트 블록까지 포함) 페이지 전체가 사라지는 사고로 이어졌다
           (2026-08-22 실제로 겪음). 아래 :has() 패턴은 margin/padding 같은
           비파괴적 스타일에만 계속 쓴다. */
        .st-key-admin_menu_reveal_wrap { display: none !important; }
        body.admin-menu-revealed .st-key-admin_menu_reveal_wrap { display: block !important; }

        div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) {
            margin-top: 0 !important;
            margin-bottom: 0 !important;
            padding-top: 0 !important;
        }
        div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] {
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
            border-radius: 10px !important;
            margin-bottom: 0 !important;
        }
        div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] summary {
            background: linear-gradient(145deg, #1c2838 0%, #141c2a 45%, #0c1018 100%) !important;
            background-color: transparent !important;
            color: #c8d0dc !important;
            padding: 6px 8px !important;
            min-height: 0 !important;
            line-height: 1.15 !important;
            border-radius: 10px !important;
            border: 1px solid rgba(80, 95, 120, 0.35) !important;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.05) !important;
        }
        div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] details {
            background-color: #000000 !important;
        }
        div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] summary:hover {
            background: linear-gradient(145deg, #243040 0%, #1a2432 45%, #101620 100%) !important;
            color: #e8ecf2 !important;
        }
        div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] summary p,
        div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] summary span,
        div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] summary div,
        div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] summary svg {
            color: #c8d0dc !important;
            fill: #c8d0dc !important;
            font-size: 13px !important;
            line-height: 1.15 !important;
            white-space: nowrap !important;
        }
        div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] [data-testid="stExpanderDetails"] {
            background-color: #000000 !important;
            border-top: 1px solid #333333 !important;
        }
        div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] [data-testid="stExpanderDetails"] > div {
            background-color: #000000 !important;
        }
        div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] button[kind="secondary"],
        div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] button[data-testid="stBaseButton-secondary"],
        div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] button {
            background-color: #3a3a3a !important;
            color: #ffffff !important;
            border: 1px solid #555555 !important;
        }
        div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] button:hover {
            background-color: #4a4a4a !important;
            color: #ffffff !important;
            border-color: #666666 !important;
        }
        div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] button p,
        div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] button span,
        div[data-testid="stVerticalBlock"]:has(.main-admin-menu-marker) div[data-testid="stExpander"] button div {
            color: #ffffff !important;
        }
        </style>
        """, unsafe_allow_html=True)
        with st.expander(" 시스템 관리자 메뉴"):
            import os
            import admin_auth_guard

            _ADMIN_MENU_PASSWORD = os.getenv("ADMIN_MENU_PASSWORD")
            if not _ADMIN_MENU_PASSWORD:
                try:
                    _ADMIN_MENU_PASSWORD = st.secrets.get("ADMIN_MENU_PASSWORD", None)
                except Exception:
                    _ADMIN_MENU_PASSWORD = None
            if not _ADMIN_MENU_PASSWORD:
                st.error("관리자 비밀번호가 설정되지 않았습니다. 환경변수(ADMIN_MENU_PASSWORD)를 확인하세요.")
                st.stop()

            _ADMIN_MAX_ATTEMPTS = 5
            _ADMIN_LOCKOUT_SECONDS = 300  # 5분

            if not st.session_state.get("admin_menu_unlocked", False):
                _remaining = admin_auth_guard.seconds_locked_remaining()
                if _remaining > 0:
                    st.error(f"비밀번호 시도 횟수를 초과했습니다. {int(_remaining) + 1}초 후 다시 시도해 주세요.")
                else:
                    st.text_input(
                        "관리자 비밀번호",
                        type="password",
                        key="admin_menu_pwd_6n36s5",
                    )
                    if st.button("확인", key="admin_menu_pwd_submit_6n36s5"):
                        if st.session_state.get("admin_menu_pwd_6n36s5") == _ADMIN_MENU_PASSWORD:
                            admin_auth_guard.record_success()
                            st.session_state.admin_menu_unlocked = True
                            st.rerun()
                        else:
                            fail_count = admin_auth_guard.record_failure(
                                _ADMIN_MAX_ATTEMPTS, _ADMIN_LOCKOUT_SECONDS
                            )
                            if fail_count == 0:
                                st.warning(
                                    f"비밀번호가 올바르지 않습니다. 시도 횟수 초과로 {_ADMIN_LOCKOUT_SECONDS}초간 잠금됩니다."
                                )
                            else:
                                st.warning(
                                    f"비밀번호가 올바르지 않습니다. ({fail_count}/{_ADMIN_MAX_ATTEMPTS}회)"
                                )
            elif st.button(" 대시보드로 이동", key="admin_btn_dashboard"):
                st.session_state.is_admin = True
                st.session_state.go_to_admin = True
                st.rerun()


    from feedback_db import init_feedback_tables, save_feedback
    from auth_providers import current_member_id

    init_feedback_tables()

    st.markdown(
        """
<div class="main-feedback-section-marker" aria-hidden="true"></div>
<style>
.main-feedback-section-marker { display: none !important; }
div[data-testid="stVerticalBlock"]:has(.main-feedback-section-marker) {
    margin-top: 6px !important;
    margin-bottom: 0 !important;
    padding-bottom: 0 !important;
}
div[data-testid="stVerticalBlock"]:has(.main-feedback-section-marker) div[data-testid="stExpander"] {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    margin-bottom: 4px !important;
}
div[data-testid="stVerticalBlock"]:has(.main-feedback-section-marker) div[data-testid="stExpander"] summary {
    background: linear-gradient(145deg, #243052 0%, #1a2238 42%, #12182b 100%) !important;
    background-color: transparent !important;
    color: #b8c2d6 !important;
    font-weight: 700 !important;
    font-size: 13px !important;
    line-height: 1.15 !important;
    text-align: center;
    padding: 6px 8px !important;
    min-height: 0 !important;
    border-radius: 10px !important;
    border: 1px solid rgba(100, 126, 170, 0.32) !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.06) !important;
    justify-content: center !important;
}
div[data-testid="stVerticalBlock"]:has(.main-feedback-section-marker) div[data-testid="stExpander"] summary p,
div[data-testid="stVerticalBlock"]:has(.main-feedback-section-marker) div[data-testid="stExpander"] summary span {
    color: #b8c2d6 !important;
    font-weight: 700 !important;
}
div[data-testid="stVerticalBlock"]:has(.main-feedback-section-marker) div[data-testid="stExpander"] [data-testid="stExpanderDetails"] {
    background: #16213e !important;
    border: 2px solid #4a9fc4 !important;
    border-top: none !important;
    border-radius: 0 0 10px 10px !important;
    padding: 8px 10px 4px 10px !important;
}
div[data-testid="stVerticalBlock"]:has(.main-feedback-section-marker) div[data-testid="stForm"] textarea {
    background-color: #0d1528 !important;
    color: #ffffff !important;
    border: 1px solid #2a3a60 !important;
    min-height: 52px !important;
}
div[data-testid="stVerticalBlock"]:has(.main-feedback-section-marker) div[data-testid="stFormSubmitButton"] button {
    background: linear-gradient(135deg, #87CEEB, #5BB5D9) !important;
    color: #102030 !important;
    font-weight: 800 !important;
    min-height: 36px !important;
    padding: 0.35rem 0.75rem !important;
}
</style>
        """,
        unsafe_allow_html=True,
    )

    with st.container():
        st.markdown('<div class="main-feedback-section-marker"></div>', unsafe_allow_html=True)
        with st.expander("개선 요구사항", expanded=False):
            with st.form("main_feedback_form_6n36s5", clear_on_submit=True):
                fb_body = st.text_area(
                    "의견",
                    placeholder="불편한 점·원하는 기능을 짧게 적어 주세요",
                    max_chars=2000,
                    height=52,
                    label_visibility="collapsed",
                )
                submitted = st.form_submit_button("저장", use_container_width=True)
                if submitted:
                    try:
                        mid = current_member_id()
                        save_feedback(
                            fb_body,
                            nickname="익명",
                            category="기타",
                            member_id=mid,
                        )
                        st.success("저장되었습니다. 감사합니다!")
                    except ValueError as exc:
                        st.warning(str(exc))


# ==========================================
# ⚡ 화면 2: 번개조합 (Thunder View) - 로직 분리됨
# ==========================================
elif current_page == "thunder":
    import page_thunder

    # lucky_display("관리자 행운수")는 메인화면 캐릭터 이미지 주변 장식용 숫자
    # 볼(위에서 orbit-ball로 렌더링)에만 쓰여야 하고, 조합 생성에 절대 섞이면
    # 안 된다는 요청 — page_thunder.render()에 더 이상 안 넘김(과거 데이터
    # 근거 없는 admin 수기 리스트였음).
    page_thunder.render()

elif current_page == "birthday":
    import page_birthday
    page_birthday.render()

elif current_page == "hedge":
    import page_hedge
    page_hedge.render()

# ==========================================
# 💎 화면: 자동조합 상세 (Auto Combination View)
# ==========================================
elif current_page == "auto":
    import page_auto
    page_auto.render()

# ==========================================
# 🤖 화면 3: 고급필터 상세 페이지 (Advanced Filter View)
# ==========================================
elif current_page == "advanced":
    if os.path.exists("admin_filter.py"):
        with open("admin_filter.py", "r", encoding="utf-8") as f:
            exec(f.read())
    else:
        st.error("admin_filter.py 파일을 찾을 수 없습니다. 파일이 같은 폴더에 있는지 확인해주세요.")

# ==========================================
# 🔮 화면: 오늘의 타로 한 장 (Tarot View)
# ==========================================
elif current_page == "tarot":
    import sys as _sys

    _tarot_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tarot")
    if _tarot_dir not in _sys.path:
        _sys.path.insert(0, _tarot_dir)

    # 페이지마다 이름·모양이 제각각이던 "메인으로" 버튼을 자동구매·고급필터·통계센터가
    # 이미 쓰던 스타일로 통일.
    from shared_ui_styles import main_nav_button_css, main_nav_button_html

    st.markdown(
        # .block-container가 기본적으로 위쪽 96px를 Streamlit 자체 헤더 자리로
        # 비워둔다 — 헤더는 화면에 없는데 자리만 남아 진짜 빈 공간이 됐다(실측
        # 확인, 다른 상세페이지들과 동일한 원인이라 같이 맞춤).
        '<style>.block-container{padding-top:10px !important;} '
        "header[data-testid='stHeader'], section[data-testid='stSidebar']"
        "{display:none !important;}</style>"
        + main_nav_button_css()
        + f'<div style="max-width:160px;">{main_nav_button_html()}</div>',
        unsafe_allow_html=True,
    )

    import tarot_page
    tarot_page.render()

# ==========================================
# 📊 화면 4: 통계 대시보드 (Stats View)
# ==========================================
# ==========================================
# 📊 [안전하게 추가] 통계 대시보드 (Stats View)
# ==========================================
elif current_page == "stats":
    st.markdown("""
    <style>
        .stApp { background-color: #12182b; color: white; }
        html, body, #root, .stApp, [data-testid="stAppViewContainer"],
        [data-testid="stAppViewContainer"] > section.main {
            overflow-x: hidden !important;
        }
        .block-container { padding: 10px !important; max-width: 600px; }
        section[data-testid="stSidebar"], header[data-testid="stHeader"] { display: none; }
        
        /* 탭(Tab) 디자인 고급화 */
        button[data-baseweb="tab"] { background-color: transparent !important; color: #888 !important; font-weight: bold; font-size: 15px; padding-bottom: 12px !important; }
        button[data-baseweb="tab"][aria-selected="true"] { color: #ffb300 !important; border-bottom: 3px solid #ffb300 !important; }
        
        /* 통계 카드 디자인 */
        .stat-card { background: linear-gradient(145deg, #1c2645, #12182b); border-radius: 14px; padding: 16px; border: 1px solid #2a3a60; margin-bottom: 14px; box-shadow: 0 4px 8px rgba(0,0,0,0.4); }
        .stat-title { color: #4fc3f7; font-size: 14px; font-weight: 900; margin-bottom: 8px; border-bottom: 1px solid #2a3a60; padding-bottom: 6px; display: flex; justify-content: space-between; align-items: center; }
        .stat-value { color: #ffffff; font-size: 16px; font-weight: bold; line-height: 1.4; }
        .highlight { color: #ffeb3b; font-size: 22px; font-weight: 900; }
        .tag { background: #2a3a60; padding: 2px 8px; border-radius: 12px; font-size: 11px; color: #aaa; }
        .auto-back-main-btn {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            width: 100%;
            min-height: 48px;
            padding: 8px 12px;
            box-sizing: border-box;
            background: #000000 !important;
            color: #ffffff !important;
            border: 2px solid #333333 !important;
            border-radius: 12px !important;
            text-decoration: none !important;
            font-weight: 700 !important;
            font-size: 14px !important;
        }
        .auto-back-main-btn:hover {
            background: #111111 !important;
            border-color: #555555 !important;
            color: #ffffff !important;
        }
        .auto-back-main-icon {
            width: 28px;
            height: 28px;
            border-radius: 50%;
            object-fit: cover;
            border: 2px solid #ffb300;
            flex-shrink: 0;
        }
    </style>
    """, unsafe_allow_html=True)

    # 1. 상단 네비게이션
    col_back, col_title = st.columns([3, 7])
    with col_back:
        stats_icon_html = (
            f'<img class="auto-back-main-icon" src="data:image/jpeg;base64,{icon_base64}" alt="로또신령">'
            if icon_base64
            else "🏠"
        )
        st.markdown(
            f'<a href="?" target="_self" class="auto-back-main-btn">{stats_icon_html}<span>메인으로</span></a>',
            unsafe_allow_html=True,
        )
    with col_title:
        st.markdown("<h3 style='color:#ffb300; margin:0; padding-top:2px;'>📊 로또 통계 센터</h3>", unsafe_allow_html=True)

    st.markdown("<div style='margin-top:15px;'></div>", unsafe_allow_html=True)

    # 2. 엑셀 데이터 기반 통계 집계
    try:
        from lotto_stats import compute_all_stats, lotto_data_path

        stats = compute_all_stats(lotto_data_path())
        draw_no = stats["latest"]["draw_no"]
        numbers = stats["latest"]["numbers"]
        sum_val = stats["latest"]["sum"]
        ac_val = stats["latest"]["ac"]
        hot_items = stats["hot"]
        hot_display = " · ".join(str(n) for n, _ in hot_items)
        cold_nums = stats["cold"]
        cold_display = ", ".join(str(n) for n in cold_nums) if cold_nums else "없음"
        carry_count = stats["carry"]["count"]
        carry_checked = stats["carry"]["checked"]
        is_sum_good = "🔥 이상적" if 120 <= sum_val <= 150 else "❄️ 주의"
        from lotto_stats import get_marketing_win_rank_summary

        try:
            draw_round_int = int(str(draw_no).replace("회", "").strip())
            from lotto_stats import sync_marketing_win_ranks_for_round

            sync_marketing_win_ranks_for_round(draw_round_int)
            st.session_state["marketing_win_rank_summary"] = get_marketing_win_rank_summary(
                draw_round_int
            )
        except (TypeError, ValueError):
            st.session_state["marketing_win_rank_summary"] = {}
    except Exception as e:
        stats = None
        draw_no, numbers, sum_val, ac_val = "오류", [0, 0, 0, 0, 0, 0], 0, "-"
        hot_display, cold_display = "-", "-"
        carry_count, carry_checked = 0, 0
        is_sum_good = "-"
        st.session_state["marketing_win_rank_summary"] = {}
        st.error(f"통계 데이터 로딩 오류: {e}")

    # 3. 3개의 탭으로 모바일 화면 최적화
    # Streamlit 기본 탭의 "선택 안 된 탭" 글자색이 밝은 배경 기준(짙은 남색)이라,
    # 이 페이지의 어두운 배경 위에서는 거의 안 보였다(선택된 탭만 보라색이라
    # 겨우 읽힘). 이 페이지 탭에만 스코프해서 밝은 회색으로 고정한다.
    st.markdown(
        """
        <style>
        .st-key-stats_tabs_wrap [data-testid="stTab"] [data-testid="stMarkdownContainer"] p {
            color: #94a3b8 !important;
        }
        .st-key-stats_tabs_wrap [data-testid="stTab"][aria-selected="true"] [data-testid="stMarkdownContainer"] p {
            color: #A78BFA !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    with st.container(key="stats_tabs_wrap"):
        tab1, tab2, tab3 = st.tabs(["🧠 전문가 지표", "🔥 출현 빈도", "🎯 패턴 분석"])

    # --- TAB 1: 전문가 지표 ---
    with tab1:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-title"><span>1. AC값 (산술적 복잡도)</span> <span class="tag">최근 {draw_no}회차</span></div>
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span class="stat-value" style="color:#aaa; font-size:13px;">이상적 구간 (7~10)</span>
                <span class="highlight">{ac_val}</span>
            </div>
            <div style="font-size:12px; color:#4fc3f7; margin-top:8px;">💡 AC값이 7 이상일 때 1등 당첨 확률이 통계적으로 가장 높습니다.</div>
        </div>
        
        <div class="stat-card">
            <div class="stat-title"><span>2. 당첨 번호 총합 (Sum)</span> <span class="tag">최근 {draw_no}회차</span></div>
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span class="stat-value">총합: {sum_val}</span>
                <span class="highlight" style="font-size:16px;">{is_sum_good} (120~150 강세)</span>
            </div>
        </div>
        
        <div class="stat-card">
            <div class="stat-title">3. 이월수 출현 패턴</div>
            <div class="stat-value">최근 {carry_checked}회 중 <span style="color:#ffb300;">{carry_count}회</span> 이월수 출현</div>
            <div style="font-size:12px; color:#aaa; margin-top:4px;">직전 회차 당첨번호가 다음 회차에도 포함된 실제 집계입니다.</div>
        </div>
        """, unsafe_allow_html=True)

    # --- TAB 2: 출현 빈도 ---
    with tab2:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-title">4. 역대 최다 출현 (Hot 10)</div>
            <div class="stat-value" style="letter-spacing: 1px;">
                {hot_display}
            </div>
        </div>
        
        <div class="stat-card">
            <div class="stat-title">5. 장기 미출현 (Cold)</div>
            <div class="stat-value">
                <span style="color:#4fc3f7;">{cold_display}</span>
            </div>
            <div style="font-size:12px; color:#aaa; margin-top:4px;">최근 15회차 동안 1~6구에 미출현한 번호입니다.</div>
        </div>
        
        <div class="stat-card">
            <div class="stat-title">6. 색상별 당첨 비율 (최근 10회)</div>
            <div style="display:flex; height:24px; border-radius:12px; overflow:hidden; margin-top:10px;">
                <div style="background:#f9a825; width:20%;" title="노랑 (1~10)"></div>
                <div style="background:#1976d2; width:35%;" title="파랑 (11~20)"></div>
                <div style="background:#e53935; width:25%;" title="빨강 (21~30)"></div>
                <div style="background:#757575; width:10%;" title="회색 (31~40)"></div>
                <div style="background:#388e3c; width:10%;" title="초록 (41~45)"></div>
            </div>
            <div style="font-size:12px; color:#aaa; margin-top:8px; text-align:center;">현재 <span style="color:#4fc3f7; font-weight:bold;">파란공(11~20)</span>이 가장 강세입니다.</div>
        </div>
        """, unsafe_allow_html=True)

    # --- TAB 3: 패턴 분석 (lotto_stats.py 실데이터) ---
    with tab3:
        if stats is not None:
            pattern = stats["pattern"]
            pat_n = pattern["basis_n"]
            oe = pattern["odd_even"]
            lh = pattern["low_high"]
            dec = pattern["decade"]
            ld = pattern["last_digit"]

            odd_even_text = (
                f'현재 누적 트렌드 ➡️ <span style="color:#ffb300;">'
                f'홀 {oe["top_odds"]} : 짝 {oe["top_evens"]}</span> '
                f'(최근 {oe["checked"]}회 중 {oe["top_count"]}회)'
            )
            low_high_text = (
                f'현재 누적 트렌드 ➡️ <span style="color:#ffb300;">'
                f'저 {lh["top_low"]} : 고 {lh["top_high"]}</span> '
                f'(최근 {lh["checked"]}회 중 {lh["top_count"]}회)'
            )

            if dec["warnings"]:
                decade_lines = []
                for w in dec["warnings"]:
                    decade_lines.append(
                        f'⚠️ <span style="color:#e53935;">{w["band"]} 구간({w["range"]})</span> '
                        f'{w["streak"]}주 연속 전멸 현상 발생'
                    )
                decade_text = "<br/>".join(decade_lines)
            else:
                totals = dec["band_totals"]
                summary_parts = [
                    f'{name} {totals[name]}회'
                    for name, _, _ in (
                        ("1번대", 1, 9),
                        ("10번대", 10, 19),
                        ("20번대", 20, 29),
                        ("30번대", 30, 39),
                        ("40번대", 40, 45),
                    )
                ]
                decade_text = (
                    f'최근 {dec["checked"]}회 각 구간 출현: '
                    f'<span style="color:#4fc3f7;">{" · ".join(summary_parts)}</span>'
                )

            last_digit_text = (
                f'최근 동끝수 <span style="color:#4fc3f7;">[ {ld["top_digit"]} ]</span> '
                f'({ld["top_count"]}회 출현, 최근 {ld["checked"]}회 기준)'
            )
        else:
            pat_n = 0
            odd_even_text = low_high_text = decade_text = last_digit_text = "데이터 로딩 오류"

        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-title">7. 홀짝 비율 <span class="tag">최근 {pat_n}회</span></div>
            <div class="stat-value">
                {odd_even_text}
            </div>
        </div>
        
        <div class="stat-card">
            <div class="stat-title">8. 고저 비율 (1~22 vs 23~45) <span class="tag">최근 {pat_n}회</span></div>
            <div class="stat-value">
                {low_high_text}
            </div>
        </div>
        
        <div class="stat-card">
            <div class="stat-title">9. 번호대별 분포 현상 <span class="tag">최근 {pat_n}회</span></div>
            <div class="stat-value">
                {decade_text}
            </div>
        </div>
        
        <div class="stat-card">
            <div class="stat-title">10. 끝수 (일의 자리) 출현 <span class="tag">최근 {pat_n}회</span></div>
            <div class="stat-value">
                {last_digit_text}
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown(
        '<p style="font-size:11px; color:#888; text-align:center; margin-top:20px; line-height:1.5;">'
        "※ 본 통계는 과거 데이터 집계이며, 로또는 완전 무작위 추첨으로 "
        "다음 회차 결과를 보장하지 않습니다"
        "</p>",
        unsafe_allow_html=True,
    )

# ==========================================================
# 📋 개인정보 처리방침 — Play 스토어 등 외부 제출용 단독 URL
# (앱 안 "회원 고지·약관" 아코디언과 같은 내용이지만, 앱을 열거나 로그인하지
#  않고도 바로 볼 수 있는 독립된 페이지가 필요해서 별도 경로로 뺐다.)
# ==========================================================
elif current_page == "privacy":
    st.markdown(
        """
        <style>
        .stApp { background-color: #12182b; color: white; }
        .block-container { max-width: 680px; padding: 24px 20px; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    from legal_notices import NOTICES

    st.markdown("## 개인정보 처리방침")
    st.markdown(NOTICES["privacy"]["body"])
    # 사업자 정보는 사업자등록 완료 전까지는 미기재 항목이 그대로 노출되므로,
    # 실제 값이 채워지기 전까지 이 공개 페이지에는 넣지 않는다.


# ==========================================================
# 📋 메인 화면 — 회원 고지·약관 (운영자 미리보기, 관리자 메뉴 바로 위)
# ==========================================================
if current_page == "main":
    st.markdown("""
    <div class="main-legal-notices-marker" aria-hidden="true"></div>
    <style>
    .main-legal-notices-marker { display: none !important; }
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) {
        margin-top: 0 !important;
        margin-bottom: 0 !important;
        padding-top: 0 !important;
        padding-bottom: 0 !important;
    }
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) div[data-testid="stExpander"] {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        border-radius: 10px !important;
        margin-bottom: 4px !important;
    }
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) div[data-testid="stExpander"] summary {
        background: linear-gradient(145deg, #2a2548 0%, #1c2038 45%, #12182b 100%) !important;
        background-color: transparent !important;
        padding: 6px 8px !important;
        min-height: 0 !important;
        line-height: 1.15 !important;
        border-radius: 10px !important;
        border: 1px solid rgba(120, 100, 170, 0.3) !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.05) !important;
    }
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) div[data-testid="stExpander"] details,
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) div[data-testid="stExpander"] [data-testid="stExpanderDetails"],
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) div[data-testid="stExpander"] [data-testid="stExpanderDetails"] > div {
        background-color: #0d1528 !important;
    }
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) div[data-testid="stExpander"] summary,
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) div[data-testid="stExpander"] summary p,
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) div[data-testid="stExpander"] summary span {
        color: #b39ddb !important;
        font-weight: 700 !important;
        font-size: 13px !important;
        white-space: nowrap !important;
        line-height: 1.15 !important;
    }
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) div[data-testid="stExpander"] [data-testid="stExpanderDetails"] p,
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) div[data-testid="stExpander"] [data-testid="stExpanderDetails"] li {
        color: #e0e0e0 !important;
        font-size: 13px !important;
        line-height: 1.55 !important;
    }
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) button[data-baseweb="tab"] {
        color: #888 !important;
        font-size: 12px !important;
    }
    div[data-testid="stVerticalBlock"]:has(.main-legal-notices-marker) button[data-baseweb="tab"][aria-selected="true"] {
        color: #ce93d8 !important;
        border-bottom-color: #ce93d8 !important;
    }
    </style>
    """, unsafe_allow_html=True)
    with st.expander("📋 회원 고지·약관 (오픈 전 검토용)"):
        from legal_notices import render_notice_preview

        render_notice_preview()
        st.info(
            "※ 현재 **운영자만** 메인 하단에서 확인하는 준비 화면입니다. "
            "회원 공개·간편인증·적립금 연동은 다음 단계에서 적용합니다."
        )


