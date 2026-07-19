from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.description_learning_db import DescriptionLearningBase


class DescriptionLearningEvent(DescriptionLearningBase):
    """One user-approved description and the context that produced it."""

    __tablename__ = "description_learning_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    merchant_normalized: Mapped[str] = mapped_column(String(160), nullable=False)
    amount_band: Mapped[str | None] = mapped_column(String(30), index=True)
    currency_code: Mapped[str | None] = mapped_column(String(3))
    category_id: Mapped[int | None] = mapped_column(index=True)
    transaction_type: Mapped[str | None] = mapped_column(String(15), index=True)
    description_text: Mapped[str] = mapped_column(String(240), nullable=False)
    description_normalized: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="screenshot")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


class DescriptionPattern(DescriptionLearningBase):
    """An explainable feature-to-description connection."""

    __tablename__ = "description_patterns"
    __table_args__ = (
        UniqueConstraint(
            "pattern_type",
            "pattern_text",
            "description_normalized",
            name="uq_description_pattern_connection",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pattern_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    pattern_text: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    description_normalized: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    description_text: Mapped[str] = mapped_column(String(240), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    observations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )
