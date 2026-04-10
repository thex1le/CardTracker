def clamp(value: float, min_val: float = 0.0, max_val: float = 100.0) -> float:
    return max(min_val, min(max_val, value))


def normalize_pct_change(value: float, max_gain: float = 200.0) -> float:
    """Normalize a percentage change to 0-1. Clamps at max_gain."""
    if max_gain == 0:
        return 0.0
    return clamp(value / max_gain, 0.0, 1.0)


def normalize_ratio(value: float, bad_threshold: float = 3.0) -> float:
    """Normalize a ratio where bad_threshold = worst case -> returns 0-1 danger score."""
    if bad_threshold == 0:
        return 0.0
    return clamp(value / bad_threshold, 0.0, 1.0)
