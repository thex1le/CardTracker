"""Signal detection engine.

Analyzes player stats to generate actionable signals:
- Breakout detection (performance vs baseline)
- Milestone proximity alerts
- Callup probability heuristics
- Statcast elite flags
"""
from __future__ import annotations

from datetime import datetime, date
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Player, ProspectRanking, Signal
from app.models.baseball import PlayerStatsBaseball, StatcastMetrics
from app.adapters.baseball.scoring import _safe_float
from app.adapters.baseball.mlb_stats import is_pitcher, CURRENT_YEAR


# Thresholds
BREAKOUT_THRESHOLD = 0.15  # 15% improvement over baseline
MILESTONE_THRESHOLDS_HITTING = {
    "hr": [10, 15, 20, 25, 30],
    "sb": [10, 20, 30],
    "rbi": [50, 75, 100],
    "h": [100, 150],
}
MILESTONE_THRESHOLDS_PITCHING = {
    "p_so": [50, 100, 150, 200],
    "w": [5, 10, 15],
}
STATCAST_ELITE_EXIT_VELO = 91.0  # ~90th percentile
STATCAST_ELITE_BARREL_RATE = 10.0  # ~90th percentile


async def detect_all_signals(db: AsyncSession) -> list[dict]:
    """Run all signal detectors across all tracked players."""
    result = await db.execute(
        select(Player).where(Player.sport == "baseball")
    )
    players = result.scalars().all()
    all_signals = []

    for player in players:
        signals = await detect_signals_for_player(db, player)
        all_signals.extend(signals)

    return all_signals


async def detect_signals_for_player(db: AsyncSession, player: Player) -> list[dict]:
    """Run all detectors for a single player."""
    signals = []
    is_p = is_pitcher(player.position or "")

    # Get latest season stats
    stats_result = await db.execute(
        select(PlayerStatsBaseball)
        .where(PlayerStatsBaseball.player_id == player.id)
        .order_by(PlayerStatsBaseball.season.desc())
    )
    stats = stats_result.scalars().all()
    if not stats:
        return signals

    # Group stats by season
    by_season = {}
    for s in stats:
        by_season.setdefault(s.season, []).append(s)

    # 1. Breakout detection
    breakout = _detect_breakout(player, by_season, is_p)
    if breakout:
        signals.append(breakout)
        await _upsert_signal(db, breakout)

    # 2. Milestone proximity
    milestones = _detect_milestones(player, by_season, is_p)
    for m in milestones:
        signals.append(m)
        await _upsert_signal(db, m)

    # 3. Callup probability
    callup = await _detect_callup(db, player, by_season, is_p)
    if callup:
        signals.append(callup)
        await _upsert_signal(db, callup)

    # 4. Statcast elite
    statcast = await _detect_statcast_elite(db, player)
    if statcast:
        signals.append(statcast)
        await _upsert_signal(db, statcast)

    await db.commit()
    return signals


def _detect_breakout(player: Player, by_season: dict, is_p: bool) -> dict | None:
    """Compare most recent season to prior season. Flag large improvements."""
    seasons = sorted(by_season.keys(), reverse=True)
    if len(seasons) < 2:
        return None

    current = by_season[seasons[0]]
    previous = by_season[seasons[1]]

    if is_p:
        curr_era = _weighted_era(current)
        prev_era = _weighted_era(previous)
        if prev_era is None or curr_era is None or prev_era == 0:
            return None
        # Lower ERA is better — improvement = (prev - curr) / prev
        improvement = (prev_era - curr_era) / prev_era
        if improvement >= BREAKOUT_THRESHOLD:
            return {
                "player_id": player.id,
                "player_name": player.name,
                "signal_type": "breakout",
                "severity": "high" if improvement >= 0.25 else "medium",
                "title": f"ERA breakout: {prev_era:.2f} -> {curr_era:.2f}",
                "description": f"{player.name} ERA improved {improvement:.0%} from {seasons[1]} to {seasons[0]}",
            }
    else:
        curr_ops = _weighted_ops(current)
        prev_ops = _weighted_ops(previous)
        if prev_ops is None or curr_ops is None or prev_ops == 0:
            return None
        improvement = (curr_ops - prev_ops) / prev_ops
        if improvement >= BREAKOUT_THRESHOLD:
            return {
                "player_id": player.id,
                "player_name": player.name,
                "signal_type": "breakout",
                "severity": "high" if improvement >= 0.25 else "medium",
                "title": f"OPS breakout: {prev_ops:.3f} -> {curr_ops:.3f}",
                "description": f"{player.name} OPS improved {improvement:.0%} from {seasons[1]} to {seasons[0]}",
            }

    return None


