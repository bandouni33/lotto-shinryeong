# AI_STATUS.md — 로또신령 현재 상태

> 새 채팅은 **이 파일 → `git status`/`git log` → 관련 코드** 순서로 확인 후 작업한다.
> 채팅 기억보다 이 파일과 실제 코드가 우선. 확인 안 된 내용은 적지 않는다.
> 마지막 갱신: 2026-10-05 (로그인 후 보던 화면 유지 — 서버 우회 반영, main.
> PC 로컬은 미커밋분이 남아 있을 수 있음 → §6 참조)

## 1. 프로젝트 현재 상태
- 구조: **Streamlit(Python) 서버** (`app.py`, `user_page.py`, `page_*.py`, `wallet_*.py` 등) + **Expo/React Native WebView 앱** (`LottoShinryeong/`)
- DB: Turso (`db_turso.py`). 운영 Streamlit Cloud와 자체 PC서버가 **같은 운영 DB를 공유**함 (`Cloud_공유DB_확인_상한롤백_2026-10-04.txt`에서 확인)
- 앱 버전: `LottoShinryeong/app.json` expo.version **1.0.2**
- 동시접속 상한: `admission_control.DEFAULT_MAX_CONCURRENT_SESSIONS = 60` (운영 DB 값도 60으로 롤백 확인)
- 세션 TTL: `.streamlit/config.toml` `disconnectedSessionTTL = 120` (300 → 120 롤백)
- Streamlit 버전 고정: `streamlit==1.64.0`

## 2. 최근 완료 작업 (2026-10-02 ~ 10-05, git log 기준)
- **(10-05) `tests/test_resume_and_experiment.py` 격리 정비** — 진입점 테스트 2건이 격리 없이 운영 Turso에 붙어 **실행마다 운영 `security_events`에 시험 기록 1~2건**을 남기던 문제(네이티브 로그인 계측에 섞였을 수 있음). 전 테스트를 `@_isolated`(`isolated_db()`)로 감싸고, 빠진 테스트가 생기면 실패하는 안전장치 테스트 추가. 7/7 통과(접속정보 없는 환경에서도), 안전장치는 일부러 빼서 실패 확인.
- **(10-05) 로그인 후 "보던 화면 그대로" (앱)** — 타로·자동·번개·번호검증 등에서 로그인하면 메인으로 튕기던 문제. 원인: 설치된 앱 빌드가 로그인 후 `buildUri()`로 page 없이 다시 로드. 처방(서버만, 빌드 불필요): 로그인 버튼을 누른 화면을 임시저장(`auth_providers.remember_return_page_at_login_click`, 배너 열 때도 `_remember_pending_resume`이 page 저장) → 로그인 완료 때 `_restore_pending_resume`가 그 화면으로 복귀. 허용 화면 목록은 `auth_providers.RETURN_PAGES` 한 곳. 웹(state 우선)·다음 앱 빌드(`reloadWith`)·계정삭제/관리자 화면은 결과 불변. 검증 `tests/test_login_return_page.py` 21/21(원본 코드에서는 실패 확인) + 로그인 관련 테스트 23개 파일 통과.
- **(10-05) 저장내역 짝 카드 강조를 왼쪽·오른쪽 조각 독립 판정으로 수정** — 번개조합(`combo_history_ui.same_source_pair_card_html`)·자동구매(`page_auto._history_pair_card_html`) 동일 규칙. 양쪽 새것 → 카드 전체(기존 모양), 한쪽만 → 그 열만. 예전엔 왼쪽만 보고 카드 전체를 강조해 옛 저장분까지 깜박였다.
- **(10-05) `tests/test_history_chunk_pairing.py` 러너 수정** — 실패를 PASS로 삼키던 결함. 실제로는 6건 실패였음 → 원인별 수정 후 **21/21**(C4 계산 오류, C10/C11 `_combo(11)` 중복번호 시험데이터 결함 + C10 CSS 선택자까지 세던 오류, 강조를 조각 수로 세기, C13/C14 신규). 관련 테스트 10개 파일 59건 통과.
- 저장내역 2열 배치를 **5개 조각(chunk) 단위**로 변경 (`cdffea7`, `be336ff`) — 당시 "19/19"는 위 러너 결함으로 부정확했음
- **1·2등 배출 배너** (`win_event_banner.py`) — 회차당 1회 모달, 1244회차부터 노출, 디자인 수정 다수
- 회차별 배출표 → 확정 스냅샷(`combo_round_stats`, 조합수 제외) 전환, 최근 5회차만 표시
- 조합생성 워커 프로세스 미종료 문제 수정 (`29894f3`)
- 무활동 자동 로그아웃 3분 → 2분 (`6d6d7cc`)
- 서버 주소 고정 1단계: DDNS 갱신·크래시 복구·IP 하드코딩 제거 (`ac300db`)
- 동시접속 확장 조사 2~4단계 (상한 120·TTL 300 시험 → **둘 다 롤백**, VPS 검토 보고서)
- iOS 준비: `native_platform` 파라미터 추가, **iOS 네이티브는 결제 버튼 대신 "준비중" 고정** (`79a31f2`)
- 카카오 로그인 sandbox iframe 갇힘 긴급 완화 (`0e12070`)
- 배너 닫기(×) z-index 수정, 부하테스트 하네스 추가

