from src.models.combination import LottoCombination


def _ball_color(number: int) -> str:
    if number <= 10:
        return "#FBC400"
    if number <= 20:
        return "#69C8F2"
    if number <= 30:
        return "#FF7272"
    if number <= 40:
        return "#AAAAAA"
    return "#B0D840"


def render_combination_row(index: int, combo: LottoCombination) -> str:
    balls = "".join(
        f'<span class="lotto-ball" style="background:{_ball_color(n)};">{n:02d}</span>'
        for n in combo.sorted_numbers
    )
    return f"""
    <div class="combo-card">
        <div class="combo-header">조합 {index}</div>
        <div class="ball-row">{balls}</div>
        <div class="combo-meta">
            합 {combo.total_sum}
            · 홀:짝 {combo.odd_count}:{combo.even_count}
            · 저:고 {combo.low_count}:{combo.high_count}
        </div>
    </div>
    """


def render_results(combinations: list[LottoCombination]) -> str:
    rows = "".join(
        render_combination_row(i, combo) for i, combo in enumerate(combinations, 1)
    )
    return f'<div class="results-stack">{rows}</div>'
