import { useEffect, useRef } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Animated, Dimensions } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { router } from 'expo-router';
import * as Haptics from 'expo-haptics';

const { width } = Dimensions.get('window');

export default function HomeScreen() {
  const glowAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(glowAnim, { toValue: 1, duration: 1500, useNativeDriver: true }),
        Animated.timing(glowAnim, { toValue: 0, duration: 1500, useNativeDriver: true }),
      ])
    ).start();
  }, []);

  const iconOpacity = glowAnim.interpolate({ inputRange: [0, 1], outputRange: [0.7, 1] });
  const iconScale = glowAnim.interpolate({ inputRange: [0, 1], outputRange: [0.97, 1.03] });

  const openPage = (page: string) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    router.push({ pathname: '/web/[page]', params: { page } });
  };

  const balls = [
    { num: 1, color: '#f9a825' },
    { num: 14, color: '#1976d2' },
    { num: 16, color: '#1976d2' },
    { num: 34, color: '#757575' },
    { num: 41, color: '#388e3c' },
    { num: 44, color: '#388e3c' },
  ];
  const bonus = { num: 13, color: '#1976d2' };

  const menus = [
    { icon: '⚡', title: '번개조합', sub: '빠른 조합', border: '#f9a825', page: 'thunder' },
    { icon: '🤖', title: '자동구매', sub: 'SMS 발송', border: '#1976d2', page: 'auto' },
    { icon: '📊', title: '통계센터', sub: '당첨 분석', border: '#388e3c', page: 'stats' },
    { icon: '👑', title: '고급필터', sub: '프리미엄', border: '#7b1fa2', page: 'advanced' },
  ];

  return (
    <View style={styles.container}>
      <StatusBar style="light" />
      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>

        <Animated.View style={[styles.iconWrap, { opacity: iconOpacity, transform: [{ scale: iconScale }] }]}>
          <Text style={styles.iconEmoji}>🌟</Text>
          <Text style={styles.appName}>로또신령</Text>
        </Animated.View>

        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <Text style={styles.cardLabel}>🌀 최근 당첨번호</Text>
            <Text style={styles.cardRound}>1227회</Text>
          </View>
          <View style={styles.ballRow}>
            {balls.map((b) => (
              <View key={b.num} style={[styles.ball, { backgroundColor: b.color }]}>
                <Text style={styles.ballText}>{b.num}</Text>
              </View>
            ))}
            <Text style={styles.plus}>+</Text>
            <View style={[styles.ball, { backgroundColor: bonus.color, borderWidth: 2, borderColor: '#fff' }]}>
              <Text style={styles.ballText}>{bonus.num}</Text>
            </View>
          </View>
          <TouchableOpacity style={styles.moreBtn} onPress={() => openPage('stats')}>
            <Text style={styles.moreBtnText}>세부내역 더보기 ➡️</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <Text style={styles.cardLabel}>🏆 역대 최고 당첨금</Text>
            <TouchableOpacity onPress={() => openPage('stats')}>
              <Text style={styles.moreText}>더보기 ➡️</Text>
            </TouchableOpacity>
          </View>
          <View style={styles.topPrize}>
            <View style={[styles.ball, { backgroundColor: '#f9a825', width: 24, height: 24 }]}>
              <Text style={[styles.ballText, { fontSize: 10 }]}>1</Text>
            </View>
            <Text style={styles.prizeAmount}>407억 원</Text>
          </View>
        </View>

        <View style={styles.menuGrid}>
          {menus.map((m) => (
            <TouchableOpacity
              key={m.title}
              style={[styles.menuBox, { borderColor: m.border }]}
              onPress={() => openPage(m.page)}
              activeOpacity={0.7}
            >
              <Text style={styles.menuIcon}>{m.icon}</Text>
              <Text style={styles.menuTitle}>{m.title}</Text>
              <Text style={styles.menuSub}>{m.sub}</Text>
            </TouchableOpacity>
          ))}
        </View>

      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#1a1a2e' },
  scroll: { paddingHorizontal: 16, paddingBottom: 30 },
  iconWrap: { alignItems: 'center', paddingTop: 20, marginBottom: 16 },
  iconEmoji: { fontSize: 56 },
  appName: { color: '#f9a825', fontSize: 20, fontWeight: 'bold', marginTop: 4, letterSpacing: 2 },
  card: { backgroundColor: '#16213e', borderRadius: 16, padding: 14, marginBottom: 12, shadowColor: '#000', shadowOpacity: 0.4, shadowRadius: 8, elevation: 5 },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  cardLabel: { color: '#aaa', fontSize: 12 },
  cardRound: { color: '#f9a825', fontSize: 12 },
  ballRow: { flexDirection: 'row', alignItems: 'center', gap: 6, justifyContent: 'center' },
  ball: { width: 32, height: 32, borderRadius: 16, justifyContent: 'center', alignItems: 'center' },
  ballText: { color: 'white', fontWeight: 'bold', fontSize: 12 },
  plus: { color: 'white', fontWeight: 'bold', fontSize: 16 },
  moreBtn: { marginTop: 10, alignItems: 'center' },
  moreBtnText: { color: '#f9a825', fontSize: 12 },
  moreText: { color: '#f9a825', fontSize: 12 },
  topPrize: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 4 },
  prizeAmount: { color: 'white', fontSize: 22, fontWeight: 'bold' },
  menuGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginTop: 4 },
  menuBox: { width: (width - 44) / 2, backgroundColor: '#16213e', borderRadius: 16, paddingVertical: 20, alignItems: 'center', borderWidth: 1.5, shadowColor: '#000', shadowOpacity: 0.5, shadowRadius: 6, elevation: 6 },
  menuIcon: { fontSize: 30, marginBottom: 6 },
  menuTitle: { color: 'white', fontWeight: 'bold', fontSize: 14, marginBottom: 3 },
  menuSub: { color: '#888', fontSize: 11 },
});
