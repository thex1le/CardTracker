from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.database import Base


class PlayerStatsBaseball(Base):
    __tablename__ = "player_stats_baseball"

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    season = Column(Integer, nullable=False)
    level = Column(String(50))
    league = Column(String(100))
    is_pitcher = Column(Boolean, default=False)

    # Shared
    g = Column(Integer, default=0)  # games played

    # Hitting stats
    ab = Column(Integer, default=0)
    h = Column(Integer, default=0)
    hr = Column(Integer, default=0)
    rbi = Column(Integer, default=0)
    sb = Column(Integer, default=0)
    bb = Column(Integer, default=0)
    so = Column(Integer, default=0)
    avg = Column(String(10))
    obp = Column(String(10))
    slg = Column(String(10))
    ops = Column(String(10))

    # Pitching stats
    w = Column(Integer, default=0)
    l = Column(Integer, default=0)
    era = Column(String(10))
    gs = Column(Integer, default=0)
    ip = Column(String(10))
    whip = Column(String(10))
    p_avg = Column(String(10))  # batting avg against
    p_h = Column(Integer, default=0)  # hits allowed
    p_so = Column(Integer, default=0)  # strikeouts (pitching)
    p_bb = Column(Integer, default=0)  # walks (pitching)

    fetched_at = Column(DateTime, default=datetime.utcnow)

    player = relationship("Player", back_populates="baseball_stats")

    __table_args__ = (
        Index("ix_bbstats_player_season", "player_id", "season"),
    )


class StatcastMetrics(Base):
    __tablename__ = "statcast_metrics"

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    season = Column(Integer)
    exit_velo_avg = Column(Float)
    exit_velo_max = Column(Float)
    barrel_rate = Column(Float)
    hard_hit_rate = Column(Float)
    xba = Column(Float)
    xslg = Column(Float)
    xwoba = Column(Float)
    sprint_speed = Column(Float)
    fetched_at = Column(DateTime, default=datetime.utcnow)

    player = relationship("Player")

    __table_args__ = (
        Index("ix_statcast_player_season", "player_id", "season"),
    )
