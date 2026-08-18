import { useCallback, useRef } from 'react';
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
  const scannedRef = useRef(false);

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
        barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
        onBarcodeScanned={handleBarcodeScanned}
      />
      <View style={[styles.overlay, { paddingTop: insets.top + 24, paddingBottom: insets.bottom + 24 }]}>
        <View style={styles.topRow}>
          <TouchableOpacity style={styles.closeBtn} onPress={() => goToTarget()} activeOpacity={0.7}>
            <Text style={styles.closeBtnText}>✕</Text>
          </TouchableOpacity>
        </View>
        <View style={styles.frameRow}>
          <View style={styles.frame} />
        </View>
        <View style={styles.bottomRow}>
          <Text style={styles.hint}>로또 용지의 QR코드를 사각형 안에 맞춰주세요</Text>
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
  topRow: { flexDirection: 'row', justifyContent: 'flex-end' },
  closeBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  closeBtnText: { color: '#fff', fontSize: 18, fontWeight: '700' },
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
