from __future__ import annotations

import logging
from datetime import date, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.event import PlayerEvent
from app.name_resolution.resolver import PlayerNameResolver

logger = logging.getLogger(__name__)

# Map MLB transaction type codes to our event_type values
TRANSACTION_MAP = {
    "TR": "role_change",
    "DFA": "demotion",
    "OU": "demotion",
    "IL": "il",
    "IA": "injury_return",
    "SC": "call_up",
    "FO": "role_change",
}


async def fetch_transactions(days_back: int = 7) -> list[dict]:
    """Fetch recent MLB transactions from MLB Stats API.

    Endpoint: GET /transactions?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD
    """
    end = date.today()
    start = end - timedelta(days=days_back)
    url = f"{settings.mlb_stats_api_base}/transactions"
    params = {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json().get("transactions", [])
    except Exception as e:
        logger.error("Failed to fetch transactions: %s", e)
        return []


async def ingest_transactions(db: AsyncSession, player_resolver: PlayerNameResolver) -> int:
    """Fetch transactions, map to tracked players, store as player_events.

    Returns count of new events inserted.
    Deduplicates on (player_id, event_type, event_date, source).
    """
    raw = await fetch_transactions()
    if not raw:
        return 0

    count = 0
    for txn in raw:
        try:
            type_code = txn.get("typeCode", "")
            event_type = TRANSACTION_MAP.get(type_code)
            if not event_type:
                continue

            person = txn.get("person", {})
            player_name = person.get("fullName", "")
            if not player_name:
                continue

            # Resolve player
            title_for_resolve = f"{player_name} baseball mlb card"
            result = player_resolver.resolve(title_for_resolve)
            if result is None:
                continue

            txn_date_str = txn.get("date", "")
            if not txn_date_str:
                continue
            txn_date = date.fromisoformat(txn_date_str[:10])

            description = txn.get("description", "")
            title = f"{event_type.replace('_', ' ').title()}: {player_name}"

            # Check for duplicate
            existing = await db.execute(
                select(PlayerEvent).where(
                    PlayerEvent.player_id == result.player_id,
                    PlayerEvent.event_type == event_type,
                    PlayerEvent.event_date == txn_date,
                    PlayerEvent.source == "mlb_transactions",
                )
            )
            if existing.scalar_one_or_none():
                continue

            importance = 0.8 if event_type in ("call_up", "injury_return") else 0.5

            db.add(PlayerEvent(
                player_id=result.player_id,
                event_type=event_type,
                event_date=txn_date,
                title=title,
                details=description,
                source="mlb_transactions",
                importance_score=importance,
            ))
            count += 1

        except Exception as e:
            logger.warning("Error processing transaction: %s", e)
            continue

    if count:
        await db.commit()

    logger.info("Ingested %d new transaction events", count)
    return count
