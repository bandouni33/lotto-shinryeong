import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  BackHandler,
  Platform,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { WebView } from 'react-native-webview';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { router } from 'expo-router';

import { getStreamlitPageUrl } from '@/constants/streamlit';

type Props = {
  page: string;
  title?: string;
  /** 메인(홈) Streamlit — 뒤로가기 숨김, 히스토리 없을 때 앱 종료 */
  showBack?: boolean;
};

export default function StreamlitWebView({ page, title, showBack = true }: Props) {
  const insets = useSafeAreaInsets();
  const uri = getStreamlitPageUrl(page);
  const webViewRef = useRef<WebView>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [canGoBack, setCanGoBack] = useState(false);

  const onNavigationStateChange = useCallback((navState: { canGoBack: boolean }) => {
    setCanGoBack(navState.canGoBack);
  }, []);

  const goToStreamlitHome = useCallback(() => {
    router.replace('/');
  }, []);

  const handleNativeBack = useCallback(() => {
    if (error) {
      setError(null);
      return true;
    }
    if (canGoBack && webViewRef.current) {
      webViewRef.current.goBack();
      return true;
    }
    if (showBack) {
      goToStreamlitHome();
      return true;
    }
    BackHandler.exitApp();
    return true;
  }, [canGoBack, error, goToStreamlitHome, showBack]);

  useEffect(() => {
    if (Platform.OS !== 'android') {
      return;
    }
    const sub = BackHandler.addEventListener('hardwareBackPress', handleNativeBack);
    return () => sub.remove();
  }, [handleNativeBack]);

  const onToolbarBack = () => {
    if (canGoBack && webViewRef.current) {
      webViewRef.current.goBack();
      return;
    }
    if (showBack) {
      goToStreamlitHome();
    }
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.toolbar}>
        {showBack ? (
          <TouchableOpacity style={styles.backBtn} onPress={onToolbarBack} activeOpacity={0.7}>
            <Text style={styles.backText}>← 메인</Text>
          </TouchableOpacity>
        ) : (
          <View style={styles.backPlaceholder} />
        )}
        <Text style={styles.title} numberOfLines={1}>
          {title ?? page}
        </Text>
      </View>

      {error ? (
        <View style={styles.errorBox}>
          <Text style={styles.errorTitle}>페이지를 불러오지 못했습니다</Text>
          <Text style={styles.errorMsg}>{error}</Text>
          <Text style={styles.errorHint}>
            서버 주소: {uri}
            {'\n'}
            (Cloud: lotto-shinryeong.streamlit.app · 로컬: run_server.ps1)
          </Text>
          <TouchableOpacity style={styles.retryBtn} onPress={() => setError(null)}>
            <Text style={styles.retryText}>다시 시도</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <WebView
          ref={webViewRef}
          key={uri}
          source={{ uri }}
          style={styles.webview}
          onNavigationStateChange={onNavigationStateChange}
          onLoadStart={() => setLoading(true)}
          onLoadEnd={() => setLoading(false)}
          onError={(e) => {
            setLoading(false);
            setError(e.nativeEvent.description || '연결 실패');
          }}
          onHttpError={(e) => {
            if (e.nativeEvent.statusCode >= 400) {
              setLoading(false);
              setError(`HTTP ${e.nativeEvent.statusCode}`);
            }
          }}
          javaScriptEnabled
          domStorageEnabled
          sharedCookiesEnabled
          startInLoadingState
          allowsBackForwardNavigationGestures
          {...(Platform.OS === 'android' ? { mixedContentMode: 'always' as const } : {})}
        />
      )}

      {loading && !error ? (
        <View style={styles.loadingOverlay}>
          <ActivityIndicator size="large" color="#f9a825" />
          <Text style={styles.loadingText}>로또신령 불러오는 중…</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#12182b' },
  toolbar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#2a3a60',
    gap: 8,
  },
  backBtn: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 8,
    backgroundColor: '#1c2645',
  },
  backPlaceholder: { width: 72 },
  backText: { color: '#f9a825', fontWeight: '700', fontSize: 14 },
  title: { flex: 1, color: '#e0e0e0', fontWeight: '700', fontSize: 15 },
  webview: { flex: 1, backgroundColor: '#12182b' },
  loadingOverlay: {
    ...StyleSheet.absoluteFillObject,
    top: 52,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'rgba(18, 24, 43, 0.85)',
    gap: 12,
  },
  loadingText: { color: '#b0bec5', fontSize: 14 },
  errorBox: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 24,
    gap: 10,
  },
  errorTitle: { color: '#fff', fontSize: 18, fontWeight: '800' },
  errorMsg: { color: '#ef5350', fontSize: 14, textAlign: 'center' },
  errorHint: { color: '#90a4ae', fontSize: 12, textAlign: 'center', lineHeight: 18 },
  retryBtn: {
    marginTop: 8,
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 10,
    backgroundColor: '#f9a825',
  },
  retryText: { color: '#1a1a2e', fontWeight: '800' },
});
