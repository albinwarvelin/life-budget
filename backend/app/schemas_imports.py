from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ImportDraftResponse(BaseModel):
    id: int
    row_index: int
    raw_text: str
    raw_amount_text: str | None
    source_bounds: dict[str, int] | None
    transaction_date: date | None
    merchant: str | None
    description: str | None
    predicted_description: str | None
    signed_amount: Decimal | None
    currency_code: str
    account_id: int
    predicted_category_id: int | None
    predicted_transaction_type: str | None
    category_confidence: float
    type_confidence: float
    description_confidence: float
    extraction_confidence: float
    validation_errors: list[str]
    possible_duplicate: bool
    status: str
    model_config = ConfigDict(from_attributes=True)


class ImportBatchResponse(BaseModel):
    id: int
    original_filename: str
    content_type: str
    account_id: int
    currency_code: str
    status: str
    progress: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    drafts: list[ImportDraftResponse]
    model_config = ConfigDict(from_attributes=True)


class ApprovedImportRow(BaseModel):
    """The final values explicitly confirmed in the review dialog."""

    draft_id: int
    accepted: bool = True
    # Rejected OCR drafts deliberately need no valid transaction values. The
    # review UI must be able to exclude a row precisely because OCR left one
    # of these fields blank or malformed.
    transaction_date: date | None = None
    merchant: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=240)
    signed_amount: Decimal | None = Field(default=None, decimal_places=2)
    currency_code: str = Field(min_length=3, max_length=3)
    account_id: int = Field(ge=1)
    transaction_type: Literal["expense", "income", "reimbursement", "savings", "transfer"]
    category_id: int | None = Field(default=None, ge=1)
    notes: str | None = None

    @model_validator(mode="before")
    @classmethod
    def ignore_invalid_transaction_fields_for_rejected_rows(cls, value):
        """Allow an unreadable OCR row to be explicitly rejected.

        Empty strings cannot be parsed as dates or decimals. Clearing these
        fields before field validation is safe only for rejected rows because
        the approval service never creates a transaction from them.
        """
        if isinstance(value, dict) and value.get("accepted") is False:
            rejected = dict(value)
            rejected["transaction_date"] = None
            rejected["merchant"] = None
            rejected["signed_amount"] = None
            return rejected
        return value

    @model_validator(mode="after")
    def require_complete_accepted_row(self):
        """Give one clear error if an accepted OCR row is incomplete."""
        if not self.accepted:
            return self
        missing = [
            label
            for label, field_value in (
                ("date", self.transaction_date),
                ("merchant", self.merchant),
                ("amount", self.signed_amount),
            )
            if field_value is None
        ]
        if missing:
            raise ValueError(f"Accepted rows require: {', '.join(missing)}")
        return self

    @field_validator("currency_code")
    @classmethod
    def uppercase_currency(cls, value: str) -> str:
        return value.upper()


class ApproveImportRequest(BaseModel):
    rows: list[ApprovedImportRow] = Field(min_length=1)


class ApproveImportResponse(BaseModel):
    batch_id: int
    created_transaction_ids: list[int]
    rejected_draft_ids: list[int]
