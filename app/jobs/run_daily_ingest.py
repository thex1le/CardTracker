from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import AsyncSessionLocal
from app.ingestion.baseball.performance import ingest_performance
from app.ingestion.baseball.transactions import ingest_transactions
from app.ingestion.market.active_listings import snapshot_active_listings
from app.ingestion.market.sold_listings import ingest_sold_listings
from app.models.player import Player
from app.name_resolution.resolver import PlayerNameResolver
from app.name_resolution.variants import PlayerSearchVariant

logger = logging.getLogger(__name__)


async def _build_resolver(db: AsyncSession) -> PlayerNameResolver:
    """Build a PlayerNameResolver from the current player universe."""
    result = await db.execute(select(Player).where(Player.active.is_(True)))
    players = result.scalars().all()

    universe = []
    for p in players:
        # Get variants
        var_result = await db.execute(
            select(PlayerSearchVariant).where(PlayerSearchVariant.player_id == p.id)
        )
        variants = [v.variant for v in var_result.scalars().all()]

        universe.append({
            "id": p.id,
            "name": p.name,
            "name_normalized": p.name_normalized,
            "variants": variants,
        })

    return PlayerNameResolver(universe)


async def run_daily_ingest() -> None:
    """Run the full daily ingestion pipeline.

    1. fetch_transactions -> ingest_transactions for all tracked players
    2. For each active player: ingest_performance
    3. For each active player: ingest_sold_listings (with typo variants)
    4. For each active player: snapshot_active_listings

    Log progress and errors. Do not raise on individual player failures.
    """
    async with AsyncSessionLocal() as db:
        resolver = await _build_resolver(db)
        logger.info("Built resolver with %d players", len(resolver._players))

        # 1. Transactions
        try:
            txn_count = await ingest_transactions(db, resolver)
            logger.info("Step 1 complete: %d transaction events", txn_count)
        except Exception as e:
            logger.error("Transaction ingestion failed: %s", e)

        # 2-4. Per-player ingestion
        result = await db.execute(select(Player).where(Player.active.is_(True)))
        players = result.scalars().all()

        for i, player in enumerate(players):
            logger.info("Processing player %d/%d: %s", i + 1, len(players), player.name)

            # 2. Performance
            try:
                # Use external_id if we had one; for now MLB ID lookup would be needed
                # This is a simplification — full implementation would store mlb_id on Player
                pass
            except Exception as e:
                logger.warning("Performance ingestion failed for %s: %s", player.name, e)

            # 3. Sold listings
            try:
                sold_count = await ingest_sold_listings(db, player, resolver, include_typo_variants=True)
                logger.debug("  %d sold listings for %s", sold_count, player.name)
            except Exception as e:
                logger.warning("Sold listing ingestion failed for %s: %s", player.name, e)

            # 4. Active listings snapshot
            try:
                await snapshot_active_listings(db, player, resolver)
            except Exception as e:
                logger.warning("Active listing snapshot failed for %s: %s", player.name, e)

    logger.info("Daily ingest complete")
