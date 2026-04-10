from __future__ import annotations

import asyncio
import httpx
from datetime import date

MLB_API = "https://statsapi.mlb.com/api/v1"
CURRENT_YEAR = date.today().year
SEASONS = [CURRENT_YEAR - 1, CURRENT_YEAR - 2]
PITCHER_POSITIONS = {"SP", "RP", "P", "SIRP", "CL", "LHRP", "RHRP", "LHP", "RHP"}

# Semaphore to rate-limit MLB API calls
_semaphore = asyncio.Semaphore(5)


def is_pitcher(pos: str) -> bool:
    return pos in PITCHER_POSITIONS


async def search_player(client: httpx.AsyncClient, name: str) -> str | None:
    """Search MLB API for a player by name, return player ID."""
    async with _semaphore:
        try:
            resp = await client.get(
                f"{MLB_API}/people/search",
                params={"names": name, "sportIds": "1,11,12,13,14,15,16"},
                timeout=10,
            )
            data = resp.json()
            people = data.get("people", [])
            if people:
                for p in people:
                    if p.get("fullName", "").lower() == name.lower():
                        return str(p["id"])
                return str(people[0]["id"])
        except Exception:
            pass
    return None


async def fetch_player_stats(
    client: httpx.AsyncClient, player_id: str, is_p: bool, seasons: list[int] | None = None
) -> dict:
    """Fetch stats for a player across given seasons (MLB + MiLB)."""
    seasons = seasons or SEASONS
    group = "pitching" if is_p else "hitting"
    stats_by_year = {}

    for season in seasons:
        async with _semaphore:
            try:
                resp = await client.get(
                    f"{MLB_API}/people/{player_id}",
                    params={
                        "hydrate": f"stats(group=[{group}],type=[season],sportId=[1,11,12,13,14,15,16],season={season})"
                    },
                    timeout=10,
                )
                data = resp.json()
            except Exception:
                continue

        person = data.get("people", [{}])[0]
        all_stats = person.get("stats", [])

        for stat_group in all_stats:
            for split in stat_group.get("splits", []):
                if str(split.get("season")) != str(season):
                    continue
                s = split.get("stat", {})
                level = split.get("sport", {}).get("name", "Unknown")
                league = split.get("league", {}).get("name", "")

                if is_p:
                    entry = {
                        "season": season,
                        "level": level,
                        "league": league,
                        "is_pitcher": True,
                        "w": s.get("wins", 0),
                        "l": s.get("losses", 0),
                        "era": s.get("era", "-"),
                        "g": s.get("gamesPlayed", 0),
                        "gs": s.get("gamesStarted", 0),
                        "ip": s.get("inningsPitched", "0"),
                        "so": s.get("strikeOuts", 0),
                        "bb": s.get("baseOnBalls", 0),
                        "whip": s.get("whip", "-"),
                        "avg": s.get("avg", "-"),
                        "h": s.get("hits", 0),
                    }
                else:
                    entry = {
                        "season": season,
                        "level": level,
                        "league": league,
                        "is_pitcher": False,
                        "g": s.get("gamesPlayed", 0),
                        "ab": s.get("atBats", 0),
                        "h": s.get("hits", 0),
                        "hr": s.get("homeRuns", 0),
                        "rbi": s.get("rbi", 0),
                        "sb": s.get("stolenBases", 0),
                        "bb": s.get("baseOnBalls", 0),
                        "so": s.get("strikeOuts", 0),
                        "avg": s.get("avg", "-"),
                        "obp": s.get("obp", "-"),
                        "slg": s.get("slg", "-"),
                        "ops": s.get("ops", "-"),
                    }
                stats_by_year.setdefault(season, []).append(entry)

    return stats_by_year
