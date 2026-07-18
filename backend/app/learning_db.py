from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class LearningBase(DeclarativeBase):
    """Metadata for the private category-learning database."""


settings = get_settings()
connect_args = (
    {"check_same_thread": False} if settings.learning_database_url.startswith("sqlite") else {}
)
learning_engine = create_engine(settings.learning_database_url, connect_args=connect_args)
LearningSessionLocal = sessionmaker(bind=learning_engine, autoflush=False, expire_on_commit=False)


def ensure_learning_schema() -> None:
    """Create the small learning schema when the service first needs it."""
    # This database is deliberately independent from the Alembic-managed
    # financial database. It contains no balances, transactions, or account
    # names—only normalized learning signals and anonymous IDs.
    from app.learning_models import CategoryLearningEvent, CategoryPattern  # noqa: F401

    inspector = inspect(learning_engine)
    if "alembic_version" in inspector.get_table_names():
        return
    # Bootstrap an untouched development checkout so the API remains usable
    # before the documented migration command has been run. Stamping the
    # initial revision keeps this fallback compatible with the learning
    # Alembic chain; future revisions will then be applied normally.
    LearningBase.metadata.create_all(learning_engine)
    with learning_engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO alembic_version (version_num) VALUES ('0001_initial_learning_schema')"
            )
        )


def get_learning_db() -> Generator[Session, None, None]:
    """Provide a session to the isolated learning store."""
    ensure_learning_schema()
    db = LearningSessionLocal()
    try:
        yield db
    finally:
        db.close()
