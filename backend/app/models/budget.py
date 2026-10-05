from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    JSON,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Currency(Base):
    """A supported currency identified by its uppercase three-letter code."""

    __tablename__ = "currencies"

    code: Mapped[str] = mapped_column(String(3), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    accounts: Mapped[list["Account"]] = relationship(back_populates="currency")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="currency")


class Account(Base):
    """A money-holding account whose balance is expressed in one currency."""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    account_type: Mapped[str] = mapped_column(String(30), nullable=False)
    currency_code: Mapped[str] = mapped_column(ForeignKey("currencies.code"), nullable=False)
    institution: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    currency: Mapped[Currency] = relationship(back_populates="accounts")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")


class Category(Base):
    """An expense or income label, optionally nested under a parent category."""

    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('expense', 'income', 'reimbursement', 'savings')", name="ck_categories_kind"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Keep the legacy name as a fallback while storing the user-facing labels
    # separately for each supported UI language.
    localized_names: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    kind: Mapped[str] = mapped_column(String(15), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    parent: Mapped["Category | None"] = relationship(remote_side="Category.id")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="category")


class Transaction(Base):
    """A manual financial event; savings and transfers may use signed amounts."""

    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint(
            "transaction_type IN ('expense', 'income', 'reimbursement', 'savings', 'transfer')",
            name="ck_transactions_type",
        ),
        CheckConstraint(
            "amount >= 0 OR transaction_type IN ('savings', 'transfer')",
            name="ck_transactions_amount_non_negative",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency_code: Mapped[str] = mapped_column(ForeignKey("currencies.code"), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(15), nullable=False)
    description: Mapped[str | None] = mapped_column(String(240))
    merchant: Mapped[str] = mapped_column(String(160), nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="manual")
    # Preserve the approved source row independently of insertion time. A
    # removed draft must not delete the financial record it originally created.
    import_draft_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_draft_rows.id", ondelete="SET NULL"), unique=True, index=True
    )
    attachment_filename: Mapped[str | None] = mapped_column(String(255))
    attachment_path: Mapped[str | None] = mapped_column(String(500))
    attachment_content_type: Mapped[str | None] = mapped_column(String(120))
    attachment_size: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    account: Mapped[Account] = relationship(back_populates="transactions")
    currency: Mapped[Currency] = relationship(back_populates="transactions")
    category: Mapped[Category | None] = relationship(back_populates="transactions")


class ImportBatch(Base):
    """One locally stored screenshot moving through extraction and review."""

    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="screenshot")
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    currency_code: Mapped[str] = mapped_column(ForeignKey("currencies.code"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", index=True)
    progress: Mapped[int] = mapped_column(nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    drafts: Mapped[list["ImportDraftRow"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan", order_by="ImportDraftRow.row_index"
    )


class ImportDraftRow(Base):
    """Editable OCR output that cannot affect finances until explicit approval."""

    __tablename__ = "import_draft_rows"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("import_batches.id"), nullable=False, index=True
    )
    row_index: Mapped[int] = mapped_column(nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    raw_amount_text: Mapped[str | None] = mapped_column(String(80))
    source_bounds: Mapped[dict[str, int] | None] = mapped_column(JSON)
    transaction_date: Mapped[date | None] = mapped_column(Date)
    merchant: Mapped[str | None] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(String(240))
    # Keep the model output separate from the editable value for auditability.
    predicted_description: Mapped[str | None] = mapped_column(String(240))
    signed_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    account_id: Mapped[int] = mapped_column(nullable=False)
    predicted_category_id: Mapped[int | None] = mapped_column()
    predicted_transaction_type: Mapped[str | None] = mapped_column(String(15))
    category_confidence: Mapped[float] = mapped_column(nullable=False, default=0.0)
    type_confidence: Mapped[float] = mapped_column(nullable=False, default=0.0)
    description_confidence: Mapped[float] = mapped_column(nullable=False, default=0.0)
    extraction_confidence: Mapped[float] = mapped_column(nullable=False, default=0.0)
    validation_errors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    possible_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    batch: Mapped[ImportBatch] = relationship(back_populates="drafts")
