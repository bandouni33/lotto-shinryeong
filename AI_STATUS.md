# AI_STATUS.md — 로또신령 현재 상태

> 새 채팅은 **이 파일 → `git status`/`git log` → 관련 코드** 순서로 확인 후 작업한다.
> 채팅 기억보다 이 파일과 실제 코드가 우선. 확인 안 된 내용은 적지 않는다.
> 마지막 갱신: 2026-10-05 (기준 커밋 `be336ff`, main, working tree clean)

## 1. 프로젝트 현재 상태
- 구조: **Streamlit(Python) 서버** (`app.py`, `user_page.py`, `page_*.py`, `wallet_*.py` 등) + **Expo/React Native WebView 앱** (`LottoShinryeong/`)
- DB: Turso (`db_turso.py`). 운영 Streamlit Cloud와 자체 PC서버가 **같은 운영 DB를 공유**함 (`Cloud_공유DB_확인_상한롤백_2026-10-04.txt`에서 확인)
- 앱 버전: `LottoShinryeong/app.json` expo.version **1.0.2**
- 동시접속 상한: `admission_control.DEFAULT_MAX_CONCURRENT_SESSIONS = 60` (운영 DB 값도 60으로 롤백 확인)
- 세션 TTL: `.streamlit/config.toml` `disconnectedSessionTTL = 120` (300 → 120 롤백)
- Streamlit 버전 고정: `streamlit==1.64.0`

## 2. 최근 완료 작업 (2026-10-02 ~ 10-04, git log 기준)
- 저장내역 2열 배치를 **5개 조각(chunk) 단위**로 변경 (`cdffea7`, `be336ff`) — 테스트 19/19
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

## 5. 다음 작업
1. 토요일 실사용 관측 실행·결과 정리 (0원)
2. 렌더당 DB 왕복 줄이기 — 캐시 후보 조사 (0원)
3. iOS build 8 실기기 QA 진행
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