## 3. 현재 작업 중인 내용
- 동시접속 확장: 다음 단계는 **토요일 실사용 관측**(게이트 횟수·p95·DB 오류) — `토요일관측_준비_2026-10-04.txt`, 관측 대상은 Cloud
- iOS build 8 (1.0.2) TestFlight 실기기 QA — `iOS_build8_실기기QA_체크리스트_2026-10-04.txt`

## 4. 해결되지 않은 문제
- **네이티브 빌드 대기 항목** (`네이티브_빌드_대기목록.md`, 통합 빌드로 묶어 반영 예정)
  - §1 카카오 로그인 WebView 재생성 2회→1회 / §2 로그인 후 보던 화면 복귀 / §3 안드로이드 뒤로가기로 다이얼로그 닫기 / §4 로딩 오버레이 불투명 / §5 R8 난독화 / §6 카카오 로그인 멈춤 영구잠금 / §7 IAP 결제 멈춤 영구잠금 / §8 eas.json 빌드 URL Cloud→PC서버(DDNS) 전환
  - OTA(EAS Update) 미설정 → **JS 변경도 전부 재빌드 필요**
- **`wallet_ui.TEST_CHARGE_ENABLED = True`** — 심사 제출 전 `False`로 내려야 함
- iOS 결제(StoreKit) 미구현 — 현재 "준비중"으로 가림
- 기술부채: `st.components.v1.html` deprecation — **Streamlit 버전 올리기 전 `st.iframe` 전환 선행 필수** (`기술부채_추적.md`)
- 동시접속: 병목은 코어가 아니라 **DB 왕복(도쿄 ~75ms × 렌더당 10~28회)** — 운영 부하·VPS 실측 미검증
- 로그인된 세션 기준 관측 도구 없음 (Cloud 보고서 "다음 과제")
- **로그인 후 화면 유지는 실기기 미확인** — 네이티브 로그인 자체가 카카오 잠금 수정 빌드 반영 후에야 가능
- `tests/test_manual_privacy_notice.py`도 진입점(app.py)을 **격리 없이** 띄운다 — 같은 방식 정비 필요(승인 대기)
- 저장내역 **한쪽 열만 강조될 때의 모양**(보라 테두리·"방금 저장" 배지 위치) 실기기 미확인 — 테스트는 HTML 구조만 검증

## 5. 다음 작업
1. 토요일 실사용 관측 실행·결과 정리 (0원)
2. 렌더당 DB 왕복 줄이기 — 캐시 후보 조사 (0원)
3. iOS build 8 실기기 QA 진행 (+ 저장내역 한쪽 열 강조 모양, 로그인 후 화면 유지 4개 화면 실기기 확인)
4. 네이티브 통합 빌드 (§1~§8 묶음) — 빌드 전 `TEST_CHARGE_ENABLED=False` 확인
5. VPS·진입점 분리는 **승인 후** 진행

