/**
 * Streamlit 로또신령 웹앱 주소.
 * .env 에 EXPO_PUBLIC_STREAMLIT_URL=http://PC_IP:8501 설정 권장.
 */
const DEFAULT_URL = 'http://220.127.15.204:8501';

export function getStreamlitBaseUrl(): string {
  const fromEnv = process.env.EXPO_PUBLIC_STREAMLIT_URL?.trim();
  return (fromEnv || DEFAULT_URL).replace(/\/$/, '');
}

export function getStreamlitPageUrl(page: string): string {
  const base = getStreamlitBaseUrl();
  const safePage = page || 'main';
  return `${base}/?page=${encodeURIComponent(safePage)}`;
}
