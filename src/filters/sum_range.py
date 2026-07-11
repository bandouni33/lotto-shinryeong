from src.filters.base import LottoFilter
from src.models.combination import LottoCombination


class SumRangeFilter(LottoFilter):
    name = "총합 범위 제한"
    tier_required = "free"

    def __init__(self, min_sum: int = 100, max_sum: int = 170):
        self.min_sum = min_sum
        self.max_sum = max_sum

    def passes(self, combo: LottoCombination, context: dict) -> bool:
        return self.min_sum <= combo.total_sum <= self.max_sum
