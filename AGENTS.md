# 로또신령 — 작업 지침 (루트)

이 문서는 **이 앱을 모르는 상태에서 부분 수정 요청을 받았을 때** 통일성을 깨거나 연계
기능을 건드려 오류가 나는 것을 막기 위한 것이다. 코드를 고치기 전에 이 문서의
**§2 기준점 표**에서 해당 기능의 행을 먼저 찾는다. 느린 Expo 쪽 지침은
`LottoShinryeong/AGENTS.md`(버전 문서 우선)를 함께 본다.

## §1 행동 규칙 (한 줄)

> **이 프로젝트에서 특정 기능 하나만 고쳐달라는 요청이 오면, 먼저 §2 표에서 그 기능의
> 기준점을 찾아 거기만 수정할 것. 다른 곳에 리터럴·복사본을 새로 만들지 말 것.**

추가로 지킬 것:
- 이름·플래그·상품ID·금액·요일·단가는 **표에 적힌 기준점 파일에만** 존재해야 한다. 다른
  파일에 같은 값이 보이면 그건 버그 예약이다(그 자리에서 기준점을 import하도록 바꾼다).
- **같은 기능의 버튼·창은 화면마다 새로 만들지 않는다**(2026-09-26 사용자 지시). 로그인
  안내·적립금 안내·부족/충전·구독 안내·"메인으로" 이동은 §2의 K~M 기준점을 **호출만**
  한다 — 화면별 사본이 생기면 한 곳만 고쳐져 나머지 화면이 조용히 어긋난다(실제 사고:
  타로만 적립금 안내창 X가 먹통이고 부족/충전창이 안 떴음).
- 화면 CSS·문구를 새로 쓰기 전에 §3의 보류 항목(테마/토큰)과 죽은 코드 목록을 확인한다.
- 기준점을 바꾸면 **§2의 "같이 영향받는 곳"과 "걸리는 테스트"를 전부 실행**하고 결과를
  보고한다. 결제·로그인·지급 경로는 승인 없이 바꾸지 않는다.

## §2 기준점 표 (기능 → 단일 기준점 → 연계 → 검사)

