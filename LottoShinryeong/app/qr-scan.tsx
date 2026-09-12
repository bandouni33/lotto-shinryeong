import { useCallback, useEffect, useRef, useState } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { CameraView, useCameraPermissions, type BarcodeScanningResult } from 'expo-camera';
import { router, useLocalSearchParams } from 'expo-router';
import { HEARTBEAT_MS, touchLastActive } from '@/utils/session-timeout';

/**
 * 로또 용지 QR 촬영 화면 — "안티조합·액땜조합" 진입 시 streamlit-webview.tsx의
 * onShouldStartLoadWithRequest가 ?page=hedge&qrscan=1 로드를 가로채서 여기로 보낸다.
 * 스캔 성공 시 v= 값만 뽑아 /web/[page]?page=hedge&qr=... 로 넘겨서, page_hedge.py가
 * 그 문자열을 파싱해 5줄을 자동 입력한다(포맷은 실물 티켓 여러 장으로 검증됨).
 */
export default function QrScanScreen() {
  const insets = useSafeAreaInsets();
  const { target } = useLocalSearchParams<{ target?: string }>();
  const targetPage = typeof target === 'string' && target ? target : 'hedge';
  const [permission, requestPermission] = useCameraPermissions();
  const [showIntro, setShowIntro] = useState(true);
  const [torchOn, setTorchOn] = useState(false);
  const scannedRef = useRef(false);
  // 2026-09-12(사용자 실측 — "거리조절 시간이 오래 걸림", "예전엔 살짝 스치기만
  // 해도 스캔됐다"): 카메라 인식이 안 된다는 신고에 대응해 넣었던 기본 줌(0.3)이
  // 오히려 화각을 좁혀 원래는 관대했던 거리 허용 범위를 좁힌 것으로 실측
  // 확인됐다 — 줌은 되돌린다(손전등만 남김). expo-camera의 zoom은 광학이
  // 아니라 디지털(크롭+업스케일)이라, 확대해도 실제 해상도가 늘지 않고
  // 화각만 줄어 "정확한 거리"를 더 좁은 범위로 강제하는 역효과만 냈다.
  //
  // 2026-09-12(사용자 신고 — QR스캔 눌렀는데 로그인 상태인데도 로그인이
  // 안 됐다고 나옴): 진짜 원인은 로그인 체크 로직이 아니라 세션 타임아웃이었다.
  // streamlit-webview.tsx는 마운트돼 있는 동안만 20초마다 touchLastActive()로
  // "마지막 활동 시각"을 갱신하는데, QR 촬영 화면(이 파일)으로 넘어오면 그
  // WebView 컴포넌트 자체가 언마운트되면서 하트비트가 멈춘다. 위 거리조절
  // 문제 때문에 이 화면에서 3분(BACKGROUND_LOGOUT_MS) 넘게 머물면, 웹뷰로
  // 돌아가는 순간 "3분 넘게 활동 없었음"으로 잘못 판정돼 진짜로 자동 로그아웃
  // 처리됐다 — 유저는 계속 앱을 쓰고 있었는데도. 이 화면도 열려있는 동안
  // 똑같이 하트비트를 찍어서, 카메라로 시간을 보내는 동안은 비활동으로
  // 안 잡히게 한다.
  useEffect(() => {
    touchLastActive();
    const heartbeat = setInterval(touchLastActive, HEARTBEAT_MS);
    return () => clearInterval(heartbeat);
  }, []);
  // 화면에 그린 금색 사각형 가이드는 안내용일 뿐, expo-camera의 바코드 인식은 카메라
  // 시야 전체를 스캔한다 — 가이드 밖의 QR(예: 테이블에 여러 장 놓인 다른 티켓)도
  // 그대로 인식돼버리는 한계가 있다. bounds 좌표로 가이드 사각형 안쪽만 채택하도록
  // 제한을 시도했었는데, bounds가 카메라 원본 해상도 좌표계라 화면 레이아웃 좌표와
  // 안 맞아서 모든 스캔이 걸러지는(스캔이 아예 안 되는) 회귀가 실기기에서 발생함
  // (2026-08-19). 실기기 좌표 로그 없이는 정확한 보정이 어려워 일단 되돌린다 —
  // "여러 장 중 엉뚱한 티켓이 스캔될 수 있음"보다 "스캔이 아예 안 됨"이 훨씬 나쁘다.

  const goToTarget = useCallback(
    (qr?: string) => {
      router.replace({
        pathname: '/web/[page]',
        params: qr ? { page: targetPage, qr } : { page: targetPage },
      });
    },
    [targetPage]
  );

  const handleBarcodeScanned = useCallback(
    ({ data }: BarcodeScanningResult) => {
      if (scannedRef.current) return;
      if (!data || !data.includes('dhlottery')) {
        // 로또 용지 QR이 아닌 다른 QR — 무시하고 계속 스캔 대기(에러로 화면을 막지 않음).
        return;
      }
      scannedRef.current = true;
      const match = data.match(/[?&]v=([^&]+)/);
      goToTarget(match ? match[1] : data);
    },
    [goToTarget]
  );

  if (!permission) {
    return <View style={[styles.center, { paddingTop: insets.top }]} />;
  }

  if (!permission.granted) {
    return (
      <View style={[styles.center, { paddingTop: insets.top }]}>
        <Text style={styles.title}>카메라 권한이 필요해요</Text>
        <Text style={styles.msg}>
          로또 용지의 QR코드를 촬영해서{'\n'}번호를 자동으로 입력하려면 카메라 접근을 허용해 주세요.
        </Text>
        <TouchableOpacity style={styles.primaryBtn} onPress={requestPermission} activeOpacity={0.8}>
          <Text style={styles.primaryBtnText}>권한 허용</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.linkBtn} onPress={() => goToTarget()} activeOpacity={0.7}>
          <Text style={styles.linkBtnText}>직접 입력할게요</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <CameraView
        style={StyleSheet.absoluteFillObject}
        facing="back"
        // 2026-09-13(사용자 실측 — 손전등 추가 이후 "각도를 바꿔도 전혀 인식 안 됨",
        // 원래 되던 버전보다 더 나빠짐): 원래 잘 되던 코드와 지금 코드의 실제
        // 차이는 이 enableTorch prop 하나뿐이었다(줌은 이미 되돌림). 꺼진 상태
        // (false)여도 이 prop을 "명시적으로" 넘기면 Android 쪽 카메라 세션이
        // 매번 재구성되면서 QR 인식에 필요한 안정된 캡처 상태가 깨지는 게
        // expo-camera의 알려진 Android 카메라/토치 관련 이슈들(예: expo/expo
        // #16520 "flash 켜면 바코드 스캐너 크래시")과 같은 계열로 보인다.
        // 꺼져 있을 땐 이 prop 자체를 아예 안 넘겨서(원래 코드와 동일한 상태로)
        // 카메라가 손전등 관련 재구성을 전혀 겪지 않게 하고, 유저가 실제로
        // 켤 때만 prop을 넣는다.
        {...(torchOn ? { enableTorch: true } : {})}
        barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
        onBarcodeScanned={handleBarcodeScanned}
      />
      <View style={[styles.overlay, { paddingTop: insets.top + 24, paddingBottom: insets.bottom + 24 }]}>
        <View style={styles.topRow}>
          <TouchableOpacity
            style={styles.closeBtn}
            onPress={() => setTorchOn((v) => !v)}
            activeOpacity={0.7}
          >
            <Text style={styles.closeBtnText}>{torchOn ? '🔦' : '💡'}</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.closeBtn} onPress={() => goToTarget()} activeOpacity={0.7}>
            <Text style={styles.closeBtnText}>✕</Text>
          </TouchableOpacity>
        </View>
        <View style={styles.frameRow}>
          {showIntro ? (
            <TouchableOpacity style={styles.introCard} onPress={() => setShowIntro(false)} activeOpacity={0.85}>
              <Text style={styles.introText}>
                지금 자동으로 구매한 복권에 확신이 없다면{'\n'}
                이 화면에서 QR 스캔해서 헤지 조합의 결과와{'\n'}
                반전의 재미를 함께 경험해 보세요
              </Text>
              <Text style={styles.introDismiss}>탭하면 닫혀요</Text>
            </TouchableOpacity>
          ) : null}
          <View style={styles.frame} />
        </View>
        <View style={styles.bottomRow}>
          <Text style={styles.hint}>QR코드가 사각형을 가득 채우도록 가까이 대주세요{'\n'}(잘 안 되면 💡을 눌러 손전등을 켜보세요)</Text>
          <TouchableOpacity style={styles.linkBtnOnCamera} onPress={() => goToTarget()} activeOpacity={0.7}>
            <Text style={styles.linkBtnOnCameraText}>직접 입력할게요</Text>
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
}

