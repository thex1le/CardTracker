from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

if TYPE_CHECKING:
    from app.models.event import PlayerEvent
    from app.models.score_daily import ScoreDaily


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    name_normalized: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    team: Mapped[str | None] = mapped_column(String(100))
    position: Mapped[str | None] = mapped_column(String(20))
    bats: Mapped[str | None] = mapped_column(String(5))
    throws: Mapped[str | None] = mapped_column(String(5))
    age: Mapped[int | None] = mapped_column(Integer)
    prospect_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    top_prospect_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    market_size_tier: Mapped[str | None] = mapped_column(String(10))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())

    events: Mapped[list[PlayerEvent]] = relationship("PlayerEvent", back_populates="player", lazy="selectin")
    scores: Mapped[list[ScoreDaily]] = relationship("ScoreDaily", back_populates="player", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Player {self.id} {self.name}>"
