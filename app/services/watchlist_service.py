"""Watchlist and alerts service."""
from __future__ import annotations

from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Player, CompositeScore
from app.models.watchlist import WatchlistItem, AlertPreference, UserAlert


async def get_watchlist(db: AsyncSession) -> list[dict]:
    """Get all watchlist items with latest scores."""
    result = await db.execute(
        select(WatchlistItem).order_by(WatchlistItem.added_at.desc())
    )
    items = result.scalars().all()

    out = []
    for item in items:
        player = await db.get(Player, item.player_id)

        # Latest score
        score_result = await db.execute(
            select(CompositeScore)
            .where(CompositeScore.player_id == item.player_id)
            .order_by(CompositeScore.computed_at.desc())
            .limit(1)
        )
        cs = score_result.scalar_one_or_none()

        out.append({
            "id": item.id,
            "player_id": item.player_id,
            "player_name": player.name if player else "Unknown",
            "team": player.team if player else "",
            "position": player.position if player else "",
            "notes": item.notes,
            "added_at": item.added_at.isoformat() if item.added_at else None,
            "score": cs.score if cs else None,
            "score_breakdown": {
                "performance": cs.performance_sub,
                "momentum": cs.momentum_sub,
                "card_price": cs.card_price_sub,
                "sentiment": cs.sentiment_sub,
                "availability": cs.availability_sub,
            } if cs else None,
        })

    return out


async def add_to_watchlist(db: AsyncSession, player_id: int, notes: str = None) -> dict:
    """Add a player to the watchlist."""
    # Check if already on watchlist
    existing = await db.execute(
        select(WatchlistItem).where(WatchlistItem.player_id == player_id)
    )
    if existing.scalar_one_or_none():
        return {"status": "exists", "message": "Player already on watchlist"}

    item = WatchlistItem(
        player_id=player_id,
        notes=notes,
        added_at=datetime.utcnow(),
    )
    db.add(item)

    # Add default alert preferences
    for alert_type, threshold in [
        ("score_change", 10.0),
        ("sentiment_red", None),
        ("price_spike", None),
    ]:
        db.add(AlertPreference(
            watchlist_item=item,
            alert_type=alert_type,
            threshold=threshold,
            enabled=True,
        ))

    await db.commit()
    return {"status": "ok", "id": item.id}


async def remove_from_watchlist(db: AsyncSession, item_id: int) -> dict:
    """Remove a player from the watchlist."""
    item = await db.get(WatchlistItem, item_id)
    if not item:
        return {"status": "error", "message": "Watchlist item not found"}

    await db.delete(item)
    await db.commit()
    return {"status": "ok"}


async def get_unread_alerts(db: AsyncSession, limit: int = 50) -> list[dict]:
    """Get unread user alerts."""
    result = await db.execute(
        select(UserAlert)
        .where(UserAlert.is_read == False)
        .order_by(UserAlert.created_at.desc())
        .limit(limit)
    )
    alerts = result.scalars().all()

    out = []
    for a in alerts:
        player = await db.get(Player, a.player_id)
        out.append({
            "id": a.id,
            "player_id": a.player_id,
            "player_name": player.name if player else "Unknown",
            "alert_type": a.alert_type,
            "title": a.title,
            "body": a.body,
            "is_read": a.is_read,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        })
    return out


async def mark_alert_read(db: AsyncSession, alert_id: int) -> dict:
    """Mark an alert as read."""
    alert = await db.get(UserAlert, alert_id)
    if not alert:
        return {"status": "error"}
    alert.is_read = True
    await db.commit()
    return {"status": "ok"}


async def generate_alerts(db: AsyncSession) -> int:
    """Generate alerts for watchlisted players based on score changes and events."""
    result = await db.execute(select(WatchlistItem))
    items = result.scalars().all()
    count = 0

    for item in items:
        player = await db.get(Player, item.player_id)
        if not player:
            continue

        # Get last 2 scores to check for changes
        scores_result = await db.execute(
            select(CompositeScore)
            .where(CompositeScore.player_id == item.player_id)
            .order_by(CompositeScore.computed_at.desc())
            .limit(2)
        )
        scores = scores_result.scalars().all()

        if len(scores) >= 2:
            delta = scores[0].score - scores[1].score
            if abs(delta) >= 5:
                direction = "up" if delta > 0 else "down"
                db.add(UserAlert(
                    player_id=item.player_id,
                    alert_type="score_change",
                    title=f"{player.name} score moved {direction} by {abs(delta):.0f} pts",
                    body=f"Score changed from {scores[1].score:.0f} to {scores[0].score:.0f}",
                ))
                count += 1

    await db.commit()
    return count
