from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or a local .env file."""

    app_env: str = "development"
    database_url: str = "sqlite:///./life_budget.db"
    # Keep learned merchant/category patterns isolated from financial records.
    learning_database_url: str = "sqlite:///./life_budget_learning.db"
    frontend_origin: str = "http://localhost:5173"
    upload_dir: str = "uploads"

    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Return one cached settings object so the app and Alembic share configuration."""
    return Settings()
