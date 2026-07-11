import pandas as pd

class LottoAnalyzer:
    def __init__(self, history_path, patterns_path, frequency_path):
        # 1. 당첨 이력 로드 (역순 데이터를 정순으로 정렬)
        df_history = pd.read_csv(history_path)
        # '회차' 열을 기준으로 정순 정렬 (역순인 경우 정순으로 변환)
        self.history = df_history.sort_values(by='회차', ascending=True)
        
        # 2. 패턴 및 빈도 데이터 로드
        self.patterns = pd.read_csv(patterns_path)
        self.frequency = pd.read_csv(frequency_path)
        
        # 소자배 분류 기준
        self.primes = {2, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43}
        self.multiples_of_3 = {3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36, 39, 42, 45}
        all_nums = set(range(1, 46))
        self.naturals = all_nums - self.primes - self.multiples_of_3

    def get_latest_draw(self):
        """가장 최근 회차의 당첨 번호 추출"""
        latest = self.history.iloc[-1]
        # CSV의 '1구'~'6구' 헤더를 그대로 사용
        return [latest['1구'], latest['2구'], latest['3구'], latest['4구'], latest['5구'], latest['6구']]

    def get_so_ja_bae_limits(self):
        """[동적 추론] 최근 회차 분석 기반 최대 개수 결정"""
        last_nums = self.get_latest_draw()
        
        counts = {
            "prime": sum(1 for n in last_nums if n in self.primes),
            "natural": sum(1 for n in last_nums if n in self.naturals),
            "multiple": sum(1 for n in last_nums if n in self.multiples_of_3)
        }
        
        limits = {"prime": 4, "natural": 4, "multiple": 4}
        for key in limits:
            if counts.get(key, 0) >= 4:
                limits[key] = 3
        return limits

# 실행 확인용
if __name__ == "__main__":
    analyzer = LottoAnalyzer("history.csv", "patterns.csv", "frequency.csv")
    print("가장 최근 당첨 번호:", analyzer.get_latest_draw())
    print("다음 회차 동적 소자배 필터:", analyzer.get_so_ja_bae_limits())