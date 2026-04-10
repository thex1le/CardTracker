"""Card market service.

Manages card price data, computes trends, detects volume spikes,
and identifies price-to-performance gaps.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from collections import defaultdict
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Player, Card, PricePoint
from app.adapters.shared.ebay_130point import search_sold_cards, extract_card_info


async def refresh_card_prices(db: AsyncSession, player_id: int) -> int:
    """Scrape latest sold data for a player's cards, store in DB. Returns count of new entries."""
    player = await db.get(Player, player_id)
    if not player:
        return 0

    listings = await search_sold_cards(player.name)
    if not listings:
        return 0

    count = 0
    for listing in listings:
        card_info = extract_card_info(listing["title"])

        # Find or create card record
        card = await _find_or_create_card(db, player_id, listing["title"], card_info)

        # Skip if we already have this price point (dedup by title + date)
        existing = await db.execute(
            select(PricePoint).where(
                PricePoint.card_id == card.id,
                PricePoint.listing_title == listing["title"],
                PricePoint.sold_date == listing.get("sold_date"),
            )
        )
        if existing.scalar_one_or_none():
            continue

        db.add(PricePoint(
            card_id=card.id,
            source="130point",
            price_cents=listing["price_cents"],
            sold_date=listing.get("sold_date"),
            listing_title=listing["title"],
            fetched_at=datetime.utcnow(),
        ))
        count += 1

    await db.commit()
    return count


async def _find_or_create_card(db: AsyncSession, player_id: int, title: str, card_info: dict) -> Card:
    """Find a matching card or create a new one based on listing info."""
    # Try to match by set + year + auto + grade
    query = select(Card).where(Card.player_id == player_id)
    if card_info.get("card_year"):
        query = query.where(Card.card_year == card_info["card_year"])
    if card_info.get("card_set"):
        query = query.where(Card.card_set == card_info["card_set"])
    if card_info.get("is_graded") and card_info.get("grade"):
        query = query.where(Card.grade == card_info["grade"])

    result = await db.execute(query.limit(1))
    card = result.scalar_one_or_none()

    if not card:
        card = Card(
            player_id=player_id,
            card_name=_build_card_name(title, card_info),
            card_year=card_info.get("card_year"),
            card_set=card_info.get("card_set"),
            card_number=card_info.get("card_number"),
            is_auto=card_info.get("is_auto", False),
            is_graded=card_info.get("is_graded", False),
            grade=card_info.get("grade"),
            created_at=datetime.utcnow(),
        )
        db.add(card)
        await db.flush()

    return card


def _build_card_name(title: str, card_info: dict) -> str:
    """Build a short card name from extracted info."""
    parts = []
    if card_info.get("card_year"):
        parts.append(str(card_info["card_year"]))
    if card_info.get("card_set"):
        parts.append(card_info["card_set"])
    if card_info.get("is_auto"):
        parts.append("Auto")
    if card_info.get("grade"):
        parts.append(card_info["grade"])
    if card_info.get("card_number"):
        parts.append(f"#{card_info['card_number']}")
    return " ".join(parts) if parts else title[:80]


