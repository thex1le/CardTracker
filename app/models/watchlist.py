from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, Index,
)
from sqlalchemy.orm import relationship
from app.database import Base


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False, unique=True)
    notes = Column(Text, nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow)

    player = relationship("Player")
    alert_prefs = relationship("AlertPreference", back_populates="watchlist_item", cascade="all, delete-orphan")


class AlertPreference(Base):
    __tablename__ = "alert_preferences"

    id = Column(Integer, primary_key=True)
    watchlist_item_id = Column(Integer, ForeignKey("watchlist_items.id"), nullable=False)
    alert_type = Column(String(50))  # 'score_change', 'sentiment_red', 'price_spike', 'signal'
    threshold = Column(Float, nullable=True)  # e.g., score change > 5
    enabled = Column(Boolean, default=True)

    watchlist_item = relationship("WatchlistItem", back_populates="alert_prefs")


class UserAlert(Base):
    __tablename__ = "user_alerts"

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    alert_type = Column(String(50))
    title = Column(String(300))
    body = Column(Text)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    player = relationship("Player")

    __table_args__ = (
        Index("ix_alerts_unread", "is_read", "created_at"),
    )
