import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  BackHandler,
  Linking,
  Platform,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { WebView } from 'react-native-webview';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import * as ExpoLinking from 'expo-linking';

import { getStreamlitBaseUrl, getStreamlitPageUrl } from '@/constants/streamlit';
import { getOrCreateGuestId } from '@/utils/guest-id';
import { consumeFreshStartFlag } from '@/utils/fresh-start';

type Props = {
  page: string;
  title?: string;
  /** 메인(홈) Streamlit — 뒤로가기 숨김, 히스토리 없을 때 앱 종료 */
  showBack?: boolean;
  /** getStreamlitPageUrl에 그대로 실어보낼 추가 쿼리파라미터(예: QR 스캔 결과) */
  extraParams?: Record<string, string>;
};

export default function StreamlitWebView({ page, title, showBack = true, extraParams }: Props) {
  const insets = useSafeAreaInsets();
  const [guestId, setGuestId] = useState<string | null>(null);
  const webViewRef = useRef<WebView>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [canGoBack, setCanGoBack] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getOrCreateGuestId().then((id) => {
      if (!cancelled) {
        setGuestId(id);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // 이 프로세스에서 맨 처음 뜨는 웹뷰(=앱을 콜드 스타트한 직후)에만 true — 사용자가
  // 앱을 완전히 종료했다 다시 켰을 때 로그인 세션을 정리하기 위한 신호로 쓴다
  // (utils/fresh-start.ts 설명 참고). 홈 버튼 등으로 잠깐 백그라운드 갔다 온
  // 경우나, 앱 안에서 다른 화면으로 이동한 경우엔 false.
  const [isFreshStart] = useState(() => consumeFreshStartFlag());
  const mergedParams = isFreshStart ? { ...extraParams, fresh_start: '1' } : extraParams;
  const uri = getStreamlitPageUrl(page, guestId, mergedParams);

  // QR 스캔 후 넘어오는 것처럼 ?qr=... 붙은 페이지에서, Streamlit이 그 1회성
  // 파라미터를 읽자마자 지우면서 내부적으로 history API를 건드리는 것으로 보이는데,
  // 그걸 웹뷰가 "새 페이지 로드 시작"으로 오인해서 onLoadStart만 다시 불리고
  // onLoadEnd가 안 따라오는 경우가 실기기에서 확인됐다("불러오는 중" 오버레이가
  // 실제로는 다 로드된 화면 위에 영원히 떠 있는 상태로 멈춤). 실제 네트워크 로드가
  // 아니라 판단하기 애매한 상황이라 근본 원인을 웹뷰 이벤트만으로 명확히 구분하긴
  // 어려워서, 대신 로딩 표시가 일정 시간 넘게 안 꺼지면 강제로 꺼버리는 안전장치를
  // 둔다 — 정상적인 실제 로드는 이 시간 안에 항상 끝나므로 부작용이 없다.
  useEffect(() => {
    if (!loading) {
      return;
    }
    const timer = setTimeout(() => setLoading(false), 6000);
    return () => clearTimeout(timer);
  }, [loading, uri]);

  // "안티조합·액땜조합" 진입 링크(?page=hedge&qrscan=1)를 QR 촬영 화면으로 보내는
  // 경로를 세 겹으로 둔다 — 실기기마다 어느 게 실제로 걸리는지가 달라서
  // (2026-08-19~22 여러 차례 확인) 하나에만 의존하면 특정 기종에서 아예 안 걸린다.
  // 한 번 넘어가면 qrScanRedirected.current로 잠가서 세 경로가 중복으로 넘어가지
  // 않게 한다.
  const qrScanRedirected = useRef(false);
  const goToQrScan = useCallback(() => {
    if (qrScanRedirected.current) {
      return;
    }
    qrScanRedirected.current = true;
    router.replace({ pathname: '/qr-scan', params: { target: 'hedge' } });
  }, []);

  // 1) onNavigationStateChange — 웹뷰의 실제 URL이 바뀔 때마다 항상 불리는(리액티브)
  // 이벤트라 세 경로 중 가장 신뢰도가 높다. 실기기(Android 16, Samsung SM-M166S)에서
  // window.ReactNativeWebView 자체가 안 만들어져 2)의 postMessage 경로가 완전히
  // 무력화되는 게 실측으로 확인됐다(2026-08-22, page_hedge.py의 진단 배너로 확인) —
  // 그 대체 경로로 추가함.
  const onNavigationStateChange = useCallback(
    (navState: { canGoBack: boolean; url?: string }) => {
      setCanGoBack(navState.canGoBack);
      if (navState.url && navState.url.includes('qrscan=1')) {
        goToQrScan();
      }
    },
    [goToQrScan]
  );

  // 카카오 로그인처럼 앱 밖 도메인(kauth.kakao.com 등)으로 나가야 하는 링크를
  // 웹뷰 자체 호스트와 구분하기 위한 기준 hostname. 카카오 로그인이 끝나고
  // 우리 서버(base)로 돌아오는 콜백 리다이렉트는 hostname이 같으므로 계속
  // 웹뷰 안에서 처리되고, kauth.kakao.com/accounts.kakao.com 같은 제3자
  // 도메인만 아래에서 기기 기본 브라우저로 넘어간다.
  const ownHostname = (() => {
    try {
      return new URL(getStreamlitBaseUrl()).hostname;
    } catch {
      return null;
    }
  })();

  // 2026-09-05: 카카오 로그인을 그냥 기기 기본 브라우저(Linking.openURL)로
  // 완전히 던져버리면, 로그인이 끝나도 그 결과는 그 브라우저 세션 안에만
  // 남고 앱(이 웹뷰)으로 자동으로 돌아오는 절차가 없다 — 로그인 직후 앱에
  // 돌아와도 계속 로그인 안 된 것처럼 보이던 문제의 원인이었다. 대신
  // Custom Tab(WebBrowser.openAuthSessionAsync)으로 열되, 카카오 자체는
  // 리다이렉트로 커스텀 스킴을 등록조차 못 하게 막아서(콘솔에서 "유효하지
  // 않은 URL"로 거부됨) 카카오에는 항상 기존 https 리다이렉트를 그대로
  // 쓴다. 대신 그 https 콜백 페이지(auth_providers.handle_oauth_callback,
  // 로그인 처리를 다 끝낸 뒤 — 이 시점에 이미 올바른 gid로 로그인이
  // 완료돼 있다)가 JS로 한 번 더 myapp://oauth/kakao로 이동시키고, 이
  // "2차 이동"만 Custom Tab이 자동 감지해 앱으로 복귀시킨다(Expo 공식
  // 문서: redirectUrl 매칭 시 promise가 자동 resolve됨, 별도 Linking
  // 리스너 불필요). 복귀 즉시 이 웹뷰를 새로고침해서 방금 완료된 로그인을
  // restore_member_from_guest()로 이어받는다.
  const KAKAO_OAUTH_REDIRECT = ExpoLinking.createURL('oauth/kakao');
  const handleKakaoAuth = useCallback(async (authUrl: string) => {
    try {
      const result = await WebBrowser.openAuthSessionAsync(authUrl, KAKAO_OAUTH_REDIRECT);
      if (result.type === 'success') {
        webViewRef.current?.reload();
      }
      // 'cancel'/'dismiss'(사용자가 취소) — 그냥 로그인 배너 화면 그대로 둔다.
    } catch {
      // Custom Tab 실행 자체가 실패해도 앱이 죽으면 안 되니 조용히 무시 —
      // 사용자는 로그인 배너에서 다시 시도할 수 있다.
    }
  }, [KAKAO_OAUTH_REDIRECT]);

  // 2) onShouldStartLoadWithRequest — 로드 자체를 가로채 취소하고 대신 보낸다.
  // (2026-08-19: 메인 화면 진입 링크에서는 이 방식이 잘 됐는데, 안티/액땜 상세페이지
  // 자체에 새로 넣은 "QR스캔" 버튼(같은 페이지 안에서 쿼리파라미터만 바뀌는 링크)을
  // 누르면 실기기에서 인터셉트가 안 걸리고 그냥 페이지가 다시 로드되는 문제가
  // 보고됐다 — 안드로이드 웹뷰가 "같은 경로, 쿼리만 다른" 네비게이션을 이 콜백
  // 없이 처리하는 경우가 있는 것으로 보인다.) 그래도 되는 기종에서는 이게 가장
  // 빠르게(실제 로드 자체를 막으면서) 넘어가므로 그대로 둔다.
  //
  // 2026-09-05: "카카오로 시작하기"를 누르면 kauth.kakao.com이 웹뷰 안에서
  // 빈 화면으로 뜨는 문제 — 카카오가 앱 내장 웹뷰(인앱 브라우저)에서의 로그인
  // 시도를 보안상 차단하기 때문이었다. 우리 서버와 다른 hostname으로 나가는
  // 요청은 웹뷰에서 막고 기기 기본 브라우저(Linking.openURL)로 넘겨, 로그인은
  // 정상 브라우저에서 끝내고 콜백으로 우리 앱(같은 hostname)에 돌아오게 한다.
  const onShouldStartLoadWithRequest = useCallback(
    (request: { url: string }) => {
      if (request.url.includes('qrscan=1')) {
        goToQrScan();
        return false;
      }
      if (/^https?:\/\//i.test(request.url) && ownHostname) {
        try {
          const requestHostname = new URL(request.url).hostname;
          if (requestHostname === 'kauth.kakao.com') {
            handleKakaoAuth(request.url);
            return false;
          }
          if (requestHostname !== ownHostname) {
            Linking.openURL(request.url).catch(() => {});
            return false;
          }
        } catch {
          // URL 파싱 실패 시 안전하게 웹뷰 내부 로드로 처리
        }
      }
      return true;
    },
    [goToQrScan, ownHostname, handleKakaoAuth]
  );

  // 3) onMessage(postMessage) — 웹뷰 JS가 곧장 네이티브로 메시지를 보내는 경로.
  // window.ReactNativeWebView 자체가 없는 기기에서는 이 경로가 애초에 실행조차
  // 안 되지만(위 1번 설명 참고), 되는 기기에서는 가장 즉각적이라 그대로 둔다.
  // window.ReactNativeWebView가 없는 일반 브라우저에서는 페이지 쪽(page_hedge.py)이
  // 이 메시지를 아예 안 보내고 URL 폴백만 쓰도록 이미 분기해뒀다.
  const onMessage = useCallback(
    (event: { nativeEvent: { data: string } }) => {
      let payload: { type?: string; target?: string } | null = null;
      try {
        payload = JSON.parse(event.nativeEvent.data);
      } catch {
        return;
      }
      if (payload?.type === 'openQrScan') {
        goToQrScan();
      }
    },
    [goToQrScan]
  );

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
          onShouldStartLoadWithRequest={onShouldStartLoadWithRequest}
          onMessage={onMessage}
          onLoadStart={() => setLoading(true)}
          onLoadEnd={() => setLoading(false)}
          onError={(e) => {
            setLoading(false);
            setError(e.nativeEvent.description || '연결 실패');
          }}
          // 2026-08-30: "결과저장 후 화면이 까맣게 죽고 앱을 완전히 닫아야만 풀린다"
          // 신고 — 강제 다크모드로 인한 색 반전(위 forceDarkOn으로 대응)과는 별개로,
          // 안드로이드 웹뷰 렌더러 프로세스 자체가 죽어도(메모리 압박 등) 이 핸들러가
          // 없으면 웹뷰가 빈/검은 화면인 채로 완전히 멈춰버리고 앱 안에서는 복구할
          // 방법이 없었다(재시작만이 유일한 탈출구였던 이유). 렌더러가 죽는 순간
          // 자동으로 reload해서 앱을 안 닫아도 복구되게 한다.
          onRenderProcessGone={(e) => {
            console.warn('WebView render process gone', e.nativeEvent);
            webViewRef.current?.reload();
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
          // 핀치 줌: getStreamlitPageUrl()이 Streamlit Cloud의 뷰어 껍데기를 건너뛰고
          // 실제 앱이 최상위 문서로 뜨는 내부 경로("/~/+/...")로 바로 접속하기 때문에,
          // 그 문서 자체의 viewport가 이미 줌을 막지 않는 값이라 별도 조치 없이 아래
          // 네이티브 옵션만으로 핀치 줌이 정상 동작한다(실기기 확인 완료) — 예전엔
          // 뷰어 껍데기 안의 중첩 iframe 구조 때문에 viewport를 아무리 고쳐도 안 됐었다.
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
                // 2026-08-30: "번개조합 결과저장 후 화면이 반전된 채 안 돌아온다(앱을
                // 완전히 닫아야만 풀림)" 신고 — page_thunder.py/page_hedge.py가 이미
                // CSS(color-scheme:light)로 안드로이드 웹뷰의 "강제 다크모드" 자동 색
                // 반전에 대응하고 있었지만, CSS는 웹뷰가 이미 반전 여부를 판단한
                // *이후*에나 적용돼 타이밍에 따라 못 막을 때가 있었다(기존 주석 참고).
                // forceDarkOn은 네이티브 웹뷰 레벨에서 이 자동 반전 알고리즘 자체를
                // 끄는 설정이라 타이밍 문제 없이 근본적으로 막는다 — CSS 쪽 대응은
                // 안전망으로 그대로 둔다. (문서상 "not persistent" — 매 웹뷰 생성 시
                // 다시 걸어야 하는데, 이 prop은 렌더마다 항상 실려 있으니 문제 없음.)
                forceDarkOn: false,
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