## 6. 중요한 주의사항
- 수정 전 **`AGENTS.md` §2 기준점 표** 확인 → 기준점 파일만 수정, 리터럴·사본 금지
- **결제·로그인·지급 경로는 승인 없이 변경 금지**
- 공통 창/버튼(로그인·적립금 안내·충전·구독·메인으로)은 K~M 기준점 **호출만**
- P1 보류(화면 틀·디자인 토큰·테마 통일) — 손대지 말 것
- 죽은 코드 수정 금지: `frontend/**`, `page_thunder_*backup.py`, `*.bak*`
- 테스트: pytest 없음 → `venv312\Scripts\python.exe tests\<파일>.py`; DB 테스트는 `tests/_db_isolation.isolated_db()`만
- `@st.cache_data` 인자명 `_` 접두사 금지(캐시키 제외됨)
- 한 번에 한 변경 → 롤백 지점 확보 → 커밋·푸시·테스트 후 다음
- 매주 일요일 14:00 배포용 조합생성
- PC 로컬(`C:\Users\PC\Desktop\lotto-app`)에 **미커밋 파일이 있을 수 있음** (10-04 보고서 기준) — 작업 전 PC 쪽 `git status`도 확인

## 7. 협업 방식 (2026-10-05)

### 7-1. 역할
- **Astra(PC 로컬)**: Windows 셸 실행 권한 보유 — 실제 서버 운영·배포, PC/Windows 인프라 작업을 맡는다.
- **이 세션(Claude)**: 2026-10-05부터 GitHub push 권한 보유 — 앱 로직(Python/Streamlit)의 구현·테스트·커밋·푸시를 직접 할 수 있다.
- 어느 쪽에 맡길지는 작업 성격으로 그때그때 판단한다: **PC/Windows 인프라**는 Astra, **앱 코드**는 이 세션.

### 7-2. 작업 순서 원칙
기존 기능에 영향 줄 수 있는 수정은 **코드를 짜기 전에** `AGENTS.md` §2 기준점 표에서 연계 파일·걸리는 테스트부터 확인하고, **계획을 먼저 공유한 뒤** 진행한다.
(2026-10-05 사용자 지시 — "하나 고치면 다른 데서 터지는" 반복을 줄이기 위함.)

### 7-3. 미해결 작업
- **[해소]** `AGENTS.md` §2 기준점 표에 "저장내역 2열 배치(chunk pairing)" 행이 없던 건 — 2026-10-05 이 커밋에서 **§2 #P 행**으로 반영했다.
  - 기준점: `combo_history_ui.py`의 `CHUNK_SIZE`·`chunk_pairs()`·`chunk_is_from_newest()`
  - 영향받는 곳: `page_auto.py`(같은 함수를 import해 재사용 — 화면마다 사본을 만들지 않는다)
  - 걸리는 테스트: `tests/test_history_chunk_pairing.py`(C1~C14)
- 그 밖에 이 문서에 등록된 미해결 항목은 없다(새 항목이 생기면 여기에 적는다).

### 7-4. 검증 관행
- 코드 diff만 보고 끝내지 않는다 — 실제 테스트를 **실행**해서 확인한다(가능하면 Python 3.12 = `venv312`).
- 기존 기능에 닿는 변경이면 §2 표의 "걸리는 테스트"를 전부 돌린다.
- 단위 테스트 통과만으로 끝내지 않고 **조립된 경로**(실제 진입점 `app.py?page=...`)를 한 번 띄워 결과를 확인한다.
- **[해소 2026-10-05]** `tests/test_history_chunk_pairing.py` 러너가 실패를 PASS로 삼키던 결함 → `test.run(result)`로 판정하도록 수정, 실패 시 exit 1 확인. 다른 테스트 파일에는 같은 패턴 없음(저장소 전수 확인).
- 교훈: `unittest.TestCase`를 직접 `test()`로 호출하는 러너를 만들지 말 것. 테스트 결과 숫자는 **실패를 일부러 내서 실제로 FAIL이 찍히는지** 한 번 확인한다.
