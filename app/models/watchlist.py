from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Watchlist(Base):
    __tablename__ = "watchlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    players: Mapped[list["WatchlistPlayer"]] = relationship(
        back_populates="watchlist", cascade="all, delete-orphan", lazy="selectin"
    )


class WatchlistPlayer(Base):
    __tablename__ = "watchlist_players"
    __table_args__ = (
        UniqueConstraint("watchlist_id", "player_id", name="uq_watchlist_player"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    watchlist_id: Mapped[int] = mapped_column(Integer, ForeignKey("watchlists.id"))
    player_id: Mapped[int] = mapped_column(Integer, ForeignKey("players.id"))
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    watchlist: Mapped["Watchlist"] = relationship(back_populates="players")
