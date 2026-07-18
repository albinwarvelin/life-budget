from pydantic import BaseModel, Field


class CategoryPredictionRequest(BaseModel):
    """The fields that influence a category suggestion while entering a draft."""

    merchant: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=240)
    account_id: int | None = Field(default=None, ge=1)
    transaction_type: str | None = Field(default=None, max_length=15)


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
