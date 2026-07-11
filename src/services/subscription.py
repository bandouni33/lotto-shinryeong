from src.engine.pipeline import FilterPipeline
from src.filters.base import LottoFilter
from src.filters.consecutive import ConsecutiveExcludeFilter
from src.filters.high_low_carry import CarryOverFilter, HighLowRatioFilter
from src.filters.odd_even import OddEvenRatioFilter
from src.filters.sum_range import SumRangeFilter
from src.models.membership import MembershipTier

FREE_FILTERS: list[LottoFilter] = [
    OddEvenRatioFilter(),
    SumRangeFilter(min_sum=100, max_sum=170),
]

PREMIUM_FILTERS: list[LottoFilter] = FREE_FILTERS + [
    ConsecutiveExcludeFilter(max_consecutive=2),
    HighLowRatioFilter(),
    CarryOverFilter(min_overlap=0, max_overlap=2),
]


def get_filters_for_tier(tier: MembershipTier) -> list[LottoFilter]:
    return FREE_FILTERS if tier == MembershipTier.FREE else PREMIUM_FILTERS


def get_pipeline_for_tier(tier: MembershipTier) -> FilterPipeline:
    return FilterPipeline(get_filters_for_tier(tier))


def get_filter_names_for_tier(tier: MembershipTier) -> list[str]:
    return [f.name for f in get_filters_for_tier(tier)]
