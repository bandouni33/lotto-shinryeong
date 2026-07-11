from src.filters.base import LottoFilter
from src.models.combination import LottoCombination


class ConsecutiveExcludeFilter(LottoFilter):
    """3개 이상 연속 번호가 있으면 제외"""

    name = "연속 번호 제외"
    tier_required = "premium"

    def __init__(self, max_consecutive: int = 2):
        self.max_consecutive = max_consecutive

    def passes(self, combo: LottoCombination, context: dict) -> bool:
        nums = combo.sorted_numbers
        streak = 1
        for i in range(1, len(nums)):
            if nums[i] == nums[i - 1] + 1:
                streak += 1
                if streak > self.max_consecutive:
                    return False
            else:
                streak = 1
        return True
