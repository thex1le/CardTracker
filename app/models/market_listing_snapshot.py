from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class MarketListingSnapshot(Base):
    __tablename__ = "market_listing_snapshots"
    __table_args__ = (
        UniqueConstraint("player_id", "snapshot_date", name="uq_snapshot_player_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(Integer, ForeignKey("players.id"), index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, index=True)
    active_listing_count: Mapped[int] = mapped_column(Integer, default=0)
    new_listing_count_1d: Mapped[int] = mapped_column(Integer, default=0)
    auction_count: Mapped[int] = mapped_column(Integer, default=0)
    bin_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
