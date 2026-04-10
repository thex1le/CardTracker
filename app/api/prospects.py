from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services import prospect_service

router = APIRouter(prefix="/api", tags=["prospects"])


@router.get("/prospects")
async def get_prospects(refresh: bool = False, db: AsyncSession = Depends(get_db)):
    """Get top 100 prospects with stats and rankings.

    Pass ?refresh=true to force a fresh fetch from external APIs.
    Otherwise serves from the database cache.
    """
    # Try cached data first
    if not refresh:
        cached = await prospect_service.get_cached_prospects(db)
        if cached:
            return cached

    # No cache or refresh requested — fetch fresh
    return await prospect_service.refresh_prospects(db)


@router.get("/prospects/{player_id}/history")
async def get_ranking_history(player_id: int, db: AsyncSession = Depends(get_db)):
    """Get ranking history for a player."""
    from sqlalchemy import select
    from app.models.base import ProspectRanking, Player

    result = await db.execute(
        select(Player).where(Player.id == player_id)
    )
    player = result.scalar_one_or_none()
    if not player:
        return {"error": "Player not found"}

    rankings = await db.execute(
        select(ProspectRanking)
        .where(ProspectRanking.player_id == player_id)
        .order_by(ProspectRanking.fetched_at.desc())
        .limit(20)
    )
    history = [
        {
            "rank": r.rank,
            "fv": r.fv,
            "eta": r.eta,
            "source": r.source,
            "date": r.fetched_at.isoformat() if r.fetched_at else None,
        }
        for r in rankings.scalars().all()
    ]
    return {"player": player.name, "history": history}
