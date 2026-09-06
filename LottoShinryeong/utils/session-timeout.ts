import AsyncStorage from '@react-native-async-storage/async-storage';

/**
 * 앱이 백그라운드로 간 지 일정 시간(TIMEOUT_MS)이 지나면 자동 로그아웃시키기
 * 위한 "마지막 백그라운드 진입 시각" 기록.
 *
 * 2026-09-06: 처음엔 이 값을 컴포넌트 안의 JS 변수(useRef)로만 들고 있었는데,
 * 실기기 테스트에서 2시간 넘게 백그라운드에 있다 돌아와도 로그인이 그대로
 * 유지되는 문제가 보고됐다 — 화면 전환·리렌더 등으로 그 컴포넌트가 다시
 * 마운트되면 메모리에 있던 기록이 조용히 초기화될 수 있어 신뢰할 수 없는
 * 방식이었다. getOrCreateGuestId()와 동일하게 AsyncStorage(기기 저장소)에
 * 기록해두면, 컴포넌트가 몇 번을 다시 마운트되든(심지어 프로세스가 완전히
 * 재시작돼도) 값이 그대로 남아있어 훨씬 신뢰할 수 있다.
 */
const STORAGE_KEY = 'lotto_backgrounded_at';
export const BACKGROUND_LOGOUT_MS = 3 * 60 * 1000;

export async function markBackgrounded(): Promise<void> {
  try {
    await AsyncStorage.setItem(STORAGE_KEY, String(Date.now()));
  } catch {
    // 저장 실패해도 앱은 계속 동작해야 한다 — 이번엔 자동 로그아웃 판단만 못 할 뿐.
  }
}

/** 백그라운드 진입 기록을 지운다(다시 활성화됐을 때, 판단이 끝난 뒤 호출). */
export async function clearBackgroundedMark(): Promise<void> {
  try {
    await AsyncStorage.removeItem(STORAGE_KEY);
  } catch {
    // 무시 — 다음에 또 기록되면 그만이다.
  }
}

/** 저장된 "백그라운드 진입 시각"이 TIMEOUT_MS 이상 지났으면 true. */
export async function isSessionTimedOut(): Promise<boolean> {
  try {
    const stored = await AsyncStorage.getItem(STORAGE_KEY);
    if (!stored) {
      return false;
    }
    const backgroundedAt = parseInt(stored, 10);
    if (Number.isNaN(backgroundedAt)) {
      return false;
    }
    return Date.now() - backgroundedAt >= BACKGROUND_LOGOUT_MS;
  } catch {
    return false;
  }
}
