import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  AppState,
  BackHandler,
  Linking,
  Platform,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { WebView } from 'react-native-webview';
import {
  fetchProducts,
  finishTransaction,
  getAvailablePurchases,
  getPendingTransactionsIOS,
  initConnection,
  isUserCancelledError,
  purchaseErrorListener,
  purchaseUpdatedListener,
  requestPurchase,
  type Product,
  type ProductSubscription,
  type Purchase,
} from 'expo-iap';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { login as kakaoNativeLogin } from '@react-native-seoul/kakao-login';
import * as AppleAuthentication from 'expo-apple-authentication';

import { getStreamlitBaseUrl, getStreamlitPageUrl } from '@/constants/streamlit';
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

// 2026-09-26(구글 인앱결제): Streamlit 쪽(wallet_ui.py)이 "이 상품을 결제해달라"를
// 알리는 두 경로의 이름 — 카카오 네이티브 로그인(kakao_native_trigger)과 같은
// 이중화 기법이다(브릿지가 없는 기기에서는 URL 쿼리로 폴백).
const IAP_URL_PARAM = 'iap_buy';
const IAP_PLAN_URL_PARAM = 'iap_plan';

/** 스토어에서 읽은 가격(displayPrice)을 서버로 넘길 때 쓰는 파라미터 이름 —
 * 서버(wallet_ui.IAP_PRICE_PARAMS)와 한 쌍이다. */
const IAP_PRICE_PARAMS: Record<string, string> = {
  points_1000: 'iap_price_points_1000',
  points_3000: 'iap_price_points_3000',
  'premium-monthly': 'iap_price_premium_monthly',
  'premium-quarterly': 'iap_price_premium_quarterly',
};
const IAP_IN_APP_SKUS = ['points_1000', 'points_3000'];
const IAP_SUBSCRIPTION_SKU = 'premium';

// 2026-10-09(iOS 1.0.2 반려 2.1(a) 대응 — 애플 인앱결제): App Store 구독 제품 ID → 서버가 쓰는 요금제 키
// (서버 products.APPLE_SUBSCRIPTION_PRODUCTS 와 한 쌍 — 테스트가 대조한다). 애플 제품 ID 는 하이픈을 못 써서
// 구글 기본요금제 ID 와 이름이 다르다. 적립금(소모성)은 구글과 같은 ID(IAP_IN_APP_SKUS)다.
const APPLE_SUBSCRIPTION_SKUS: Record<string, string> = {
  premium_monthly: 'premium-monthly',
  premium_3months: 'premium-quarterly',
};
// 앱 ↔ 서버(apple_iap.py) 신호 이름 — 결제한 거래 ID 를 보내고, 서버가 처리를 끝낸 거래를 알려 준다.
const IAP_APPLE_TX_PARAM = 'iap_apple_tx';
const IAP_FINISH_URL_PARAM = 'iap_finish';
const IAP_RESTORE_URL_PARAM = 'iap_restore';
// 서버가 '끝내기' 신호를 안 주면(일시 오류 — 애플이 다음 실행 때 다시 보낸다) 이만큼 뒤 다음 거래로 넘어간다.
const APPLE_DELIVERY_TIMEOUT_MS = 30000;
// App Store 주소(구독 관리 등)는 웹뷰가 아니라 App Store 앱으로 넘긴다.
const APP_STORE_URL_PREFIXES = ['https://apps.apple.com/', 'itms-apps://'];
function isAppStoreUrl(url: string): boolean {
  return Platform.OS === 'ios' && APP_STORE_URL_PREFIXES.some((prefix) => url.startsWith(prefix));
}
/** 상품 가격 조회를 이만큼만 기다리고 첫 화면을 띄운다(스토어가 느려도 앱은 뜨게). */
const PRICE_WAIT_MS = 2500;

// 2026-10-01(진단): kakaoNativeLogin()이 응답 없이 멈추면(카카오톡 전환 후
// 복귀 실패 등) 아래 락이 영원히 안 풀려서, 그 뒤로 몇 번을 다시 눌러도
// 조용히 무시됐다(오늘 실사용 로그로 확인 — 실패 두 건 모두 완료/실패
// 이벤트가 하나도 없이 신호전송만 반복됨). 일정 시간 안에 응답이 없으면
// 타임아웃으로 간주해 락을 풀어준다 — 그래야 사용자가 재시도할 수 있다.
const KAKAO_NATIVE_LOGIN_TIMEOUT_MS = 20000;

// 2026-10-06(iOS 실기기 — 카카오 로그인 먹통·이벤트창 빈칸·타로 장식 없음·하단 레이아웃 깨짐):
// react-native-webview 는 iOS 에서만 **iframe 로드까지** originWhitelist 검사를 거친다
// (RNCWebViewImpl decidePolicyForNavigationAction → createOnShouldStartLoadWithRequest).
// 기본값은 about:blank + http/https 라서 Streamlit components.html 이 쓰는 about:srcdoc iframe 이
// 전부 차단되고 외부 앱 열기(Linking)로 넘겨져 조용히 사라진다 — 서버가 iframe 으로 넣는
// 로그인 신호 스크립트·스타일·장식이 iOS 앱에서만 하나도 실행되지 않던 원인이다.
// 안드로이드는 iframe 로드에 이 검사를 하지 않아 영향이 없다. 카카오톡 등 외부 앱 스킴은
// 지금처럼 목록 밖이라 기존 동작(외부 앱으로 넘김)이 그대로 유지된다.
const WEBVIEW_ORIGIN_WHITELIST = ['http://*', 'https://*', 'about:srcdoc'];

// 2026-10-06(Apple 로그인): 이 빌드가 Apple 로그인 수신부를 갖고 있음을 서버에 알리는 표시.
// 서버(wallet_ui.APPLE_LOGIN_CAPABILITY_PARAM)는 이 값이 있을 때만 Apple 버튼을 그린다 —
// 수신부가 없는 이전 빌드(심사 중 1.0.2 build 8 등)에 눌러도 반응 없는 버튼이 생기지 않게.
const APPLE_LOGIN_CAPABILITY_PARAMS: Record<string, string> =
  Platform.OS === 'ios' ? { apple_login: '1' } : {};

// 2026-10-09(구글 인앱결제 점검 B4): 이 빌드가 결제 수신부(아래 expo-iap 배선)를 갖고 있음을
// 서버에 알리는 표시. 서버(wallet_ui.IAP_CAPABILITY_PARAM)는 이 값이 있을 때만 결제 버튼을 그린다 —
// 결제 스위치를 켠 뒤에도 수신부 없는 옛 빌드에는 먹통 버튼 대신 "앱 업데이트" 안내가 나간다.
// 같은 날 iOS 도 애플 결제 수신부가 생겨 두 플랫폼 모두 보낸다(서버는 native_platform 으로 스토어를 가른다).
const IAP_CAPABILITY_PARAMS: Record<string, string> = { iap: '1' };

// 2026-10-10(같은 세션 화면 이동 — 서버 in_session_nav.APP_CAPABILITY_PARAM): 이 빌드는 주소만 바뀌는
// 이동(history.pushState/replaceState)에도 "불러오는 중"을 바로 내린다(아래 PAGE_READY_INJECTED_JS 의
// history 감시). 이 표시가 없는 옛 빌드에는 서버가 같은 세션 이동을 켜지 않는다(옛 빌드는 6초 가렸다).
const SPA_NAV_CAPABILITY_PARAMS: Record<string, string> = { spa_nav: '1' };

// 2026-10-09(구독 관리 링크): Play 스토어 주소(정기 결제 관리·스토어 페이지)는 웹뷰 안이 아니라
// Play 스토어 앱으로 넘긴다 — 웹뷰 안에서 열면 앱으로 돌아올 길이 없어진다.
const PLAY_STORE_URL_PREFIXES = ['https://play.google.com/', 'market://'];
function isPlayStoreUrl(url: string): boolean {
  return Platform.OS === 'android' && PLAY_STORE_URL_PREFIXES.some((prefix) => url.startsWith(prefix));
}

