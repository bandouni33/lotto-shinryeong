from abc import ABC, abstractmethod

from src.models.combination import LottoCombination


class LottoFilter(ABC):
    name: str
    tier_required: str  # "free" | "premium"

    @abstractmethod
    def passes(self, combo: LottoCombination, context: dict) -> bool:
        pass
