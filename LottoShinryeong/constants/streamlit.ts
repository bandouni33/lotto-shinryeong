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
  if (typeof window !== 'undefined') {
    const host = window.location.hostname;
    if (host === 'localhost' || host === '127.0.0.1') {
      return 'http://127.0.0.1:8501';
    }
  }
  return DEFAULT_URL.replace(/\/$/, '');
}

export function getStreamlitPageUrl(page: string): string {
  const base = getStreamlitBaseUrl();
  const safePage = page || 'main';
  return `${base}/?page=${encodeURIComponent(safePage)}`;
}
