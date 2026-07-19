from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class DescriptionLearningBase(DeclarativeBase):
    """Metadata for the isolated description-suggestion database."""


settings = get_settings()
connect_args = (
    {"check_same_thread": False}
    if settings.description_learning_database_url.startswith("sqlite")
    else {}
)
description_learning_engine = create_engine(
    settings.description_learning_database_url, connect_args=connect_args
)
DescriptionLearningSessionLocal = sessionmaker(
    bind=description_learning_engine, autoflush=False, expire_on_commit=False
)


def ensure_description_learning_schema() -> None:
    """Bootstrap a new model store while preserving an Alembic upgrade path."""
    from app.description_learning_models import (  # noqa: F401
        DescriptionLearningEvent,
        DescriptionPattern,
    )

    if "alembic_version" in inspect(description_learning_engine).get_table_names():
        return
    DescriptionLearningBase.metadata.create_all(description_learning_engine)
    with description_learning_engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS alembic_version "
                "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES ('0001_description_learning')")
        )


def get_description_learning_db() -> Generator[Session, None, None]:
    ensure_description_learning_schema()
    with DescriptionLearningSessionLocal() as db:
        yield db