def _detect_milestones(player: Player, by_season: dict, is_p: bool) -> list[dict]:
    """Check if a player is approaching stat milestones in their current season."""
    seasons = sorted(by_season.keys(), reverse=True)
    if not seasons:
        return []

    current = by_season[seasons[0]]
    milestones = []
    thresholds = MILESTONE_THRESHOLDS_PITCHING if is_p else MILESTONE_THRESHOLDS_HITTING

    for stat_key, marks in thresholds.items():
        total = sum(getattr(s, stat_key, 0) or 0 for s in current)
        for mark in marks:
            gap = mark - total
            # Within 3 of a milestone
            if 0 < gap <= 3:
                stat_label = stat_key.replace("p_", "").upper()
                milestones.append({
                    "player_id": player.id,
                    "player_name": player.name,
                    "signal_type": "milestone",
                    "severity": "low",
                    "title": f"{total} {stat_label} — {gap} away from {mark}",
                    "description": f"{player.name} has {total} {stat_label} in {seasons[0]}, approaching {mark} milestone",
                })
            elif gap == 0:
                stat_label = stat_key.replace("p_", "").upper()
                milestones.append({
                    "player_id": player.id,
                    "player_name": player.name,
                    "signal_type": "milestone",
                    "severity": "medium",
                    "title": f"Milestone reached: {mark} {stat_label}!",
                    "description": f"{player.name} reached {mark} {stat_label} in {seasons[0]}",
                })

    return milestones


async def _detect_callup(db: AsyncSession, player: Player, by_season: dict, is_p: bool) -> dict | None:
    """Heuristic callup probability based on rank, ETA, level, performance."""
    # Get latest ranking
    rank_result = await db.execute(
        select(ProspectRanking)
        .where(ProspectRanking.player_id == player.id)
        .order_by(ProspectRanking.fetched_at.desc())
        .limit(1)
    )
    ranking = rank_result.scalar_one_or_none()
    if not ranking:
        return None

    score = 0
    reasons = []

    # Factor 1: Prospect rank (top 10 = 30pts, top 25 = 20pts, top 50 = 10pts)
    if ranking.rank and ranking.rank <= 10:
        score += 30
        reasons.append(f"Top 10 prospect (#{ranking.rank})")
    elif ranking.rank and ranking.rank <= 25:
        score += 20
        reasons.append(f"Top 25 prospect (#{ranking.rank})")
    elif ranking.rank and ranking.rank <= 50:
        score += 10
        reasons.append(f"Top 50 prospect (#{ranking.rank})")

    # Factor 2: ETA matches current year (25pts)
    try:
        eta_year = int(ranking.eta) if ranking.eta else 0
    except ValueError:
        eta_year = 0
    if eta_year == CURRENT_YEAR:
        score += 25
        reasons.append(f"ETA is {CURRENT_YEAR}")
    elif eta_year == CURRENT_YEAR + 1:
        score += 10
        reasons.append(f"ETA is {CURRENT_YEAR + 1}")

    # Factor 3: Playing at AAA level (25pts) or AA (10pts)
    seasons = sorted(by_season.keys(), reverse=True)
    if seasons:
        current_splits = by_season[seasons[0]]
        levels = [s.level for s in current_splits if s.level]
        for level in levels:
            ll = level.lower()
            if "triple" in ll or "aaa" in ll or "international" in ll:
                score += 25
                reasons.append(f"Currently at AAA ({level})")
                break
            elif "double" in ll or "aa" in ll or "eastern" in ll or "southern" in ll:
                score += 10
                reasons.append(f"Currently at AA ({level})")
                break

    # Factor 4: Strong performance (20pts if good stats)
    if seasons:
        current_splits = by_season[seasons[0]]
        if is_p:
            era = _weighted_era(current_splits)
            if era is not None and era < 3.50:
                score += 20
                reasons.append(f"Strong ERA ({era:.2f})")
        else:
            ops = _weighted_ops(current_splits)
            if ops is not None and ops >= 0.800:
                score += 20
                reasons.append(f"Strong OPS ({ops:.3f})")

    if score >= 40:
        severity = "high" if score >= 70 else "medium"
        return {
            "player_id": player.id,
            "player_name": player.name,
            "signal_type": "callup",
            "severity": severity,
            "title": f"Callup probability: {min(score, 100)}%",
            "description": f"{player.name}: {'; '.join(reasons)}",
            "data": {"probability": min(score, 100), "reasons": reasons},
        }

    return None


