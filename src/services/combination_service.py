import random
from dataclasses import dataclass

from src.data.mock_draws import generate_mock_draws, get_last_draw
from src.engine.generator import generate_random_combination
from src.models.combination import LottoCombination
from src.models.membership import MembershipTier
from src.services.subscription import get_filter_names_for_tier, get_pipeline_for_tier


@dataclass
class CombinationResult:
    combinations: list[LottoCombination]
    last_draw: list[int]
    tier: MembershipTier
    filters_applied: list[str]
    requested_count: int

    @property
    def is_complete(self) -> bool:
        return len(self.combinations) >= self.requested_count


def generate_combinations(
    tier: MembershipTier,
    count: int = 5,
    max_attempts: int = 50_000,
    draw_seed: int = 42,
) -> CombinationResult:
    draws = generate_mock_draws(count=100, seed=draw_seed)
    last_draw = get_last_draw(draws)
    context = {"last_draw": last_draw, "draw_history": draws}

    pipeline = get_pipeline_for_tier(tier)
    results: list[LottoCombination] = []
    seen: set[tuple[int, ...]] = set()

    rng = random.Random()
    attempts = 0
    while len(results) < count and attempts < max_attempts:
        attempts += 1
        combo = generate_random_combination(seed=rng.randint(0, 10**9))
        if combo.numbers in seen:
            continue
        if pipeline.apply(combo, context):
            seen.add(combo.numbers)
            results.append(combo)

    return CombinationResult(
        combinations=results,
        last_draw=last_draw,
        tier=tier,
        filters_applied=get_filter_names_for_tier(tier),
        requested_count=count,
    )
