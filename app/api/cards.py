from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.base import Player, Card, PricePoint
from app.services import card_market

router = APIRouter(prefix="/api", tags=["cards"])


@router.get("/cards")
async def get_cards(
    player_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get cards, optionally filtered by player."""
    query = select(Card).order_by(Card.card_year.desc())
    if player_id:
        query = query.where(Card.player_id == player_id)

    result = await db.execute(query.limit(200))
    cards = result.scalars().all()

    out = []
    for c in cards:
        player = await db.get(Player, c.player_id)
        out.append({
            "id": c.id,
            "player_id": c.player_id,
            "player_name": player.name if player else "Unknown",
            "card_name": c.card_name,
            "card_year": c.card_year,
            "card_set": c.card_set,
            "card_number": c.card_number,
            "is_auto": c.is_auto,
            "is_graded": c.is_graded,
            "grade": c.grade,
        })
    return out


@router.get("/cards/{card_id}/prices")
async def get_card_prices(card_id: int, days: int = 90, db: AsyncSession = Depends(get_db)):
    """Get price history for a card."""
    trend = await card_market.get_price_trend(db, card_id, days)

    # Also return raw recent prices
    result = await db.execute(
        select(PricePoint)
        .where(PricePoint.card_id == card_id)
        .order_by(PricePoint.sold_date.desc())
        .limit(50)
    )
    points = result.scalars().all()

    return {
        "trend": trend,
        "recent_sales": [
            {
                "price_cents": p.price_cents,
                "sold_date": p.sold_date,
                "listing_title": p.listing_title,
                "source": p.source,
            }
            for p in points
        ],
    }


@router.get("/players/{player_id}/market")
async def get_player_market(player_id: str, db: AsyncSession = Depends(get_db)):
    """Get market summary for a player. Accepts internal DB id or external MLB id."""
    db_id = await _resolve_player_id(db, player_id)
    if not db_id:
        return {"player_id": player_id, "cards": [], "has_data": False, "error": "Player not found"}
    return await card_market.get_player_market_summary(db, db_id)


@router.post("/players/{player_id}/market/refresh")
async def refresh_player_market(player_id: str, db: AsyncSession = Depends(get_db)):
    """Scrape latest card prices for a player from 130point."""
    db_id = await _resolve_player_id(db, player_id)
    if not db_id:
        return {"status": "error", "message": "Player not found"}
    count = await card_market.refresh_card_prices(db, db_id)
    return {"status": "ok", "new_listings": count, "player_id": db_id}


async def _resolve_player_id(db: AsyncSession, player_id: str) -> Optional[int]:
    """Resolve a player_id that could be internal DB id or external MLB id."""
    # Try as internal ID first
    try:
        int_id = int(player_id)
        player = await db.get(Player, int_id)
        if player:
            return player.id
    except (ValueError, TypeError):
        pass

    # Try as external ID
    result = await db.execute(
        select(Player).where(Player.external_id == str(player_id)).limit(1)
    )
    player = result.scalar_one_or_none()
    return player.id if player else None


@router.post("/market/refresh-all")
async def refresh_all_market(db: AsyncSession = Depends(get_db)):
    """Scrape card prices for all tracked players. Rate-limited, takes a while."""
    result = await db.execute(
        select(Player).where(Player.sport == "baseball").order_by(Player.id)
    )
    players = result.scalars().all()

    total = 0
    for player in players[:20]:  # Limit to top 20 to stay within rate limits
        count = await card_market.refresh_card_prices(db, player.id)
        total += count

    return {"status": "ok", "players_scraped": min(len(players), 20), "new_listings": total}