| # | 기능 | 단일 기준점 (여기만 고친다) | 같이 영향받는 곳 (연계·파생 리스크) | 어긋나면 걸리는 테스트 |
|---|---|---|---|---|
| A | 다이얼로그 열기·로그인 후 재개 | `dialog_registry.py` (`DIALOGS`) | `wallet_ui._resume_after_auth`(레지스트리 순회), `user_scope._LOGOUT_EXACT_KEYS`(파생), `wallet_ui._PN_TRIGGER_FLAGS`(파생), 각 화면의 `resume=` 호출부 | `tests/test_dialog_registry.py`, `tests/test_resume_and_experiment.py`, `tests/test_login_gate_callbacks.py` |
| B | 당첨번호 볼 색·글자색 | `ball_style.py` (`ball_color` / `ball_text_color` / `ball_gradient` / `ball_html`) | `user_page.py`(메인 최근당첨번호·회전볼), `page_thunder.py`(번호판), 그 밖의 볼 렌더 | `tests/test_ball_style.py` |
| C | 상품·가격·기간·지급량 | `products.py` (`PRODUCTS`) | `wallet_db.py`(WON_PER_POINT·CHARGE_WON_AMOUNTS·구독 기간), `google_play_pg.py`(POINTS_PRODUCTS·SUBSCRIPTION_BASE_PLAN_DAYS), `wallet_ui.py`(IAP 상품·가격표시 기본값·파라미터), `legal_notices.py`(PRICING), `LottoShinryeong/components/streamlit-webview.tsx`(SKU·파라미터명) | `tests/test_products_definition.py`, `tests/test_iap_native_branch.py`, `tests/test_google_play_sub_once.py`, `tests/test_gplay_lifecycle.py` |
| D | 기능별 포인트 단가 | `wallet_db.py` (`THUNDER_COST_PER_GAME`·`HEDGE_COST_PER_COMBO`·`AUTO_COST_PER_UNIT`·`TAROT_EXTRA_DRAW_COST` + `calc_*_cost`) | `legal_notices.format_*_points_notice`(안내 문구), 각 화면의 비용 표시 | `tests/test_products_definition.py` |
| E | 화면 틀(폭·상단여백·헤더 숨김) | **보류**(P1, 심사 제출 후) — 현재는 화면별 CSS | `.block-container` 덮어쓰기, `header[data-testid="stHeader"]` 숨김 | 보류 중에는 손대지 말 것 |
| F | 디자인 토큰(색·글자크기·여백·z-index) | **보류**(P1) | 모든 화면 CSS(`!important` 다수) | 보류 |
| G | 테마(다크/라이트) | `.streamlit/config.toml` (한 곳) | 화면 CSS의 배경·글자색 전제 | 보류 — 지금은 라이트 테마 + 다크 전제 CSS가 섞여 있다 |
| H | 네이티브 앱 여부 판정 | `wallet_ui.in_native_app()` (결제 버튼은 `wallet_ui.iap_available()` — 수신부 있는 안드로이드 빌드만; 업데이트 안내 배너 대상은 `wallet_ui.is_outdated_android_app()` — 56 이하 안드로이드 앱만) | `native=1` 판정이 필요한 모든 곳(카카오 배너, IAP 분기) | `tests/test_iap_native_branch.py`, `tests/test_update_notice_target.py` |
| I | 서버↔앱 파라미터·프로토콜 이름 | 파이썬 쪽 상수(`wallet_ui.IAP_PRICE_PARAMS` 등) + TS 상수(`IAP_PRICE_PARAMS`) | `streamlit-webview.tsx`, `google_play_pg.py` | `tests/test_iap_native_branch.py` |
| J | 화면 문구·라벨 | `legal_notices.py`(고지·가격 안내) / 기능별 상수 | 화면에 직접 박힌 한글 라벨 | 심사 문구 정리 커밋 참고 — 라벨이 여러 곳에 복사되면 제로폭 공백 사건처럼 일부만 바뀐다 |
| K | 적립금 안내창(구매 전 확인창) | `wallet_ui.points_notice_dialog` + **열림 플래그는 `dialog_registry.DIALOGS`에 `points_notice_trigger=True`로 등록**(자동구매·번개·안티액땜·타로) | 네 화면의 열림 플래그·X닫기 정리(`_points_notice_on_dismiss`)·로그아웃 정리 키 | `tests/test_dialog_registry.py`(D9), `tests/test_tarot_gate_flow.py`(T1) |
| L | 적립금 부족/충전창 | 화면이 아니라 공통 자리 **`wallet_ui.render_wallet_bar` 한 곳에서만** 띄운다(화면은 `open_insufficient_balance_dialog()`로 플래그만 세운다) | 각 화면 안의 띄우기 사본(금지), 충전창 `charge_dialog` | `tests/test_dialog_registry.py`(D8), `tests/test_tarot_gate_flow.py`(T2) |
| M | "메인으로" 이동 버튼·링크 | `shared_ui_styles.brand_home_link_html()` (href는 `user_scope.internal_nav_href`) | 각 화면 좌상단 아이콘, 타로 게이트 | `tests/test_kakao_login_branch_links.py`, `tests/test_tarot_gate_flow.py`(T3) |
| N | 계정 삭제(회원 탈퇴) 실행 | `account_deletion.delete_account()` (순서·대상 목록) + 표별 SQL은 각 DB 모듈(`wallet_db.anonymize_member_account`·`marketing_db.delete_guest_data`·`birthday_db.delete_all_birthdays`·`feedback_db.delete_member_feedback`) | 앱 내 진입점 `wallet_ui._my_info_dialog`(버튼 키 `wallet_delete_account_btn`) → `_delete_account_dialog`; 웹 공개 URL `user_page`의 `page=delete_account`; 문구 `legal_notices.ACCOUNT_DELETION_BODY`; 삭제/보관 목록 `account_deletion.DELETED_ITEMS`·`RETAINED_ITEMS` | `tests/test_account_deletion.py`(I1~I8, B1·B2, F1·F2), `tests/test_dialog_registry.py` |
| O | 무료 지급 우회 판정 | `auth_providers._dev_mock_enabled()`(명시적으로 켤 때만 True) + `kakao_configured()`(env → st.secrets) → `wallet_ui._testing_period_active()` | 3650일 무료 구독 지급·조용한 자동 로그인 분기(`wallet_ui`), `.env`·`run_server.ps1`(개발용 켜기) | `tests/test_free_grant_hardening.py`(H1~H5), `scripts/preflight_review_build.py` |
| P | 저장내역 2열 배치(5개 조각 짝짓기) | `combo_history_ui.py` (`CHUNK_SIZE`·`chunk_pairs()`·`chunk_is_from_newest()`) | `page_auto.py`(같은 함수를 import해 재사용 — 화면마다 사본을 만들지 않는다), 조각을 카드 함수가 먹는 모양으로 감싸는 `_chunk_batch`(회차 `draw_round`를 잃으면 당첨·보너스 동그라미가 조용히 사라진다), 화면별 강조 판정 | `tests/test_history_chunk_pairing.py`(C1~C16) |
| Q | 로그인 수단(카카오·Apple) 앱 신호·검증 | `wallet_ui.NATIVE_LOGIN_TRIGGERS`(메시지·URL 신호 이름)·`wallet_ui.apple_login_available()`(`APPLE_LOGIN_CAPABILITY_PARAM`) + `auth_providers.verify_apple_identity_token`(`APPLE_BUNDLE_ID`·`APPLE_ISSUER`) + 버튼 문구 `login_gate.GATE_BUTTON_APPLE` | `LottoShinryeong/components/streamlit-webview.tsx`(수신부·`APPLE_LOGIN_CAPABILITY_PARAMS`·`WEBVIEW_ORIGIN_WHITELIST`), `app.json`(usesAppleSignIn·플러그인·번들 ID), `user_page`(native_apple_token·native_login_error 처리), `user_scope.internal_nav_href`(native_platform·apple_login 이어 보내기), `security_log`(계측 이벤트) | `tests/test_apple_login.py`(A1~A10), `tests/test_kakao_native_login_diag.py`, `tests/test_webview_origin_whitelist.py` |
| R | 구글 결제 이후 수명주기(갱신·해지·보류·환불·승인 재시도) | 권한 규칙 `google_play_pg.subscription_entitlement`(상태→권한) + 저장 `wallet_db`의 `gplay_purchases` 표·`activate_gplay_subscription`·`update_gplay_subscription`·`reclaim_voided_gplay_points` | `user_page`(회원 확인 `refresh_member_subscriptions_if_due`·백그라운드 `maybe_run_maintenance_in_background`), 구독 행 `subscriptions.source_ref`, 앱 결제 전 고지 `legal_notices.IAP_CHARGE_NOTICE`·`IAP_SUBSCRIPTION_NOTICE` | `tests/test_gplay_lifecycle.py`(L1~L20, preflight R8이 실행), `tests/test_reset_tester_balances.py`(출시 전 적립금 초기화 대상) |
| S | 애플(App Store) 인앱결제 — 검증·지급·구독 상태·환불·거래 끝내기 | `apple_iap.py`(App Store Server API, 키 `APPLE_IAP_KEY_ID`·`APPLE_IAP_ISSUER_ID`·`APPLE_IAP_PRIVATE_KEY`는 Cloud secrets) + 상품 `products.APPLE_SUBSCRIPTION_PRODUCTS`·`IAP_PRICE_FALLBACK_IOS` + 저장은 R행의 `gplay_purchases` 표를 `store='apple'`로 공용(키 `apple:<거래/원거래 ID>`, 원장 ref `pg:gplay:apple:…`) | `wallet_ui`(iOS 분기 `APPLE_IAP_ENABLED`·`apple_iap_available()`·`_render_apple_*`, iOS 가격 `ios:` 저장 키), `legal_notices.IAP_*_NOTICE_IOS`, `user_page`(애플 훅·`page=terms`), `streamlit-webview.tsx`(`APPLE_SUBSCRIPTION_SKUS`·`iap_apple_tx`·`iapFinish`/`iap_finish`·`iapRestore`, finishTransaction 은 서버 신호 뒤에만), 구글 `google_play_pg.refresh_subscription`(애플 행 건너뜀) | `tests/test_apple_iap.py`(A1~A16), `tests/test_ios_payment_hidden.py`(S1~S6), `scripts/preflight_review_build.py --phase ios` |
| T | 같은 세션 안 화면 이동(새로 불러오기 대신) — 시험판 | `in_session_nav.py` (`IN_SESSION_NAV_ENABLED` 스위치·`ENABLED_PAGES`=이용자 메뉴 8개(메인·자동·번개·번호검증·고급필터·통계·타로·생일, 2026-10-10 확대), 화면을 옮길 때 한 화면용 상태(로그인 안내·재개 의도·창 플래그=`dialog_registry.logout_keys()`)는 `_go`가 지움, 기록 칸은 Streamlit 이 쌓음(직접 pushState 금지 — 두 칸이면 뒤로가기 고장), 앱은 `spa_nav=1` 싣는 빌드만 — 옛 빌드는 pushState 에 "불러오는 중" 6초 가림) — `user_page`가 `current_page` 확정 직후 `render()` 한 번만 부름 | 메뉴·로고 `<a href>`는 그대로(가로채기만, 버튼 없으면 예전 링크 이동), 앱 뒤로가기(history.pushState→웹뷰 canGoBack→popstate), 세션 상태가 화면 간에 이어짐(화면별 플래그가 남을 수 있음 — 대상 화면을 늘릴 때 확인), 스크롤 칸은 `stMain` | `tests/test_in_session_nav.py`(N1~N7) + 로컬 렌더 실측(위치 픽셀 동일) |
| U | 고급필터 세팅 회원별 저장(재접속·재부팅 유지) | `af_settings_db.py`(`af_user_settings`: draft·saved·k295) + `admin_filter`의 `_hydrate_premium_settings_from_disk`·`_autosave_premium_draft`·`_persist_saved_premium_settings`·`_persist_k295` | 서버 파일(data/users)은 보조로만 남음(Cloud 재부팅 때 지워짐), 위젯 값은 화면을 안 그린 실행 뒤 Streamlit 이 지우므로 다시 채움(안 채우면 자동 저장이 기본값으로 덮어씀), 탈퇴 `account_deletion`(DELETED_ITEMS·탈퇴 안내 문구) | `tests/test_af_settings_persist.py`(P1~P5, G1~G6 로그인 전 세팅 이어받기 — `af_guest_drafts`·`_af_adopt_guest_draft`·`_autosave_guest_draft`), `tests/test_account_deletion.py` |

