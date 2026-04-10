from __future__ import annotations

import asyncio
from datetime import datetime
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Player, ProspectRanking
from app.models.baseball import PlayerStatsBaseball
from app.adapters.baseball import fangraphs, mlb_stats, scoring


async def refresh_prospects(db: AsyncSession) -> list[dict]:
    """Fetch prospects from FanGraphs, store/update in DB, fetch stats, return full data."""
    prospects = await fangraphs.fetch_top_prospects(100)
    if not prospects:
        return []

    results = []
    async with httpx.AsyncClient(timeout=15) as client:
        # Process in batches of 5 to avoid SQLite contention
        for i in range(0, len(prospects), 5):
            batch = prospects[i:i + 5]
            batch_results = await asyncio.gather(
                *[_process_prospect(client, p) for p in batch],
                return_exceptions=True,
            )
            for r in batch_results:
                if isinstance(r, dict):
                    results.append(r)

    # Persist all to DB
    for r in results:
        player = await _upsert_player(db, r)
        r["db_player_id"] = player.id

        db.add(ProspectRanking(
            player_id=player.id,
            source="fangraphs",
            rank=r["bowman_rank"],
            fv=r.get("fv", ""),
            eta=r.get("eta", ""),
            fetched_at=datetime.utcnow(),
        ))

        if r.get("player_id") and not player.external_id:
            player.external_id = r["player_id"]

        if r["stats"]:
            is_p = r["is_pitcher"]
            await _store_stats(db, player.id, r["stats"], is_p)

    await db.commit()

    # Compute rank changes now that rankings are stored
    for r in results:
        r["rank_change"] = await _compute_rank_change(db, r["db_player_id"], r["bowman_rank"])

    # Sort by score descending, assign perf_rank
    results.sort(key=lambda x: x["score"], reverse=True)
    for i, r in enumerate(results):
        r["perf_rank"] = i + 1
        r.pop("db_player_id", None)

    return results


async def _process_prospect(client: httpx.AsyncClient, prospect: dict) -> dict:
    """Fetch external data for a single prospect (no DB access)."""
    is_p = mlb_stats.is_pitcher(prospect["pos"])

    # Search for MLB player ID
    ext_id = await mlb_stats.search_player(client, prospect["name"])

    # Fetch stats if we found the player
    stats_by_year = {}
    if ext_id:
        stats_by_year = await mlb_stats.fetch_player_stats(client, ext_id, is_p)

    score = scoring.compute_score(stats_by_year, is_p)

    return {
        "bowman_rank": prospect["rank"],
        "name": prospect["name"],
        "team": prospect["team"],
        "pos": prospect["pos"],
        "fv": prospect.get("fv", ""),
        "eta": prospect.get("eta", ""),
        "player_id": ext_id,
        "is_pitcher": is_p,
        "stats": stats_by_year,
        "score": score,
        "rank_change": 0,
        "perf_rank": 0,
    }


async def _upsert_player(db: AsyncSession, data: dict) -> Player:
    """Find or create a player record."""
    result = await db.execute(
        select(Player).where(
            Player.sport == "baseball",
            Player.name == data["name"],
        )
    )
    player = result.scalar_one_or_none()

    if player:
        player.team = data["team"]
        player.position = data["pos"]
        player.updated_at = datetime.utcnow()
    else:
        player = Player(
            sport="baseball",
            name=data["name"],
            team=data["team"],
            position=data["pos"],
        )
        db.add(player)
        await db.flush()

    return player


