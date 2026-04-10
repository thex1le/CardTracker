from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./cardscout.db"
    app_name: str = "CardScout"
    debug: bool = True
    cache_ttl: int = 3600  # 1 hour
    redis_url: str = "redis://localhost:6379/0"
    # Sync DB URL for Celery tasks (SQLite without aiosqlite)
    sync_database_url: str = "sqlite:///./cardscout.db"
    # NewsAPI key (free tier: 100 req/day) — get one at newsapi.org
    newsapi_key: str = ""

    model_config = {"env_file": ".env"}


settings = Settings()
