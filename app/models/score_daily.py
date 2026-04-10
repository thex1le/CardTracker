from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, Float, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

if TYPE_CHECKING:
    from app.models.player import Player


class ScoreDaily(Base):
    __tablename__ = "score_daily"
    __table_args__ = (
        UniqueConstraint("player_id", "score_date", name="uq_score_player_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(Integer, ForeignKey("players.id"), index=True)
    score_date: Mapped[date] = mapped_column(Date, index=True)
    hype_score: Mapped[float] = mapped_column(Float, default=0.0)
    market_score: Mapped[float] = mapped_column(Float, default=0.0)
    supply_score: Mapped[float] = mapped_column(Float, default=0.0)
    hobby_fit_score: Mapped[float] = mapped_column(Float, default=0.0)
    opportunity_score: Mapped[float] = mapped_column(Float, default=0.0)
    exit_risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    data_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    summary_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    player: Mapped[Player] = relationship("Player", back_populates="scores")

    def __repr__(self) -> str:
        return f"<ScoreDaily player={self.player_id} {self.score_date} opp={self.opportunity_score:.1f}>"