const FRAME_SIZE = 240;

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000' },
  center: {
    flex: 1,
    backgroundColor: '#12182b',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 28,
    gap: 14,
  },
  title: { color: '#fff', fontSize: 18, fontWeight: '800' },
  msg: { color: '#b0bec5', fontSize: 14, textAlign: 'center', lineHeight: 20 },
  primaryBtn: {
    marginTop: 8,
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 12,
    backgroundColor: '#f9a825',
  },
  primaryBtnText: { color: '#1a1a2e', fontWeight: '800', fontSize: 15 },
  linkBtn: { marginTop: 4, padding: 10 },
  linkBtnText: { color: '#90a4ae', fontSize: 13, textDecorationLine: 'underline' },
  overlay: {
    flex: 1,
    justifyContent: 'space-between',
    paddingHorizontal: 20,
  },
  topRow: { flexDirection: 'row', justifyContent: 'flex-end', gap: 10 },
  closeBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  closeBtnText: { color: '#fff', fontSize: 18, fontWeight: '700' },
  introCard: {
    backgroundColor: 'rgba(18, 24, 43, 0.92)',
    borderRadius: 14,
    borderWidth: 1,
    borderColor: 'rgba(249, 168, 37, 0.55)',
    paddingHorizontal: 18,
    paddingVertical: 14,
    gap: 8,
    maxWidth: 320,
    marginBottom: 16,
  },
  introText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '700',
    lineHeight: 21,
    textAlign: 'center',
  },
  introDismiss: {
    color: '#90a4ae',
    fontSize: 11,
    textAlign: 'center',
  },
  frameRow: { alignItems: 'center' },
  frame: {
    width: FRAME_SIZE,
    height: FRAME_SIZE,
    borderRadius: 16,
    borderWidth: 3,
    borderColor: '#f9a825',
    backgroundColor: 'transparent',
  },
  bottomRow: { alignItems: 'center', gap: 14 },
  hint: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
    textAlign: 'center',
    textShadowColor: 'rgba(0,0,0,0.6)',
    textShadowRadius: 4,
  },
  linkBtnOnCamera: {
    paddingHorizontal: 18,
    paddingVertical: 10,
    borderRadius: 999,
    backgroundColor: 'rgba(0,0,0,0.5)',
  },
  linkBtnOnCameraText: { color: '#fff', fontSize: 13, fontWeight: '700' },
});
