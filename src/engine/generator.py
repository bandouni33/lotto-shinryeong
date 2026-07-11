import random

from src.models.combination import LottoCombination


def generate_random_combination(seed: int | None = None) -> LottoCombination:
    rng = random.Random(seed)
    nums = tuple(sorted(rng.sample(range(1, 46), 6)))
    return LottoCombination(numbers=nums)
