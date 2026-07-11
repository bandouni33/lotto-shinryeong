from src.filters.base import LottoFilter
from src.models.combination import LottoCombination

ALLOWED_ODD_EVEN_RATIOS = {
    (3, 3),
    (2, 4),
    (4, 2),
    (1, 5),
    (5, 1),
}


class OddEvenRatioFilter(LottoFilter):
    name = "홀짝 비율 제한"
    tier_required = "free"

    def passes(self, combo: LottoCombination, context: dict) -> bool:
        ratio = (combo.odd_count, combo.even_count)
        return ratio in ALLOWED_ODD_EVEN_RATIOS
