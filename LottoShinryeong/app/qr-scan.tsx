import { useCallback, useRef, useState } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { CameraView, useCameraPermissions, type BarcodeScanningResult } from 'expo-camera';
import { router, useLocalSearchParams } from 'expo-router';

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
  // 2026-09-12(사용자 신고 — 카메라는 열리지만 QR 인식이 안 됨): 그동안의
  // 수정 이력은 전부 "버튼→카메라 화면 진입" 트리거 경로였고, 정작 인식
  // 자체를 돕는 설정은 하나도 없었다. 로또 용지 QR은 5줄 배당 정보까지
  // 들어가면 최대 60여 자를 인코딩해 모듈이 촘촘한 편이라 기본 줌(0, 즉
  // 미확대)·손전등 꺼짐 상태로는 실제 사용 거리에서 모듈을 못 읽거나,
  // 코팅된 복권 용지 특유의 표면 반사·저조도에서 인식이 실패하기 쉽다.
  // expo-camera 공식 문서(v54) 기준 zoom(0~1)·enableTorch를 명시적으로
  // 켜서 두 요인을 모두 완화한다 — autofocus는 iOS 전용 prop이라 안드로이드엔
  // 효과가 없어 여기서 다루지 않는다.
  const QR_SCAN_ZOOM = 0.3;
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
        zoom={QR_SCAN_ZOOM}
        enableTorch={torchOn}
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
