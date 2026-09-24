SEASONS = ("春", "夏", "秋", "冬")
DEFAULT_LINE = 7.0


def weigh(aroma: float, taste: float, liquor: float, line: float = DEFAULT_LINE) -> tuple[str, str, float]:
    score = round(aroma * 0.3 + taste * 0.5 + liquor * 0.2, 2)
    if score >= line:
        return "通过", f"加权分达到放行线（{line:g}）", score
    return "不通过", f"加权分低于放行线（{line:g}）", score
