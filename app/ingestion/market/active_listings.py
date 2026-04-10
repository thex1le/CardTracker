from __future__ import annotations

import logging
from datetime import date, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.market_listing_snapshot import MarketListingSnapshot
from app.models.player import Player
from app.name_resolution.resolver import PlayerNameResolver

logger = logging.getLogger(__name__)

EBAY_FINDING_URL = "https://svcs.ebay.com/services/search/FindingService/v1"


async def search_ebay_active(query: str, max_results: int = 100) -> list[dict]:
    """Query eBay Finding API for active (current) listings.

    Uses findItemsByKeywords operation.
    """
    if not settings.ebay_app_id:
        logger.warning("EBAY_APP_ID not configured — skipping eBay search")
        return []

    params = {
        "OPERATION-NAME": "findItemsByKeywords",
        "SERVICE-VERSION": "1.13.0",
        "SECURITY-APPNAME": settings.ebay_app_id,
        "RESPONSE-DATA-FORMAT": "JSON",
        "REST-PAYLOAD": "",
        "keywords": query,
        "categoryId": "213",  # Baseball Cards
        "paginationInput.entriesPerPage": str(min(max_results, 100)),
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(EBAY_FINDING_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        response_key = "findItemsByKeywordsResponse"
        items_container = data.get(response_key, [{}])[0]
        search_result = items_container.get("searchResult", [{}])[0]
        items = search_result.get("item", [])
        return items

    except Exception as e:
        logger.error("eBay active search failed for '%s': %s", query, e)
        return []


async def snapshot_active_listings(
    db: AsyncSession,
    player: Player,
    resolver: PlayerNameResolver,
) -> None:
    """Search active listings for player, count totals, upsert snapshot."""
    query = f"{player.name} baseball card"
    items = await search_ebay_active(query)

    total = 0
    auctions = 0
    bins = 0

    for item in items:
        title = item.get("title", [None])[0]
        if not title:
            continue
        result = resolver.resolve(title)
        if result and result.player_id == player.id:
            total += 1
            listing_type = item.get("listingInfo", [{}])[0].get("listingType", [None])[0]
            if listing_type == "Auction":
                auctions += 1
            else:
                bins += 1

    today = date.today()

    # Get yesterday's snapshot for delta
    yesterday = today - timedelta(days=1)
    result = await db.execute(
        select(MarketListingSnapshot).where(
            MarketListingSnapshot.player_id == player.id,
            MarketListingSnapshot.snapshot_date == yesterday,
        )
    )
    prev = result.scalar_one_or_none()
    new_count = max(0, total - (prev.active_listing_count if prev else 0))

    # Upsert today's snapshot
    result = await db.execute(
        select(MarketListingSnapshot).where(
            MarketListingSnapshot.player_id == player.id,
            MarketListingSnapshot.snapshot_date == today,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.active_listing_count = total
        existing.new_listing_count_1d = new_count
        existing.auction_count = auctions
        existing.bin_count = bins
    else:
        db.add(MarketListingSnapshot(
            player_id=player.id,
            snapshot_date=today,
            active_listing_count=total,
            new_listing_count_1d=new_count,
            auction_count=auctions,
            bin_count=bins,
        ))

    await db.commit()
    logger.info("Snapshot for %s: %d active (%d auction, %d BIN)", player.name, total, auctions, bins)
