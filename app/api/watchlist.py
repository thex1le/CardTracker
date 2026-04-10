from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services import watchlist_service

router = APIRouter(prefix="/api", tags=["watchlist"])


class WatchlistAdd(BaseModel):
    player_id: int
    notes: Optional[str] = None


@router.get("/watchlist")
async def get_watchlist(db: AsyncSession = Depends(get_db)):
    """Get all watchlist items with scores."""
    return await watchlist_service.get_watchlist(db)


@router.post("/watchlist")
async def add_to_watchlist(body: WatchlistAdd, db: AsyncSession = Depends(get_db)):
    """Add a player to the watchlist."""
    return await watchlist_service.add_to_watchlist(db, body.player_id, body.notes)


@router.delete("/watchlist/{item_id}")
async def remove_from_watchlist(item_id: int, db: AsyncSession = Depends(get_db)):
    """Remove a player from the watchlist."""
    return await watchlist_service.remove_from_watchlist(db, item_id)


@router.get("/alerts")
async def get_alerts(db: AsyncSession = Depends(get_db)):
    """Get unread user alerts."""
    return await watchlist_service.get_unread_alerts(db)


@router.post("/alerts/{alert_id}/read")
async def mark_read(alert_id: int, db: AsyncSession = Depends(get_db)):
    """Mark an alert as read."""
    return await watchlist_service.mark_alert_read(db, alert_id)