### A(다이얼로그)에 등록된 재개 이름 — 이 목록이 정본이다

`open_thunder_dialog`, `open_hedge_dialog`, `open_hedge_qr_scan`, `auto_show_points`,
`af_show_subscribe`, `my_info_dialog`, `wallet_show_charge`, `open_tarot_dialog`,
`delete_account_dialog`, `win_event_banner`

- 새 창을 추가할 때: `dialog_registry.DIALOGS`에 항목 추가 → 화면에서는
  `dialog_registry.flag_key(이름)`과 `DIALOGS[이름].name`만 사용(문자열을 새로 쓰지 않는다).
- `tests/test_dialog_registry.py`가 **호출부·소비부·문서 목록·로그아웃 정리 목록**이
  서로 어긋나면 실패시킨다. 2026-09-26에 실제로 있었던 사고: `af_show_subscribe`가
  매핑에 없어 로그인 후 구독창이 열리지 않았고, `af_show_step1_points` 계열은 아무도
  쓰지 않는 죽은 분기였다(호출부도 소비부도 없음 → 제거).

## §3 보류·주의 항목 (지금 손대지 말 것)

- **P1 보류**: 화면 틀 통일(E)·디자인 토큰(F)·테마 통일(G), `!important` 정리.
  이유: 통신판매업 신고 대기 + 심사 제출을 앞둔 시점이라 회귀 범위가 넓은 작업은
  제출 완료 후로 미룸(2026-09-26 사용자 지시).
