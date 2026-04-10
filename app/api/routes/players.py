from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.event import PlayerEvent
from app.models.market_listing_snapshot import MarketListingSnapshot
from app.models.market_sale import MarketSale
from app.models.performance_daily import PerformanceDaily
from app.models.score_daily import ScoreDaily
from app.services.player_service import get_player, search_players

router = APIRouter(prefix="/players", tags=["players"])


@router.get("")
async def list_players(
    q: str | None = None,
    active: bool = True,
    db: AsyncSession = Depends(get_db),
):
    players = await search_players(db, q=q, active=active)
    return [
        {
            "id": p.id,
            "name": p.name,
            "team": p.team,
            "position": p.position,
            "prospect_flag": p.prospect_flag,
            "active": p.active,
        }
        for p in players
    ]


@router.get("/{player_id}")
async def player_detail(player_id: int, db: AsyncSession = Depends(get_db)):
    player = await get_player(db, player_id)
    if not player:
        return {"error": "Player not found"}

    today = date.today()
    thirty_ago = today - timedelta(days=30)
    fourteen_ago = today - timedelta(days=14)

    # Latest scores
    score_result = await db.execute(
        select(ScoreDaily)
        .where(ScoreDaily.player_id == player_id)
        .order_by(ScoreDaily.score_date.desc())
        .limit(1)
    )
    latest_score = score_result.scalar_one_or_none()

    # Recent events (30 days)
    events_result = await db.execute(
        select(PlayerEvent)
        .where(PlayerEvent.player_id == player_id, PlayerEvent.event_date >= thirty_ago)
        .order_by(PlayerEvent.event_date.desc())
    )
    events = [
        {
            "event_type": e.event_type,
            "event_date": e.event_date.isoformat(),
            "title": e.title,
            "details": e.details,
            "importance_score": e.importance_score,
        }
        for e in events_result.scalars().all()
    ]

    # Recent performance (14 games)
    perf_result = await db.execute(
        select(PerformanceDaily)
        .where(PerformanceDaily.player_id == player_id, PerformanceDaily.game_date >= fourteen_ago)
        .order_by(PerformanceDaily.game_date.desc())
    )
    performance = [
        {
            "game_date": p.game_date.isoformat(),
            "at_bats": p.at_bats,
            "hits": p.hits,
            "home_runs": p.home_runs,
            "rbi": p.rbi,
            "walks": p.walks,
            "strikeouts": p.strikeouts,
            "ops": p.ops,
        }
        for p in perf_result.scalars().all()
    ]

    # Recent sales (30 days)
    sales_result = await db.execute(
        select(MarketSale)
        .where(MarketSale.player_id == player_id, MarketSale.sale_date >= thirty_ago)
        .order_by(MarketSale.sale_date.desc())
    )
    sales = [
        {
            "card_title": s.card_title,
            "card_type": s.card_type,
            "grader": s.grader,
            "grade": s.grade,
            "sale_price": s.sale_price,
            "sale_date": s.sale_date.isoformat(),
            "listing_type": s.listing_type,
            "match_method": s.player_match_method,
        }
        for s in sales_result.scalars().all()
    ]

    # Listing snapshots (14 days)
    snap_result = await db.execute(
        select(MarketListingSnapshot)
        .where(
            MarketListingSnapshot.player_id == player_id,
            MarketListingSnapshot.snapshot_date >= fourteen_ago,
        )
        .order_by(MarketListingSnapshot.snapshot_date.desc())
    )
    snapshots = [
        {
            "snapshot_date": s.snapshot_date.isoformat(),
            "active_listing_count": s.active_listing_count,
            "new_listing_count_1d": s.new_listing_count_1d,
            "auction_count": s.auction_count,
            "bin_count": s.bin_count,
        }
        for s in snap_result.scalars().all()
    ]

    scores_dict = None
    summary = None
    if latest_score:
        scores_dict = {
            "hype_score": latest_score.hype_score,
            "market_score": latest_score.market_score,
            "supply_score": latest_score.supply_score,
            "hobby_fit_score": latest_score.hobby_fit_score,
            "opportunity_score": latest_score.opportunity_score,
            "exit_risk_score": latest_score.exit_risk_score,
            "data_confidence": latest_score.data_confidence,
            "score_date": latest_score.score_date.isoformat(),
        }
        summary = latest_score.summary_text

    return {
        "id": player.id,
        "name": player.name,
        "team": player.team,
        "position": player.position,
        "bats": player.bats,
        "throws": player.throws,
        "age": player.age,
        "prospect_flag": player.prospect_flag,
        "top_prospect_flag": player.top_prospect_flag,
        "market_size_tier": player.market_size_tier,
        "active": player.active,
        "scores": scores_dict,
        "summary_text": summary,
        "recent_events": events,
        "recent_performance": performance,
        "recent_sales": sales,
        "listing_snapshots": snapshots,
    }
