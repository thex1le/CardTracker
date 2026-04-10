from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class AlertOut(BaseModel):
    id: int
    player_id: int
    alert_type: str
    alert_date: date
    severity: str
    title: str
    body: str
    score_snapshot: dict | None
    acknowledged: bool
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
