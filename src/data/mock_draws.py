import random


def generate_mock_draws(count: int = 100, seed: int = 42) -> list[list[int]]:
    """동행복권 스타일 가상 역대 당첨 번호 생성"""
    rng = random.Random(seed)
    draws = []
    for _ in range(count):
        draw = sorted(rng.sample(range(1, 46), 6))
        draws.append(draw)
    return draws


def get_last_draw(draws: list[list[int]]) -> list[int]:
    return draws[-1] if draws else []
