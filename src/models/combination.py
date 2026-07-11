from dataclasses import dataclass


@dataclass(frozen=True)
class LottoCombination:
    numbers: tuple[int, ...]

    def __post_init__(self):
        if len(self.numbers) != 6:
            raise ValueError("로또 조합은 6개 번호여야 합니다")
        if len(set(self.numbers)) != 6:
            raise ValueError("중복 번호가 있습니다")
        if any(n < 1 or n > 45 for n in self.numbers):
            raise ValueError("번호는 1~45 사이여야 합니다")

    @property
    def sorted_numbers(self) -> list[int]:
        return sorted(self.numbers)

    @property
    def total_sum(self) -> int:
        return sum(self.numbers)

    @property
    def odd_count(self) -> int:
        return sum(1 for n in self.numbers if n % 2 == 1)

    @property
    def even_count(self) -> int:
        return 6 - self.odd_count

    @property
    def low_count(self) -> int:
        return sum(1 for n in self.numbers if n <= 22)

    @property
    def high_count(self) -> int:
        return 6 - self.low_count

    def __str__(self) -> str:
        return " ".join(f"{n:02d}" for n in self.sorted_numbers)
