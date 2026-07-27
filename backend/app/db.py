from collections.abc import Generator

from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings
from app.database_engine import create_database_engine


class Base(DeclarativeBase):
    """Base class that supplies SQLAlchemy metadata for models and Alembic."""

    pass


settings = get_settings()
engine = create_database_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Provide one database session per request and always close it afterward."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