- **죽은 코드 — 수정하지 말 것**(대비 오류 등이 있어도 되살리지 않는다):
  `frontend/**`(앱에서 아무도 import하지 않음), `page_thunder_*_backup.py`,
  `page_thunder_GOLD_backup.py`, `*.bak*`, `user_page.py 대시보드 연결까지.txt`.
- **테스트 실행 환경**: pytest 없음. 각 테스트 파일의 `__main__` 러너로
  `venv312\Scripts\python.exe tests\<파일>.py` 실행. DB 테스트는 `tests/_db_isolation.py`의
  `isolated_db()`로만 운영 Turso를 만진다(그 밖의 DB 접속은 금지).

## §4 자주 밟는 함정 (이 프로젝트 고유)

- `st.dialog`·`login_gate`는 렌더 도중 `st.rerun()`을 던진다 → 열린 컨테이너 안에서
  호출하면 고아 DOM 중복 렌더가 난다. 게이트 판정은 `st.button(..., on_click=콜백)`으로.
- `@st.cache_data` 함수의 인자 이름이 밑줄로 시작하면 캐시 키에서 제외된다 → 무효화용
  인자에 `_`를 붙이면 캐시 무효화가 통째로 무력해진다.
- Streamlit 내부이동 링크(`user_scope.internal_nav_href`)는 `page`·`gid`·`native`·`native_platform`·
  `apple_login`·`iap`(구글 결제 수신부 있는 빌드, 2026-10-09)만 실어 보낸다 → 그 밖에 주소에 실어 보낸 값(예: 앱이 보낸 스토어 가격)은 화면 이동에서 사라진다.
  그래서 가격은 앱이 보낸 값을 서버가 저장해두고 재사용한다(`wallet_ui.iap_prices`).
