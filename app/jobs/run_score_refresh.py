from __future__ import annotations

import logging

from sqlalchemy import select

from app.core.db import AsyncSessionLocal
from app.models.player import Player
from app.services.score_service import refresh_scores_for_player

logger = logging.getLogger(__name__)


async def run_score_refresh() -> None:
    """Compute and store scores for all active players."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Player).where(Player.active.is_(True)))
        players = result.scalars().all()

        scored = 0
        for i, player in enumerate(players):
            try:
                score = await refresh_scores_for_player(db, player)
                if score and score.opportunity_score > 0:
                    scored += 1
            except Exception as e:
                logger.warning("Score refresh failed for %s: %s", player.name, e)

        logger.info("Score refresh complete: %d/%d players with non-zero scores", scored, len(players))
