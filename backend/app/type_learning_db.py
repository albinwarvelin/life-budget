from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


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


def ensure_type_learning_schema() -> None:
    """Bootstrap a new local store and keep it compatible with its Alembic chain."""
    from app.type_learning_models import TypeLearningEvent, TypePattern  # noqa: F401

    inspector = inspect(type_learning_engine)
    if "alembic_version" in inspector.get_table_names():
        return
    TypeLearningBase.metadata.create_all(type_learning_engine)
    with type_learning_engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS alembic_version "
                "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES ('0001_type_learning')")
        )


def get_type_learning_db() -> Generator[Session, None, None]:
    ensure_type_learning_schema()
    with TypeLearningSessionLocal() as db:
        yield db
