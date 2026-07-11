from src.filters.base import LottoFilter
from src.models.combination import LottoCombination


class FilterPipeline:
    def __init__(self, filters: list[LottoFilter]):
        self.filters = filters

    def apply(self, combo: LottoCombination, context: dict) -> bool:
        return all(f.passes(combo, context) for f in self.filters)

    def filter_combinations(
        self,
        combinations: list[LottoCombination],
        context: dict,
    ) -> list[LottoCombination]:
        return [c for c in combinations if self.apply(c, context)]