// 2026-10-09(테스터 신고 "앱인데 크롬 화면이 뜬다·QR 안 됨" — 서버 기록으로 확인): 새 창으로 여는 링크
// (target=_blank·window.open)는 안드로이드 웹뷰 기본값이 "기기 기본 브라우저로 열기"라, 앱 주소(native=1·gid
// 포함)가 그대로 크롬에서 열렸다. 크롬에는 앱 기능(QR 카메라·카카오 앱 로그인)이 없어 눌러도 반응이 없었다.
// 우리 서버 주소면 앱 안에서 열고, Play 스토어는 Play 앱으로, 그 밖의 외부 사이트만 기본 브라우저로 넘긴다.
function isOwnServerUrl(url: string): boolean {
  try {
    return new URL(url).host === new URL(getStreamlitBaseUrl()).host;
  } catch {
    return false;
  }
}

// 2026-10-08(이용자 평가 "로딩이 길고 화면 이동이 끊긴다" — 실기기 영상 실측): 예전엔 문서
// 로드가 끝나면(onLoadEnd) 바로 "불러오는 중" 화면을 내렸는데, Streamlit 은 그 뒤에 자바스크립트로
// 화면을 그리기 시작해서 흰 화면(약 3.5초) → 빈 어두운 화면(약 9.5초)이 그대로 보였다.
// 이제 Streamlit 이 첫 실행을 마쳤다는 신호(stApp 의 data-test-script-state 가 running →
// notRunning)를 받을 때까지 "불러오는 중" 화면을 유지한다. 서버 코드는 바꾸지 않는다.
//  · 신호는 이 스크립트가 최상위 문서에서 직접 보낸다(postMessage {type:'pageReady'}).
//  · Streamlit 이 주소 파라미터만 지우는 경우(history.replaceState — QR 진입 등)에 웹뷰가 로드
//    시작만 알리고 끝을 안 알리는 일이 있어(아래 6초 안전장치 주석), 그때도 이미 그려진 화면이면
//    곧바로 pageReady 를 다시 보낸다.
//  · 신호가 끝내 안 오면 PAGE_READY_MAX_WAIT_MS 뒤에 어쨌든 내린다(멈춘 것처럼 보이지 않게).
const PAGE_READY_MESSAGE_TYPE = 'pageReady';
const PAGE_READY_MAX_WAIT_MS = 15000;
const PAGE_READY_INJECTED_JS = `
(function () {
  if (window.__lnPageReadyInstalled) { return; }
  window.__lnPageReadyInstalled = true;
  function post() {
    try {
      if (window.ReactNativeWebView && window.ReactNativeWebView.postMessage) {
        window.ReactNativeWebView.postMessage(JSON.stringify({ type: '${PAGE_READY_MESSAGE_TYPE}' }));
      }
    } catch (e) {}
  }
  function app() { return document.querySelector('[data-testid="stApp"]'); }
  function state() { var a = app(); return a ? a.getAttribute('data-test-script-state') : null; }
  // 이 앱의 모든 화면은 어두운 배경을 직접 칠한다 — 배경이 아직 Streamlit 기본(밝은색)이면 화면
  // 스타일이 덜 들어온 상태다(시뮬레이션: 첫 실행이 끝난 순간에도 배경이 밝은 경우가 있었다).
  function painted() {
    var a = app(); if (!a) { return false; }
    var m = /rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/.exec(getComputedStyle(a).backgroundColor || '');
    if (!m) { return false; }
    return (Number(m[1]) + Number(m[2]) + Number(m[3])) / 3 < 128;
  }
  // 첫 화면은 실행이 연달아 이어지는 경우가 많아(로그인 복원·부품 값 전달로 인한 재실행) 실행이 끝난
  // 상태가 SETTLE_MS 동안 이어지고 화면이 칠해졌을 때만 "다 그렸다"로 본다.
  var SETTLE_MS = 400, POLL_MS = 100, idleSince = null, sent = false;
  var timer = setInterval(function () {
    if (sent) { clearInterval(timer); return; }
    if (state() !== 'notRunning') { idleSince = null; return; }
    if (idleSince === null) { idleSince = Date.now(); return; }
    if (Date.now() - idleSince >= SETTLE_MS && painted()) { sent = true; clearInterval(timer); post(); }
  }, POLL_MS);
  // Streamlit 이 주소 파라미터만 지울 때(history.replaceState — QR 진입 등) 웹뷰가 로드 시작만
  // 알리고 끝을 안 알리는 경우가 있어, 이미 그려진 화면이면 곧바로 다시 알린다.
  ['replaceState', 'pushState'].forEach(function (name) {
    var orig = history[name];
    if (typeof orig !== 'function') { return; }
    history[name] = function () {
      var r = orig.apply(this, arguments);
      if (sent) { postWhenSettled(); }
      return r;
    };
  });
  // 2026-10-10(실기기 영상): 예전엔 주소가 바뀌는 그 순간에 바로 알렸는데, 웹뷰의 '로드 시작'(onLoadStart)이
  // 그보다 늦게 와서 "불러오는 중"이 다시 켜진 채 안전장치 시간까지 남았다(같은 세션 이동·로그인 뒤 토큰 지우기·
  // 번개조합 저장 등). 이제 잠깐 뒤(로드 시작 신호 다음)에, 그리고 Streamlit 실행이 끝났을 때 알린다.
  var settleTimer = null;
  function postWhenSettled() {
    if (settleTimer) { clearInterval(settleTimer); }
    var startedAt = Date.now();
    settleTimer = setInterval(function () {
      var waited = Date.now() - startedAt;
      if (waited < 250) { return; }
      if (state() === 'notRunning' || waited > 12000) {
        clearInterval(settleTimer); settleTimer = null; post();
      }
    }, 100);
  }
})();
true;
`;

function withTimeout<T>(promise: Promise<T>, ms: number, timeoutMessage: string = 'kakao_native_login_timeout'): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(timeoutMessage)), ms);
    promise.then(
      (value) => { clearTimeout(timer); resolve(value); },
      (err) => { clearTimeout(timer); reject(err); },
    );
  });
}

/** URL의 기존 쿼리를 그대로 두고 넘긴 키만 바꾼 주소를 만든다(2026-09-26).
 * 로그인·결제 후 "지금 보고 있던 그 주소"로 되돌아가기 위한 것이라
 * page/gid/native/가격 파라미터가 전부 보존된다(재빌드하면 처음 페이지로 튕긴다). */
function withParams(url: string, params: Record<string, string | undefined>): string {
  const [base, query = ''] = url.split('#')[0].split('?');
  const pairs = new Map<string, string>();
  for (const part of query.split('&')) {
    if (!part) {
      continue;
    }
    const eq = part.indexOf('=');
    pairs.set(eq === -1 ? part : part.slice(0, eq), eq === -1 ? '' : part.slice(eq + 1));
  }
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') {
      pairs.delete(key);
    } else {
      pairs.set(key, encodeURIComponent(value));
    }
  }
  const qs = Array.from(pairs.entries())
    .map(([key, value]) => (value === '' ? key : `${key}=${value}`))
    .join('&');
  return qs ? `${base}?${qs}` : base;
}

/** 서버가 보내는 결제 요청 — basePlanId가 있으면 정기결제(구독), 없으면 소모성 상품. */
type IapRequest = { sku: string; basePlanId?: string };

/** RN에는 브라우저와 달리 searchParams가 완전하지 않은 URL 구현체가 있어
 * (react-native-url-polyfill 없이) 문자열로 직접 뽑는다. */
function paramFromUrl(url: string | undefined, key: string): string | null {
  if (!url) {
    return null;
  }
  const match = new RegExp(`[?&]${key}=([^&#]*)`).exec(url);
  if (!match) {
    return null;
  }
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return match[1];
  }
}

