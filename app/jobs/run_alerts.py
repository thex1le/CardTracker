from __future__ import annotations

import logging

from app.core.db import AsyncSessionLocal
from app.services.alert_service import run_alerts as _run_alerts

logger = logging.getLogger(__name__)


async def run_alerts() -> None:
    """Generate alerts based on today's scores."""
    async with AsyncSessionLocal() as db:
        count = await _run_alerts(db)
        logger.info("Alert generation complete: %d new alerts", count)
