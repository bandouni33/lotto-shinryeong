/**
 * Streamlit 로또신령 웹앱 주소 (K-926 UI = user_page 메인).
 * EAS production 빌드: EXPO_PUBLIC_STREAMLIT_URL=https://lotto-shinryeong.streamlit.app
 */
const DEFAULT_URL = 'https://lotto-shinryeong.streamlit.app';

export function getStreamlitBaseUrl(): string {
  const fromEnv = process.env.EXPO_PUBLIC_STREAMLIT_URL?.trim();
  if (fromEnv) {
    return fromEnv.replace(/\/$/, '');
  }
  if (typeof window !== 'undefined' && window.location && window.location.hostname) {
    const host = window.location.hostname;
    if (host === 'localhost' || host === '127.0.0.1') {
      return 'http://127.0.0.1:8501';
    }
  }
  return DEFAULT_URL.replace(/\/$/, '');
}

export function getStreamlitPageUrl(
  page: string,
  guestId?: string | null,
  extraParams?: Record<string, string>
): string {
  const base = getStreamlitBaseUrl();
  const safePage = page || 'main';
  // Streamlit Community Cloud는 실제 앱을 최상위 문서가 아니라, 자체 "뷰어" 껍데기
  // 문서 안에 심어둔 iframe(주소가 base + "/~/+/...")에서 그린다. 실기기 진단으로
  // 확인한 결과, 안드로이드 웹뷰의 핀치줌은 이 중첩 iframe 구조에서는 (안쪽 iframe의
  // viewport meta를 정확히 고쳐놔도) 전혀 동작하지 않았다 — 반면 이 내부 경로로
  // 껍데기 없이 바로 접속하면 실제 앱이 최상위 문서가 되고, 그 자체의 viewport도
  // 이미 줌을 막지 않는 값이라 핀치줌이 정상 동작했다(빈 테스트 페이지로 이미
  // 네이티브 줌 자체는 문제 없음을 확인한 뒤, 이 경로로 직접 접속해 실제 콘텐츠도
  // 문제없이 로드되고 viewport가 처음부터 정상임을 확인했다).
  // 로컬 개발 서버(streamlit run)는 이 뷰어 껍데기 자체가 없어 그대로 루트를 쓴다.
  const isLocal = base.includes('127.0.0.1') || base.includes('localhost');
  const path = isLocal ? '/' : '/~/+/';
  let url = `${base}${path}?page=${encodeURIComponent(safePage)}`;
  if (guestId) {
    url += `&gid=${encodeURIComponent(guestId)}`;
  }
  if (extraParams) {
    for (const [key, value] of Object.entries(extraParams)) {
      url += `&${key}=${encodeURIComponent(value)}`;
    }
  }
  return url;
}
