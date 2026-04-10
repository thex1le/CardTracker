from __future__ import annotations

import logging
from datetime import date, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.performance_daily import PerformanceDaily

logger = logging.getLogger(__name__)


async def fetch_player_game_log(player_id: int, days_back: int = 14) -> list[dict]:
    """Fetch recent game log for a player from MLB Stats API.

    Endpoint: GET /people/{mlbam_id}/stats?stats=gameLog&season=YYYY
    Returns list of game stat dicts.
    """
    season = date.today().year
    url = f"{settings.mlb_stats_api_base}/people/{player_id}/stats"
    params = {"stats": "gameLog", "season": season}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        splits = []
        for group in data.get("stats", []):
            for split in group.get("splits", []):
                game_date_str = split.get("date", "")
                if not game_date_str:
                    continue
                game_date = date.fromisoformat(game_date_str[:10])
                cutoff = date.today() - timedelta(days=days_back)
                if game_date >= cutoff:
                    split["_game_date"] = game_date
                    splits.append(split)

        return splits

    except Exception as e:
        logger.error("Failed to fetch game log for player %d: %s", player_id, e)
        return []


def compute_rolling_stats(game_rows: list[dict], days: int = 7) -> dict:
    """Compute rolling sums/averages over last N days.

    Returns dict with recent_ops_7d, recent_hr_7d, recent_k_7d, recent_saves_7d.
    """
    cutoff = date.today() - timedelta(days=days)
    recent = [g for g in game_rows if g.get("_game_date", date.min) >= cutoff]

    total_ab = 0
    total_h = 0
    total_bb = 0
    total_hbp = 0
    total_sf = 0
    total_hr = 0
    total_so = 0
    total_saves = 0
    total_tb = 0
    total_pa = 0

    for g in recent:
        stat = g.get("stat", {})
        ab = stat.get("atBats", 0)
        h = stat.get("hits", 0)
        bb = stat.get("baseOnBalls", 0)
        hbp = stat.get("hitByPitch", 0)
        sf = stat.get("sacFlies", 0)
        hr = stat.get("homeRuns", 0)
        so = stat.get("strikeOuts", 0)
        saves = stat.get("saves", 0)

        # Total bases approximation
        doubles = stat.get("doubles", 0)
        triples = stat.get("triples", 0)
        tb = h + doubles + 2 * triples + 3 * hr

        total_ab += ab
        total_h += h
        total_bb += bb
        total_hbp += hbp
        total_sf += sf
        total_hr += hr
        total_so += so
        total_saves += saves
        total_tb += tb
        total_pa += ab + bb + hbp + sf

    # OPS = OBP + SLG
    obp = (total_h + total_bb + total_hbp) / max(total_pa, 1)
    slg = total_tb / max(total_ab, 1)
    ops = obp + slg if total_pa > 0 else None

    return {
        "recent_ops_7d": round(ops, 3) if ops is not None else None,
        "recent_hr_7d": total_hr,
        "recent_k_7d": total_so,
        "recent_saves_7d": total_saves,
    }


async def ingest_performance(db: AsyncSession, player_id: int, mlb_id: int | None = None) -> int:
    """Fetch recent game log, compute 7d rolling stats, upsert performance_daily.

    Returns rows upserted.
    """
    if mlb_id is None:
        return 0

    game_log = await fetch_player_game_log(mlb_id)
    if not game_log:
        return 0

    rolling = compute_rolling_stats(game_log)
    count = 0

    for g in game_log:
        stat = g.get("stat", {})
        game_date = g["_game_date"]

        # Check existing
        existing = await db.execute(
            select(PerformanceDaily).where(
                PerformanceDaily.player_id == player_id,
                PerformanceDaily.game_date == game_date,
            )
        )
        row = existing.scalar_one_or_none()

        ip_str = stat.get("inningsPitched", "0")
        try:
            ip = float(ip_str) if ip_str else None
        except (ValueError, TypeError):
            ip = None

        values = dict(
            plate_appearances=stat.get("plateAppearances"),
            at_bats=stat.get("atBats"),
            hits=stat.get("hits"),
            home_runs=stat.get("homeRuns"),
            runs=stat.get("runs"),
            rbi=stat.get("rbi"),
            walks=stat.get("baseOnBalls"),
            strikeouts=stat.get("strikeOuts"),
            stolen_bases=stat.get("stolenBases"),
            innings_pitched=ip,
            earned_runs=stat.get("earnedRuns"),
            pitch_strikeouts=stat.get("strikeOuts") if ip else None,
            saves=stat.get("saves"),
            recent_ops_7d=rolling["recent_ops_7d"],
            recent_hr_7d=rolling["recent_hr_7d"],
            recent_k_7d=rolling["recent_k_7d"],
            recent_saves_7d=rolling["recent_saves_7d"],
        )

        # Compute single-game OPS
        ab = stat.get("atBats", 0)
        h = stat.get("hits", 0)
        bb = stat.get("baseOnBalls", 0)
        hbp = stat.get("hitByPitch", 0)
        sf = stat.get("sacFlies", 0)
        pa = ab + bb + hbp + sf
        doubles = stat.get("doubles", 0)
        triples = stat.get("triples", 0)
        hr = stat.get("homeRuns", 0)
        tb = h + doubles + 2 * triples + 3 * hr
        if pa > 0 and ab > 0:
            obp = (h + bb + hbp) / pa
            slg = tb / ab
            values["ops"] = round(obp + slg, 3)

        if row:
            for k, v in values.items():
                setattr(row, k, v)
        else:
            db.add(PerformanceDaily(player_id=player_id, game_date=game_date, **values))
            count += 1

    if count:
        await db.commit()

    return count
