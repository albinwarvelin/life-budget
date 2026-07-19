from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.learning_db import LearningBase


class CategoryLearningEvent(LearningBase):
    """An auditable, user-confirmed merchant/description categorization."""

    __tablename__ = "category_learning_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    merchant_normalized: Mapped[str] = mapped_column(String(160), index=True)
    description_normalized: Mapped[str] = mapped_column(String(240), default="")
    category_id: Mapped[int] = mapped_column(index=True)
    account_id: Mapped[int | None] = mapped_column(index=True)
    transaction_type: Mapped[str | None] = mapped_column(String(15))
    amount_band: Mapped[str | None] = mapped_column(String(30), index=True)
    currency_code: Mapped[str | None] = mapped_column(String(3))
    source: Mapped[str] = mapped_column(String(30), default="manual")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


class CategoryPattern(LearningBase):
    """A weighted connection between an input pattern and a category."""

    __tablename__ = "category_patterns"
    __table_args__ = (
        UniqueConstraint(
            "pattern_type",
            "pattern_text",
            "category_id",
            "account_id",
            "transaction_type",
            name="uq_category_pattern_connection",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pattern_type: Mapped[str] = mapped_column(String(20), index=True)
    pattern_text: Mapped[str] = mapped_column(String(320), index=True)
    category_id: Mapped[int] = mapped_column(index=True)
    account_id: Mapped[int | None] = mapped_column(index=True)
    transaction_type: Mapped[str | None] = mapped_column(String(15))
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    observations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )
