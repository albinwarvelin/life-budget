"""One replaceable local projection for all prediction heads."""

from threading import Lock

from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings
from app.database_engine import create_database_engine
from app.migration_runner import upgrade_database_to_head


class PredictionBase(DeclarativeBase):
    pass


prediction_engine = create_database_engine(get_settings().prediction_database_url)
PredictionSessionLocal = sessionmaker(bind=prediction_engine, expire_on_commit=False)
_schema_ready = False
_schema_lock = Lock()


def ensure_prediction_schema() -> None:
    global _schema_ready
    with _schema_lock:
        if not _schema_ready:
            upgrade_database_to_head("alembic_predictions.ini")
            _schema_ready = True
