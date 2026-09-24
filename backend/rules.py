def weigh(aroma: float, taste: float, liquor: float, line: float = 7.0) -> tuple[str, str, float]:
    score = round(aroma * 0.3 + taste * 0.5 + liquor * 0.2, 2)
    if score >= line:
        return "通过", f"加权分达到放行线 {line}", score
    return "不通过", f"加权分低于放行线 {line}", score
