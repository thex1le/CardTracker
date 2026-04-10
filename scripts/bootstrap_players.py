"""CLI script to seed the player universe from MLB active rosters.

Usage: python scripts/bootstrap_players.py [--limit N]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

import httpx

# Ensure project root is on path
sys.path.insert(0, ".")

from app.core.config import settings
from app.core.db import AsyncSessionLocal, Base, engine
from app.models.player import Player
from app.name_resolution.normalizer import normalize_name
from app.name_resolution.variants import PlayerSearchVariant, generate_typo_variants

from sqlalchemy import select

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
logger = logging.getLogger(__name__)

MLB_API = settings.mlb_stats_api_base

LARGE_MARKET = {"NYY", "LAD", "BOS", "CHC", "SF", "NYM", "HOU", "ATL", "PHI"}
SMALL_MARKET = {"OAK", "MIA", "PIT", "KC"}


def market_tier(abbrev: str) -> str:
    if abbrev in LARGE_MARKET:
        return "large"
    if abbrev in SMALL_MARKET:
        return "small"
    return "medium"


async def fetch_teams(client: httpx.AsyncClient) -> list[dict]:
    resp = await client.get(f"{MLB_API}/teams", params={"sportId": 1})
    resp.raise_for_status()
    return resp.json().get("teams", [])


async def fetch_roster(client: httpx.AsyncClient, team_id: int) -> list[dict]:
    try:
        resp = await client.get(
            f"{MLB_API}/teams/{team_id}/roster",
            params={"rosterType": "active"},
        )
        resp.raise_for_status()
        return resp.json().get("roster", [])
    except Exception as e:
        logger.warning("Failed to fetch roster for team %s: %s", team_id, e)
        return []


async def main(limit: int | None = None) -> None:
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with httpx.AsyncClient(timeout=15) as client:
        teams = await fetch_teams(client)
        logger.info("Found %d MLB teams", len(teams))

        all_players: list[dict] = []
        for team in teams:
            team_id = team["id"]
            abbrev = team.get("abbreviation", "")
            team_name = team.get("name", "")
            tier = market_tier(abbrev)

            roster = await fetch_roster(client, team_id)
            for entry in roster:
                person = entry.get("person", {})
                pos = entry.get("position", {}).get("abbreviation", "")
                all_players.append({
                    "mlb_id": str(person.get("id", "")),
                    "name": person.get("fullName", ""),
                    "team": abbrev,
                    "team_name": team_name,
                    "position": pos,
                    "tier": tier,
                })

        logger.info("Fetched %d total players from rosters", len(all_players))

    if limit:
        all_players = all_players[:limit]

    inserted = 0
    updated = 0

    async with AsyncSessionLocal() as db:
        for p in all_players:
            if not p["name"]:
                continue

            norm = normalize_name(p["name"])

            result = await db.execute(
                select(Player).where(Player.name_normalized == norm)
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.team = p["team"]
                existing.position = p["position"]
                existing.market_size_tier = p["tier"]
                existing.active = True
                updated += 1
                player_id = existing.id
            else:
                player = Player(
                    name=p["name"],
                    name_normalized=norm,
                    team=p["team"],
                    position=p["position"],
                    market_size_tier=p["tier"],
                    active=True,
                )
                db.add(player)
                await db.flush()
                player_id = player.id
                inserted += 1

            # Generate and store typo variants
            # First remove old variants
            from sqlalchemy import delete
            await db.execute(
                delete(PlayerSearchVariant).where(PlayerSearchVariant.player_id == player_id)
            )

            variants = generate_typo_variants(p["name"])
            for v in variants:
                # Determine variant type
                if " " in v and v.split()[0] in norm.split()[-1:]:
                    vtype = "transposition"
                elif any(c in v for c in "."):
                    vtype = "initial_style"
                else:
                    vtype = "typo"

                db.add(PlayerSearchVariant(
                    player_id=player_id,
                    variant=v,
                    variant_type=vtype,
                ))

        await db.commit()

    logger.info("Done: %d inserted, %d updated", inserted, updated)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bootstrap player universe from MLB rosters")
    parser.add_argument("--limit", type=int, default=None, help="Max players to seed")
    args = parser.parse_args()
    asyncio.run(main(limit=args.limit))
