from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert
from app.models.market_sale import MarketSale
from app.models.player import Player
from app.models.score_daily import ScoreDaily


async def get_opportunities(
    db: AsyncSession,
    position: str | None = None,
    team: str | None = None,
    prospects_only: bool = False,
    min_confidence: float = 0.0,
    limit: int = 25,
) -> list[dict]:
    """Return top opportunity feed sorted by opportunity_score desc.

    Filters out players where data_confidence < min_confidence.
    Filters out players with < 5 total sales in last 30 days from top 10.
    """
    today = date.today()
    stmt = (
        select(ScoreDaily, Player)
        .join(Player, ScoreDaily.player_id == Player.id)
        .where(ScoreDaily.score_date == today)
        .where(ScoreDaily.data_confidence >= min_confidence)
        .order_by(ScoreDaily.opportunity_score.desc())
    )

    if position:
        stmt = stmt.where(Player.position == position)
    if team:
        stmt = stmt.where(Player.team == team)
    if prospects_only:
        stmt = stmt.where(Player.prospect_flag.is_(True))

    result = await db.execute(stmt.limit(limit + 10))  # fetch extra for filtering
    rows = result.all()

    # For top 10, check sales count
    thirty_ago = today - timedelta(days=30)
    feed = []
    for score, player in rows:
        if len(feed) < 10:
            sales_result = await db.execute(
                select(MarketSale).where(
                    MarketSale.player_id == player.id,
                    MarketSale.sale_date >= thirty_ago,
                )
            )
            sales_count = len(sales_result.scalars().all())
            if sales_count < 5 and score.data_confidence < 0.3:
                continue

        feed.append({
            "player_id": player.id,
            "player_name": player.name,
            "team": player.team,
            "position": player.position,
            "opportunity_score": score.opportunity_score,
            "hype_score": score.hype_score,
            "market_score": score.market_score,
            "supply_score": score.supply_score,
            "hobby_fit_score": score.hobby_fit_score,
            "exit_risk_score": score.exit_risk_score,
            "data_confidence": score.data_confidence,
            "summary": score.summary_text,
        })
        if len(feed) >= limit:
            break

    return feed


async def get_misspelled_feed(db: AsyncSession, limit: int = 25) -> list[dict]:
    """Return recent misspelled_listing alerts with player info and price delta."""
    stmt = (
        select(Alert, Player)
        .join(Player, Alert.player_id == Player.id)
        .where(Alert.alert_type == "misspelled_listing")
        .order_by(Alert.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "alert_id": alert.id,
            "player_id": player.id,
            "player_name": player.name,
            "team": player.team,
            "severity": alert.severity,
            "title": alert.title,
            "body": alert.body,
            "alert_date": alert.alert_date.isoformat(),
            "score_snapshot": alert.score_snapshot,
        }
        for alert, player in rows
    ]
