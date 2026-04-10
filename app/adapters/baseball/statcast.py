"""Statcast data adapter via pybaseball.

pybaseball pulls from Baseball Savant (Statcast). Data is only available
for MLB-level players, not minor leaguers. Returns None for players
who haven't appeared in the majors.
"""
from __future__ import annotations

from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Player
from app.models.baseball import StatcastMetrics


def fetch_statcast_for_player(player_name: str, season: int) -> dict | None:
    """Fetch Statcast data for a player using pybaseball.

    This is a sync function because pybaseball uses requests internally.
    Call from a thread or Celery task.
    """
    try:
        from pybaseball import playerid_lookup, statcast_batter_exitvelo_barrels
        import pandas as pd

        # Parse name
        parts = player_name.strip().split()
        if len(parts) < 2:
            return None
        first = parts[0]
        last = " ".join(parts[1:])

        # Look up player ID
        lookup = playerid_lookup(last, first, fuzzy=True)
        if lookup.empty:
            return None

        mlb_id = int(lookup.iloc[0]["key_mlbam"])

        # Fetch exit velocity / barrel data
        ev_data = statcast_batter_exitvelo_barrels(season, minBBE=1)
        if ev_data is None or ev_data.empty:
            return None

        player_row = ev_data[ev_data["player_id"] == mlb_id]
        if player_row.empty:
            return None

        row = player_row.iloc[0]
        return {
            "exit_velo_avg": _safe_get(row, "avg_hit_speed"),
            "exit_velo_max": _safe_get(row, "max_hit_speed"),
            "barrel_rate": _safe_get(row, "brl_percent"),
            "hard_hit_rate": _safe_get(row, "ev95percent"),
        }

    except Exception:
        return None


def fetch_sprint_speed(player_name: str, season: int) -> float | None:
    """Fetch sprint speed for a player."""
    try:
        from pybaseball import statcast_sprint_speed

        data = statcast_sprint_speed(season, min_opp=1)
        if data is None or data.empty:
            return None

        parts = player_name.strip().split()
        if len(parts) < 2:
            return None

        # Search by name (pybaseball uses "Last, First" format)
        last = " ".join(parts[1:])
        first = parts[0]
        search_name = f"{last}, {first}"

        match = data[data["name_display_last_first"].str.contains(last, case=False, na=False)]
        if match.empty:
            return None

        return float(match.iloc[0]["hp_to_1b"]) if "hp_to_1b" in match.columns else None

    except Exception:
        return None


def fetch_expected_stats(player_name: str, season: int) -> dict | None:
    """Fetch xBA, xSLG, xwOBA from Baseball Savant."""
    try:
        from pybaseball import expected_stats

        data = expected_stats(season, minPA=1)
        if data is None or data.empty:
            return None

        parts = player_name.strip().split()
        if len(parts) < 2:
            return None

        last = " ".join(parts[1:])
        match = data[data["last_name"].str.contains(last, case=False, na=False)]
        if match.empty:
            return None

        row = match.iloc[0]
        return {
            "xba": _safe_get(row, "est_ba"),
            "xslg": _safe_get(row, "est_slg"),
            "xwoba": _safe_get(row, "est_woba"),
        }

    except Exception:
        return None


async def store_statcast(db: AsyncSession, player_id: int, season: int, data: dict):
    """Store Statcast metrics in the database."""
    # Check for existing entry
    result = await db.execute(
        select(StatcastMetrics).where(
            StatcastMetrics.player_id == player_id,
            StatcastMetrics.season == season,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        for key, val in data.items():
            if val is not None:
                setattr(existing, key, val)
        existing.fetched_at = datetime.utcnow()
    else:
        metrics = StatcastMetrics(
            player_id=player_id,
            season=season,
            fetched_at=datetime.utcnow(),
            **{k: v for k, v in data.items() if v is not None},
        )
        db.add(metrics)


def _safe_get(row, col):
    """Safely extract a numeric value from a pandas row."""
    try:
        val = row[col]
        import math
        if math.isnan(val):
            return None
        return float(val)
    except (KeyError, TypeError, ValueError):
        return None