async def get_price_trend(db: AsyncSession, card_id: int, days: int = 90) -> dict:
    """Calculate price trend for a card over the given period."""
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

    result = await db.execute(
        select(PricePoint)
        .where(PricePoint.card_id == card_id, PricePoint.sold_date >= cutoff)
        .order_by(PricePoint.sold_date.asc())
    )
    points = result.scalars().all()

    if not points:
        return {"card_id": card_id, "data_points": 0}

    prices = [p.price_cents for p in points]
    dates = [p.sold_date for p in points]

    # Bucket by week for sparkline
    weekly = defaultdict(list)
    for p in points:
        if p.sold_date:
            # Use the date string directly for grouping by week
            weekly[p.sold_date[:7]].append(p.price_cents)  # group by YYYY-MM

    avg_by_month = {k: sum(v) // len(v) for k, v in sorted(weekly.items())}

    # Trend calculation
    first_half = prices[:len(prices) // 2] if len(prices) > 1 else prices
    second_half = prices[len(prices) // 2:] if len(prices) > 1 else prices

    avg_first = sum(first_half) / len(first_half) if first_half else 0
    avg_second = sum(second_half) / len(second_half) if second_half else 0

    if avg_first > 0:
        trend_pct = ((avg_second - avg_first) / avg_first) * 100
    else:
        trend_pct = 0

    return {
        "card_id": card_id,
        "data_points": len(points),
        "avg_price_cents": sum(prices) // len(prices),
        "min_price_cents": min(prices),
        "max_price_cents": max(prices),
        "latest_price_cents": prices[-1],
        "trend_pct": round(trend_pct, 1),
        "trend_direction": "up" if trend_pct > 5 else "down" if trend_pct < -5 else "flat",
        "sparkline": list(avg_by_month.values()),
        "sparkline_labels": list(avg_by_month.keys()),
    }


async def detect_volume_spike(db: AsyncSession, card_id: int) -> dict | None:
    """Detect if recent sales volume is significantly above average.

    Spike = last 7 days volume > 2x the 30-day daily average.
    """
    now = datetime.utcnow()
    cutoff_30 = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    cutoff_7 = (now - timedelta(days=7)).strftime("%Y-%m-%d")

    # 30-day count
    result_30 = await db.execute(
        select(func.count()).where(
            PricePoint.card_id == card_id,
            PricePoint.sold_date >= cutoff_30,
        )
    )
    count_30 = result_30.scalar() or 0

    # 7-day count
    result_7 = await db.execute(
        select(func.count()).where(
            PricePoint.card_id == card_id,
            PricePoint.sold_date >= cutoff_7,
        )
    )
    count_7 = result_7.scalar() or 0

    if count_30 < 3:
        return None

    daily_avg_30 = count_30 / 30
    daily_avg_7 = count_7 / 7

    if daily_avg_30 > 0 and daily_avg_7 > (daily_avg_30 * 2):
        return {
            "card_id": card_id,
            "volume_7d": count_7,
            "volume_30d": count_30,
            "daily_avg_7d": round(daily_avg_7, 2),
            "daily_avg_30d": round(daily_avg_30, 2),
            "spike_ratio": round(daily_avg_7 / daily_avg_30, 1),
        }

    return None


async def get_player_market_summary(db: AsyncSession, player_id: int) -> dict:
    """Get full market summary for a player: all cards, trends, spikes."""
    result = await db.execute(
        select(Card).where(Card.player_id == player_id).order_by(Card.card_year.desc())
    )
    cards = result.scalars().all()

    if not cards:
        return {"player_id": player_id, "cards": [], "has_data": False}

    card_summaries = []
    for card in cards:
        trend = await get_price_trend(db, card.id)
        spike = await detect_volume_spike(db, card.id)

        card_summaries.append({
            "id": card.id,
            "name": card.card_name,
            "year": card.card_year,
            "set": card.card_set,
            "is_auto": card.is_auto,
            "is_graded": card.is_graded,
            "grade": card.grade,
            "trend": trend,
            "volume_spike": spike,
        })

    return {
        "player_id": player_id,
        "cards": card_summaries,
        "has_data": True,
        "total_cards": len(cards),
    }


async def compute_price_performance_gap(
    db: AsyncSession, player_id: int, performance_score: float
) -> dict | None:
    """Compare player's performance trend to card price trend.

    A positive gap means performance is outpacing price (buy signal).
    A negative gap means price is outpacing performance (overpriced).
    """
    result = await db.execute(
        select(Card).where(Card.player_id == player_id).limit(5)
    )
    cards = result.scalars().all()
    if not cards:
        return None

    # Get average price trend across all cards
    trend_pcts = []
    for card in cards:
        trend = await get_price_trend(db, card.id, days=30)
        if trend.get("data_points", 0) >= 2:
            trend_pcts.append(trend["trend_pct"])

    if not trend_pcts:
        return None

    avg_price_trend = sum(trend_pcts) / len(trend_pcts)

    # Normalize performance score to a rough % scale
    # (OPS of 0.800 or pitcher score of 7.0 = "good" baseline)
    perf_normalized = performance_score * 100 if performance_score < 2 else performance_score * 10

    gap = perf_normalized - avg_price_trend

    return {
        "player_id": player_id,
        "performance_score": performance_score,
        "avg_price_trend_pct": round(avg_price_trend, 1),
        "gap": round(gap, 1),
        "signal": "underpriced" if gap > 10 else "overpriced" if gap < -10 else "fair",
    }
