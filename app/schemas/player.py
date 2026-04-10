from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class PlayerSummary(BaseModel):
    id: int
    name: str
    team: str | None
    position: str | None
    prospect_flag: bool
    active: bool

    model_config = {"from_attributes": True}


class PlayerDetail(BaseModel):
    id: int
    name: str
    team: str | None
    position: str | None
    bats: str | None
    throws: str | None
    age: int | None
    prospect_flag: bool
    top_prospect_flag: bool
    market_size_tier: str | None
    active: bool
    scores: dict | None = None
    recent_events: list[dict] = []
    recent_performance: list[dict] = []
    recent_sales: list[dict] = []
    listing_snapshots: list[dict] = []
    summary_text: str | None = None

    model_config = {"from_attributes": True}
