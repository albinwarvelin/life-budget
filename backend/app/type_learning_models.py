from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.type_learning_db import TypeLearningBase


class TypeLearningEvent(TypeLearningBase):
    """One user-approved signed amount and its final transaction type."""

    __tablename__ = "type_learning_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    amount_sign: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    amount_band: Mapped[str | None] = mapped_column(String(30), index=True)
    currency_code: Mapped[str | None] = mapped_column(String(3))
    merchant_normalized: Mapped[str] = mapped_column(String(160), nullable=False)
    category_id: Mapped[int | None] = mapped_column(index=True)
    transaction_type: Mapped[str] = mapped_column(String(15), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="screenshot")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


class TypePattern(TypeLearningBase):
    """A transparent weighted feature-to-transaction-type connection."""

    __tablename__ = "type_patterns"
    __table_args__ = (
        UniqueConstraint(
            "pattern_type",
            "pattern_text",
            "category_id",
            "transaction_type",
            name="uq_type_pattern_connection",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pattern_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    pattern_text: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    category_id: Mapped[int | None] = mapped_column(index=True)
    transaction_type: Mapped[str] = mapped_column(String(15), nullable=False, index=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    observations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )
