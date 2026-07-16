from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CurrencyCreate(BaseModel):
    """Input for adding a currency to the user's explicit currency catalog."""

    code: str = Field(min_length=3, max_length=3)
    name: str = Field(min_length=1, max_length=100)

    @field_validator("code")
    @classmethod
    def uppercase_code(cls, value: str) -> str:
        return value.upper()


class CurrencyResponse(CurrencyCreate):
    model_config = ConfigDict(from_attributes=True)


class AccountCreate(BaseModel):
    """Input for an account; the route verifies that the currency exists."""

    name: str = Field(min_length=1, max_length=120)
    account_type: str = Field(min_length=1, max_length=30)
    currency_code: str = Field(min_length=3, max_length=3)
    institution: str | None = Field(default=None, max_length=120)

    @field_validator("currency_code")
    @classmethod
    def uppercase_currency(cls, value: str) -> str:
        return value.upper()


class AccountResponse(AccountCreate):
    id: int
    is_active: bool
    model_config = ConfigDict(from_attributes=True)


class CategoryCreate(BaseModel):
    """Input for a category whose kind controls which transactions may use it."""

    name: str = Field(min_length=1, max_length=120)
    kind: Literal["expense", "income"]
    parent_id: int | None = None


class CategoryResponse(CategoryCreate):
    id: int
    is_active: bool
    model_config = ConfigDict(from_attributes=True)


class TransactionCreate(BaseModel):
    """Input for a transaction before database relationship checks are performed."""

    transaction_date: date
    account_id: int
    amount: Decimal = Field(ge=0, decimal_places=2)
    currency_code: str = Field(min_length=3, max_length=3)
    transaction_type: Literal["expense", "income", "transfer"]
    description: str = Field(min_length=1, max_length=240)
    merchant: str | None = Field(default=None, max_length=160)
    category_id: int | None = None
    notes: str | None = None
    source: str = Field(default="manual", max_length=30)

    @field_validator("currency_code")
    @classmethod
    def uppercase_currency(cls, value: str) -> str:
        return value.upper()


class TransactionResponse(TransactionCreate):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
