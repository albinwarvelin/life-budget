from collections.abc import Generator

from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings
from app.database_engine import create_database_engine
from app.migration_runner import upgrade_database_to_head


class DescriptionLearningBase(DeclarativeBase):
    """Metadata for the isolated description-suggestion database."""


settings = get_settings()
description_learning_engine = create_database_engine(settings.description_learning_database_url)
DescriptionLearningSessionLocal = sessionmaker(
    bind=description_learning_engine, autoflush=False, expire_on_commit=False
)
_schema_ready = False


def ensure_description_learning_schema() -> None:
    """Upgrade the description learner once before its first use in this process."""
    global _schema_ready
    if _schema_ready:
        return
    upgrade_database_to_head("alembic_description_learning.ini")
    _schema_ready = True


def get_description_learning_db() -> Generator[Session, None, None]:
    ensure_description_learning_schema()
    with DescriptionLearningSessionLocal() as db:
        yield db
