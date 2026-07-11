from src.filters.base import LottoFilter
from src.models.combination import LottoCombination

ALLOWED_HIGH_LOW_RATIOS = {
    (2, 4),
    (3, 3),
    (4, 2),
    (1, 5),
    (5, 1),
}


class HighLowRatioFilter(LottoFilter):
    """1~22 저 / 23~45 고"""

    name = "고저 비율 제한"
    tier_required = "premium"

    def passes(self, combo: LottoCombination, context: dict) -> bool:
        return (combo.low_count, combo.high_count) in ALLOWED_HIGH_LOW_RATIOS


class CarryOverFilter(LottoFilter):
    """직전 회차 당첨 번호와 겹치는 개수 제한"""

    name = "이월수 필터"
    tier_required = "premium"

    def __init__(self, min_overlap: int = 0, max_overlap: int = 2):
        self.min_overlap = min_overlap
        self.max_overlap = max_overlap

    def passes(self, combo: LottoCombination, context: dict) -> bool:
        last_draw = context.get("last_draw")
        if not last_draw:
            return True
        overlap = len(set(combo.numbers) & set(last_draw))
        return self.min_overlap <= overlap <= self.max_overlap