async def _store_stats(db: AsyncSession, player_id: int, stats_by_year: dict, is_p: bool):
    """Store player stats in the database."""
    for season, splits in stats_by_year.items():
        for s in splits:
            stat = PlayerStatsBaseball(
                player_id=player_id,
                season=season,
                level=s.get("level", ""),
                league=s.get("league", ""),
                is_pitcher=is_p,
                g=s.get("g", 0),
                ab=s.get("ab", 0),
                h=s.get("h", 0),
                hr=s.get("hr", 0),
                rbi=s.get("rbi", 0),
                sb=s.get("sb", 0),
                bb=s.get("bb", 0),
                so=s.get("so", 0),
                avg=s.get("avg"),
                obp=s.get("obp"),
                slg=s.get("slg"),
                ops=s.get("ops"),
                w=s.get("w", 0),
                l=s.get("l", 0),
                era=s.get("era"),
                gs=s.get("gs", 0),
                ip=s.get("ip"),
                whip=s.get("whip"),
                p_avg=s.get("avg") if is_p else None,
                p_h=s.get("h", 0) if is_p else 0,
                p_so=s.get("so", 0) if is_p else 0,
                p_bb=s.get("bb", 0) if is_p else 0,
                fetched_at=datetime.utcnow(),
            )
            db.add(stat)


async def _compute_rank_change(db: AsyncSession, player_id: int, current_rank: int) -> int:
    """Compare current rank to previous ranking snapshot."""
    result = await db.execute(
        select(ProspectRanking.rank)
        .where(
            ProspectRanking.player_id == player_id,
            ProspectRanking.source == "fangraphs",
        )
        .order_by(ProspectRanking.fetched_at.desc())
        .offset(1)
        .limit(1)
    )
    prev = result.scalar_one_or_none()
    if prev is None:
        return 0
    return prev - current_rank


async def get_cached_prospects(db: AsyncSession) -> list[dict]:
    """Load prospects from database for fast reads."""
    result = await db.execute(
        select(Player).where(Player.sport == "baseball").order_by(Player.name)
    )
    players = result.scalars().all()
    if not players:
        return []

    results = []
    for player in players:
        # Get latest ranking
        rank_result = await db.execute(
            select(ProspectRanking)
            .where(ProspectRanking.player_id == player.id, ProspectRanking.source == "fangraphs")
            .order_by(ProspectRanking.fetched_at.desc())
            .limit(1)
        )
        ranking = rank_result.scalar_one_or_none()
        if not ranking:
            continue

        is_p = mlb_stats.is_pitcher(player.position or "")

        # Get stats
        stats_result = await db.execute(
            select(PlayerStatsBaseball)
            .where(PlayerStatsBaseball.player_id == player.id)
            .order_by(PlayerStatsBaseball.season.desc())
        )
        stats_rows = stats_result.scalars().all()

        stats_by_year = {}
        for s in stats_rows:
            entry = _stat_row_to_dict(s, is_p)
            stats_by_year.setdefault(s.season, []).append(entry)

        score = scoring.compute_score(stats_by_year, is_p)
        rank_change = await _compute_rank_change(db, player.id, ranking.rank)

        results.append({
            "bowman_rank": ranking.rank,
            "name": player.name,
            "team": player.team,
            "pos": player.position,
            "fv": ranking.fv or "",
            "eta": ranking.eta or "",
            "player_id": player.external_id,
            "is_pitcher": is_p,
            "stats": stats_by_year,
            "score": score,
            "rank_change": rank_change,
            "perf_rank": 0,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    for i, r in enumerate(results):
        r["perf_rank"] = i + 1

    return results


def _stat_row_to_dict(s: PlayerStatsBaseball, is_p: bool) -> dict:
    if is_p:
        return {
            "season": s.season, "level": s.level, "league": s.league,
            "is_pitcher": True,
            "w": s.w, "l": s.l, "era": s.era, "g": s.g, "gs": s.gs,
            "ip": s.ip, "so": s.p_so, "bb": s.p_bb, "whip": s.whip,
            "avg": s.p_avg, "h": s.p_h,
        }
    return {
        "season": s.season, "level": s.level, "league": s.league,
        "is_pitcher": False,
        "g": s.g, "ab": s.ab, "h": s.h, "hr": s.hr, "rbi": s.rbi,
        "sb": s.sb, "bb": s.bb, "so": s.so, "avg": s.avg,
        "obp": s.obp, "slg": s.slg, "ops": s.ops,
    }
