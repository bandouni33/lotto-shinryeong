import AsyncStorage from '@react-native-async-storage/async-storage';

/**
 * 비로그인 사용자를 앱을 껐다 켜도 같은 사람으로 알아보기 위한 기기별 식별자.
 *
 * 예전엔 웹뷰 쿠키(document.cookie)로 이걸 저장했는데, 안드로이드 웹뷰가 쿠키를
 * 곧바로 디스크에 저장하지 않는 데다(화면 전환마다 웹뷰가 새로 생성되는 이 앱
 * 구조상 저장 전에 유실되기 쉬웠음), 이걸 강제로 flush하려고 넣은 네이티브
 * 패키지들(react-native-cookies, preeternal 등)이 전부 최신 아키텍처와 충돌해
 * 앱을 크래시시켰다. AsyncStorage는 RN 진영에서 가장 오래·널리 검증된 저장소라
 * 이런 문제가 없고, 쿠키처럼 "저장됐는지 불확실한" 타이밍 이슈 자체가 없다.
 *
 * 이 id는 URL 쿼리 파라미터(?gid=...)로 Streamlit 서버에 전달된다.
 */
const STORAGE_KEY = 'lotto_guest_id';

function generateId(): string {
  const rand = () => Math.random().toString(36).slice(2, 10);
  return `${Date.now().toString(36)}${rand()}${rand()}`;
}

export type GuestIdResult = {
  id: string;
  /**
   * 'stored': 이전에 저장해둔 값을 그대로 읽어옴 (정상 — 재실행해도 같은 id 유지).
   * 'created': 처음이라 새로 만들어 저장함 (정상 — 다음부터는 'stored'여야 함).
   * 'fallback-error': AsyncStorage 접근 자체가 실패해 저장 안 되는 임시 id —
   *   이 경우 화면을 새로 열 때마다 다른 id가 나와서 서버 쪽 영속성 기능이
   *   전부 무력화된다. 실기기에서 "고쳤는데도 하나도 안 바뀐다"는 증상의
   *   유력한 원인이라 진단용으로 구분해둔다.
   */
  source: 'stored' | 'created' | 'fallback-error';
  error?: string;
};

export async function getOrCreateGuestId(): Promise<GuestIdResult> {
  try {
    const existing = await AsyncStorage.getItem(STORAGE_KEY);
    if (existing) {
      return { id: existing, source: 'stored' };
    }
    const created = generateId();
    await AsyncStorage.setItem(STORAGE_KEY, created);
    return { id: created, source: 'created' };
  } catch (e) {
    // 저장소 접근 자체가 실패해도(드묾) 앱은 계속 동작해야 하니, 이번 세션에서만
    // 쓰는 임시 id로 대체한다 — 다음 실행에서 다시 만들어질 뿐, 크래시는 없다.
    return { id: generateId(), source: 'fallback-error', error: String(e) };
  }
}
