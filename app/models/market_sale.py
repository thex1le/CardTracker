from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class MarketSale(Base):
    __tablename__ = "market_sales"
    __table_args__ = (
        UniqueConstraint(
            "source", "source_item_id",
            name="uq_sale_source_item",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(Integer, ForeignKey("players.id"), index=True)
    card_title: Mapped[str] = mapped_column(String(500))
    card_type: Mapped[str | None] = mapped_column(String(30))
    grader: Mapped[str | None] = mapped_column(String(10))
    grade: Mapped[str | None] = mapped_column(String(10))
    sale_price: Mapped[float] = mapped_column(Float)
    sale_date: Mapped[date] = mapped_column(Date, index=True)
    listing_type: Mapped[str | None] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(20), default="ebay")
    source_item_id: Mapped[str | None] = mapped_column(String(50), index=True)
    player_match_method: Mapped[str] = mapped_column(String(20))
    player_match_score: Mapped[float] = mapped_column(Float)
    raw_title_player_str: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(default=func.now())
