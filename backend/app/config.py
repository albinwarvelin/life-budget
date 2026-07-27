from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or a local .env file."""

    app_env: str = "development"
    database_url: str = "sqlite:///./life_budget.db"
    # Keep learned merchant/category patterns isolated from financial records.
    learning_database_url: str = "sqlite:///./life_budget_learning.db"
    # Transaction-type learning is isolated as requested so its signals and
    # migration history can evolve independently from category learning.
    type_learning_database_url: str = "sqlite:///./life_budget_type_learning.db"
    # Free-text description suggestions have their own replaceable model store.
    description_learning_database_url: str = "sqlite:///./life_budget_description_learning.db"
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
