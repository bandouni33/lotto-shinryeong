import AsyncStorage from '@react-native-async-storage/async-storage';

/**
 * 앱이 백그라운드로 간 지 일정 시간(TIMEOUT_MS)이 지나면 자동 로그아웃시키기
 * 위한 "마지막 활동 시각" 기록.
 *
 * 2026-09-06: 처음엔 "백그라운드로 가는 바로 그 순간에" 기록하는 방식이었는데,
 * 실기기에서 계속 실패했다 — 조사 결과, 안드로이드는 백그라운드 전환/강제종료
 * 시점에 프로세스를 곧바로 정리해버릴 수 있어서, 그 순간에 시작한 비동기
 * AsyncStorage 쓰기가 완료되기 전에 죽어버릴 위험이 실제로 보고된 바 있다
 * (react-native 커뮤니티에 유사 사례 다수). 게다가 이 앱처럼 "뒤로가기로
 * 종료"하는 경로에서는 AppState의 'active' 복귀 이벤트 자체가 안정적으로
 * 오지 않는다는 React Native 공식 이슈(#32720)도 확인됨.
 *
 * 그래서 "위험한 순간에 급하게 쓰기"가 아니라, **앱이 정상적으로 켜져있는
 * 동안 계속(하트비트) 미리미리 기록**해두는 방식으로 바꾼다 — 앱이 어떤
 * 방식으로 갑자기 죽든, 죽기 직전까지 이미 안전하게 저장된 "마지막 활동
 * 시각"이 항상 남아있고, 다음에 켜질 때(이벤트 수신 여부와 무관하게, 마운트
 * 시점에 직접) 그 기록과 지금 시각을 비교하기만 하면 되므로 특정 이벤트가
 * 안정적으로 오는지에 의존하지 않는다.
 */
const STORAGE_KEY = 'lotto_last_active_at';
export const BACKGROUND_LOGOUT_MS = 3 * 60 * 1000;
/** 하트비트 주기 — 이 간격보다 오래 못 쓰고 죽는 경우는 없다고 가정할 만큼
 * 짧게(20초) 잡는다. 지나치게 잦으면 배터리/저장소에 불필요한 부담. */
export const HEARTBEAT_MS = 20 * 1000;

export async function touchLastActive(): Promise<void> {
  try {
    await AsyncStorage.setItem(STORAGE_KEY, String(Date.now()));
  } catch {
    // 저장 실패해도 앱은 계속 동작해야 한다 — 이번엔 자동 로그아웃 판단만 못 할 뿐.
  }
}

/** 저장된 "마지막 활동 시각"이 BACKGROUND_LOGOUT_MS 이상 지났으면 true. */
export async function isSessionTimedOut(): Promise<boolean> {
  try {
    const stored = await AsyncStorage.getItem(STORAGE_KEY);
    if (!stored) {
      return false;
    }
    const lastActive = parseInt(stored, 10);
    if (Number.isNaN(lastActive)) {
      return false;
    }
    return Date.now() - lastActive >= BACKGROUND_LOGOUT_MS;
  } catch {
    return false;
  }
}
