from decimal import Decimal

from pydantic import BaseModel, Field


class CategoryPredictionRequest(BaseModel):
    """The fields that influence a category suggestion while entering a draft."""

    merchant: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=240)
    account_id: int | None = Field(default=None, ge=1)
    transaction_type: str | None = Field(default=None, max_length=15)
    amount: Decimal | None = Field(default=None, decimal_places=2)
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)


class CategoryPrediction(BaseModel):
    category_id: int
    confidence: float = Field(ge=0, le=1)
    reason: str


class CategoryLearningRequest(CategoryPredictionRequest):
    """A category selected or confirmed by the user."""

    category_id: int = Field(ge=1)
    source: str = Field(default="manual", max_length=30)


class LearningCategory(BaseModel):
    """The category metadata needed to label the model graph."""

    id: int
    name: str
    localized_names: dict[str, str]
    kind: str


class LearningPattern(BaseModel):
    """One weighted phrase-to-category connection in the learned model."""

    id: int
    pattern_type: str
    pattern_text: str
    category_id: int
    account_id: int | None
    transaction_type: str | None
    weight: float
    observations: int


class LearningScoringConfig(BaseModel):
    """Public scoring constants so the teaching UI can explain the model."""

    signal_weights: dict[str, float]
    account_multiplier: float
    similarity_threshold: float


class LearningModelResponse(BaseModel):
    """A safe graph snapshot; individual learning events are intentionally omitted."""

    categories: list[LearningCategory]
    patterns: list[LearningPattern]
    event_count: int
    scoring: LearningScoringConfig


class ExplorerTarget(BaseModel):
    """One prediction output shown on the right side of any model graph."""

    key: str
    label: str
    localized_names: dict[str, str] = Field(default_factory=dict)


class ExplorerPattern(BaseModel):
    """A model-neutral feature-to-output connection for the explorer."""

    id: int
    pattern_type: str
    pattern_text: str
    display_text: str | None = None
    localized_display_texts: dict[str, str] = Field(default_factory=dict)
    target_key: str
    weight: float
    observations: int
    account_id: int | None = None
    transaction_type: str | None = None
    category_id: int | None = None


class ExplorerScoringConfig(BaseModel):
    signal_weights: dict[str, float]
    similarity_threshold: float
    account_multiplier: float | None = None
    minimum_confidence: float | None = None


class ExplorerModelResponse(BaseModel):
    model_kind: str
    targets: list[ExplorerTarget]
    patterns: list[ExplorerPattern]
    event_count: int
    scoring: ExplorerScoringConfig


class DescriptionPredictionRequest(BaseModel):
    """Inputs accepted by the interactive description prediction tester."""

    merchant: str = Field(min_length=1, max_length=160)
    amount: Decimal = Field(decimal_places=2)
    currency_code: str = Field(min_length=3, max_length=3)
    category_id: int | None = Field(default=None, ge=1)
    transaction_type: str | None = Field(default=None, max_length=15)


class DescriptionPredictionContributionResponse(BaseModel):
    """One auditable term in a description candidate's calculated score."""

    signal_type: str
    signal_value: str
    matched_value: str
    description: str
    observations: int
    conditional_probability: float
    baseline_probability: float
    reliability: float
    similarity: float
    contribution: float


class DescriptionPredictionCandidateResponse(BaseModel):
    description: str
    score: float
    relative_score: float
    contributions: list[DescriptionPredictionContributionResponse]


class DescriptionPredictionResponse(BaseModel):
    description: str | None
    confidence: float = Field(ge=0, le=1)
    reason: str
    candidates: list[DescriptionPredictionCandidateResponse]
