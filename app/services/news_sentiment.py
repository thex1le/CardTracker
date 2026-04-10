"""News sentiment service.

Aggregates player news from multiple sources, scores sentiment using
keyword analysis, and assigns RED/YELLOW/GREEN alert tiers.
"""
from __future__ import annotations

from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Player, SentimentEvent
from app.adapters.shared import espn, newsapi

# --- Keyword dictionaries for sentiment scoring ---

RED_FLAG_KEYWORDS = {
    "arrested", "arrest", "ped", "suspension", "suspended", "domestic violence",
    "dui", "felony", "charged", "indicted", "banned", "torn ucl", "tommy john",
    "season-ending", "career-ending", "acl tear",
}

NEGATIVE_KEYWORDS = {
    "injured", "injury", "il", "disabled list", "surgery", "setback",
    "demotion", "demoted", "optioned", "dfa", "designated for assignment",
    "struggling", "slump", "rehab", "fracture", "strain", "sprain",
    "concussion", "hamstring", "oblique", "shoulder", "elbow",
}

POSITIVE_KEYWORDS = {
    "promoted", "called up", "callup", "call-up", "debut", "breakout",
    "all-star", "all star", "award", "mvp", "cy young", "rookie of the year",
    "silver slugger", "gold glove", "no-hitter", "no hitter", "walk-off",
    "homer", "grand slam", "dominant", "extension", "contract",
    "prospect", "top prospect", "elite", "milestone",
}

TRANSACTION_POSITIVE = {"selected", "recalled", "activated", "signed"}
TRANSACTION_NEGATIVE = {"designated", "optioned", "placed on", "released", "outrighted"}


def score_sentiment(text: str) -> tuple[float, str, str]:
    """Score text sentiment and assign alert tier.

    Returns: (score: -1.0 to 1.0, sentiment: str, alert_tier: str|None)
    """
    text_lower = text.lower()

    # Check for red flags first — override everything
    for keyword in RED_FLAG_KEYWORDS:
        if keyword in text_lower:
            return -1.0, "negative", "RED"

    pos_count = sum(1 for kw in POSITIVE_KEYWORDS if kw in text_lower)
    neg_count = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text_lower)
    total = pos_count + neg_count

    if total == 0:
        return 0.0, "neutral", None

    score = (pos_count - neg_count) / total
    # Clamp to [-1, 1]
    score = max(-1.0, min(1.0, score))

    if score <= -0.3:
        return score, "negative", "YELLOW"
    elif score >= 0.3:
        return score, "positive", "GREEN"
    else:
        return score, "neutral", None


def categorize_event(text: str, source: str) -> str:
    """Categorize a news event."""
    text_lower = text.lower()

    if source == "mlb_transactions":
        if any(kw in text_lower for kw in ["placed on", "injured", "il"]):
            return "injury"
        if any(kw in text_lower for kw in ["selected", "recalled", "called up"]):
            return "promotion"
        return "transaction"

    if any(kw in text_lower for kw in ["injured", "injury", "il", "surgery", "rehab"]):
        return "injury"
    if any(kw in text_lower for kw in ["arrested", "suspended", "ped", "dui", "charged"]):
        return "off_field"
    if any(kw in text_lower for kw in ["promoted", "called up", "debut", "callup"]):
        return "promotion"
    if any(kw in text_lower for kw in ["homer", "no-hitter", "breakout", "all-star", "award"]):
        return "performance"

    return "general"


async def refresh_news(db: AsyncSession) -> int:
    """Fetch news from all sources and store sentiment events. Returns count of new events."""
    count = 0

    # Get tracked player names
    result = await db.execute(
        select(Player).where(Player.sport == "baseball")
    )
    players = result.scalars().all()
    player_map = {p.name: p for p in players}
    player_names = list(player_map.keys())

    # 1. ESPN general MLB news — match against our players
    espn_news = await espn.get_mlb_news(limit=50)
    for article in espn_news:
        text = f"{article['title']} {article.get('description', '')}"
        matched = _match_players(text, player_names)
        for name in matched:
            player = player_map[name]
            added = await _store_event(
                db, player.id, "espn", article["title"],
                article.get("description"), article.get("url"),
                article.get("published_at"), text,
            )
            if added:
                count += 1

    # 2. ESPN injuries — match against our players
    injuries = await espn.get_mlb_injuries()
    for inj in injuries:
        name = inj["player_name"]
        if name in player_map:
            player = player_map[name]
            text = f"{name} {inj['status']} - {inj['injury_type']} {inj['detail']}"
            added = await _store_event(
                db, player.id, "espn_injury", text,
                inj.get("detail"), None,
                inj.get("date"), text,
            )
            if added:
                count += 1

    # 3. MLB transactions — match against our players
    transactions = await espn.get_mlb_transactions(limit=100)
    for txn in transactions:
        name = txn["player_name"]
        if name in player_map:
            player = player_map[name]
            text = txn.get("description", "")
            added = await _store_event(
                db, player.id, "mlb_transactions",
                f"{txn['type']}: {name}",
                text, None, txn.get("date"), text,
            )
            if added:
                count += 1

    # 4. NewsAPI — batch search for player names (uses API budget)
    if player_names:
        # Prioritize top-ranked players
        priority_names = player_names[:40]
        news_articles = await newsapi.search_player_news(priority_names, days_back=7)
        for article in news_articles:
            name = article["player_name"]
            if name in player_map:
                player = player_map[name]
                text = f"{article['title']} {article.get('description', '')}"
                added = await _store_event(
                    db, player.id, "newsapi", article["title"],
                    article.get("description"), article.get("url"),
                    article.get("published_at"), text,
                )
                if added:
                    count += 1

    await db.commit()
    return count


