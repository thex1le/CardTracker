from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

if TYPE_CHECKING:
    from app.models.player import Player


class PlayerEvent(Base):
    __tablename__ = "player_events"
    __table_args__ = (
        UniqueConstraint("player_id", "event_type", "event_date", "source", name="uq_event_player_type_date_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(Integer, ForeignKey("players.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(50))
    event_date: Mapped[date] = mapped_column(Date, index=True)
    title: Mapped[str] = mapped_column(String(300))
    details: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(100))
    source_url: Mapped[str | None] = mapped_column(String(500))
    importance_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    player: Mapped[Player] = relationship("Player", back_populates="events")

    def __repr__(self) -> str:
        return f"<PlayerEvent {self.event_type} player={self.player_id} {self.event_date}>"
