from pydantic import BaseModel

from app.scoring.normalization import clamp, normalize_pct_change, normalize_ratio


class SupplyFeatures(BaseModel):
    active_listing_count: int = 0
    listing_delta_3d: int = 0
    listing_delta_7d: int = 0
    listing_sales_ratio: float = 0.0


def compute_supply_score(features: SupplyFeatures) -> float:
    """Higher score = more danger (supply overwhelming demand)."""
    score = 0.0
    score += normalize_pct_change(features.listing_delta_7d, max_gain=200) * 50
    score += normalize_ratio(features.listing_sales_ratio, bad_threshold=3.0) * 50
    return clamp(score)
