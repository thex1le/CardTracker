"""Celery tasks for news and sentiment refresh."""
import asyncio

from app.tasks.celery_app import celery
from app.database import async_session
from app.services import news_sentiment


@celery.task(name="app.tasks.news_tasks.refresh_news_task")
def refresh_news_task():
    """Background task to refresh news from all sources."""

    async def _run():
        async with async_session() as db:
            return await news_sentiment.refresh_news(db)

    count = asyncio.run(_run())
    return {"status": "ok", "new_events": count}
