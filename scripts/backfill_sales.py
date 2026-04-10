"""Backfill sold listings for all active players.

Usage: python scripts/backfill_sales.py [--limit N] [--days-back D]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

sys.path.insert(0, ".")

from sqlalchemy import select

from app.core.db import AsyncSessionLocal, Base, engine
from app.ingestion.market.sold_listings import ingest_sold_listings
from app.jobs.run_daily_ingest import _build_resolver
from app.models.player import Player

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main(limit: int | None = None, days_back: int = 30) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        resolver = await _build_resolver(db)

        result = await db.execute(select(Player).where(Player.active.is_(True)))
        players = result.scalars().all()
        if limit:
            players = players[:limit]

        for i, player in enumerate(players):
            logger.info("Backfilling %d/%d: %s", i + 1, len(players), player.name)
            try:
                count = await ingest_sold_listings(db, player, resolver)
                logger.info("  -> %d sales", count)
            except Exception as e:
                logger.warning("  -> failed: %s", e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--days-back", type=int, default=30)
    args = parser.parse_args()
    asyncio.run(main(limit=args.limit, days_back=args.days_back))