- Cloud 는 git push 후 프로세스를 재시작하지 않을 수 있다 → 이미 import 된 모듈은 옛 코드로 남는다.
  화면 모듈은 `user_page._reload_if_stale`, 공용 모듈(로그인 창·로그인 처리·링크 등)은
  `user_page._reload_stale_core_modules`(`_CORE_RELOAD_ORDER`)가 "프로세스 시작 뒤 바뀐 파일"만 새로 읽는다.
  상태를 들고 있는 모듈(db_turso·wallet_db·결제 모듈)은 넣지 말 것. 새 공용 모듈을 고쳤는데 반영이 안 되면 이 목록부터 본다.
- 결제 승인은 서버 전담: 앱은 `finishTransaction`을 호출하지 않는다
  (`google_play_pg.py`가 검증→지급→consume/acknowledge). 구독 지급은
  `wallet_db.activate_gplay_subscription`(멱등 마커 `pg_charges.pg_ref_id`, 2026-10-09부터 — 이후 갱신·해지·환불은
  §2 R행). 옛 `activate_paid_advanced_sub_once`는 테스트용으로만 남아 있다(결제 경로에서 쓰지 말 것).
- 구글 결제 점검 이력·의도적으로 둔 항목은 `AI_STATUS.md` §8 — 재점검 때 그 표 기준으로 판정한다.
- 애플 결제(§2 S행): 앱이 **서버 확인 뒤에만** 거래를 끝낸다(`iapFinish`). 끝내지 않은 거래는 애플이 앱 실행마다 다시 보내므로 서버 처리는 멱등이어야 한다. 서버는 애플 알림(POST)을 못 받아 구독은 직접 조회, 환불은 '알림 이력'을 읽는다 — ASC에 서버 알림 URL(V2)이 등록돼 있어야 이력이 쌓인다. 심사관 결제는 샌드박스(운영 빌드여도)라 샌드박스 확인 경로를 지우지 말 것.
