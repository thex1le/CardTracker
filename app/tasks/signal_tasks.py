"""Celery tasks for signal detection and Statcast refresh."""
from datetime import date
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.tasks.celery_app import celery
from app.models.base import Player, Signal
from app.models.baseball import StatcastMetrics
from app.adapters.baseball import statcast as statcast_adapter

_engine = create_engine(settings.sync_database_url)


@celery.task(name="app.tasks.signal_tasks.detect_all_signals_task")
def detect_all_signals_task():
    """Runs signal detection synchronously for Celery."""
    import asyncio
    from app.database import async_session
    from app.services.signal_engine import detect_all_signals

    async def _run():
        async with async_session() as db:
            return await detect_all_signals(db)

    signals = asyncio.run(_run())
    return {"status": "ok", "signals_generated": len(signals)}


@celery.task(name="app.tasks.signal_tasks.refresh_statcast_task")
def refresh_statcast_task():
    """Fetch Statcast metrics for all MLB-level players."""
    season = date.today().year

    with Session(_engine) as db:
        players = db.execute(
            select(Player).where(
                Player.sport == "baseball",
                Player.external_id.isnot(None),
            )
        ).scalars().all()

        updated = 0
        for player in players:
            # Fetch exit velo / barrels
            ev_data = statcast_adapter.fetch_statcast_for_player(player.name, season)

            # Fetch expected stats
            xstats = statcast_adapter.fetch_expected_stats(player.name, season)

            # Fetch sprint speed
            speed = statcast_adapter.fetch_sprint_speed(player.name, season)

            if not ev_data and not xstats and speed is None:
                continue

            combined = {}
            if ev_data:
                combined.update(ev_data)
            if xstats:
                combined.update(xstats)
            if speed is not None:
                combined["sprint_speed"] = speed

            # Store sync
            existing = db.execute(
                select(StatcastMetrics).where(
                    StatcastMetrics.player_id == player.id,
                    StatcastMetrics.season == season,
                )
            ).scalar_one_or_none()

            if existing:
                for k, v in combined.items():
                    if v is not None:
                        setattr(existing, k, v)
            else:
                db.add(StatcastMetrics(
                    player_id=player.id,
                    season=season,
                    **{k: v for k, v in combined.items() if v is not None},
                ))
            updated += 1

        db.commit()

    return {"status": "ok", "players_updated": updated}
