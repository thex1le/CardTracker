from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, Float, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class PerformanceDaily(Base):
    __tablename__ = "performance_daily"
    __table_args__ = (
        UniqueConstraint("player_id", "game_date", name="uq_perf_player_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(Integer, ForeignKey("players.id"), index=True)
    game_date: Mapped[date] = mapped_column(Date, index=True)

    # Hitting
    plate_appearances: Mapped[int | None] = mapped_column(Integer)
    at_bats: Mapped[int | None] = mapped_column(Integer)
    hits: Mapped[int | None] = mapped_column(Integer)
    home_runs: Mapped[int | None] = mapped_column(Integer)
    runs: Mapped[int | None] = mapped_column(Integer)
    rbi: Mapped[int | None] = mapped_column(Integer)
    walks: Mapped[int | None] = mapped_column(Integer)
    strikeouts: Mapped[int | None] = mapped_column(Integer)
    stolen_bases: Mapped[int | None] = mapped_column(Integer)

    # Pitching
    innings_pitched: Mapped[float | None] = mapped_column(Float)
    earned_runs: Mapped[int | None] = mapped_column(Integer)
    pitch_strikeouts: Mapped[int | None] = mapped_column(Integer)
    saves: Mapped[int | None] = mapped_column(Integer)

    # Computed
    ops: Mapped[float | None] = mapped_column(Float)
    recent_ops_7d: Mapped[float | None] = mapped_column(Float)
    recent_hr_7d: Mapped[int | None] = mapped_column(Integer)
    recent_k_7d: Mapped[int | None] = mapped_column(Integer)
    recent_saves_7d: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(default=func.now())
