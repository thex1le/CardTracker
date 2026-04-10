from pydantic import BaseModel

from app.scoring.normalization import clamp, normalize_pct_change


class MarketFeatures(BaseModel):
    sales_count_3d: int = 0
    sales_count_7d: int = 0
    sales_count_7d_change: float = 0.0  # pct change vs prior 7d
    median_sale_3d: float = 0.0
    median_sale_7d: float = 0.0
    median_sale_delta_pct: float = 0.0
    sales_velocity_delta: float = 0.0
    data_points: int = 0  # used for confidence calculation


def compute_market_score(features: MarketFeatures) -> float:
    score = 0.0
    score += normalize_pct_change(features.sales_count_7d_change, max_gain=200) * 40
    score += normalize_pct_change(features.median_sale_delta_pct, max_gain=100) * 35
    score += normalize_pct_change(features.sales_velocity_delta, max_gain=100) * 25
    return clamp(score)
