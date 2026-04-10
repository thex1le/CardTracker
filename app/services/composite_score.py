"""Composite investment score engine.

Combines all data pipelines into a single 0-100 score per player:
  - Performance (30%): stats-based scoring
  - Prospect momentum (20%): ranking changes + FV
  - Card price (20%): price trend direction
  - Sentiment (15%): average sentiment score
  - Availability (15%): injury/IL status
"""
from __future__ import annotations

from datetime import datetime, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import (
    Player, ProspectRanking, Signal, Card, PricePoint,
    SentimentEvent, CompositeScore,
)
from app.models.baseball import PlayerStatsBaseball
from app.adapters.baseball.scoring import compute_score as compute_perf_score
from app.adapters.baseball.mlb_stats import is_pitcher, SEASONS

# Weights
W_PERFORMANCE = 0.30
W_MOMENTUM = 0.20
W_CARD_PRICE = 0.20
W_SENTIMENT = 0.15
W_AVAILABILITY = 0.15


async def compute_all_scores(db: AsyncSession) -> list[dict]:
    """Compute composite scores for all tracked players."""
    result = await db.execute(
        select(Player).where(Player.sport == "baseball")
    )
    players = result.scalars().all()

    # First pass: compute raw sub-scores for percentile normalization
    raw_scores = []
    for player in players:
        raw = await _compute_raw_subscores(db, player)
        raw["player"] = player
        raw_scores.append(raw)

    # Normalize each sub-score to 0-100 via percentile ranking
    for key in ["performance", "momentum", "card_price", "sentiment", "availability"]:
        values = sorted(set(r[key] for r in raw_scores))
        if len(values) <= 1:
            for r in raw_scores:
                r[f"{key}_norm"] = 50.0
        else:
            for r in raw_scores:
                rank = values.index(r[key])
                r[f"{key}_norm"] = (rank / (len(values) - 1)) * 100

    # Compute weighted composite
    results = []
    for r in raw_scores:
        perf = r["performance_norm"]
        mom = r["momentum_norm"]
        card = r["card_price_norm"]
        sent = r["sentiment_norm"]
        avail = r["availability_norm"]

        composite = (
            perf * W_PERFORMANCE +
            mom * W_MOMENTUM +
            card * W_CARD_PRICE +
            sent * W_SENTIMENT +
            avail * W_AVAILABILITY
        )

        player = r["player"]

        # Store in DB
        db.add(CompositeScore(
            player_id=player.id,
            score=round(composite, 1),
            performance_sub=round(perf, 1),
            momentum_sub=round(mom, 1),
            card_price_sub=round(card, 1),
            sentiment_sub=round(sent, 1),
            availability_sub=round(avail, 1),
            computed_at=datetime.utcnow(),
        ))

        results.append({
            "player_id": player.id,
            "player_name": player.name,
            "team": player.team,
            "position": player.position,
            "score": round(composite, 1),
            "breakdown": {
                "performance": round(perf, 1),
                "momentum": round(mom, 1),
                "card_price": round(card, 1),
                "sentiment": round(sent, 1),
                "availability": round(avail, 1),
            },
        })

    await db.commit()

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


async def get_player_score(db: AsyncSession, player_id: int) -> dict:
    """Get the latest composite score for a single player."""
    result = await db.execute(
        select(CompositeScore)
        .where(CompositeScore.player_id == player_id)
        .order_by(CompositeScore.computed_at.desc())
        .limit(1)
    )
    score = result.scalar_one_or_none()

    player = await db.get(Player, player_id)

    if not score:
        return {
            "player_id": player_id,
            "player_name": player.name if player else "Unknown",
            "score": None,
            "message": "No score computed yet. Run /api/scores/compute first.",
        }

    return {
        "player_id": player_id,
        "player_name": player.name if player else "Unknown",
        "score": score.score,
        "breakdown": {
            "performance": score.performance_sub,
            "momentum": score.momentum_sub,
            "card_price": score.card_price_sub,
            "sentiment": score.sentiment_sub,
            "availability": score.availability_sub,
        },
        "computed_at": score.computed_at.isoformat() if score.computed_at else None,
    }


