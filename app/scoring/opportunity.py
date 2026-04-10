from app.scoring.market import MarketFeatures
from app.scoring.normalization import clamp


def compute_opportunity_score(
    hype: float,
    market: float,
    supply: float,
    hobby_fit: float,
) -> float:
    opportunity = (0.30 * hype) + (0.30 * market) + (0.25 * hobby_fit) - (0.15 * supply)
    return clamp(opportunity)


def compute_exit_risk_score(
    price_spike_score: float,
    listing_spike_score: float,
    market_cooling_score: float,
) -> float:
    exit_risk = (0.40 * price_spike_score) + (0.35 * listing_spike_score) + (0.25 * market_cooling_score)
    return clamp(exit_risk)


def compute_data_confidence(market_features: MarketFeatures) -> float:
    """Returns 0.0-1.0 based on data completeness."""
    dp = market_features.data_points
    if dp < 3:
        return 0.2
    if dp < 10:
        return 0.5
    if dp < 25:
        return 0.75
    return 1.0
