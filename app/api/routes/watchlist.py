from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.player import Player
from app.models.score_daily import ScoreDaily
from app.models.watchlist import Watchlist, WatchlistPlayer
from app.schemas.watchlist import WatchlistCreate, WatchlistPlayerAdd

router = APIRouter(prefix="/watchlists", tags=["watchlist"])


@router.get("")
async def list_watchlists(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Watchlist))
    watchlists = result.scalars().all()
    return [
        {
            "id": w.id,
            "name": w.name,
            "user_id": w.user_id,
            "player_count": len(w.players),
        }
        for w in watchlists
    ]


@router.post("")
async def create_watchlist(body: WatchlistCreate, db: AsyncSession = Depends(get_db)):
    wl = Watchlist(name=body.name, user_id=body.user_id)
    db.add(wl)
    await db.commit()
    await db.refresh(wl)
    return {"id": wl.id, "name": wl.name, "user_id": wl.user_id}


@router.get("/{watchlist_id}")
async def get_watchlist(watchlist_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Watchlist).where(Watchlist.id == watchlist_id))
    wl = result.scalar_one_or_none()
    if not wl:
        raise HTTPException(status_code=404, detail="Watchlist not found")

    players = []
    for wp in wl.players:
        player_result = await db.execute(select(Player).where(Player.id == wp.player_id))
        player = player_result.scalar_one_or_none()
        if not player:
            continue

        score_result = await db.execute(
            select(ScoreDaily)
            .where(ScoreDaily.player_id == player.id)
            .order_by(ScoreDaily.score_date.desc())
            .limit(1)
        )
        score = score_result.scalar_one_or_none()

        players.append({
            "player_id": player.id,
            "name": player.name,
            "team": player.team,
            "position": player.position,
            "scores": {
                "opportunity_score": score.opportunity_score if score else None,
                "hype_score": score.hype_score if score else None,
                "market_score": score.market_score if score else None,
            } if score else None,
        })

    return {
        "id": wl.id,
        "name": wl.name,
        "user_id": wl.user_id,
        "players": players,
    }


@router.post("/{watchlist_id}/players")
async def add_player_to_watchlist(
    watchlist_id: int,
    body: WatchlistPlayerAdd,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Watchlist).where(Watchlist.id == watchlist_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Watchlist not found")

    # Check duplicate
    existing = await db.execute(
        select(WatchlistPlayer).where(
            WatchlistPlayer.watchlist_id == watchlist_id,
            WatchlistPlayer.player_id == body.player_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Player already in watchlist")

    wp = WatchlistPlayer(watchlist_id=watchlist_id, player_id=body.player_id)
    db.add(wp)
    await db.commit()
    return {"status": "added"}


@router.delete("/{watchlist_id}/players/{player_id}")
async def remove_player_from_watchlist(
    watchlist_id: int,
    player_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WatchlistPlayer).where(
            WatchlistPlayer.watchlist_id == watchlist_id,
            WatchlistPlayer.player_id == player_id,
        )
    )
    wp = result.scalar_one_or_none()
    if not wp:
        raise HTTPException(status_code=404, detail="Player not in watchlist")

    await db.delete(wp)
    await db.commit()
    return {"status": "removed"}
