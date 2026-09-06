import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  AppState,
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
import { login as kakaoNativeLogin } from '@react-native-seoul/kakao-login';

import { getStreamlitPageUrl } from '@/constants/streamlit';
import { getOrCreateGuestId } from '@/utils/guest-id';
import { consumeFreshStartFlag } from '@/utils/fresh-start';
import { HEARTBEAT_MS, isSessionTimedOut, touchLastActive } from '@/utils/session-timeout';

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
  // 2026-09-06: isFreshStart는 컴포넌트가 살아있는 동안 계속 true로 남아있는데,
  // mergedParams(아래)는 렌더될 때마다 다시 계산되므로 — 카카오 네이티브
  // 로그인이 webview를 다시 로드시킬 때마다(토큰 실어 보낼 때, 토큰 지울 때)
  // fresh_start=1이 매번 다시 실려 나가고 있었다. 서버(user_page.py)는 이
  // 신호를 받을 때마다 "이 기기의 로그인 연결을 끊어라"로 해석해서
  // (kakao_configured()가 켜진 뒤로는 무조건 실행됨), 로그인 직후 새로
  // 만든 guest-member 연결을 곧바로 다시 끊어버리고 있었다 — 이게 "서버는
  // 로그인 성공(member_id 할당)까지 다 되는데 내정보에는 반영이 안 되는"
  // 증상의 진짜 원인이었다. 최초 1회 uri 계산에만 실리게 하고 그 이후로는
  // 다시 안 실리도록 소비 처리한다(nativeKakaoToken과 달리 "로드 완료" 시점을
  // 기다릴 필요가 없다 — 이 신호는 서버가 실제로 받았는지 확인할 필요 없이
  // "한 번만 시도하면 충분"하기 때문에 즉시 소비해도 안전하다).
  const freshStartConsumedRef = useRef(false);
  useEffect(() => {
    freshStartConsumedRef.current = true;
  }, []);
  // 2026-09-06: "완전 종료했는지"를 프로세스 생존 여부로 판단하는 위 방식은
  // 안드로이드에서 신뢰할 수 없다는 게 실사용 습관(뒤로가기로 종료 후 최근
  // 앱 목록에서 모두 닫기)으로 확인됐다 — 은행앱들이 쓰는 방식(시간 기준
  // 재인증)으로 보완했었는데, 그다음 두 번의 시도(메모리 기록 → AsyncStorage
  // 기록)도 전부 실기기에서 실패했다. 원인을 조사한 결과 두 가지가 겹친
  // 것으로 보인다: (1) 이 앱처럼 "뒤로가기로 종료"하는 경로에서는 AppState의
  // 'active' 복귀 이벤트 자체가 안정적으로 안 온다는 React Native 공식 이슈
  // (facebook/react-native#32720), (2) "백그라운드로 가는 바로 그 순간에"
  // 기록하려는 시도는, 안드로이드가 그 순간 프로세스를 곧바로 정리해버릴 수
  // 있어 비동기 저장이 완료되기 전에 죽는 경쟁 상태가 실제로 보고된 바 있다.
  // 즉 "위험한 순간에 급하게 쓰기 + 특정 이벤트가 오길 기다리기" 두 가지
  // 전제 자체가 불안정했다.
  //
  // 그래서 이벤트를 기다리지 않는 하트비트 방식으로 바꾼다: 앱이 정상적으로
  // 켜져있는 동안 20초마다 "마지막 활동 시각"을 미리미리 기록해두고,
  // 마운트될 때마다(콜드스타트든 화면 재진입이든, 어떤 이벤트가 왔는지와
  // 무관하게) 그 기록과 지금 시각을 비교한다. 앱이 어떤 방식으로 갑자기
  // 죽든 최대 20초 전에는 이미 안전하게 저장된 기록이 남아있으므로,
  // 특정 전환 이벤트가 안정적으로 오는지에 더 이상 의존하지 않는다.
  const [timeoutLogoutTrigger, setTimeoutLogoutTrigger] = useState(0);
  const sentTimeoutTriggerRef = useRef(0);
  useEffect(() => {
    sentTimeoutTriggerRef.current = timeoutLogoutTrigger;
  }, [timeoutLogoutTrigger]);
  useEffect(() => {
    let cancelled = false;
    const checkAndTouch = () => {
      isSessionTimedOut()
        .then((timedOut) => {
          if (!cancelled && timedOut) {
            setTimeoutLogoutTrigger((n) => n + 1);
          }
        })
        .finally(() => {
          if (!cancelled) {
            touchLastActive();
          }
        });
    };
    checkAndTouch(); // 마운트 시점(콜드스타트 포함) 1회 확인 + 즉시 갱신
    const heartbeat = setInterval(() => {
      touchLastActive();
    }, HEARTBEAT_MS);
    // AppState 이벤트가 이 기기/경로에서 안 오더라도(위 #32720 참고) 위
    // 하트비트가 이미 최근 활동 시각을 계속 갱신해두므로 안전하다 — 이
    // 리스너는 'active' 복귀 시 더 빠르게(20초 기다리지 않고) 판정해주는
    // 보조 수단일 뿐, 이것 하나에만 의존하지 않는다.
    const sub = AppState.addEventListener('change', (nextState) => {
      if (nextState === 'active') {
        checkAndTouch();
      }
    });
    return () => {
      cancelled = true;
      clearInterval(heartbeat);
      sub.remove();
    };
  }, []);
  const shouldSendFreshStart =
    (isFreshStart && !freshStartConsumedRef.current) ||
    timeoutLogoutTrigger > sentTimeoutTriggerRef.current;
  // 2026-09-06: 카카오 네이티브 SDK 로그인(handleKakaoNativeLogin)이 성공하면
  // 받은 access_token을 여기 담아 다음 웹뷰 로드 한 번에만 실어 보낸다 —
  // 서버가 그 토큰을 카카오에 직접 검증해 로그인을 끝낸다(auth_providers.py
  // finalize_login_with_native_token 참고). 1회용이라 로드 완료 후 지운다.
  const [nativeKakaoToken, setNativeKakaoToken] = useState<string | null>(null);
  const mergedParams = {
    ...(extraParams || {}),
    // 2026-09-06: 안드로이드 웹뷰가 "기본 URL만 같으면 쿼리스트링이 달라져도
    // 캐시된 예전 페이지를 그대로 보여주는" 문제가 react-native-webview에서
    // 다수 보고됨(cacheEnabled=false를 꺼도 해결 안 되는 경우 다수) — 지난
    // 두 번의 자동 로그아웃 수정이 전부 실패한 진짜 원인이 여기 있었을 가능성이
    // 높다(JS 쪽 판단 로직 자체는 처음부터 맞았는데, fresh_start=1을 실은
    // 새 URL이 서버까지 실제로 도달을 못 하고 있었을 수 있음). 캐시 설정에
    // 기대지 않고, 이 신호를 보낼 때만 URL에 매번 다른 값(현재 시각)을 끼워
    // 넣어 웹뷰가 "완전히 새로운 주소"로 인식하고 무조건 새로 요청하게
    // 만든다(RFC 7234 — 캐시 키는 항상 쿼리스트링 포함 전체 URL).
    ...(shouldSendFreshStart ? { fresh_start: '1', _cb: String(Date.now()) } : {}),
    ...(nativeKakaoToken ? { native_kakao_token: nativeKakaoToken } : {}),
  };
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

  // 2026-09-06: 카카오 로그인을 REST API+웹뷰 방식에서 네이티브 SDK로 전환 —
  // 카카오 공식 지원 사유(devtalk.kakao.com 답변: "웹뷰는 플랫폼마다 동작이
  // 달라 공식 지원 불가, 네이티브 SDK 사용 권장")로, 어제 겪었던 웹뷰 차단·
  // 외부 브라우저 복귀 실패 문제가 구조적으로 발생할 수 없다. 카카오톡 앱이
  // 설치돼 있으면 그 앱과 직접 통신(웹뷰/외부 브라우저 전혀 안 거침), 없으면
  // 라이브러리가 자동으로 Custom Tab 기반 계정 로그인으로 대체한다.
  // 받은 access_token은 서버가 카카오에 직접 검증하도록 다음 웹뷰 로드에
  // 실어 보낸다(로그인 자체가 이미 끝난 뒤라 앱 밖으로 나갈 필요가 없다).
  const handleKakaoNativeLogin = useCallback(async () => {
    // 2026-09-06: 클라이언트 쪽 3단계(브릿지 수신 → login() 성공 → 토큰 세팅)는
    // Alert 진단으로 이미 확인 완료 — 매번 뜨는 팝업이 오히려 뒤 화면(서버
    // 진단 결과)을 가려서 제거한다. 이제 서버 쪽 결과만 화면에서 직접 확인한다.
    try {
      const token = await kakaoNativeLogin();
      setNativeKakaoToken(token.accessToken);
    } catch {
      // 사용자가 취소했거나 카카오 로그인 자체가 실패 — 로그인 배너에서
      // 다시 시도할 수 있으니 조용히 무시한다.
    }
  }, []);

  // 2026-09-06: QR스캔에서 이미 겪은 문제(위 qrScanRedirected 부근 주석 —
  // 특정 실기기에서 window.ReactNativeWebView 자체가 안 만들어져 postMessage
  // 경로가 완전히 무력화됨) 카카오 로그인 트리거도 똑같이 postMessage 단일
  // 경로에만 의존하고 있었다 — QR스캔과 동일하게 URL 트리거 경로를 겹쳐 보내는
  // 이중화로 바꾼다. 두 경로가 동시에 걸려도 한 번만 실행되도록 락을 건다.
  const kakaoLoginLockRef = useRef(false);
  const triggerKakaoNativeLoginOnce = useCallback(() => {
    if (kakaoLoginLockRef.current) {
      return;
    }
    kakaoLoginLockRef.current = true;
    handleKakaoNativeLogin().finally(() => {
      kakaoLoginLockRef.current = false;
    });
  }, [handleKakaoNativeLogin]);

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
      if (navState.url && navState.url.includes('kakao_native_trigger=1')) {
        triggerKakaoNativeLoginOnce();
      }
    },
    [goToQrScan, triggerKakaoNativeLoginOnce]
  );

  // 2) onShouldStartLoadWithRequest — 로드 자체를 가로채 취소하고 대신 보낸다.
  // (2026-08-19: 메인 화면 진입 링크에서는 이 방식이 잘 됐는데, 안티/액땜 상세페이지
  // 자체에 새로 넣은 "QR스캔" 버튼(같은 페이지 안에서 쿼리파라미터만 바뀌는 링크)을
  // 누르면 실기기에서 인터셉트가 안 걸리고 그냥 페이지가 다시 로드되는 문제가
  // 보고됐다 — 안드로이드 웹뷰가 "같은 경로, 쿼리만 다른" 네비게이션을 이 콜백
  // 없이 처리하는 경우가 있는 것으로 보인다.) 그래도 되는 기종에서는 이게 가장
  // 빠르게(실제 로드 자체를 막으면서) 넘어가므로 그대로 둔다.
  const onShouldStartLoadWithRequest = useCallback(
    (request: { url: string }) => {
      if (request.url.includes('qrscan=1')) {
        goToQrScan();
        return false;
      }
      if (request.url.includes('kakao_native_trigger=1')) {
        triggerKakaoNativeLoginOnce();
        return false;
      }
      return true;
    },
    [goToQrScan, triggerKakaoNativeLoginOnce]
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
      } else if (payload?.type === 'kakaoNativeLogin') {
        triggerKakaoNativeLoginOnce();
      }
    },
    [goToQrScan, triggerKakaoNativeLoginOnce]
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
      ) : guestId === null ? (
        // 2026-09-06: 기기 식별자(guestId)를 AsyncStorage에서 비동기로 불러오는
        // 동안 예전엔 아무것도 안 그려서(null), 네이티브 스플래시가 내려간
        // 직후부터 실제 웹뷰가 뜨기 전까지 빈 화면이 잠깐 보이는 "멈춘 듯한"
        // 인상을 줬다 — 아래 로딩 오버레이와 똑같은 스피너를 여기서도 보여줘서
        // 그 틈을 없앤다(실제 대기 시간은 그대로지만, 사용자에게는 "로딩 중"이
        // 명확히 보이므로 멈춘 것처럼 느껴지지 않는다).
        <View style={styles.loadingOverlay}>
          <ActivityIndicator size="large" color="#f9a825" />
          <Text style={styles.loadingText}>로또신령 불러오는 중…</Text>
        </View>
      ) : (
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
          onLoadEnd={() => {
            setLoading(false);
            // 2026-09-06: 카카오 access_token은 1회용이라 여기서 지워야
            // 하는 건 맞지만, onLoadEnd는 Streamlit의 SPA 껍데기(정적
            // HTML/JS 번들)가 화면에 뜨는 순간 곧바로 발생한다 — 실제
            // 로그인 처리(카카오 서버 검증 + DB 기록)는 그 뒤에 웹소켓으로
            // 별도 실행되는데, onLoadEnd에서 즉시 토큰을 지우면 uri가
            // 바뀌면서 웹뷰가 통째로 새로고침된다 — 이게 아직 끝나지 않은
            // 로그인 처리를 중간에 끊어버릴 수 있는 여지가 있어(실제로는
            // fresh_start 중복 전송이 진짜 원인이었지만, 이 경쟁상태 자체도
            // 이론적으로 가능하므로 안전장치로 남겨둔다) 약간의 지연 후에
            // 지운다.
            if (nativeKakaoToken) {
              setTimeout(() => setNativeKakaoToken(null), 3000);
            }
          }}
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
                // 2026-09-06: 위 캐시버스팅(_cb) URL 파라미터가 근본 해결책이지만,
                // 이 로드(자동 로그아웃 신호를 보내는 바로 그 순간)만큼은 이중
                // 안전장치로 캐시 자체도 꺼둔다 — 평소 탐색에는 안 걸어서(성능
                // 저하 방지) 정상적인 캐싱 이득은 그대로 유지한다.
                ...(shouldSendFreshStart
                  ? { cacheEnabled: false, cacheMode: 'LOAD_NO_CACHE' as const }
                  : {}),
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
