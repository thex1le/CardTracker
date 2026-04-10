from __future__ import annotations

from pydantic import BaseModel


class FeedItem(BaseModel):
    player_id: int
    player_name: str
    team: str | None
    position: str | None
    opportunity_score: float
    hype_score: float
    market_score: float
    supply_score: float
    hobby_fit_score: float
    exit_risk_score: float
    data_confidence: float
    summary: str | None


class MisspelledItem(BaseModel):
    alert_id: int
    player_id: int
    player_name: str
    team: str | None
    severity: str
    title: str
    body: str
    alert_date: str
    score_snapshot: dict | None
