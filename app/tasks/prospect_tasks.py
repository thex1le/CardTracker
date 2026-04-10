"""Celery tasks for prospect data refresh.

These run in a sync context (Celery workers), so we use synchronous
SQLAlchemy and httpx for DB/API access.
"""
import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.tasks.celery_app import celery
from app.models.base import Player, ProspectRanking
from app.models.baseball import PlayerStatsBaseball
from app.adapters.baseball import scoring
from app.adapters.baseball.mlb_stats import is_pitcher, PITCHER_POSITIONS, SEASONS

# Sync engine for Celery tasks
_engine = create_engine(settings.sync_database_url)


def _search_player_sync(client: httpx.Client, name: str):
    try:
        resp = client.get(
            "https://statsapi.mlb.com/api/v1/people/search",
            params={"names": name, "sportIds": "1,11,12,13,14,15,16"},
            timeout=10,
        )
        people = resp.json().get("people", [])
        if people:
            for p in people:
                if p.get("fullName", "").lower() == name.lower():
                    return str(p["id"])
            return str(people[0]["id"])
    except Exception:
        pass
    return None


def _fetch_stats_sync(client: httpx.Client, player_id: str, is_p: bool):
    group = "pitching" if is_p else "hitting"
    stats_by_year = {}
    for season in SEASONS:
        try:
            resp = client.get(
                f"https://statsapi.mlb.com/api/v1/people/{player_id}",
                params={
                    "hydrate": f"stats(group=[{group}],type=[season],sportId=[1,11,12,13,14,15,16],season={season})"
                },
                timeout=10,
            )
            data = resp.json()
        except Exception:
            continue
        person = data.get("people", [{}])[0]
        for stat_group in person.get("stats", []):
            for split in stat_group.get("splits", []):
                if str(split.get("season")) != str(season):
                    continue
                s = split.get("stat", {})
                level = split.get("sport", {}).get("name", "Unknown")
                league = split.get("league", {}).get("name", "")
                if is_p:
                    entry = {"season": season, "level": level, "league": league, "is_pitcher": True,
                             "w": s.get("wins", 0), "l": s.get("losses", 0), "era": s.get("era", "-"),
                             "g": s.get("gamesPlayed", 0), "gs": s.get("gamesStarted", 0),
                             "ip": s.get("inningsPitched", "0"), "so": s.get("strikeOuts", 0),
                             "bb": s.get("baseOnBalls", 0), "whip": s.get("whip", "-"),
                             "avg": s.get("avg", "-"), "h": s.get("hits", 0)}
                else:
                    entry = {"season": season, "level": level, "league": league, "is_pitcher": False,
                             "g": s.get("gamesPlayed", 0), "ab": s.get("atBats", 0), "h": s.get("hits", 0),
                             "hr": s.get("homeRuns", 0), "rbi": s.get("rbi", 0), "sb": s.get("stolenBases", 0),
                             "bb": s.get("baseOnBalls", 0), "so": s.get("strikeOuts", 0),
                             "avg": s.get("avg", "-"), "obp": s.get("obp", "-"),
                             "slg": s.get("slg", "-"), "ops": s.get("ops", "-")}
                stats_by_year.setdefault(season, []).append(entry)
    return stats_by_year


@celery.task(name="app.tasks.prospect_tasks.refresh_prospects_task")
def refresh_prospects_task():
    """Background task to refresh all prospect data."""
    from datetime import datetime

    # Fetch prospects from FanGraphs (sync)
    with httpx.Client(timeout=15) as client:
        resp = client.get(
            "https://www.fangraphs.com/api/prospects/board/prospects-list",
            params={"pos": "all", "lg": 2, "stats": "bat", "qual": 0, "type": 0,
                    "team": "", "season": datetime.now().year, "month": 0, "ind": 0,
                    "pagenum": 1, "pageitems": 100, "draft": "", "sort": "rank", "sortdir": "asc"},
            headers={"User-Agent": "CardScout/1.0"},
        )
        prospects = resp.json()[:100]

    with Session(_engine) as db:
        for fg in prospects:
            name = fg.get("playerName", "")
            team = fg.get("Team", "")
            pos = fg.get("Position", "")
            rank = fg.get("Ovr_Rank", 0)

            # Upsert player
            player = db.execute(
                select(Player).where(Player.sport == "baseball", Player.name == name)
            ).scalar_one_or_none()

            if not player:
                player = Player(sport="baseball", name=name, team=team, position=pos)
                db.add(player)
                db.flush()
            else:
                player.team = team
                player.position = pos

            # Store ranking
            db.add(ProspectRanking(
                player_id=player.id, source="fangraphs", rank=rank,
                fv=str(fg.get("FV_Current", "")), eta=str(fg.get("ETA_Current", "")),
                fetched_at=datetime.utcnow(),
            ))

            # Fetch MLB stats
            is_p = pos in PITCHER_POSITIONS
            if not player.external_id:
                with httpx.Client(timeout=10) as api_client:
                    ext_id = _search_player_sync(api_client, name)
                if ext_id:
                    player.external_id = ext_id

            if player.external_id:
                with httpx.Client(timeout=10) as api_client:
                    stats = _fetch_stats_sync(api_client, player.external_id, is_p)
                for season, splits in stats.items():
                    for s in splits:
                        db.add(PlayerStatsBaseball(
                            player_id=player.id, season=season,
                            level=s.get("level", ""), league=s.get("league", ""),
                            is_pitcher=is_p, g=s.get("g", 0),
                            ab=s.get("ab", 0), h=s.get("h", 0), hr=s.get("hr", 0),
                            rbi=s.get("rbi", 0), sb=s.get("sb", 0), bb=s.get("bb", 0),
                            so=s.get("so", 0), avg=s.get("avg"), obp=s.get("obp"),
                            slg=s.get("slg"), ops=s.get("ops"),
                            w=s.get("w", 0), l=s.get("l", 0), era=s.get("era"),
                            gs=s.get("gs", 0), ip=s.get("ip"), whip=s.get("whip"),
                            p_avg=s.get("avg") if is_p else None,
                            p_h=s.get("h", 0) if is_p else 0,
                            p_so=s.get("so", 0) if is_p else 0,
                            p_bb=s.get("bb", 0) if is_p else 0,
                            fetched_at=datetime.utcnow(),
                        ))

        db.commit()

    return {"status": "ok", "count": len(prospects)}
