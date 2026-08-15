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
import { getOrCreateGuestId } from '@/utils/guest-id';

type Props = {
  page: string;
  title?: string;
  /** 메인(홈) Streamlit — 뒤로가기 숨김, 히스토리 없을 때 앱 종료 */
  showBack?: boolean;
};

export default function StreamlitWebView({ page, title, showBack = true }: Props) {
  const insets = useSafeAreaInsets();
  const [guestId, setGuestId] = useState<string | null>(null);
  const [guestIdSource, setGuestIdSource] = useState<string>('로딩중');
  const [viewportDebug, setViewportDebug] = useState<string>('대기중');
  const webViewRef = useRef<WebView>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [canGoBack, setCanGoBack] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getOrCreateGuestId().then((result) => {
      if (!cancelled) {
        setGuestId(result.id);
        setGuestIdSource(
          result.source === 'fallback-error'
            ? `실패:${result.error?.slice(0, 40)}`
            : result.source
        );
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const uri = getStreamlitPageUrl(page, guestId);

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

      {/* 임시 진단용 표시 — 구매내역/타로 제한/핀치줌이 실기기에서 왜 반영 안 되는지
          원격으로는 확인할 방법이 없어서, 문제 원인을 좁히기 위해 잠깐 넣어둔다.
          원인 확인되면 제거할 것. */}
      <View style={styles.debugBar}>
        <Text style={styles.debugText} numberOfLines={1}>
          gid[{guestIdSource}]:{guestId ? guestId.slice(0, 10) : '-'} url-has-gid:
          {uri.includes('&gid=') ? 'YES' : 'NO'}
        </Text>
        {/* 프레임별 진단이 길어서 한 줄로 자르면 정작 중요한(iframe 안쪽) 값이
            잘려 안 보였다 — 잘라내지 않고 " | " 구분자마다 줄바꿈해서 전부 보여준다. */}
        {viewportDebug.split(' | ').map((seg, i) => (
          <Text key={i} style={styles.debugText}>
            {i === 0 ? 'viewport: ' : '  '}
            {seg}
          </Text>
        ))}
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
      ) : guestId === null ? null : (
        // TODO(update-banner-link): target="_blank" 링크(예: user_page.py의 업데이트 안내
        // 배너 "지금 업데이트" st.link_button)가 새 탭이 아니라 이 웹뷰 안에서 그대로 열림 —
        // setSupportMultipleWindows/onOpenWindow 핸들러가 없기 때문. update_url이 스토어
        // 웹페이지면 그럭저럭 동작하지만, APK 직링크면 onFileDownload 핸들러 없이는
        // 다운로드가 아예 안 될 가능성이 높음. 고치려면 onShouldStartLoadWithRequest로
        // 외부 URL을 기기 기본 브라우저(Linking.openURL)로 넘기는 처리 추가 필요 —
        // 이 프로젝트(LottoShinryeong) 재빌드가 필요한 변경이라 별도로 진행.
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
          injectedJavaScript={`
            (function() {
              // injectedJavaScriptBeforeContentLoaded 쪽 수정이 실제로 붙었는지, 그것도
              // "어느 문서에" 붙었는지까지 프레임별로 한 번에 보고한다 — 아래
              // injectedJavaScriptBeforeContentLoaded의 scanFrames와 동일한 순회 로직.
              var lines = [];
              function visit(doc, label) {
                var meta = doc.querySelector ? doc.querySelector('meta[name="viewport"]') : null;
                lines.push('[' + label + ']' + (meta ? JSON.stringify(meta.getAttribute('content')) : '태그없음'));
                var frames = doc.querySelectorAll ? doc.querySelectorAll('iframe') : [];
                for (var i = 0; i < frames.length; i++) {
                  try {
                    var inner = frames[i].contentDocument;
                    if (inner) visit(inner, label + '>f' + i);
                  } catch (e) {
                    lines.push('[' + label + '>f' + i + ']접근불가');
                  }
                }
              }
              visit(document, 'top');
              if (window.ReactNativeWebView) {
                window.ReactNativeWebView.postMessage('viewport:[로드완료] ' + lines.join(' | '));
              }
            })();
            true;
          `}
          onMessage={(e) => {
            const data = e.nativeEvent.data;
            if (typeof data === 'string' && data.startsWith('viewport:')) {
              setViewportDebug(data.slice('viewport:'.length));
            }
          }}
          javaScriptEnabled
          domStorageEnabled
          sharedCookiesEnabled
          startInLoadingState
          allowsBackForwardNavigationGestures
          // 웹 콘텐츠 쪽에 자체 핀치 줌(frontend/components/pinch_zoom.py)을 구현해봤지만
          // iframe(타로 카드 스프레드 등) 안까지는 이벤트가 닿지 않아 그 부분에선 오히려
          // 네이티브 줌이 방해 없이 더 잘 동작했다 — 자체 구현을 걷어내고 네이티브 확대
          // 옵션을 다시 켠다(핀치 줌 허용 + 확대/축소 버튼은 숨김).
          //
          // Streamlit이 자체 번들 index.html에 심어둔
          // <meta name="viewport" content="...,user-scalable=no">가 네이티브 줌을 막고
          // 있어서(user_page.py에서 st.components.html로 페이지 로드 후에 이 태그를
          // 고쳐봤지만 실기기에서 효과 없었음 — 안드로이드 WebView는 최초 네비게이션 시
          // 파싱한 viewport 값으로 줌 스케일 한계를 확정 짓고, 그 이후의 DOM 변경은
          // 반영하지 않는 것으로 보인다), 문서 자체가 만들어지자마자(다른 리소스가
          // 로드되기 전) 실행되는 이 훅에서 한 번 더 같은 수정을 시도한다 — Streamlit
          // 쪽 스크립트보다 더 이른 시점에 개입해야 줌 스케일이 잠기기 전에 값을
          // 바꿀 수 있다.
          injectedJavaScriptBeforeContentLoaded={`
            (function() {
              // injectedJavaScriptBeforeContentLoaded 시점엔 window.ReactNativeWebView
              // 브리지가 아직 준비 안 됐을 수 있어서, 바로 못 보내면 큐에 쌓아뒀다가
              // 브리지가 생기는 즉시(최대 5초, 100ms 간격) 순서대로 흘려보낸다.
              var pending = [];
              function report(msg) { pending.push(msg); flush(); }
              var tries = 0;
              function flush() {
                if (!window.ReactNativeWebView) {
                  if (tries++ < 50) setTimeout(flush, 100);
                  return;
                }
                while (pending.length) {
                  window.ReactNativeWebView.postMessage('viewport:' + pending.shift());
                }
              }

              var target = 'width=device-width, initial-scale=1, shrink-to-fit=no';
              // 실기기 진단으로 확인해보니, 맨 위 문서만 고쳐서는 안 됐다 — Streamlit
              // Cloud는 실제 화면(로그인/구매/타로 등 진짜 내용)을 최상위 문서가 아니라
              // 그 안에 심어둔 iframe(주소가 "/~/+/..."인) 안에서 그린다. 최상위 문서의
              // viewport는 그 iframe의 줌 동작과 무관해서, 최상위만 고치면 겉보기엔
              // "수정됨"으로 보고되는데도 실제 줌은 여전히 막혀 있었다. 그래서 최상위부터
              // 시작해 접근 가능한(같은 출처) iframe을 전부 재귀적으로 찾아 각각 고친다.
              var watched = [];
              function isWatched(doc) {
                for (var i = 0; i < watched.length; i++) if (watched[i] === doc) return true;
                return false;
              }
              function fixDoc(doc, label) {
                var meta = doc.querySelector && doc.querySelector('meta[name="viewport"]');
                if (!meta) return;
                var before = meta.getAttribute('content');
                if (before !== target) {
                  meta.setAttribute('content', target);
                  report('[' + label + '] 수정 ' + JSON.stringify(before));
                }
                if (!isWatched(doc)) {
                  watched.push(doc);
                  try {
                    new MutationObserver(function() { fixDoc(doc, label); }).observe(doc.documentElement, {
                      childList: true,
                      subtree: true,
                      attributes: true,
                      attributeFilter: ['content'],
                    });
                  } catch (e) {}
                }
              }
              function scan(doc, label) {
                fixDoc(doc, label);
                var frames = doc.querySelectorAll ? doc.querySelectorAll('iframe') : [];
                for (var i = 0; i < frames.length; i++) {
                  (function(f, idx) {
                    try {
                      var inner = f.contentDocument;
                      if (inner) scan(inner, label + '>f' + idx);
                    } catch (e) {}
                  })(frames[i], i);
                }
              }
              scan(document, 'top');
              // 그 iframe 자체가 아직 안 만들어졌을 수도 있어서, 최상위 문서에 새 노드가
              // 추가될 때마다(=iframe이 그때 생겼을 수 있으므로) 다시 훑는다.
              new MutationObserver(function() { scan(document, 'top'); }).observe(document.documentElement, {
                childList: true,
                subtree: true,
              });
            })();
            true;
          `}
          scalesPageToFit
          {...(Platform.OS === 'android'
            ? {
                // 2026-08-15: setBuiltInZoomControls:true + mixedContentMode:'always'를
                // 같이 켜면 실기기에서 앱이 열리자마자 크래시했다(react-native-webview
                // 13.15.0). mixedContentMode를 빼고 나니 정상 작동 확인됨 — 이 두 옵션의
                // 조합이 원인이었다. mixedContentMode는 현재 필요하지 않아(모든 리소스가
                // https) 제거한 채로 둔다.
                setBuiltInZoomControls: true,
                setDisplayZoomControls: false,
              }
            : {})}
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
  debugBar: {
    paddingHorizontal: 10,
    paddingVertical: 3,
    backgroundColor: '#3a2a00',
  },
  debugText: { color: '#ffd54f', fontSize: 10 },
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
