from __future__ import annotations

from pydantic import BaseModel


class WatchlistCreate(BaseModel):
    name: str
    user_id: str


class WatchlistPlayerAdd(BaseModel):
    player_id: int


class WatchlistOut(BaseModel):
    id: int
    name: str
    user_id: str
    player_count: int = 0

    model_config = {"from_attributes": True}
