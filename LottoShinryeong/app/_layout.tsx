import 'react-native-gesture-handler';
import 'react-native-reanimated';

import { DarkTheme, DefaultTheme, ThemeProvider } from '@react-navigation/native';
import * as SplashScreen from 'expo-splash-screen';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { useColorScheme } from '@/hooks/use-color-scheme';

export const unstable_settings = {
  anchor: '(tabs)',
};

// 2026-09-06: 이 앱에 스플래시 화면을 "언제 내릴지" 제어하는 코드가 아예 없었다 —
// Expo 기본 동작은 JS 번들이 다 로드되기 전에 스플래시를 자동으로 먼저 내려버릴
// 수 있는데, 그 사이(스플래시 내려감 ~ React가 실제로 뭔가 그리기 시작하는 순간)
// 빈 화면이 보여서 "앱이 살짝 멈춘 듯한" 인상을 줬다(실사용자 신고, 2026-09-06).
// preventAutoHideAsync()를 모듈 최상단(컴포넌트 밖)에서 즉시 호출해 자동 숨김을
// 막아두고, 아래 RootLayout이 실제로 마운트된 뒤에만 명시적으로 내린다.
SplashScreen.preventAutoHideAsync().catch(() => {
  // 이미 숨겨졌거나 지원 안 되는 환경이어도 앱은 계속 동작해야 한다.
});

export default function RootLayout() {
  const colorScheme = useColorScheme();

  useEffect(() => {
    SplashScreen.hideAsync().catch(() => {});
  }, []);

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
          <Stack>
            <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
            <Stack.Screen name="web/[page]" options={{ headerShown: false }} />
            <Stack.Screen name="qr-scan" options={{ headerShown: false }} />
            <Stack.Screen name="modal" options={{ presentation: 'modal', title: 'Modal' }} />
          </Stack>
          <StatusBar style="light" />
        </ThemeProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
