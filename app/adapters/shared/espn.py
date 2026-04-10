"""ESPN undocumented API adapter for player news and injuries.

Free, no auth required. Endpoints can change without notice.
"""
from __future__ import annotations

import httpx

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb"


async def get_mlb_news(limit: int = 50) -> list[dict]:
    """Fetch latest MLB news headlines from ESPN."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{ESPN_BASE}/news", params={"limit": limit})
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        print(f"ESPN news error: {e}")
        return []

    results = []
    for article in data.get("articles", []):
        results.append({
            "title": article.get("headline", ""),
            "description": article.get("description", ""),
            "url": article.get("links", {}).get("web", {}).get("href", ""),
            "source": "ESPN",
            "published_at": article.get("published", ""),
            "categories": [c.get("description", "") for c in article.get("categories", [])],
        })

    return results


async def get_mlb_injuries() -> list[dict]:
    """Fetch current MLB injury report from ESPN."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # ESPN injuries endpoint
            resp = await client.get(
                "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/injuries"
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        print(f"ESPN injuries error: {e}")
        return []

    injuries = []
    for team_data in data.get("injuries", []):
        team_name = team_data.get("team", {}).get("abbreviation", "")
        for item in team_data.get("injuries", []):
            athlete = item.get("athlete", {})
            injuries.append({
                "player_name": athlete.get("displayName", ""),
                "player_id": str(athlete.get("id", "")),
                "team": team_name,
                "position": athlete.get("position", {}).get("abbreviation", ""),
                "status": item.get("status", ""),
                "injury_type": item.get("type", {}).get("description", "") if isinstance(item.get("type"), dict) else str(item.get("type", "")),
                "detail": item.get("longComment", "") or item.get("shortComment", ""),
                "date": item.get("date", ""),
            })

    return injuries


async def get_mlb_transactions(limit: int = 50) -> list[dict]:
    """Fetch recent MLB transactions (callups, DFA, IL placements, etc.)."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://statsapi.mlb.com/api/v1/transactions",
                params={"startDate": _days_ago(7), "endDate": _today()},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        print(f"MLB transactions error: {e}")
        return []

    txns = []
    for t in data.get("transactions", []):
        player = t.get("person", {})
        txns.append({
            "player_name": player.get("fullName", ""),
            "player_id": str(player.get("id", "")),
            "team": t.get("toTeam", {}).get("name", "") or t.get("fromTeam", {}).get("name", ""),
            "type": t.get("typeDesc", ""),
            "description": t.get("description", ""),
            "date": t.get("date", ""),
        })

    return txns


def _today():
    from datetime import date
    return date.today().strftime("%Y-%m-%d")


def _days_ago(n):
    from datetime import date, timedelta
    return (date.today() - timedelta(days=n)).strftime("%Y-%m-%d")
