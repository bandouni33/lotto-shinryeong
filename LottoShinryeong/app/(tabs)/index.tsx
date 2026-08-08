import StreamlitWebView from '@/components/streamlit-webview';

/** K-926: Streamlit 메인(user_page)과 동일 — 구 네이티브 홈(K-927) 미사용 */
export default function HomeScreen() {
  return <StreamlitWebView page="main" title="로또신령" showBack={false} />;
}
