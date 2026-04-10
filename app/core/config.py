from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./cardedge.db"
    ebay_app_id: str = ""
    ebay_cert_id: str = ""
    ebay_token: str = ""
    mlb_stats_api_base: str = "https://statsapi.mlb.com/api/v1"
    environment: str = "development"
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
