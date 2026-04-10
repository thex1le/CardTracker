import httpx
from datetime import date

FANGRAPHS_PROSPECTS_URL = "https://www.fangraphs.com/api/prospects/board/prospects-list"


async def fetch_top_prospects(count: int = 100) -> list[dict]:
    """Fetch current top prospects from FanGraphs API."""
    current_year = date.today().year
    params = {
        "pos": "all",
        "lg": 2,
        "stats": "bat",
        "qual": 0,
        "type": 0,
        "team": "",
        "season": current_year,
        "month": 0,
        "ind": 0,
        "pagenum": 1,
        "pageitems": count,
        "draft": "",
        "sort": "rank",
        "sortdir": "asc",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            FANGRAPHS_PROSPECTS_URL,
            params=params,
            headers={"User-Agent": "CardScout/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()

    prospects = []
    for p in data[:count]:
        prospects.append({
            "rank": p.get("Ovr_Rank", 0),
            "name": p.get("PlayerName", "") or p.get("playerName", ""),
            "team": p.get("Team", ""),
            "pos": p.get("Position", ""),
            "fv": str(p.get("FV_Current", "")),
            "eta": str(p.get("ETA_Current", "")),
        })
    return prospects
