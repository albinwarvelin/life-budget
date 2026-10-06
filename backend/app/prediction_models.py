from datetime import datetime

from sqlalchemy import Boolean, DateTime, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.prediction_db import PredictionBase


class TrainingExample(PredictionBase):
    """At most one current example per transaction; tombstones prevent resurrection."""

    __tablename__ = "training_examples"
    transaction_id: Mapped[int] = mapped_column(primary_key=True)
    revision: Mapped[int] = mapped_column(nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class ModelSnapshot(PredictionBase):
    """JSON parameters only: no executable pickle or untrusted model loading."""

    __tablename__ = "model_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_revision: Mapped[int] = mapped_column(index=True)
    algorithm_version: Mapped[str] = mapped_column(String(40))
    parameters: Mapped[dict] = mapped_column(JSON)
    report: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class PredictionState(PredictionBase):
    __tablename__ = "prediction_state"
    id: Mapped[int] = mapped_column(primary_key=True)
    initialized: Mapped[bool] = mapped_column(Boolean, default=False)
    dataset_revision: Mapped[int] = mapped_column(default=0)
    active_snapshot_id: Mapped[int | None] = mapped_column()
