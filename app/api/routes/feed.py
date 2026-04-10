from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.services.feed_service import get_misspelled_feed, get_opportunities

router = APIRouter(prefix="/feed", tags=["feed"])


@router.get("/opportunities")
async def opportunities(
    position: str | None = None,
    team: str | None = None,
    prospects_only: bool = False,
    min_confidence: float = 0.0,
    limit: int = 25,
    db: AsyncSession = Depends(get_db),
):
    return await get_opportunities(
        db,
        position=position,
        team=team,
        prospects_only=prospects_only,
        min_confidence=min_confidence,
        limit=limit,
    )


@router.get("/misspelled")
async def misspelled(
    limit: int = 25,
    db: AsyncSession = Depends(get_db),
):
    return await get_misspelled_feed(db, limit=limit)
