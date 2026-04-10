"""Celery tasks for card market data refresh."""
import asyncio
from sqlalchemy import select

from app.tasks.celery_app import celery
from app.database import async_session
from app.models.base import Player
from app.services import card_market


@celery.task(name="app.tasks.card_tasks.refresh_all_card_prices_task")
def refresh_all_card_prices_task():
    """Background task to refresh card prices for top prospects."""

    async def _run():
        async with async_session() as db:
            result = await db.execute(
                select(Player).where(Player.sport == "baseball").order_by(Player.id)
            )
            players = result.scalars().all()

            total = 0
            for player in players[:20]:
                count = await card_market.refresh_card_prices(db, player.id)
                total += count

            return total

    total = asyncio.run(_run())
    return {"status": "ok", "new_listings": total}