async def _detect_statcast_elite(db: AsyncSession, player: Player) -> dict | None:
    """Flag players with elite Statcast metrics."""
    result = await db.execute(
        select(StatcastMetrics)
        .where(StatcastMetrics.player_id == player.id)
        .order_by(StatcastMetrics.season.desc())
        .limit(1)
    )
    metrics = result.scalar_one_or_none()
    if not metrics:
        return None

    elite_traits = []
    if metrics.exit_velo_avg and metrics.exit_velo_avg >= STATCAST_ELITE_EXIT_VELO:
        elite_traits.append(f"Exit Velo {metrics.exit_velo_avg:.1f} mph")
    if metrics.barrel_rate and metrics.barrel_rate >= STATCAST_ELITE_BARREL_RATE:
        elite_traits.append(f"Barrel Rate {metrics.barrel_rate:.1f}%")
    if metrics.xwoba and metrics.xwoba >= 0.370:
        elite_traits.append(f"xwOBA {metrics.xwoba:.3f}")
    if metrics.sprint_speed and metrics.sprint_speed >= 29.0:
        elite_traits.append(f"Sprint Speed {metrics.sprint_speed:.1f} ft/s")

    if elite_traits:
        return {
            "player_id": player.id,
            "player_name": player.name,
            "signal_type": "statcast_elite",
            "severity": "high" if len(elite_traits) >= 2 else "medium",
            "title": f"Statcast elite: {', '.join(elite_traits)}",
            "description": f"{player.name} shows elite underlying metrics in {metrics.season}",
            "data": {
                "exit_velo": metrics.exit_velo_avg,
                "barrel_rate": metrics.barrel_rate,
                "xwoba": metrics.xwoba,
                "sprint_speed": metrics.sprint_speed,
            },
        }

    return None


async def _upsert_signal(db: AsyncSession, sig: dict):
    """Insert or update a signal, avoiding duplicates."""
    # Check for existing active signal of same type for same player
    result = await db.execute(
        select(Signal).where(
            Signal.player_id == sig["player_id"],
            Signal.signal_type == sig["signal_type"],
            Signal.title == sig["title"],
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.severity = sig["severity"]
        existing.description = sig["description"]
        existing.detected_at = datetime.utcnow()
    else:
        db.add(Signal(
            player_id=sig["player_id"],
            signal_type=sig["signal_type"],
            severity=sig["severity"],
            title=sig["title"],
            description=sig["description"],
            detected_at=datetime.utcnow(),
        ))


# --- Helpers ---

def _weighted_ops(splits: list) -> float | None:
    total_ab = sum(s.ab or 0 for s in splits)
    if total_ab == 0:
        return None
    weighted = sum(_safe_float(s.ops) * (s.ab or 0) for s in splits if (s.ab or 0) > 0)
    return weighted / total_ab


def _weighted_era(splits: list) -> float | None:
    total_ip = sum(_safe_float(s.ip) for s in splits)
    if total_ip == 0:
        return None
    weighted = sum(_safe_float(s.era) * _safe_float(s.ip) for s in splits if _safe_float(s.ip) > 0)
    return weighted / total_ip
