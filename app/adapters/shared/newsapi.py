"""NewsAPI adapter for player news.

Free tier: 100 requests/day. Strategy: batch player names into OR queries
(up to 5 names per query) to maximize coverage within the budget.
"""
from __future__ import annotations

import httpx
from datetime import datetime, timedelta
from app.config import settings

NEWSAPI_URL = "https://newsapi.org/v2/everything"
NEWSAPI_KEY = getattr(settings, "newsapi_key", "")


async def search_player_news(
    player_names: list[str],
    days_back: int = 7,
) -> list[dict]:
    """Search NewsAPI for articles mentioning any of the given player names.

    Batches names into OR queries to conserve API budget.
    Returns list of dicts with: title, description, url, source, published_at, matched_query
    """
    if not NEWSAPI_KEY:
        return []

    from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    results = []

    # Batch into groups of 5 names per query
    for i in range(0, len(player_names), 5):
        batch = player_names[i:i + 5]
        # Build OR query: "name1" OR "name2" OR ...
        query = " OR ".join(f'"{name}"' for name in batch)

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    NEWSAPI_URL,
                    params={
                        "q": query,
                        "from": from_date,
                        "language": "en",
                        "sortBy": "publishedAt",
                        "pageSize": 50,
                        "apiKey": NEWSAPI_KEY,
                    },
                )
                if resp.status_code == 426:
                    # Free tier doesn't support some features
                    continue
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            print(f"NewsAPI error: {e}")
            continue

        articles = data.get("articles", [])
        for article in articles:
            # Determine which player(s) this article matches
            title = article.get("title", "") or ""
            desc = article.get("description", "") or ""
            text = f"{title} {desc}".lower()

            for name in batch:
                # Check if player name appears in title or description
                name_parts = name.lower().split()
                last_name = name_parts[-1] if name_parts else ""
                if last_name and last_name in text:
                    results.append({
                        "player_name": name,
                        "title": title,
                        "description": desc,
                        "url": article.get("url", ""),
                        "source": article.get("source", {}).get("name", ""),
                        "published_at": article.get("publishedAt", ""),
                    })
                    break  # Don't double-count

    return results


async def search_single_player(player_name: str, days_back: int = 14) -> list[dict]:
    """Search news for a single player. Uses 1 API request."""
    return await search_player_news([player_name], days_back)
