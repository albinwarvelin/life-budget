from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or a local .env file."""

    app_env: str = "development"
    database_url: str = "sqlite:///./life_budget.db"
    # All prediction heads share one revisioned training projection. Financial
    # records remain in the primary database and are never rewritten by ML.
    prediction_database_url: str = "sqlite:///./life_budget_predictions.db"
    frontend_origin: str = "http://localhost:5173"
    # A production build is served by FastAPI so the local application needs
    # only one long-running process and all browser requests stay same-origin.
    frontend_dist_dir: str = str(Path(__file__).resolve().parents[2] / "frontend" / "dist")
    upload_dir: str = "uploads"
    tesseract_command: str = "tesseract"
    tesseract_languages: str = "eng+swe+nor"

    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Return one cached settings object so the app and Alembic share configuration."""
    return Settings()
