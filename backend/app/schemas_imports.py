from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    transaction_date: date
    merchant: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=240)
    signed_amount: Decimal = Field(decimal_places=2)
    currency_code: str = Field(min_length=3, max_length=3)
    account_id: int = Field(ge=1)
    transaction_type: Literal["expense", "income", "reimbursement", "savings", "transfer"]
    category_id: int | None = Field(default=None, ge=1)
    notes: str | None = None

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
