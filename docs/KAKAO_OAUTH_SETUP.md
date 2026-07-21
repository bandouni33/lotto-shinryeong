# 카카오 OAuth 연동 가이드

## 1. 카카오 개발자 콘솔

1. [Kakao Developers](https://developers.kakao.com) 로그인
2. **내 애플리케이션 → 애플리케이션 추가하기**
3. 앱 이름·사업자 정보 입력 후 생성

## 2. 카카오 로그인 활성화

1. 생성한 앱 → **제품 설정 → 카카오 로그인**
2. **활성화 설정** ON
3. **Redirect URI** 등록 (둘 다 추가 권장):
   - `http://210.99.230.83:8501` (모바일·외부 PC)
   - `http://localhost:8501` (로컬 개발)

> Redirect URI는 `.env`의 `KAKAO_REDIRECT_URI`와 **완전히 일치**해야 합니다.

## 3. 동의 항목 (선택)

**카카오 로그인 → 동의항목**에서 서비스에 필요한 항목만 요청하세요.  
본 앱은 회원 식별용 **카카오계정(회원번호)** 만 사용합니다.

## 4. 앱 키 복사

**앱 설정 → 앱 키 → REST API 키** 를 복사합니다.

**카카오 로그인 → 보안** 에서 Client Secret을 사용하는 경우, Secret도 `.env`에 추가합니다.

## 5. 프로젝트 `.env` 설정

프로젝트 루트 `.env` (git에 올리지 않음):

```env
KAKAO_REST_API_KEY=여기에_REST_API_키
KAKAO_CLIENT_SECRET=          # Secret 사용 시만
KAKAO_REDIRECT_URI=http://210.99.230.83:8501
LOTTO_DEV_MOCK_AUTH=0
```

## 6. 서버 재시작

```powershell
pip install -r requirements.txt
.\run_server.ps1
```

시작 로그에 `Kakao OAuth: configured` 가 보이면 설정 완료입니다.

## 7. 동작 확인

1. 앱에서 **간편인증** 다이얼로그 열기
2. 필수 동의 체크 → **카카오로 시작하기** 클릭
3. 카카오 로그인·동의 후 앱으로 복귀
4. 최초 가입 시 **5,000P** 지급 토스트 (Mock이 아닌 실제 카카오 ID 기준)

## 문제 해결

| 증상 | 확인 |
|------|------|
| redirect_uri mismatch | Kakao 콘솔 URI와 `.env` `KAKAO_REDIRECT_URI` 일치 |
| invalid_client | REST API 키 오타, Client Secret 필요 여부 |
| Mock 로그인만 됨 | `LOTTO_DEV_MOCK_AUTH=0`, `KAKAO_REST_API_KEY` 설정 후 재시작 |
| 토큰 오류 메시지 | 앱 화면에 표시되는 카카오 API 응답 확인 |
