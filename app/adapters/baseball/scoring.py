def _safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def hitter_score(stats_by_year: dict) -> float:
    """OPS-based score averaged across seasons."""
    season_ops = []
    for season, splits in stats_by_year.items():
        total_ab = sum(s.get("ab", 0) for s in splits)
        if total_ab == 0:
            continue
        weighted_ops = sum(
            _safe_float(s.get("ops", 0)) * s.get("ab", 0)
            for s in splits if s.get("ab", 0) > 0
        )
        season_ops.append(weighted_ops / total_ab)
    if not season_ops:
        return 0.0
    return sum(season_ops) / len(season_ops)


def pitcher_score(stats_by_year: dict) -> float:
    """Inverted ERA-based score (lower ERA = higher score) averaged across seasons."""
    season_scores = []
    for season, splits in stats_by_year.items():
        total_ip = sum(_safe_float(s.get("ip", 0)) for s in splits)
        if total_ip == 0:
            continue
        weighted_era = sum(
            _safe_float(s.get("era", 0)) * _safe_float(s.get("ip", 0))
            for s in splits if _safe_float(s.get("ip", 0)) > 0
        )
        avg_era = weighted_era / total_ip
        season_scores.append(max(0, 10 - avg_era))
    if not season_scores:
        return 0.0
    return sum(season_scores) / len(season_scores)


def compute_score(stats_by_year: dict, is_pitcher: bool) -> float:
    if is_pitcher:
        return round(pitcher_score(stats_by_year), 3)
    return round(hitter_score(stats_by_year), 3)
