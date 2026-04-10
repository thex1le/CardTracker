"""Seed hobby fit scores for all players.

Usage: python scripts/seed_hobby_fit.py
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import date

sys.path.insert(0, ".")

from sqlalchemy import select

from app.core.db import AsyncSessionLocal, Base, engine
from app.models.player import Player
from app.models.score_daily import ScoreDaily
from app.scoring.hobby_fit import compute_hobby_fit_score

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Player).where(Player.active.is_(True)))
        players = result.scalars().all()

        today = date.today()
        count = 0
        for player in players:
            hobby_fit = compute_hobby_fit_score(player)

            existing = await db.execute(
                select(ScoreDaily).where(
                    ScoreDaily.player_id == player.id,
                    ScoreDaily.score_date == today,
                )
            )
            row = existing.scalar_one_or_none()
            if row:
                row.hobby_fit_score = hobby_fit
            else:
                db.add(ScoreDaily(
                    player_id=player.id,
                    score_date=today,
                    hobby_fit_score=hobby_fit,
                ))
            count += 1

        await db.commit()
        logger.info("Seeded hobby fit scores for %d players", count)


if __name__ == "__main__":
    asyncio.run(main())
