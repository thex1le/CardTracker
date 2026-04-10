from __future__ import annotations

import logging
from datetime import date, timedelta
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import PlayerEvent
from app.models.market_listing_snapshot import MarketListingSnapshot
from app.models.market_sale import MarketSale
from app.models.performance_daily import PerformanceDaily
from app.models.player import Player
from app.models.score_daily import ScoreDaily
from app.scoring.hobby_fit import compute_hobby_fit_score
from app.scoring.hype import HypeFeatures, compute_hype_score
from app.scoring.market import MarketFeatures, compute_market_score
from app.scoring.opportunity import (
    compute_data_confidence,
    compute_exit_risk_score,
    compute_opportunity_score,
)
from app.scoring.supply import SupplyFeatures, compute_supply_score
from app.services.summary_service import generate_summary

logger = logging.getLogger(__name__)


async def refresh_scores_for_player(db: AsyncSession, player: Player) -> ScoreDaily | None:
    """Compute all scores for a player and upsert score_daily for today."""
    today = date.today()
    seven_ago = today - timedelta(days=7)
    thirty_ago = today - timedelta(days=30)

    # --- Build HypeFeatures ---
    events_7d = await db.execute(
        select(PlayerEvent).where(
            PlayerEvent.player_id == player.id,
            PlayerEvent.event_date >= seven_ago,
        )
    )
    events = events_7d.scalars().all()
    event_types = {e.event_type for e in events}

    perf_result = await db.execute(
        select(PerformanceDaily).where(
            PerformanceDaily.player_id == player.id,
            PerformanceDaily.game_date >= seven_ago,
        ).order_by(PerformanceDaily.game_date.desc())
    )
    recent_perf = perf_result.scalars().all()

    hr_7d = sum(p.home_runs or 0 for p in recent_perf)
    saves_7d = sum(p.saves or 0 for p in recent_perf)
    ops_values = [p.ops for p in recent_perf if p.ops is not None]
    ops_delta = 0.0
    if len(ops_values) >= 2:
        ops_delta = ops_values[0] - ops_values[-1]

    hype_features = HypeFeatures(
        call_up_last_7d="call_up" in event_types,
        debut_last_7d="debut" in event_types,
        injury_return_last_7d="injury_return" in event_types,
        important_event_count_7d=len(events),
        hr_last_7d=hr_7d,
        ops_delta_7d=ops_delta,
        saves_last_7d=saves_7d,
    )

    # --- Build MarketFeatures ---
    sales_7d_result = await db.execute(
        select(MarketSale).where(
            MarketSale.player_id == player.id,
            MarketSale.sale_date >= seven_ago,
        )
    )
    sales_7d = sales_7d_result.scalars().all()

    sales_prior_7d_result = await db.execute(
        select(MarketSale).where(
            MarketSale.player_id == player.id,
            MarketSale.sale_date >= seven_ago - timedelta(days=7),
            MarketSale.sale_date < seven_ago,
        )
    )
    sales_prior_7d = sales_prior_7d_result.scalars().all()

    sales_30d_result = await db.execute(
        select(MarketSale).where(
            MarketSale.player_id == player.id,
            MarketSale.sale_date >= thirty_ago,
        )
    )
    sales_30d = sales_30d_result.scalars().all()

    three_ago = today - timedelta(days=3)
    sales_3d = [s for s in sales_7d if s.sale_date >= three_ago]

    prices_7d = [s.sale_price for s in sales_7d]
    prices_prior = [s.sale_price for s in sales_prior_7d]
    median_7d = median(prices_7d) if prices_7d else 0.0
    median_prior = median(prices_prior) if prices_prior else 0.0

    count_change = 0.0
    if len(sales_prior_7d) > 0:
        count_change = ((len(sales_7d) - len(sales_prior_7d)) / len(sales_prior_7d)) * 100

    median_delta_pct = 0.0
    if median_prior > 0:
        median_delta_pct = ((median_7d - median_prior) / median_prior) * 100

    velocity_current = len(sales_7d) / 7.0
    velocity_prior = len(sales_prior_7d) / 7.0
    velocity_delta = 0.0
    if velocity_prior > 0:
        velocity_delta = ((velocity_current - velocity_prior) / velocity_prior) * 100

    market_features = MarketFeatures(
        sales_count_3d=len(sales_3d),
        sales_count_7d=len(sales_7d),
        sales_count_7d_change=count_change,
        median_sale_3d=median([s.sale_price for s in sales_3d]) if sales_3d else 0.0,
        median_sale_7d=median_7d,
        median_sale_delta_pct=median_delta_pct,
        sales_velocity_delta=velocity_delta,
        data_points=len(sales_30d),
    )

    # --- Build SupplyFeatures ---
    snapshot_result = await db.execute(
        select(MarketListingSnapshot).where(
            MarketListingSnapshot.player_id == player.id,
        ).order_by(MarketListingSnapshot.snapshot_date.desc()).limit(8)
    )
    snapshots = snapshot_result.scalars().all()

    active_count = snapshots[0].active_listing_count if snapshots else 0
    listing_7d_ago = next((s for s in snapshots if s.snapshot_date <= seven_ago), None)
    listing_3d_ago = next((s for s in snapshots if s.snapshot_date <= three_ago), None)

    supply_features = SupplyFeatures(
        active_listing_count=active_count,
        listing_delta_3d=active_count - (listing_3d_ago.active_listing_count if listing_3d_ago else active_count),
        listing_delta_7d=active_count - (listing_7d_ago.active_listing_count if listing_7d_ago else active_count),
        listing_sales_ratio=(active_count / max(len(sales_7d), 1)),
    )

    # --- Compute all scores ---
    hype_score = compute_hype_score(hype_features)
    market_score = compute_market_score(market_features)
    supply_score = compute_supply_score(supply_features)
    hobby_fit = compute_hobby_fit_score(player)
    opportunity = compute_opportunity_score(hype_score, market_score, supply_score, hobby_fit)
    exit_risk = compute_exit_risk_score(
        price_spike_score=min(median_delta_pct, 100),
        listing_spike_score=min(supply_features.listing_delta_7d * 2, 100),
        market_cooling_score=max(-velocity_delta, 0),
    )
    confidence = compute_data_confidence(market_features)

    # --- Get yesterday's scores for summary ---
    yesterday = today - timedelta(days=1)
    prev_result = await db.execute(
        select(ScoreDaily).where(
            ScoreDaily.player_id == player.id,
            ScoreDaily.score_date == yesterday,
        )
    )
    yesterday_scores = prev_result.scalar_one_or_none()

    # Build score set for summary
    class ScoreSet:
        pass
    scores = ScoreSet()
    scores.hype_score = hype_score
    scores.market_score = market_score
    scores.supply_score = supply_score
    scores.hobby_fit_score = hobby_fit
    scores.opportunity_score = opportunity
    scores.exit_risk_score = exit_risk

    summary = generate_summary(player, scores, hype_features, market_features, events)

    # --- Upsert ---
    existing_result = await db.execute(
        select(ScoreDaily).where(
            ScoreDaily.player_id == player.id,
            ScoreDaily.score_date == today,
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        existing.hype_score = hype_score
        existing.market_score = market_score
        existing.supply_score = supply_score
        existing.hobby_fit_score = hobby_fit
        existing.opportunity_score = opportunity
        existing.exit_risk_score = exit_risk
        existing.data_confidence = confidence
        existing.summary_text = summary
        row = existing
    else:
        row = ScoreDaily(
            player_id=player.id,
            score_date=today,
            hype_score=hype_score,
            market_score=market_score,
            supply_score=supply_score,
            hobby_fit_score=hobby_fit,
            opportunity_score=opportunity,
            exit_risk_score=exit_risk,
            data_confidence=confidence,
            summary_text=summary,
        )
        db.add(row)

    await db.commit()
    return row
