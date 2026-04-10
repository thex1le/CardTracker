from __future__ import annotations

import logging
import re
from datetime import date, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.market_sale import MarketSale
from app.models.player import Player
from app.name_resolution.resolver import PlayerNameResolver, ResolveResult
from app.name_resolution.variants import generate_typo_variants

logger = logging.getLogger(__name__)

EBAY_FINDING_URL = "https://svcs.ebay.com/services/search/FindingService/v1"


async def search_ebay_sold(
    query: str,
    days_back: int = 14,
    max_results: int = 100,
) -> list[dict]:
    """Query eBay Finding API for completed (sold) listings.

    Uses findCompletedItems operation.
    Filter: listingType = Auction or FixedPrice.
    Filter: soldItemsOnly = true.
    """
    if not settings.ebay_app_id:
        logger.warning("EBAY_APP_ID not configured — skipping eBay search")
        return []

    end_time = date.today()
    start_time = end_time - timedelta(days=days_back)

    params = {
        "OPERATION-NAME": "findCompletedItems",
        "SERVICE-VERSION": "1.13.0",
        "SECURITY-APPNAME": settings.ebay_app_id,
        "RESPONSE-DATA-FORMAT": "JSON",
        "REST-PAYLOAD": "",
        "keywords": query,
        "categoryId": "213",  # Baseball Cards
        "itemFilter(0).name": "SoldItemsOnly",
        "itemFilter(0).value": "true",
        "itemFilter(1).name": "EndTimeFrom",
        "itemFilter(1).value": f"{start_time.isoformat()}T00:00:00.000Z",
        "itemFilter(2).name": "EndTimeTo",
        "itemFilter(2).value": f"{end_time.isoformat()}T23:59:59.000Z",
        "paginationInput.entriesPerPage": str(min(max_results, 100)),
        "sortOrder": "EndTimeSoonest",
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(EBAY_FINDING_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        response_key = "findCompletedItemsResponse"
        items_container = data.get(response_key, [{}])[0]
        search_result = items_container.get("searchResult", [{}])[0]
        items = search_result.get("item", [])
        return items

    except Exception as e:
        logger.error("eBay search failed for '%s': %s", query, e)
        return []


async def ingest_sold_listings(
    db: AsyncSession,
    player: Player,
    resolver: PlayerNameResolver,
    include_typo_variants: bool = True,
) -> int:
    """For a player, search eBay sold listings by name and typo variants.

    Returns count of new rows inserted.
    """
    queries = [player.name]

    if include_typo_variants:
        variants = generate_typo_variants(player.name)
        queries.extend(variants)

    count = 0
    for query in queries:
        search_query = f"{query} baseball card"
        raw_items = await search_ebay_sold(search_query)

        for item in raw_items:
            try:
                title = item.get("title", [None])[0]
                if not title:
                    continue

                item_id = item.get("itemId", [None])[0]

                # Deduplicate by source_item_id
                if item_id:
                    existing = await db.execute(
                        select(MarketSale).where(
                            MarketSale.source == "ebay",
                            MarketSale.source_item_id == item_id,
                        )
                    )
                    if existing.scalar_one_or_none():
                        continue

                # Resolve player from title
                resolve_result = resolver.resolve(title)
                if resolve_result is None or resolve_result.player_id != player.id:
                    continue

                sale = parse_listing_to_sale(item, player.id, resolve_result)
                if sale:
                    db.add(MarketSale(**sale))
                    count += 1

            except Exception as e:
                logger.warning("Error processing eBay item: %s", e)
                continue

    if count:
        await db.commit()

    logger.info("Ingested %d sold listings for %s", count, player.name)
    return count


def parse_listing_to_sale(raw: dict, player_id: int, resolve_result: ResolveResult) -> dict | None:
    """Extract sale data from raw eBay listing dict."""
    try:
        title = raw.get("title", [None])[0]
        if not title:
            return None

        # Price
        selling_status = raw.get("sellingStatus", [{}])[0]
        price_info = selling_status.get("currentPrice", [{}])[0]
        price = float(price_info.get("__value__", 0))

        # Date
        end_time = raw.get("listingInfo", [{}])[0].get("endTime", [None])[0]
        if end_time:
            sale_date = date.fromisoformat(end_time[:10])
        else:
            sale_date = date.today()

        # Listing type
        listing_type_raw = raw.get("listingInfo", [{}])[0].get("listingType", [None])[0]
        listing_type = "auction" if listing_type_raw == "Auction" else "buy_it_now"

        item_id = raw.get("itemId", [None])[0]

        return {
            "player_id": player_id,
            "card_title": title,
            "card_type": parse_card_type(title),
            "grader": parse_grader_grade(title)[0],
            "grade": parse_grader_grade(title)[1],
            "sale_price": price,
            "sale_date": sale_date,
            "listing_type": listing_type,
            "source": "ebay",
            "source_item_id": item_id,
            "player_match_method": resolve_result.match_method,
            "player_match_score": resolve_result.match_score,
            "raw_title_player_str": resolve_result.matched_text,
        }

    except Exception as e:
        logger.warning("Failed to parse listing: %s", e)
        return None


def parse_card_type(title: str) -> str | None:
    """Detect card type from title keywords."""
    t = title.lower()
    if "auto" in t or "/a" in t:
        return "auto"
    if "rc" in t.split() or "rookie" in t:
        return "rookie"
    if "refractor" in t or "chrome" in t:
        return "refractor"
    if re.search(r"#?/\d{1,2}\b", t):
        return "numbered"
    return "base"


def parse_grader_grade(title: str) -> tuple[str | None, str | None]:
    """Extract grader and grade from title.

    Patterns: 'PSA 10', 'BGS 9.5', 'SGC 10', 'PSA10', 'BGS9'
    """
    match = re.search(r"\b(PSA|BGS|SGC)\s*(\d+\.?\d*)\b", title, re.IGNORECASE)
    if match:
        return match.group(1).upper(), match.group(2)
    return None, None
