from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings
from app.migration_runner import upgrade_database_to_head


class LearningBase(DeclarativeBase):
    """Metadata for the private category-learning database."""


settings = get_settings()
connect_args = (
    {"check_same_thread": False} if settings.learning_database_url.startswith("sqlite") else {}
)
learning_engine = create_engine(settings.learning_database_url, connect_args=connect_args)
LearningSessionLocal = sessionmaker(bind=learning_engine, autoflush=False, expire_on_commit=False)
_schema_ready = False


def ensure_learning_schema() -> None:
    """Upgrade the category learner once before its first use in this process."""
    global _schema_ready
    if _schema_ready:
        return
    upgrade_database_to_head("alembic_learning.ini")
    _schema_ready = True


def get_learning_db() -> Generator[Session, None, None]:
    """Provide a session to the isolated, migrated learning store."""
    ensure_learning_schema()
    with LearningSessionLocal() as db:
        yield db
