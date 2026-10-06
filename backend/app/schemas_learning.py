"""Explicit API contracts for local reviewed-data predictions."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

TransactionType = Literal["expense", "income", "reimbursement", "savings", "transfer"]


class CategoryPredictionRequest(BaseModel):
    merchant: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=240)
    account_id: int | None = Field(default=None, ge=1)
    transaction_type: TransactionType | None = None
    amount: Decimal | None = Field(default=None, decimal_places=2, max_digits=18)
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)


class CategoryPrediction(BaseModel):
    category_id: int
    confidence: float = Field(ge=0, le=1)
    reason: str


class PredictionRequest(BaseModel):
    merchant: str = Field(min_length=1, max_length=160)
    amount: Decimal = Field(decimal_places=2, max_digits=18)
    currency_code: str = Field(min_length=3, max_length=3)
    account_id: int | None = Field(default=None, ge=1)


class Contribution(BaseModel):
    feature: str
    contribution: float


class Candidate(BaseModel):
    key: str
    label: str
    probability: float = Field(ge=0, le=1)
    support: int
    contributions: list[Contribution]


class PredictionOutput(BaseModel):
    suggestion: str | None
    confidence: float = Field(ge=0, le=1)
    calibrated: bool
    reason: str
    candidates: list[Candidate]
    context_weight: float = Field(default=0, ge=0, le=0.5)


class PredictionResponse(BaseModel):
    snapshot_id: int
    outputs: dict[str, PredictionOutput]


class HeadStatus(BaseModel):
    labels: int
    calibrated: bool
    threshold: float
    regularization: float
    temperature: float


class ModelConfiguration(BaseModel):
    regularization_candidates: list[float]
    temperature_candidates: list[float]
    threshold_candidates: list[float]
    suggestion_thresholds: dict[str, float]
    description_blend_candidates: list[float]
    description_context_min_rows: int
    minimum_support: int
    minimum_validation_samples: int
    target_precision: float
    wilson_z: float
    train_fraction: float
    validation_fraction: float
    word_ngram_range: tuple[int, int]
    character_ngram_range: tuple[int, int]
    word_features: int
    character_features: int
    amount_centers: int
    amount_width: float


class ModelStatus(BaseModel):
    reviewed_transactions: int
    pending_updates: int
    updates_since_training: int
    needs_retraining: bool
    snapshot_id: int | None
    dataset_revision: int
    algorithm: str | None
    created_at: datetime | None
    report: dict | None
    heads: dict[str, HeadStatus]
    configuration: ModelConfiguration