async def get_score_movers(db: AsyncSession, days: int = 7) -> list[dict]:
    """Find players with the biggest score changes over the given period."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    result = await db.execute(
        select(Player).where(Player.sport == "baseball")
    )
    players = result.scalars().all()

    movers = []
    for player in players:
        # Get latest score
        latest_result = await db.execute(
            select(CompositeScore)
            .where(CompositeScore.player_id == player.id)
            .order_by(CompositeScore.computed_at.desc())
            .limit(1)
        )
        latest = latest_result.scalar_one_or_none()

        # Get score from ~N days ago
        prev_result = await db.execute(
            select(CompositeScore)
            .where(
                CompositeScore.player_id == player.id,
                CompositeScore.computed_at <= cutoff,
            )
            .order_by(CompositeScore.computed_at.desc())
            .limit(1)
        )
        prev = prev_result.scalar_one_or_none()

        if latest and prev:
            delta = latest.score - prev.score
            if abs(delta) >= 1.0:
                movers.append({
                    "player_id": player.id,
                    "player_name": player.name,
                    "team": player.team,
                    "current_score": latest.score,
                    "previous_score": prev.score,
                    "delta": round(delta, 1),
                    "direction": "up" if delta > 0 else "down",
                })

    movers.sort(key=lambda x: abs(x["delta"]), reverse=True)
    return movers[:20]


async def get_all_latest_scores(db: AsyncSession) -> list[dict]:
    """Get latest composite score for every player."""
    result = await db.execute(
        select(Player).where(Player.sport == "baseball")
    )
    players = result.scalars().all()

    scores = []
    for player in players:
        score_result = await db.execute(
            select(CompositeScore)
            .where(CompositeScore.player_id == player.id)
            .order_by(CompositeScore.computed_at.desc())
            .limit(1)
        )
        cs = score_result.scalar_one_or_none()

        scores.append({
            "player_id": player.id,
            "player_name": player.name,
            "team": player.team,
            "position": player.position,
            "score": cs.score if cs else None,
            "breakdown": {
                "performance": cs.performance_sub if cs else None,
                "momentum": cs.momentum_sub if cs else None,
                "card_price": cs.card_price_sub if cs else None,
                "sentiment": cs.sentiment_sub if cs else None,
                "availability": cs.availability_sub if cs else None,
            } if cs else None,
            "computed_at": cs.computed_at.isoformat() if cs and cs.computed_at else None,
        })

    scores.sort(key=lambda x: x["score"] or 0, reverse=True)
    return scores


# --- Raw sub-score computation ---

async def _compute_raw_subscores(db: AsyncSession, player: Player) -> dict:
    """Compute raw (unnormalized) sub-scores for a player."""
    return {
        "performance": await _performance_score(db, player),
        "momentum": await _momentum_score(db, player),
        "card_price": await _card_price_score(db, player),
        "sentiment": await _sentiment_score(db, player),
        "availability": await _availability_score(db, player),
    }


async def _performance_score(db: AsyncSession, player: Player) -> float:
    """Stats-based performance score. Reuses existing scoring logic."""
    is_p = is_pitcher(player.position or "")
    result = await db.execute(
        select(PlayerStatsBaseball)
        .where(PlayerStatsBaseball.player_id == player.id)
    )
    stats = result.scalars().all()

    stats_by_year = {}
    for s in stats:
        season = s.season
        if is_p:
            entry = {"ip": s.ip, "era": s.era, "so": s.p_so, "bb": s.p_bb}
        else:
            entry = {"ab": s.ab, "ops": s.ops, "hr": s.hr}
        stats_by_year.setdefault(season, []).append(entry)

    return compute_perf_score(stats_by_year, is_p)


async def _momentum_score(db: AsyncSession, player: Player) -> float:
    """Prospect ranking momentum. Higher = climbing lists."""
    result = await db.execute(
        select(ProspectRanking)
        .where(ProspectRanking.player_id == player.id)
        .order_by(ProspectRanking.fetched_at.desc())
        .limit(5)
    )
    rankings = result.scalars().all()

    if not rankings:
        return 0.0

    latest_rank = rankings[0].rank or 100
    # Base score: inverse of rank (rank 1 = 100, rank 100 = 1)
    rank_score = max(0, 101 - latest_rank)

    # Bonus for rank improvement
    if len(rankings) >= 2:
        prev_rank = rankings[1].rank or 100
        improvement = prev_rank - latest_rank
        rank_score += improvement * 2  # +2 points per rank climbed

    # FV bonus
    try:
        fv = int(rankings[0].fv) if rankings[0].fv else 0
    except ValueError:
        fv = 0
    rank_score += fv * 0.5  # FV 60 adds 30 pts, FV 70 adds 35

    return max(0, rank_score)


async def _card_price_score(db: AsyncSession, player: Player) -> float:
    """Card market trend score. Positive trend = higher score."""
    result = await db.execute(
        select(Card).where(Card.player_id == player.id)
    )
    cards = result.scalars().all()

    if not cards:
        return 50.0  # Neutral if no card data

    cutoff_30 = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
    cutoff_60 = (datetime.utcnow() - timedelta(days=60)).strftime("%Y-%m-%d")

    trends = []
    for card in cards:
        # Recent prices
        recent = await db.execute(
            select(func.avg(PricePoint.price_cents))
            .where(PricePoint.card_id == card.id, PricePoint.sold_date >= cutoff_30)
        )
        avg_recent = recent.scalar() or 0

        # Older prices
        older = await db.execute(
            select(func.avg(PricePoint.price_cents))
            .where(
                PricePoint.card_id == card.id,
                PricePoint.sold_date >= cutoff_60,
                PricePoint.sold_date < cutoff_30,
            )
        )
        avg_older = older.scalar() or 0

        if avg_older > 0:
            trend_pct = ((avg_recent - avg_older) / avg_older) * 100
            trends.append(trend_pct)

    if not trends:
        return 50.0

    avg_trend = sum(trends) / len(trends)
    # Map trend % to 0-100 scale: -50% = 0, 0% = 50, +50% = 100
    return max(0, min(100, 50 + avg_trend))


async def _sentiment_score(db: AsyncSession, player: Player) -> float:
    """Average sentiment over last 30 days, mapped to 0-100."""
    cutoff = datetime.utcnow() - timedelta(days=30)
    result = await db.execute(
        select(func.avg(SentimentEvent.sentiment_score))
        .where(
            SentimentEvent.player_id == player.id,
            SentimentEvent.published_at >= cutoff,
        )
    )
    avg = result.scalar()

    if avg is None:
        return 50.0  # Neutral if no news

    # Map [-1, 1] to [0, 100]
    return max(0, min(100, (avg + 1) * 50))


async def _availability_score(db: AsyncSession, player: Player) -> float:
    """100 = healthy, lower = injured/IL. Based on recent sentiment events."""
    # Check for injury-related sentiment events in last 14 days
    cutoff = datetime.utcnow() - timedelta(days=14)
    result = await db.execute(
        select(SentimentEvent)
        .where(
            SentimentEvent.player_id == player.id,
            SentimentEvent.category == "injury",
            SentimentEvent.published_at >= cutoff,
        )
    )
    injury_events = result.scalars().all()

    if not injury_events:
        return 100.0  # Fully healthy

    # Check severity
    has_red = any(e.alert_tier == "RED" for e in injury_events)
    has_yellow = any(e.alert_tier == "YELLOW" for e in injury_events)

    if has_red:
        return 10.0  # Season-ending type injury
    elif has_yellow:
        return 40.0  # On IL / day-to-day
    else:
        return 70.0  # Minor concern
