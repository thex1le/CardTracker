from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.base import Player, Signal
from app.models.baseball import StatcastMetrics
from app.services import signal_engine

router = APIRouter(prefix="/api", tags=["signals"])


@router.get("/signals")
async def get_signals(
    signal_type: Optional[str] = None,
    severity: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get all active signals, optionally filtered by type and severity."""
    query = select(Signal).order_by(Signal.detected_at.desc()).limit(200)
    if signal_type:
        query = query.where(Signal.signal_type == signal_type)
    if severity:
        query = query.where(Signal.severity == severity)

    result = await db.execute(query)
    signals = result.scalars().all()

    # Enrich with player names
    out = []
    for s in signals:
        player = await db.get(Player, s.player_id)
        out.append({
            "id": s.id,
            "player_id": s.player_id,
            "player_name": player.name if player else "Unknown",
            "player_team": player.team if player else "",
            "signal_type": s.signal_type,
            "severity": s.severity,
            "title": s.title,
            "description": s.description,
            "detected_at": s.detected_at.isoformat() if s.detected_at else None,
        })

    return out


@router.get("/players/{player_id}/signals")
async def get_player_signals(player_id: int, db: AsyncSession = Depends(get_db)):
    """Get signals for a specific player."""
    result = await db.execute(
        select(Signal)
        .where(Signal.player_id == player_id)
        .order_by(Signal.detected_at.desc())
        .limit(20)
    )
    signals = result.scalars().all()
    return [
        {
            "id": s.id,
            "signal_type": s.signal_type,
            "severity": s.severity,
            "title": s.title,
            "description": s.description,
            "detected_at": s.detected_at.isoformat() if s.detected_at else None,
        }
        for s in signals
    ]


@router.get("/players/{player_id}/statcast")
async def get_player_statcast(player_id: int, db: AsyncSession = Depends(get_db)):
    """Get Statcast metrics for a player."""
    result = await db.execute(
        select(StatcastMetrics)
        .where(StatcastMetrics.player_id == player_id)
        .order_by(StatcastMetrics.season.desc())
        .limit(5)
    )
    metrics = result.scalars().all()
    return [
        {
            "season": m.season,
            "exit_velo_avg": m.exit_velo_avg,
            "exit_velo_max": m.exit_velo_max,
            "barrel_rate": m.barrel_rate,
            "hard_hit_rate": m.hard_hit_rate,
            "xba": m.xba,
            "xslg": m.xslg,
            "xwoba": m.xwoba,
            "sprint_speed": m.sprint_speed,
        }
        for m in metrics
    ]


@router.post("/signals/detect")
async def trigger_signal_detection(db: AsyncSession = Depends(get_db)):
    """Manually trigger signal detection for all players."""
    signals = await signal_engine.detect_all_signals(db)
    return {"status": "ok", "signals_generated": len(signals)}
