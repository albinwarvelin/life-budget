from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings
from app.migration_runner import upgrade_database_to_head


class TypeLearningBase(DeclarativeBase):
    """Metadata for the isolated transaction-type prediction database."""


settings = get_settings()
connect_args = (
    {"check_same_thread": False} if settings.type_learning_database_url.startswith("sqlite") else {}
)
type_learning_engine = create_engine(settings.type_learning_database_url, connect_args=connect_args)
TypeLearningSessionLocal = sessionmaker(
    bind=type_learning_engine, autoflush=False, expire_on_commit=False
)
_schema_ready = False


def ensure_type_learning_schema() -> None:
    """Upgrade the type learner once before its first use in this process."""
    global _schema_ready
    if _schema_ready:
        return
    upgrade_database_to_head("alembic_type_learning.ini")
    _schema_ready = True


def get_type_learning_db() -> Generator[Session, None, None]:
    ensure_type_learning_schema()
    with TypeLearningSessionLocal() as db:
        yield db
