import { useMemo } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { router } from 'expo-router';

import { getStreamlitPageUrl } from '@/constants/streamlit';

type Props = {
  page: string;
  title?: string;
  showBack?: boolean;
};

export default function StreamlitWebView({ page, title, showBack = true }: Props) {
  const insets = useSafeAreaInsets();
  const uri = getStreamlitPageUrl(page);

  const frameStyle = useMemo(
    () =>
      ({
        flex: 1,
        width: '100%',
        border: 'none',
        minHeight: 0,
        backgroundColor: '#12182b',
      }) as const,
    [],
  );

  const openFullPage = () => {
    if (typeof window !== 'undefined') {
      window.location.href = uri;
    }
  };

  const onToolbarBack = () => {
    if (showBack) {
      router.replace('/');
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
        <TouchableOpacity style={styles.openBtn} onPress={openFullPage} activeOpacity={0.7}>
          <Text style={styles.openBtnText}>새 탭</Text>
        </TouchableOpacity>
      </View>
      <View style={styles.frameWrap}>
        {/* eslint-disable-next-line react/iframe-missing-title */}
        <iframe src={uri} style={frameStyle} title={title ?? page} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#12182b', minHeight: '100vh' as unknown as number },
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
  openBtn: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 8,
    backgroundColor: '#2a3a60',
  },
  openBtnText: { color: '#b0bec5', fontWeight: '700', fontSize: 12 },
  frameWrap: { flex: 1, minHeight: 0, width: '100%' },
});
