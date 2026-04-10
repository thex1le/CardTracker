# Import all models so Base.metadata knows about them
from app.models.base import Player, ProspectRanking, Signal, Card, PricePoint, SentimentEvent, CompositeScore  # noqa
from app.models.baseball import PlayerStatsBaseball, StatcastMetrics  # noqa
from app.models.watchlist import WatchlistItem, AlertPreference, UserAlert  # noqa
