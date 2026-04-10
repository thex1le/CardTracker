from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.base import Player, SentimentEvent
from app.services import news_sentiment

router = APIRouter(prefix="/api", tags=["news"])


@router.get("/news")
async def get_news(
    player_id: Optional[int] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """Get recent news events, optionally filtered by player."""
    query = select(SentimentEvent).order_by(SentimentEvent.published_at.desc()).limit(limit)
    if player_id:
        query = query.where(SentimentEvent.player_id == player_id)

    result = await db.execute(query)
    events = result.scalars().all()

    out = []
    for e in events:
        player = await db.get(Player, e.player_id)
        out.append({
            "id": e.id,
            "player_id": e.player_id,
            "player_name": player.name if player else "Unknown",
            "player_team": player.team if player else "",
            "headline": e.headline,
            "summary": e.summary,
            "url": e.url,
            "source": e.source,
            "sentiment": e.sentiment,
            "sentiment_score": e.sentiment_score,
            "alert_tier": e.alert_tier,
            "category": e.category,
            "published_at": e.published_at.isoformat() if e.published_at else None,
        })

    return out


@router.get("/news/alerts")
async def get_alerts(db: AsyncSession = Depends(get_db)):
    """Get active RED and YELLOW alerts across all players."""
    return await news_sentiment.get_active_alerts(db)


@router.get("/players/{player_id}/sentiment")
async def get_player_sentiment(player_id: int, db: AsyncSession = Depends(get_db)):
    """Get sentiment summary and recent events for a player."""
    return await news_sentiment.get_player_sentiment(db, player_id)


@router.post("/news/refresh")
async def refresh_news(db: AsyncSession = Depends(get_db)):
    """Manually trigger a news refresh from all sources."""
    count = await news_sentiment.refresh_news(db)
    return {"status": "ok", "new_events": count}
