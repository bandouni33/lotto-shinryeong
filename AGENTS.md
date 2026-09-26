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
- 화면 CSS·문구를 새로 쓰기 전에 §3의 보류 항목(테마/토큰)과 죽은 코드 목록을 확인한다.
- 기준점을 바꾸면 **§2의 "같이 영향받는 곳"과 "걸리는 테스트"를 전부 실행**하고 결과를
  보고한다. 결제·로그인·지급 경로는 승인 없이 바꾸지 않는다.

## §2 기준점 표 (기능 → 단일 기준점 → 연계 → 검사)

| # | 기능 | 단일 기준점 (여기만 고친다) | 같이 영향받는 곳 (연계·파생 리스크) | 어긋나면 걸리는 테스트 |
|---|---|---|---|---|
| A | 다이얼로그 열기·로그인 후 재개 | `dialog_registry.py` (`DIALOGS`) | `wallet_ui._resume_after_auth`(레지스트리 순회), `user_scope._LOGOUT_EXACT_KEYS`(파생), `wallet_ui._PN_TRIGGER_FLAGS`(파생), 각 화면의 `resume=` 호출부 | `tests/test_dialog_registry.py`, `tests/test_resume_and_experiment.py`, `tests/test_login_gate_callbacks.py` |
| B | 당첨번호 볼 색·글자색 | `ball_style.py` (`ball_color` / `ball_text_color` / `ball_gradient` / `ball_html`) | `user_page.py`(메인 최근당첨번호·회전볼), `page_thunder.py`(번호판), 그 밖의 볼 렌더 | `tests/test_ball_style.py` |
| C | 상품·가격·기간·지급량 | `products.py` (`PRODUCTS`) | `wallet_db.py`(WON_PER_POINT·CHARGE_WON_AMOUNTS·구독 기간), `google_play_pg.py`(POINTS_PRODUCTS·SUBSCRIPTION_BASE_PLAN_DAYS), `wallet_ui.py`(IAP 상품·가격표시 기본값·파라미터), `legal_notices.py`(PRICING), `LottoShinryeong/components/streamlit-webview.tsx`(SKU·파라미터명) | `tests/test_products_definition.py`, `tests/test_iap_native_branch.py`, `tests/test_google_play_sub_once.py` |
| D | 기능별 포인트 단가 | `wallet_db.py` (`THUNDER_COST_PER_GAME`·`HEDGE_COST_PER_COMBO`·`AUTO_COST_PER_UNIT`·`TAROT_EXTRA_DRAW_COST` + `calc_*_cost`) | `legal_notices.format_*_points_notice`(안내 문구), 각 화면의 비용 표시 | `tests/test_products_definition.py` |
| E | 화면 틀(폭·상단여백·헤더 숨김) | **보류**(P1, 심사 제출 후) — 현재는 화면별 CSS | `.block-container` 덮어쓰기, `header[data-testid="stHeader"]` 숨김 | 보류 중에는 손대지 말 것 |
| F | 디자인 토큰(색·글자크기·여백·z-index) | **보류**(P1) | 모든 화면 CSS(`!important` 다수) | 보류 |
| G | 테마(다크/라이트) | `.streamlit/config.toml` (한 곳) | 화면 CSS의 배경·글자색 전제 | 보류 — 지금은 라이트 테마 + 다크 전제 CSS가 섞여 있다 |
| H | 네이티브 앱 여부 판정 | `wallet_ui.in_native_app()` | `native=1` 판정이 필요한 모든 곳(카카오 배너, IAP 분기) | `tests/test_iap_native_branch.py` |
| I | 서버↔앱 파라미터·프로토콜 이름 | 파이썬 쪽 상수(`wallet_ui.IAP_PRICE_PARAMS` 등) + TS 상수(`IAP_PRICE_PARAMS`) | `streamlit-webview.tsx`, `google_play_pg.py` | `tests/test_iap_native_branch.py` |
| J | 화면 문구·라벨 | `legal_notices.py`(고지·가격 안내) / 기능별 상수 | 화면에 직접 박힌 한글 라벨 | 심사 문구 정리 커밋 참고 — 라벨이 여러 곳에 복사되면 제로폭 공백 사건처럼 일부만 바뀐다 |

### A(다이얼로그)에 등록된 재개 이름 — 이 목록이 정본이다

`open_thunder_dialog`, `open_hedge_dialog`, `open_hedge_qr_scan`, `auto_show_points`,
`af_show_subscribe`, `my_info_dialog`, `wallet_show_charge`, `open_tarot_dialog`

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
- Streamlit 내부이동 링크(`user_scope.internal_nav_href`)는 `page`·`gid`·`native`만
  실어 보낸다 → 주소에 실어 보낸 값(예: 앱이 보낸 스토어 가격)은 화면 이동에서 사라진다.
  그래서 가격은 앱이 보낸 값을 서버가 저장해두고 재사용한다(`wallet_ui.iap_prices`).
- 결제 승인은 서버 전담: 앱은 `finishTransaction`을 호출하지 않는다
  (`google_play_pg.py`가 검증→지급→consume/acknowledge). 구독 지급은
  `wallet_db.activate_paid_advanced_sub_once`(멱등 마커 `pg_charges.pg_ref_id`).