async def get_player_sentiment(db: AsyncSession, player_id: int, limit: int = 20) -> dict:
    """Get sentiment summary and recent events for a player."""
    result = await db.execute(
        select(SentimentEvent)
        .where(SentimentEvent.player_id == player_id)
        .order_by(SentimentEvent.published_at.desc())
        .limit(limit)
    )
    events = result.scalars().all()

    if not events:
        return {"player_id": player_id, "events": [], "summary": {"avg_score": 0, "alert": None}}

    scores = [e.sentiment_score for e in events if e.sentiment_score is not None]
    avg_score = sum(scores) / len(scores) if scores else 0

    # Highest active alert
    alerts = [e.alert_tier for e in events if e.alert_tier]
    top_alert = None
    if "RED" in alerts:
        top_alert = "RED"
    elif "YELLOW" in alerts:
        top_alert = "YELLOW"
    elif "GREEN" in alerts:
        top_alert = "GREEN"

    return {
        "player_id": player_id,
        "events": [
            {
                "id": e.id,
                "headline": e.headline,
                "summary": e.summary,
                "url": e.url,
                "source": e.source,
                "sentiment": e.sentiment,
                "sentiment_score": e.sentiment_score,
                "alert_tier": e.alert_tier,
                "category": e.category,
                "published_at": e.published_at.isoformat() if e.published_at else None,
            }
            for e in events
        ],
        "summary": {
            "avg_score": round(avg_score, 3),
            "alert": top_alert,
            "total_events": len(events),
            "positive": sum(1 for e in events if e.sentiment == "positive"),
            "negative": sum(1 for e in events if e.sentiment == "negative"),
            "neutral": sum(1 for e in events if e.sentiment == "neutral"),
        },
    }


async def get_active_alerts(db: AsyncSession) -> list[dict]:
    """Get all active RED and YELLOW alerts across all players."""
    result = await db.execute(
        select(SentimentEvent)
        .where(SentimentEvent.alert_tier.in_(["RED", "YELLOW"]))
        .order_by(SentimentEvent.published_at.desc())
        .limit(50)
    )
    events = result.scalars().all()

    out = []
    for e in events:
        player = await db.get(Player, e.player_id)
        out.append({
            "id": e.id,
            "player_id": e.player_id,
            "player_name": player.name if player else "Unknown",
            "player_team": player.team if player else "",
            "headline": e.headline,
            "alert_tier": e.alert_tier,
            "sentiment_score": e.sentiment_score,
            "category": e.category,
            "source": e.source,
            "published_at": e.published_at.isoformat() if e.published_at else None,
        })

    return out


# --- Helpers ---

async def _store_event(
    db: AsyncSession, player_id: int, source: str,
    headline: str, summary: str, url: str,
    published_at: str, full_text: str,
) -> bool:
    """Score and store a sentiment event. Returns True if new event was added."""
    # Dedup: skip if we already have this exact headline for this player
    existing = await db.execute(
        select(SentimentEvent).where(
            SentimentEvent.player_id == player_id,
            SentimentEvent.headline == headline,
        ).limit(1)
    )
    if existing.scalar_one_or_none():
        return False

    score, sentiment, alert_tier = score_sentiment(full_text)
    category = categorize_event(full_text, source)

    # Parse date
    pub_dt = None
    if published_at:
        try:
            pub_dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pub_dt = datetime.utcnow()

    db.add(SentimentEvent(
        player_id=player_id,
        source=source,
        headline=headline,
        summary=summary,
        url=url,
        sentiment=sentiment,
        sentiment_score=score,
        alert_tier=alert_tier,
        category=category,
        published_at=pub_dt or datetime.utcnow(),
        fetched_at=datetime.utcnow(),
    ))
    return True


def _match_players(text: str, player_names: list[str]) -> list[str]:
    """Find which tracked players are mentioned in a text."""
    text_lower = text.lower()
    matched = []
    for name in player_names:
        parts = name.lower().split()
        last_name = parts[-1] if parts else ""
        if last_name and len(last_name) > 2 and last_name in text_lower:
            matched.append(name)
    return matched