export default function StreamlitWebView({ page, title, showBack = true, extraParams }: Props) {
  const insets = useSafeAreaInsets();
  const [guestId, setGuestId] = useState<string | null>(null);
  const webViewRef = useRef<WebView>(null);
  const [loading, setLoading] = useState(true);
  // 2026-10-08: PAGE_READY_INJECTED_JS 설명 참고. awaitingPageReadyRef = 지금 로드가 아직
  // Streamlit 첫 실행 완료 신호를 못 받았는가. pageReadyUnsupportedRef = 첫 로드에서 끝내 신호가
  // 안 왔다(스크립트가 안 먹는 환경) → 이후엔 예전처럼 문서 로드 끝(onLoadEnd)에 바로 내린다.
  const awaitingPageReadyRef = useRef(true);
  const pageReadySeenRef = useRef(false);
  const pageReadyUnsupportedRef = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [canGoBack, setCanGoBack] = useState(false);
  // 2026-09-23(사용자 지시): st.dialog(내정보·사용설명서 등)가 열려있는지 —
  // Streamlit 쪽 wallet_ui.inject_manual_dialog_back_bridge()가 postMessage로
  // 실시간으로 알려준다. st.dialog는 웹뷰 히스토리를 전혀 안 써서 canGoBack이
  // 항상 false로 남는다 — 그래서 다이얼로그가 열려 있어도 뒤로가기를 누르면
  // 곧장 앱 종료로 떨어지던 문제(실기기 신고)의 대응.
  const [dialogOpen, setDialogOpen] = useState(false);

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
  // 다시 안 실리도록 소비 처리한다(이 신호는 서버가 실제로 받았는지 확인할
  // 필요 없이 "한 번만 시도하면 충분"하기 때문에 즉시 소비해도 안전하다).
  // 2026-09-17: 아래 webViewUri가 더는 렌더마다 다시 계산되는 파생값이
  // 아니게 되면서(간편인증 A안), 이 문제(카카오 로그인 재로드마다 fresh_start
  // 중복 전송) 자체가 구조적으로 재발 불가능해졌다 — 그래도 이 ref는
  // "isFreshStart를 실제로 한 번 썼는지" 표시로 여전히 정확히 필요하므로
  // 그대로 둔다.
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

  // 2026-09-17(간편인증 A안 — 아스트라 진단 P2 대응): 예전엔 uri를 렌더마다
  // 다시 계산해 key={uri}로 웹뷰를 매번 재생성했다 — 카카오 로그인 성공 시
  // (1)토큰을 실어 재생성 → onLoadEnd 3초 뒤 (2)토큰을 지우며 또 재생성,
  // 이렇게 한 번의 로그인에 웹뷰가 두 번 새로 만들어졌다. 두 번째 재생성은
  // 완전한 낭비였다 — 토큰은 이미 서버(user_page.py)가 1회용으로 소비·삭제한
  // 뒤라 다시 지울 게 없고, 오히려 막 세운 로그인 세션(웹소켓)을 다시
  // 끊어버려 "로그인은 성공했는데 내정보에 반영 안 됨" 류 증상의 원인으로
  // 추정됐다.
  //
  // 이제 웹뷰 주소는 "렌더마다 다시 계산되는 값"이 아니라 "명시적으로
  // setWebViewUri를 부를 때만 바뀌는 상태"로 관리한다 — 로그인 성공 시
  // 딱 한 번만 새 주소로 이동시키고, 그 이후로는 아무것도 건드리지 않는다.
  const [webViewUri, setWebViewUri] = useState<string | null>(null);
  const initialUriSetRef = useRef(false);
  const lastSentTimeoutTriggerRef = useRef(0);

  const buildUri = useCallback(
    (overrides?: Record<string, string>) =>
      getStreamlitPageUrl(page, guestId, {
        ...(extraParams || {}),
        // 2026-10-03: 서버(wallet_ui)가 iOS/안드로이드 네이티브를 구분할 수 있는 유일한
        // 신호. native=1("앱에서 왔는가")은 constants/streamlit.ts가 붙이지만,
        // 그 값만으로는 플랫폼을 알 수 없어 "iOS에는 결제 버튼을 안 띄운다" 같은
        // 분기를 서버에 만들 수 없다. 값은 상수 문자열이 아니라 Platform.OS를
        // 그대로 쓴다(ios/android가 그대로 내려간다).
        native_platform: Platform.OS,
        ...APPLE_LOGIN_CAPABILITY_PARAMS,
        ...IAP_CAPABILITY_PARAMS,
        ...SPA_NAV_CAPABILITY_PARAMS,
        ...priceParamsRef.current,
        ...(overrides || {}),
      }),
    [page, guestId, extraParams]
  );

  // ── 2026-09-26 스토어 가격 · 현재 주소 기억 ────────────────────────────
  // priceParamsRef: 스토어에서 읽은 실제 가격(표시용). 첫 화면 주소에 실어 보내면
  //   서버가 저장해두고 이후 모든 화면이 그 값을 쓴다(wallet_ui.iap_prices 참고) —
  //   Play Console에서 가격을 바꾸면 다음 앱 실행에 자동 반영되고 코드 수정이 필요 없다.
  //   ref로 두는 이유: state로 두면 buildUri 신원이 계속 바뀌어 다른 effect가 다시 돈다.
  const priceParamsRef = useRef<Record<string, string>>({});
  // 2026-10-09(점검 B2): 앱 시작 때 찾은 "결제는 됐는데 서버 처리(소비·승인)가 안 끝난" 구매 1건 —
  // 첫 화면 주소에 함께 실어 보내 서버가 마저 처리하게 한다(따로 다시 로드하지 않는다).
  // 구글은 3일 안에 승인이 없으면 자동 환불하므로, 결제 직후 앱이 꺼졌거나 Play 스토어에서
  // 직접 재구독한 경우도 다음 실행 때 여기서 이어진다. 여러 건이면 다음 실행 때 다음 건.
  const recoveryParamsRef = useRef<Record<string, string>>({});
  // 2026-10-09: iOS 도 App Store 가격을 읽어 첫 주소에 싣는다(최대 PRICE_WAIT_MS 기다림).
  const [pricesReady, setPricesReady] = useState(false);
  // 지금 웹뷰가 실제로 보고 있는 주소 — 로그인 성공·결제 완료 후 이 자리로 돌아온다.
  const currentUrlRef = useRef<string | null>(null);

  /** 현재 주소에 파라미터만 더한 주소. 저장된 주소가 아직 없으면(첫 로드 전)
   * buildUri()로 만든 기본 주소를 쓴다.
   *
   * 2026-10-03: native_platform 도 항상 다시 실어 보낸다. currentUrlRef 에 이미
   * 들어 있어도 withParams 가 Map 기반이라 같은 키를 덮어쓸 뿐 중복 파라미터가
   * 생기지 않는다. 로그인·결제 후 복귀 주소가 플랫폼 정보를 잃으면 그 화면에서만
   * iOS 분기(결제 버튼 숨김)가 풀려 버린다. */
  const reloadWith = useCallback(
    (params: Record<string, string>) =>
      withParams(currentUrlRef.current ?? buildUri(), {
        native_platform: Platform.OS,
        ...APPLE_LOGIN_CAPABILITY_PARAMS,
        ...IAP_CAPABILITY_PARAMS,
        ...SPA_NAV_CAPABILITY_PARAMS,
        ...params,
      }),
    [buildUri]
  );

  useEffect(() => {
    let cancelled = false;
    const finish = () => {
      if (!cancelled) {
        setPricesReady(true);
      }
    };
    const timer = setTimeout(finish, PRICE_WAIT_MS);
    (async () => {
      try {
        // iOS: initConnection 뒤 애플이 끝내지 않은 거래를 purchaseUpdatedListener 로 다시 보내 준다
        // (아래 리스너가 서버로 넘긴다 — 안드로이드의 '미처리 결제 복구'에 해당).
        await initConnection();
        const subsSkus = Platform.OS === 'ios' ? Object.keys(APPLE_SUBSCRIPTION_SKUS) : [IAP_SUBSCRIPTION_SKU];
        const [inAppFetched, subsFetched] = await Promise.all([
          fetchProducts({ skus: IAP_IN_APP_SKUS, type: 'in-app' }),
          fetchProducts({ skus: subsSkus, type: 'subs' }),
        ]);
        const displayPrices: Record<string, string> = {};
        for (const item of (Array.isArray(inAppFetched) ? inAppFetched : []) as Product[]) {
          if (item.displayPrice) {
            displayPrices[item.id] = item.displayPrice;
          }
        }
        for (const item of (Array.isArray(subsFetched) ? subsFetched : []) as ProductSubscription[]) {
          if (Platform.OS === 'ios') {
            // 애플 구독 제품 ID → 서버 요금제 키(가격 파라미터 이름은 두 플랫폼 공용).
            const planKey = APPLE_SUBSCRIPTION_SKUS[item.id];
            if (planKey && item.displayPrice) {
              displayPrices[planKey] = item.displayPrice;
            }
            continue;
          }
          if (item.displayPrice) {
            displayPrices[item.id] = item.displayPrice;
          }
          for (const offer of item.subscriptionOffers ?? []) {
            const planId = offer.basePlanIdAndroid;
            if (planId && offer.displayPrice) {
              displayPrices[planId] = offer.displayPrice;
            }
          }
        }
        const params: Record<string, string> = {};
        for (const [key, param] of Object.entries(IAP_PRICE_PARAMS)) {
          const value = displayPrices[key];
          if (value) {
            params[param] = value;
          }
        }
        priceParamsRef.current = params;
        if (Platform.OS !== 'android') {
          return; // 아래 '미처리 결제 복구'는 구글 전용(애플은 리스너가 다시 받아 처리한다)
        }
        try {
          const owned = (await getAvailablePurchases()) as Purchase[];
          const unfinished = (Array.isArray(owned) ? owned : []).find(
            (item) =>
              item.purchaseState === 'purchased' &&
              !!item.purchaseToken &&
              (item as { isAcknowledgedAndroid?: boolean | null }).isAcknowledgedAndroid === false
          );
          if (unfinished?.purchaseToken) {
            recoveryParamsRef.current = {
              iap_purchase_token: unfinished.purchaseToken,
              iap_product_id: unfinished.productId,
            };
          }
        } catch {
          // 조회 실패 — 다음 실행 때 다시 본다(구글 3일 기한 안에 여러 번 기회가 있다).
        }
      } catch {
        // 스토어 연결 실패 — 서버 기본값(상수)으로 표시된다. 결제 시점에 다시 안내된다.
      } finally {
        clearTimeout(timer);
        finish();
      }
    })();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);

  // ── 2026-09-26 구글 인앱결제 ────────────────────────────────────────────
  // 지급·승인은 서버(google_play_pg.py)가 전담한다 — 여기서는 (1) Streamlit이
  // 요청한 상품으로 Google Play 결제창을 띄우고 (2) 결제가 끝나면 purchaseToken을
  // 웹뷰 주소에 실어 서버로 넘긴다. finishTransaction은 절대 호출하지 않는다
  // (서버가 검증 후 consume/acknowledge를 직접 한다 — 구글 권장 방식).
  const [iapRequest, setIapRequest] = useState<IapRequest | null>(null);
  const purchaseInFlightRef = useRef(false);

  // 2026-10-01: 카카오 로그인 락(§6)과 같은 패턴 — fetchProducts/requestPurchase가
  // 응답 없이 멈추면 purchaseInFlightRef가 영원히 true로 남아(아래 가드) 이후
  // 결제 요청이 전부 조용히 무시된다. requestPurchase는 결제 완료가 아니라
  // "요청 전달 확인"만 돌려주고 실제 결과는 purchaseUpdatedListener로 오므로
  // (openiap 공식 문서 확인, 2026-10-01) 타임아웃을 걸어도 사용자가 결제창에서
  // 입력 중인 걸 끊지 않는다.
  const IAP_DISPATCH_TIMEOUT_MS = 20000;

  // 결제 후 서버로 토큰 전달 — 웹뷰를 새 주소로 다시 띄우면 user_page.py가
  // handle_google_play_purchase_return()으로 검증·지급·승인까지 처리한다.
  const deliverPurchaseToServer = useCallback(
    (purchase: Purchase) => {
      const token = purchase.purchaseToken ?? null;
      if (!token) {
        Alert.alert(
          '결제 확인 실패',
          '구매 정보를 받지 못했습니다. 잠시 후 다시 시도하시고, 계속 실패하면 고객센터에 문의해 주세요.'
        );
        return;
      }
      setIapRequest(null);
      setWebViewUri(
        reloadWith({
          iap_purchase_token: token,
          iap_product_id: purchase.productId,
          _cb: String(Date.now()),
        })
      );
    },
    [reloadWith]
  );

  // ── 2026-10-09 애플 인앱결제: 거래 전달 → 서버 확인·지급 → 서버의 '끝내기' 신호로 finishTransaction ──
  // 애플은 끝내지 않은 거래를 앱을 켤 때마다 다시 보내므로, 서버 확인 전에는 절대 끝내지 않는다
  // (끝낸 뒤 서버 지급이 실패하면 되살릴 길이 없다). 한 번에 한 건씩 서버로 보낸다(주소 하나에 하나).
  const applePurchasesRef = useRef<Map<string, Purchase>>(new Map());
  const appleQueueRef = useRef<string[]>([]);
  const appleInFlightRef = useRef<string | null>(null);
  const appleInFlightTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const pumpAppleQueue = useCallback(() => {
    if (appleInFlightRef.current || appleQueueRef.current.length === 0) {
      return;
    }
    const transactionId = appleQueueRef.current.shift() as string;
    appleInFlightRef.current = transactionId;
    if (appleInFlightTimerRef.current) {
      clearTimeout(appleInFlightTimerRef.current);
    }
    appleInFlightTimerRef.current = setTimeout(() => {
      // 서버가 끝내기를 안 보냈다(일시 오류 등) — 이 거래는 다음 실행 때 애플이 다시 보낸다.
      if (appleInFlightRef.current === transactionId) {
        appleInFlightRef.current = null;
        pumpAppleQueue();
      }
    }, APPLE_DELIVERY_TIMEOUT_MS);
    if (!initialUriSetRef.current) {
      // 첫 화면 주소가 아직 안 정해졌다 — 첫 주소에 함께 싣는다(덮어써져 사라지지 않게).
      recoveryParamsRef.current = { ...recoveryParamsRef.current, [IAP_APPLE_TX_PARAM]: transactionId };
      return;
    }
    setWebViewUri(reloadWith({ [IAP_APPLE_TX_PARAM]: transactionId, _cb: String(Date.now()) }));
  }, [reloadWith]);

  const deliverApplePurchase = useCallback(
    (purchase: Purchase) => {
      const transactionId = String((purchase as { transactionId?: string }).transactionId || purchase.id || '');
      if (!/^[0-9]{1,32}$/.test(transactionId)) {
        Alert.alert('결제 확인 실패', '구매 정보를 받지 못했습니다. 앱을 다시 열면 자동으로 다시 확인됩니다.');
        return;
      }
      setIapRequest(null);
      applePurchasesRef.current.set(transactionId, purchase);
      if (appleInFlightRef.current !== transactionId && !appleQueueRef.current.includes(transactionId)) {
        appleQueueRef.current.push(transactionId);
      }
      pumpAppleQueue();
    },
    [pumpAppleQueue]
  );

  const finishApplePurchase = useCallback(
    async (transactionId: string) => {
      if (Platform.OS !== 'ios' || !/^[0-9]{1,32}$/.test(transactionId)) {
        return;
      }
      let purchase = applePurchasesRef.current.get(transactionId);
      if (!purchase) {
        try {
          const pending = (await getPendingTransactionsIOS()) as Purchase[];
          purchase = (Array.isArray(pending) ? pending : []).find(
            (item) => String((item as { transactionId?: string }).transactionId || item.id) === transactionId
          );
        } catch {
          purchase = undefined;
        }
      }
      if (purchase) {
        try {
          await finishTransaction({
            purchase,
            isConsumable: !APPLE_SUBSCRIPTION_SKUS[purchase.productId],
          });
          applePurchasesRef.current.delete(transactionId);
        } catch {
          // 끝내기 실패 — 애플이 다음 실행 때 다시 보내고, 서버는 이미 처리된 거래로 보고 다시 끝내기를 보낸다.
        }
      }
      if (appleInFlightRef.current === transactionId) {
        appleInFlightRef.current = null;
        if (appleInFlightTimerRef.current) {
          clearTimeout(appleInFlightTimerRef.current);
          appleInFlightTimerRef.current = null;
        }
        pumpAppleQueue();
      }
    },
    [pumpAppleQueue]
  );

  // '구매 복원'(App Store 지침 3.1.1) — 이 Apple ID 의 유효한 구독을 찾아 서버로 다시 보낸다.
  // 구독은 로그인 계정에 묶여 있어 같은 계정이면 다른 기기에서도 그대로 이어지고, 다른 계정에 이미 연결된
  // 구독이면 서버가 안내한다. 적립금(소모성)은 복원 대상이 아니다.
  const restoreApplePurchases = useCallback(async () => {
    if (Platform.OS !== 'ios') {
      return;
    }
    try {
      await initConnection();
      const owned = (await getAvailablePurchases()) as Purchase[];
      const subs = (Array.isArray(owned) ? owned : [])
        .filter((item) => !!APPLE_SUBSCRIPTION_SKUS[item.productId])
        .sort((a, b) => (b.transactionDate || 0) - (a.transactionDate || 0));
      if (subs.length === 0) {
        Alert.alert('복원할 구독이 없습니다', '이 Apple ID로 이용 중인 로또신령 구독을 찾지 못했습니다.');
        return;
      }
      deliverApplePurchase(subs[0]);
    } catch (e) {
      Alert.alert('구매 복원에 실패했습니다', e instanceof Error ? e.message : '잠시 후 다시 시도해 주세요.');
    }
  }, [deliverApplePurchase]);

  const restoreLockRef = useRef(false);
  const triggerAppleRestoreOnce = useCallback(() => {
    if (restoreLockRef.current) {
      return;
    }
    restoreLockRef.current = true;
    restoreApplePurchases().finally(() => {
      restoreLockRef.current = false;
    });
  }, [restoreApplePurchases]);

  const finishFromUrl = useCallback(
    (url?: string) => {
      const value = paramFromUrl(url, IAP_FINISH_URL_PARAM);
      if (!value) {
        return false;
      }
      for (const id of value.split(',')) {
        finishApplePurchase(id.trim());
      }
      return true;
    },
    [finishApplePurchase]
  );

  // 매 렌더마다 새 함수를 쓰면 리스너가 재등록되므로 ref로 최신 구현을 본다.
  const deliverRef = useRef(deliverPurchaseToServer);
  useEffect(() => {
    deliverRef.current = deliverPurchaseToServer;
  }, [deliverPurchaseToServer]);
  const deliverAppleRef = useRef(deliverApplePurchase);
  useEffect(() => {
    deliverAppleRef.current = deliverApplePurchase;
  }, [deliverApplePurchase]);

  useEffect(() => {
    let cancelled = false;
    // 스토어 연결·상품 조회·미완료 구매 재전송은 아래 가격 수집 effect가 한 번에
    // 처리한다(initConnection을 두 곳에서 부르면 관리 포인트만 늘어난다).
    // purchaseUpdatedListener로 이전 실행에서 서버 전달이 실패한 구매까지 다시
    // 올라오므로, 그걸 그대로 서버에 넘기는 것이 곧 재전송 안전장치가 된다
    // (서버 멱등성이 중복 지급을 막는다).
    const updated = purchaseUpdatedListener((purchase) => {
      if (cancelled) {
        return;
      }
      // 2026-10-09(점검 H3): 결제 대기(편의점·계좌 등 승인이 늦는 수단)는 아직 돈이 안 들어온
      // 상태라 서버로 보내지 않는다 — 완료되면 이 리스너가 다시 불리거나(앱 실행 중), 다음 실행 때
      // 미처리 결제 복구(recoveryParamsRef)로 이어진다.
      if (purchase.purchaseState === 'pending') {
        setIapRequest(null);
        Alert.alert(
          '결제 승인 대기 중',
          '결제가 아직 승인되지 않았습니다. 승인이 완료되면 자동으로 지급됩니다.'
        );
        return;
      }
      if (Platform.OS === 'ios') {
        deliverAppleRef.current(purchase);
        return;
      }
      deliverRef.current(purchase);
    });
    const failed = purchaseErrorListener((error) => {
      if (cancelled || isUserCancelledError(error) || error.code === 'user-cancelled') {
        return; // 사용자 취소는 조용히 넘어간다(다시 누르면 된다).
      }
      Alert.alert('결제가 완료되지 않았습니다', error.message || '알 수 없는 오류');
    });
    return () => {
      cancelled = true;
      updated.remove();
      failed.remove();
    };
  }, []);

  // 결제 실행 — 상품 조회 → (구독이면 기본요금제에 맞는 offerToken 선택) → 결제창.
  // 결과는 위 purchaseUpdatedListener로 온다(반환값 아님 — expo-iap 규약).
  useEffect(() => {
    if (!iapRequest || purchaseInFlightRef.current) {
      return;
    }
    let cancelled = false;
    const request = iapRequest;
    (async () => {
      purchaseInFlightRef.current = true;
      try {
        if (Platform.OS === 'ios') {
          // 애플: 구독은 제품 ID 하나가 요금제 하나다(기본요금제·offerToken 없음).
          const isSub = !!APPLE_SUBSCRIPTION_SKUS[request.sku];
          const fetchedIos = await withTimeout(
            fetchProducts({ skus: [request.sku], type: isSub ? 'subs' : 'in-app' }),
            IAP_DISPATCH_TIMEOUT_MS,
            'iap_dispatch_timeout'
          );
          const listIos = (Array.isArray(fetchedIos) ? fetchedIos : []) as Array<Product | ProductSubscription>;
          if (!listIos.find((item) => item.id === request.sku)) {
            throw new Error('상품 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.');
          }
          // 타임아웃을 걸지 않는다: iOS 의 requestPurchase 는 결제 시트(Face ID·암호 입력)가 끝나야 돌아온다
          // (안드로이드는 결제창이 열리면 바로 돌아온다). 20초에 끊으면 결제는 되는데 오류 창이 뜨고,
          // 잠금이 풀려 한 번 더 결제할 수 있게 된다(독립 검토 지적, 2026-10-09).
          await (isSub
            ? requestPurchase({ request: { apple: { sku: request.sku } }, type: 'subs' })
            : requestPurchase({ request: { apple: { sku: request.sku } }, type: 'in-app' }));
          return;
        }
        const queryType = request.basePlanId ? ('subs' as const) : ('in-app' as const);
        const fetched = await withTimeout(
          fetchProducts({ skus: [request.sku], type: queryType }),
          IAP_DISPATCH_TIMEOUT_MS,
          'iap_dispatch_timeout'
        );
        const list = (Array.isArray(fetched) ? fetched : []) as Array<Product | ProductSubscription>;
        const product = list.find((item) => item.id === request.sku);
        if (!product) {
          throw new Error('상품 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.');
        }
        if (request.basePlanId) {
          const offers =
            (product as ProductSubscription).subscriptionOffers?.filter(
              (offer) => !!offer.offerTokenAndroid
            ) ?? [];
          // 2026-10-09: 같은 기본요금제에 할인·체험 혜택이 생겨도 기본 가격(혜택 없는 것)을 고른다 —
          // 서버 고지·화면 가격과 실제 결제가 어긋나지 않게. 기본 혜택은 id(=offerId)가 비어 있거나
          // 기본요금제 ID 와 같고, 가격 단계가 1개다.
          const planOffers = offers.filter((item) => item.basePlanIdAndroid === request.basePlanId);
          const offer =
            planOffers.find(
              (item) => !item.id || item.id === request.basePlanId
            ) ??
            planOffers.find((item) => (item.pricingPhasesAndroid?.pricingPhaseList?.length ?? 0) === 1) ??
            planOffers[0] ??
            null;
          if (!offer?.offerTokenAndroid) {
            throw new Error('선택하신 구독 요금제를 찾지 못했습니다.');
          }
          await withTimeout(
            requestPurchase({
              request: {
                google: {
                  skus: [request.sku],
                  subscriptionOffers: [{ sku: request.sku, offerToken: offer.offerTokenAndroid }],
                  // 2026-10-09(점검 M1): 기기 식별자(무작위값, 개인정보 아님)를 구글 부정결제 탐지에 함께 넘긴다.
                  obfuscatedAccountId: guestId ?? undefined,
                },
              },
              type: 'subs',
            }),
            IAP_DISPATCH_TIMEOUT_MS,
            'iap_dispatch_timeout'
          );
        } else {
          await withTimeout(
            requestPurchase({
              request: { google: { skus: [request.sku], obfuscatedAccountId: guestId ?? undefined } },
              type: 'in-app',
            }),
            IAP_DISPATCH_TIMEOUT_MS,
            'iap_dispatch_timeout'
          );
        }
      } catch (e) {
        if (!cancelled) {
          Alert.alert(
            '결제를 시작할 수 없습니다',
            e instanceof Error ? e.message : '알 수 없는 오류'
          );
        }
      } finally {
        purchaseInFlightRef.current = false;
        if (!cancelled) {
          setIapRequest(null);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // guestId 는 첫 화면 전에 이미 정해져 바뀌지 않는다(결제 요청이 올 때 최신값을 쓴다).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [iapRequest]);

  const parseIapRequestFromUrl = useCallback((url?: string): IapRequest | null => {
    const sku = paramFromUrl(url, IAP_URL_PARAM);
    if (!sku) {
      return null;
    }
    const basePlanId = paramFromUrl(url, IAP_PLAN_URL_PARAM) || undefined;
    return { sku, basePlanId };
  }, []);

  // postMessage와 URL 폴백이 같은 순간에 둘 다 들어와도 한 번만 실행되게 한다
  // (같은 요청이면 상태 객체를 유지 — 그래야 아래 effect가 두 번 돌지 않는다).
  const triggerIapPurchaseOnce = useCallback((request: IapRequest) => {
    setIapRequest((prev) => prev ?? request);
  }, []);

  // 최초 1회: guestId가 준비되는 순간 첫 주소를 확정한다. 콜드스타트로
  // isFreshStart가 켜져 있었거나 마운트 직후 바로 idle 타임아웃이 감지된
  // 경우엔 fresh_start도 이 최초 주소에 함께 싣는다 — 캐시버스터(_cb)는
  // 안드로이드 웹뷰가 "기본 URL만 같으면 쿼리스트링이 달라져도 캐시된
  // 예전 페이지를 그대로 보여주는" 문제(react-native-webview 다수 보고,
  // cacheEnabled=false로도 해결 안 되는 경우 있음) 때문에 매번 다른 값을
  // 끼워 넣어 웹뷰가 "완전히 새로운 주소"로 인식하게 만든다.
  useEffect(() => {
    if (guestId === null || initialUriSetRef.current || !pricesReady) {
      return;
    }
    initialUriSetRef.current = true;
    lastSentTimeoutTriggerRef.current = timeoutLogoutTrigger;
    setWebViewUri(
      buildUri({
        ...recoveryParamsRef.current,
        ...(shouldSendFreshStart ? { fresh_start: '1', _cb: String(Date.now()) } : {}),
      })
    );
    recoveryParamsRef.current = {};
    // guestId가 처음 채워지는 순간과 스토어 가격 조회가 끝난 순간(pricesReady)
    // 중 늦은 쪽에서 한 번만 실행한다 — 첫 주소에 가격 파라미터를 함께 실어 보내
    // 서버가 저장하게 하려는 것(pricesReady가 안 오면 타임아웃으로 먼저 진행한다).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guestId, pricesReady]);

  // 최초 로드 이후에 idle 타임아웃이 새로 감지되면(예: 웹뷰가 오래 떠있다가
  // 백그라운드에서 복귀) 그때만 fresh_start를 실어 딱 한 번 다시 이동시킨다.
  useEffect(() => {
    if (!initialUriSetRef.current) {
      return;
    }
    if (timeoutLogoutTrigger > lastSentTimeoutTriggerRef.current) {
      lastSentTimeoutTriggerRef.current = timeoutLogoutTrigger;
      setWebViewUri(buildUri({ fresh_start: '1', _cb: String(Date.now()) }));
    }
  }, [timeoutLogoutTrigger, buildUri]);

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
    // 2026-10-08: 6초 → PAGE_READY_MAX_WAIT_MS. 이제 "불러오는 중"은 Streamlit 이 화면을 다 그릴
    // 때까지 유지하므로(PAGE_READY_INJECTED_JS), 6초에 내리면 운영 첫 화면(실측 약 14초)에서 다시
    // 빈 화면이 드러난다. 위 QR 경우는 replaceState 감지로 즉시 신호가 오므로 여기까지 오지 않는다.
    const timer = setTimeout(() => {
      if (awaitingPageReadyRef.current && !pageReadySeenRef.current) {
        // 첫 로드부터 신호가 한 번도 안 왔다 — 이 환경에선 신호를 기다리지 않는다.
        pageReadyUnsupportedRef.current = true;
      }
      awaitingPageReadyRef.current = false;
      setLoading(false);
    }, PAGE_READY_MAX_WAIT_MS);
    return () => clearTimeout(timer);
  }, [loading, webViewUri]);

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
  // 2026-10-06(iOS 로그인 먹통 재발 방지): 예전엔 SDK 실패를 조용히 삼켜 화면·서버 어디에도
  // 흔적이 없었다(원인 찾는 데 하루가 걸림). 사용자가 직접 취소한 경우만 조용히 넘기고, 그 밖의
  // 실패는 이유를 native_login_error 로 서버에 남긴다(서버는 기록 + 공통 실패 안내 토스트).
  const reportNativeLoginError = useCallback(
    (provider: 'kakao' | 'apple', err: unknown) => {
      const e = err as { code?: unknown; message?: unknown } | null;
      const code = String(e?.code ?? '');
      const message = String(e?.message ?? err ?? '');
      const text = `${code} ${message}`.toLowerCase();
      if (code === 'ERR_REQUEST_CANCELED' || text.includes('cancel')) {
        return;
      }
      const detail = `${provider}:${code || 'error'}:${message}`.slice(0, 180);
      setWebViewUri(reloadWith({ native_login_error: detail, _cb: String(Date.now()) }));
    },
    [reloadWith]
  );

  const handleKakaoNativeLogin = useCallback(async () => {
    // 2026-09-06: 클라이언트 쪽 3단계(브릿지 수신 → login() 성공 → 토큰 세팅)는
    // Alert 진단으로 이미 확인 완료 — 매번 뜨는 팝업이 오히려 뒤 화면(서버
    // 진단 결과)을 가려서 제거한다. 이제 서버 쪽 결과만 화면에서 직접 확인한다.
    try {
      // 2026-10-01(진단): 응답이 없으면 20초에서 끊는다 — 위
      // KAKAO_NATIVE_LOGIN_TIMEOUT_MS 설명 참고(락이 영원히 안 풀리던 문제).
      const token = await withTimeout(kakaoNativeLogin(), KAKAO_NATIVE_LOGIN_TIMEOUT_MS);
      // 2026-09-17: 로그인 성공 시 딱 한 번만 새 주소로 이동시킨다 — 위
      // webViewUri 설명 참고.
      // 2026-09-26: 재빌드(buildUri) 대신 "지금 보고 있던 주소 + 토큰"으로 바꿨다 —
      // 재빌드하면 사용자가 웹뷰 안에서 이동해둔 페이지(그리고 주소에 남아있던
      // 파라미터·열린 화면 표시)를 잃고 처음 페이지로 튕긴다.
      setWebViewUri(reloadWith({ native_kakao_token: token.accessToken, _cb: String(Date.now()) }));
    } catch (err) {
      // 사용자가 취소했거나 카카오 로그인 자체가 실패했거나(타임아웃 포함) —
      // 로그인 배너에서 다시 시도할 수 있다. 타임아웃이어도
      // triggerKakaoNativeLoginOnce의 .finally()가 락을 반드시 풀어준다.
      // 2026-10-06: 취소가 아닌 실패는 이유를 서버에 보고한다(reportNativeLoginError 설명 참고).
      reportNativeLoginError('kakao', err);
    }
  }, [reloadWith, reportNativeLoginError]);

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

  // 2026-10-06(애플 심사 가이드라인 4.8): Apple 로그인 — 카카오와 같은 3단계(서버 신호 →
  // 네이티브 로그인 → 토큰을 주소에 실어 서버 검증). 이름·이메일은 요청하지 않는다
  // (requestedScopes 비움 — 서버는 애플 사용자 ID만 쓴다). authorizationCode 는 탈퇴 시 토큰
  // 해지(2단계)용으로 함께 보내며 지금 서버는 주소에서 지우기만 한다.
  // 서버 쪽 짝: wallet_ui.NATIVE_LOGIN_TRIGGERS["apple"], user_page 의 native_apple_token 처리.
  const handleAppleNativeLogin = useCallback(async () => {
    try {
      const credential = await withTimeout(
        AppleAuthentication.signInAsync({ requestedScopes: [] }),
        KAKAO_NATIVE_LOGIN_TIMEOUT_MS * 6,
        'apple_native_login_timeout'
      );
      if (!credential.identityToken) {
        reportNativeLoginError('apple', { code: 'NO_IDENTITY_TOKEN', message: 'identityToken 없음' });
        return;
      }
      setWebViewUri(
        reloadWith({
          native_apple_token: credential.identityToken,
          ...(credential.authorizationCode ? { native_apple_code: credential.authorizationCode } : {}),
          _cb: String(Date.now()),
        })
      );
    } catch (err) {
      reportNativeLoginError('apple', err);
    }
  }, [reloadWith, reportNativeLoginError]);

  const appleLoginLockRef = useRef(false);
  const triggerAppleNativeLoginOnce = useCallback(() => {
    if (Platform.OS !== 'ios' || appleLoginLockRef.current) {
      return;
    }
    appleLoginLockRef.current = true;
    handleAppleNativeLogin().finally(() => {
      appleLoginLockRef.current = false;
    });
  }, [handleAppleNativeLogin]);

  // 1) onNavigationStateChange — 웹뷰의 실제 URL이 바뀔 때마다 항상 불리는(리액티브)
  // 이벤트라 세 경로 중 가장 신뢰도가 높다. 실기기(Android 16, Samsung SM-M166S)에서
  // window.ReactNativeWebView 자체가 안 만들어져 2)의 postMessage 경로가 완전히
  // 무력화되는 게 실측으로 확인됐다(2026-08-22, page_hedge.py의 진단 배너로 확인) —
  // 그 대체 경로로 추가함.
  const onNavigationStateChange = useCallback(
    (navState: { canGoBack: boolean; url?: string }) => {
  setCanGoBack(navState.canGoBack);
  // 지금 보고 있는 실제 주소를 기억해 둔다 — 로그인·결제 후 이 주소로 돌아온다.
  if (navState.url) {
    currentUrlRef.current = navState.url;
  }
  if (navState.url && navState.url.includes('qrscan=1')) {
        goToQrScan();
      }
      if (navState.url && navState.url.includes('kakao_native_trigger=1')) {
        triggerKakaoNativeLoginOnce();
      }
      if (navState.url && navState.url.includes('apple_native_trigger=1')) {
        triggerAppleNativeLoginOnce();
      }
      const iapFromUrl = parseIapRequestFromUrl(navState.url);
      if (iapFromUrl) {
        triggerIapPurchaseOnce(iapFromUrl);
      }
      finishFromUrl(navState.url);
      if (navState.url && navState.url.includes(`${IAP_RESTORE_URL_PARAM}=1`)) {
        triggerAppleRestoreOnce();
      }
    },
    [goToQrScan, triggerKakaoNativeLoginOnce, triggerAppleNativeLoginOnce, parseIapRequestFromUrl, triggerIapPurchaseOnce, finishFromUrl, triggerAppleRestoreOnce]
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
      if (isPlayStoreUrl(request.url) || isAppStoreUrl(request.url)) {
        Linking.openURL(request.url).catch(() => {});
        return false;
      }
      if (finishFromUrl(request.url)) {
        return false;
      }
      if (request.url.includes(`${IAP_RESTORE_URL_PARAM}=1`)) {
        triggerAppleRestoreOnce();
        return false;
      }
      if (request.url.includes('qrscan=1')) {
        goToQrScan();
        return false;
      }
      if (request.url.includes('kakao_native_trigger=1')) {
        triggerKakaoNativeLoginOnce();
        return false;
      }
      if (request.url.includes('apple_native_trigger=1')) {
        triggerAppleNativeLoginOnce();
        return false;
      }
      const iapFromUrl = parseIapRequestFromUrl(request.url);
      if (iapFromUrl) {
        triggerIapPurchaseOnce(iapFromUrl);
        return false;
      }
      return true;
    },
    [goToQrScan, triggerKakaoNativeLoginOnce, triggerAppleNativeLoginOnce, parseIapRequestFromUrl, triggerIapPurchaseOnce, finishFromUrl, triggerAppleRestoreOnce]
  );

  // 3) onMessage(postMessage) — 웹뷰 JS가 곧장 네이티브로 메시지를 보내는 경로.
  // window.ReactNativeWebView 자체가 없는 기기에서는 이 경로가 애초에 실행조차
  // 안 되지만(위 1번 설명 참고), 되는 기기에서는 가장 즉각적이라 그대로 둔다.
  // window.ReactNativeWebView가 없는 일반 브라우저에서는 페이지 쪽(page_hedge.py)이
  // 이 메시지를 아예 안 보내고 URL 폴백만 쓰도록 이미 분기해뒀다.
  const onMessage = useCallback(
    (event: { nativeEvent: { data: string } }) => {
      let payload: {
        type?: string;
        target?: string;
        open?: boolean;
        productId?: string;
        basePlanId?: string;
      } | null = null;
      try {
        payload = JSON.parse(event.nativeEvent.data);
      } catch {
        return;
      }
      if (payload?.type === 'openQrScan') {
        goToQrScan();
      } else if (payload?.type === 'kakaoNativeLogin') {
        triggerKakaoNativeLoginOnce();
      } else if (payload?.type === 'appleNativeLogin') {
        triggerAppleNativeLoginOnce();
      } else if (payload?.type === 'iapPurchase' && typeof payload.productId === 'string') {
        // wallet_ui.py _fire_iap_purchase_trigger()가 보내는 결제 요청.
        triggerIapPurchaseOnce({
          sku: payload.productId,
          basePlanId: payload.basePlanId || undefined,
        });
      } else if (payload?.type === 'iapFinish' && typeof (payload as { transactionId?: unknown }).transactionId === 'string') {
        // apple_iap.render_finish_signals() — 서버가 확인·지급을 끝낸 애플 거래.
        finishApplePurchase((payload as { transactionId: string }).transactionId);
      } else if (payload?.type === 'iapRestore') {
        // apple_iap.fire_restore_trigger() — 구독 화면의 '구매 복원'.
        triggerAppleRestoreOnce();
      } else if (payload?.type === PAGE_READY_MESSAGE_TYPE) {
        // PAGE_READY_INJECTED_JS — Streamlit 이 화면을 다 그렸다.
        pageReadySeenRef.current = true;
        awaitingPageReadyRef.current = false;
        setLoading(false);
      } else if (payload?.type === 'dialogState') {
        // wallet_ui.inject_manual_dialog_back_bridge()가 보내는 신호 — st.dialog
        // (내정보·사용설명서 등 전부 공통)가 지금 열려 있는지.
        setDialogOpen(!!payload.open);
      }
    },
    [goToQrScan, triggerKakaoNativeLoginOnce, triggerAppleNativeLoginOnce, triggerIapPurchaseOnce, finishApplePurchase, triggerAppleRestoreOnce]
  );

  // 새 창 요청(target=_blank·window.open) — 위 isOwnServerUrl 설명 참고. 안드로이드 전용 이벤트.
  const onOpenWindow = useCallback(
    (event: { nativeEvent: { targetUrl: string } }) => {
      const url = event.nativeEvent.targetUrl;
      if (!url) {
        return;
      }
      if (isOwnServerUrl(url)) {
        // 앱 신호(native·플랫폼·수신부 표시)를 다시 실어 같은 웹뷰에서 연다.
        setWebViewUri(
          withParams(url, {
            native: '1',
            native_platform: Platform.OS,
            ...APPLE_LOGIN_CAPABILITY_PARAMS,
            ...IAP_CAPABILITY_PARAMS,
            ...SPA_NAV_CAPABILITY_PARAMS,
          })
        );
        return;
      }
      Linking.openURL(url).catch(() => {});
    },
    []
  );

  const goToStreamlitHome = useCallback(() => {
    router.replace('/');
  }, []);

  // 2026-09-23: 열려 있는 st.dialog의 실제 닫기(X) 버튼을 눌러준다 — Streamlit
  // 공식 dialog testid([data-testid="stDialog"])와 그 안의 aria-label="Close"
  // 버튼은 Playwright로 직접 렌더해 확인한 값(버전 바뀌어도 대개 안정적인 ARIA
  // 계약). 웹뷰의 injectJavaScript는 항상 최상위 문서에서 실행되므로(iframe이
  // 아님) 별도 브릿지 없이 바로 클릭할 수 있다.
  const closeOpenDialog = useCallback(() => {
    webViewRef.current?.injectJavaScript(
      "(function(){try{" +
        'var b=document.querySelector(\'[data-testid="stDialog"] button[aria-label="Close"]\');' +
        'if(b){b.click();}' +
        '}catch(e){}})();true;'
    );
  }, []);

  const handleNativeBack = useCallback(() => {
    if (error) {
      setError(null);
      return true;
    }
    // 2026-09-23(사용자 지시): 다이얼로그가 열려 있으면 최우선으로 그것부터
    // 닫는다 — canGoBack/showBack보다 먼저 확인해야, 다이얼로그가 열린 채로
    // 뒤로가기를 눌렀을 때 앱이 그대로 종료되던 문제가 사라진다.
    if (dialogOpen) {
      closeOpenDialog();
      setDialogOpen(false);
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
  }, [canGoBack, closeOpenDialog, dialogOpen, error, goToStreamlitHome, showBack]);

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
            서버 주소: {webViewUri}
            {'\n'}
            (Cloud: lotto-shinryeong.streamlit.app · 로컬: run_server.ps1)
          </Text>
          <TouchableOpacity style={styles.retryBtn} onPress={() => setError(null)}>
            <Text style={styles.retryText}>다시 시도</Text>
          </TouchableOpacity>
        </View>
      ) : guestId === null || webViewUri === null ? (
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
        // 2026-10-09: Play 스토어 주소(업데이트 안내 "지금 업데이트"·구독 관리)는 이제
        // onShouldStartLoadWithRequest 의 isPlayStoreUrl 이 Play 스토어 앱으로 넘긴다. 아래는 그 밖의 외부 주소 이야기.
        // TODO(update-banner-link): target="_blank" 링크(예: user_page.py의 업데이트 안내
        // 배너 "지금 업데이트" st.link_button)가 새 탭이 아니라 이 웹뷰 안에서 그대로 열림 —
        // setSupportMultipleWindows/onOpenWindow 핸들러가 없기 때문. update_url이 스토어
        // 웹페이지면 그럭저럭 동작하지만, APK 직링크면 onFileDownload 핸들러 없이는
        // 다운로드가 아예 안 될 가능성이 높음. 고치려면 onShouldStartLoadWithRequest로
        // 외부 URL을 기기 기본 브라우저(Linking.openURL)로 넘기는 처리 추가 필요 —
        // 이 프로젝트(LottoShinryeong) 재빌드가 필요한 변경이라 별도로 진행.
        <WebView
          ref={webViewRef}
          key={webViewUri}
          source={{ uri: webViewUri }}
          style={styles.webview}
          originWhitelist={WEBVIEW_ORIGIN_WHITELIST}
          onNavigationStateChange={onNavigationStateChange}
          onShouldStartLoadWithRequest={onShouldStartLoadWithRequest}
          onOpenWindow={onOpenWindow}
          onMessage={onMessage}
          injectedJavaScript={PAGE_READY_INJECTED_JS}
          onLoadStart={() => {
            awaitingPageReadyRef.current = true;
            setLoading(true);
          }}
          onLoadEnd={() => {
            // 2026-09-17: 예전엔 여기서 카카오 access_token을 3초 뒤 지우며
            // 웹뷰를 다시 로드했다 — 토큰이 uri 파생값의 일부였기 때문.
            // 이제 로그인은 handleKakaoNativeLogin이 딱 한 번만 명시적으로
            // 이동시키는 주소에 실려 나가고, 이 로드가 끝난 뒤 다시 지울
            // 것도 다시 로드할 것도 없다(주소창의 토큰은 서버가 1회용
            // 소비 직후 이미 지운다).
            // 2026-10-08: 문서 로드가 끝나도 Streamlit 이 아직 그리는 중이면 "불러오는 중"을 유지한다
            // (PAGE_READY_INJECTED_JS). 신호가 이미 왔거나 신호를 못 쓰는 환경이면 예전처럼 내린다.
            if (pageReadyUnsupportedRef.current || !awaitingPageReadyRef.current) {
              setLoading(false);
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
                // 2026-09-08: 번개조합 진입 시 "화면이 반전/겹쳐 떠있는 것처럼 보인다"
                // 스크린샷 신고 — 위 로딩 오버레이 불투명화(styles.loadingOverlay)로
                // 1차 조치했지만, 근본적으로 안드로이드 WebView는 기본적으로 별도
                // SurfaceView 레이어에 하드웨어 합성되는데, 이 레이어는 나머지 뷰
                // 계층(로딩 스피너 포함)과 완전히 동기화되지 않는 별도 컴포지터
                // 타이밍을 가져서 페이지 전환 중 순간적으로 "겹쳐 보이거나 이전
                // 프레임이 잠깐 비치는" 플래시가 생길 수 있다 — react-native-webview
                // 자체 이슈(#3690, 화면 전환 시 웹뷰만 깜빡이는 현상)와 여러 유사
                // 사례로 확인됨. androidLayerType:'software'는 WebView를 이 별도
                // 하드웨어 레이어에서 빼서 일반 뷰 계층과 같은 방식으로 합성되게 해
                // 이 클래스의 깜빡임을 구조적으로 막는다(문서화된 표준 대응).
                // 트레이드오프: 소프트웨어 렌더링이라 무거운 애니메이션/동영상엔
                // 약간의 성능 비용이 있지만, 이 앱 화면들은 대부분 텍스트·숫자판
                // 위주라 체감 영향은 적을 것으로 판단됨 — 실기기 재검증 필요.
                //
                // 2026-09-19(실기기 A/B 진단 완료): 번호판 무게·주입스크립트·이 값
                // 자체(software/none/hardware 3종) 전부 실기기에서 반전·겹침 증상과
                // 무관한 것으로 배제됐다 — 실제 원인은 로그인 배너가 native=1 파라미터
                // 유실로 웹 분기(새 탭)로 떨어져 외부 브라우저로 새는 것이었다
                // (user_scope.py internal_nav_href() 수정으로 대응, 2026-09-19).
                // androidLayerType은 다른 알려진 문제(#3690 프레임 겹침)에 대한
                // 안전망으로 'software' 고정을 유지한다.
                androidLayerType: 'software',
                // 2026-09-06: 위 캐시버스팅(_cb) URL 파라미터가 근본 해결책이지만,
                // 이 로드(자동 로그아웃 신호를 보내는 바로 그 순간)만큼은 이중
                // 안전장치로 캐시 자체도 꺼둔다 — 평소 탐색에는 안 걸어서(성능
                // 저하 방지) 정상적인 캐싱 이득은 그대로 유지한다.
                // 2026-09-17: shouldSendFreshStart(렌더 시점 판정) 대신, 지금
                // 실제로 로드 중인 webViewUri 자체에 fresh_start=1이 실려있는지로
                // 판단한다 — uri가 더는 매 렌더 파생값이 아니라 명시적으로만
                // 바뀌므로, "이번에 실제로 보낸 주소"를 직접 보는 게 더 정확하다.
                ...(webViewUri?.includes('fresh_start=1')
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
    // 2026-09-08: 기존 rgba(...,0.85)는 15% 투명이라, 화면 전환(예: 메인→번개조합의
    // 실제 <a href="?page=thunder"> 네비게이션) 도중 이 스피너 뒤로 안드로이드
    // 강제다크모드 색반전 등 전환 중인 웹뷰 프레임이 비쳐 보였다 — 사용자가 스크린샷으로
    // 제보한 "번개조합 들어가면 반전화면/다른 화면이 겹쳐 떠있는 것처럼 보임" 증상이
    // 바로 이 반투명 때문(실제 두 개의 화면/웹뷰 인스턴스가 뜬 게 아니라, 이 오버레이의
    // 15% 투과율로 전환 중 프레임이 비쳐보인 광학적 증상이었음 — 네비게이션 구조 자체는
    // <a href> 단일 웹뷰 내 이동만 쓰고 있어 중복 마운트가 애초에 불가능함을 코드로 확인함).
    // 완전 불투명으로 바꿔 전환 중인 프레임을 확실히 가린다.
    backgroundColor: '#12182b',
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
