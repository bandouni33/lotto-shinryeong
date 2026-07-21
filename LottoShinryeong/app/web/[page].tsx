import { useLocalSearchParams } from 'expo-router';

import StreamlitWebView from '@/components/streamlit-webview';

const PAGE_TITLES: Record<string, string> = {
  main: '로또신령',
  thunder: '번개조합',
  auto: '자동구매',
  stats: '통계센터',
  advanced: '고급필터',
  birthday: '생일·행운수',
};

export default function StreamlitPageScreen() {
  const { page } = useLocalSearchParams<{ page: string }>();
  const key = typeof page === 'string' ? page : 'main';
  return <StreamlitWebView page={key} title={PAGE_TITLES[key] ?? key} />;
}
