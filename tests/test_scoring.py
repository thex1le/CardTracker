import pytest

from app.scoring.hype import HypeFeatures, compute_hype_score
from app.scoring.market import MarketFeatures, compute_market_score
from app.scoring.supply import SupplyFeatures, compute_supply_score
from app.scoring.opportunity import (
    compute_data_confidence,
    compute_exit_risk_score,
    compute_opportunity_score,
)


class TestHypeScore:
    def test_call_up_gives_30(self):
        f = HypeFeatures(call_up_last_7d=True)
        assert compute_hype_score(f) == 30.0

    def test_clamped_at_100(self):
        f = HypeFeatures(
            call_up_last_7d=True,
            debut_last_7d=True,
            injury_return_last_7d=True,
            hr_last_7d=10,
            ops_delta_7d=5.0,
            saves_last_7d=10,
        )
        assert compute_hype_score(f) == 100.0

    def test_zero_features_gives_zero(self):
        f = HypeFeatures()
        assert compute_hype_score(f) == 0.0

    def test_hr_contribution_capped(self):
        f = HypeFeatures(hr_last_7d=10)
        assert compute_hype_score(f) == 20.0  # min(10*4, 20)

    def test_negative_ops_delta_ignored(self):
        f = HypeFeatures(ops_delta_7d=-0.5)
        assert compute_hype_score(f) == 0.0


class TestMarketScore:
    def test_all_zero_gives_zero(self):
        f = MarketFeatures()
        assert compute_market_score(f) == 0.0

    def test_high_sales_change(self):
        f = MarketFeatures(sales_count_7d_change=200.0)
        score = compute_market_score(f)
        assert score == pytest.approx(40.0, abs=0.1)

    def test_combined_features(self):
        f = MarketFeatures(
            sales_count_7d_change=100.0,
            median_sale_delta_pct=50.0,
            sales_velocity_delta=50.0,
        )
        score = compute_market_score(f)
        assert 0 < score < 100


class TestSupplyScore:
    def test_high_ratio_gives_high_score(self):
        f = SupplyFeatures(listing_sales_ratio=3.0)
        score = compute_supply_score(f)
        assert score == pytest.approx(50.0, abs=0.1)

    def test_zero_gives_zero(self):
        f = SupplyFeatures()
        assert compute_supply_score(f) == 0.0

    def test_both_factors(self):
        f = SupplyFeatures(listing_delta_7d=200, listing_sales_ratio=3.0)
        assert compute_supply_score(f) == 100.0


class TestOpportunityScore:
    def test_high_supply_penalty(self):
        # High supply should bring score down
        with_supply = compute_opportunity_score(50, 50, 100, 50)
        without_supply = compute_opportunity_score(50, 50, 0, 50)
        assert with_supply < without_supply

    def test_clamped_at_zero(self):
        score = compute_opportunity_score(0, 0, 100, 0)
        assert score == 0.0


class TestExitRisk:
    def test_all_high(self):
        score = compute_exit_risk_score(100, 100, 100)
        assert score == 100.0

    def test_all_zero(self):
        score = compute_exit_risk_score(0, 0, 0)
        assert score == 0.0


class TestDataConfidence:
    def test_zero_sales(self):
        f = MarketFeatures(data_points=0)
        assert compute_data_confidence(f) == 0.2

    def test_three_sales(self):
        f = MarketFeatures(data_points=3)
        assert compute_data_confidence(f) == 0.5

    def test_ten_sales(self):
        f = MarketFeatures(data_points=10)
        assert compute_data_confidence(f) == 0.75

    def test_twenty_five_sales(self):
        f = MarketFeatures(data_points=25)
        assert compute_data_confidence(f) == 1.0
