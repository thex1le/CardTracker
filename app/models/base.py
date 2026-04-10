from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, Index,
)
from sqlalchemy.orm import relationship
from app.database import Base


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True)
    external_id = Column(String(50))  # e.g., MLB player ID
    sport = Column(String(20), default="baseball")
    name = Column(String(200), nullable=False)
    team = Column(String(100))
    position = Column(String(20))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    rankings = relationship("ProspectRanking", back_populates="player", lazy="selectin")
    baseball_stats = relationship("PlayerStatsBaseball", back_populates="player", lazy="selectin")
    signals = relationship("Signal", back_populates="player", lazy="selectin")
    sentiment_events = relationship("SentimentEvent", back_populates="player", lazy="selectin")

    __table_args__ = (
        Index("ix_players_sport_external", "sport", "external_id", unique=True),
    )


class ProspectRanking(Base):
    __tablename__ = "prospect_rankings"

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    source = Column(String(50), default="fangraphs")  # 'fangraphs', 'mlb_pipeline', etc.
    rank = Column(Integer)
    fv = Column(String(10))  # Future Value grade
    eta = Column(String(10))  # Estimated MLB arrival year
    fetched_at = Column(DateTime, default=datetime.utcnow)

    player = relationship("Player", back_populates="rankings")

    __table_args__ = (
        Index("ix_ranking_player_source_date", "player_id", "source", "fetched_at"),
    )


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    signal_type = Column(String(50))  # 'breakout', 'statcast_elite', 'milestone', 'callup'
    severity = Column(String(10))  # 'high', 'medium', 'low'
    title = Column(String(200))
    description = Column(Text)
    detected_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)

    player = relationship("Player", back_populates="signals")

    __table_args__ = (
        Index("ix_signals_player_type", "player_id", "signal_type"),
    )


class Card(Base):
    __tablename__ = "cards"

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    card_name = Column(String(300))
    card_year = Column(Integer)
    card_set = Column(String(200))
    card_number = Column(String(50))
    is_auto = Column(Boolean, default=False)
    is_graded = Column(Boolean, default=False)
    grade = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    player = relationship("Player")
    price_points = relationship("PricePoint", back_populates="card", lazy="selectin")

    __table_args__ = (
        Index("ix_cards_player", "player_id"),
    )


class PricePoint(Base):
    __tablename__ = "price_points"

    id = Column(Integer, primary_key=True)
    card_id = Column(Integer, ForeignKey("cards.id"), nullable=False)
    source = Column(String(50))  # '130point', 'sportscardspro'
    price_cents = Column(Integer)
    sold_date = Column(String(10))  # YYYY-MM-DD
    listing_title = Column(String(500))
    fetched_at = Column(DateTime, default=datetime.utcnow)

    card = relationship("Card", back_populates="price_points")

    __table_args__ = (
        Index("ix_prices_card_date", "card_id", "sold_date"),
    )


class SentimentEvent(Base):
    __tablename__ = "sentiment_events"

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    source = Column(String(50))  # 'newsapi', 'espn', 'mlb_transactions'
    headline = Column(String(500))
    summary = Column(Text, nullable=True)
    url = Column(String(1000), nullable=True)
    sentiment = Column(String(10))  # 'positive', 'neutral', 'negative'
    sentiment_score = Column(Float)  # -1.0 to 1.0
    alert_tier = Column(String(10), nullable=True)  # 'RED', 'YELLOW', 'GREEN'
    category = Column(String(50))  # 'performance', 'injury', 'off_field', 'transaction'
    published_at = Column(DateTime)
    fetched_at = Column(DateTime, default=datetime.utcnow)

    player = relationship("Player", back_populates="sentiment_events")

    __table_args__ = (
        Index("ix_sentiment_player_date", "player_id", "published_at"),
    )


class CompositeScore(Base):
    __tablename__ = "composite_scores"

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    score = Column(Float)  # 0-100
    performance_sub = Column(Float)
    momentum_sub = Column(Float)
    card_price_sub = Column(Float)
    sentiment_sub = Column(Float)
    availability_sub = Column(Float)
    computed_at = Column(DateTime, default=datetime.utcnow)

    player = relationship("Player")

    __table_args__ = (
        Index("ix_scores_player_date", "player_id", "computed_at"),
    )
