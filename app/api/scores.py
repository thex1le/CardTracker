from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services import composite_score

router = APIRouter(prefix="/api", tags=["scores"])


@router.get("/scores")
async def get_all_scores(db: AsyncSession = Depends(get_db)):
    """Get latest composite scores for all players."""
    return await composite_score.get_all_latest_scores(db)


@router.get("/scores/movers")
async def get_movers(days: int = 7, db: AsyncSession = Depends(get_db)):
    """Get players with biggest score changes."""
    return await composite_score.get_score_movers(db, days)


@router.get("/players/{player_id}/score")
async def get_player_score(player_id: int, db: AsyncSession = Depends(get_db)):
    """Get detailed composite score breakdown for a player."""
    return await composite_score.get_player_score(db, player_id)


@router.post("/scores/compute")
async def compute_scores(db: AsyncSession = Depends(get_db)):
    """Compute composite scores for all players."""
    results = await composite_score.compute_all_scores(db)
    return {"status": "ok", "players_scored": len(results)}
