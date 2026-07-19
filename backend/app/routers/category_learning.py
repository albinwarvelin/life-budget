from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.learning_db import get_learning_db
from app.models import Category
from app.schemas_learning import (
    CategoryLearningRequest,
    LearningCategory,
    LearningModelResponse,
    LearningPattern,
    LearningScoringConfig,
    CategoryPrediction,
    CategoryPredictionRequest,
)
from app.repositories.category_learning import count_learning_events, list_patterns
from app.services.category_learning import (
    ACCOUNT_MULTIPLIER,
    SIGNAL_WEIGHTS,
    SIMILARITY_THRESHOLD,
    predict_categories,
    record_learning_event,
)

router = APIRouter()


@router.get("/category-learning/model", response_model=LearningModelResponse)
def get_learning_model(
    limit: int = Query(default=2000, ge=1, le=5000),
    db: Session = Depends(get_db),
    learning_db: Session = Depends(get_learning_db),
) -> LearningModelResponse:
    """Return a read-only, privacy-conscious snapshot for the model explorer."""
    categories = list(db.scalars(select(Category).where(Category.is_active.is_(True))))
    return LearningModelResponse(
        categories=[
            LearningCategory(
                id=category.id,
                name=category.name,
                localized_names=category.localized_names,
                kind=category.kind,
            )
            for category in categories
        ],
        patterns=[
            LearningPattern.model_validate(pattern, from_attributes=True)
            for pattern in list_patterns(learning_db, limit=limit)
        ],
        event_count=count_learning_events(learning_db),
        scoring=LearningScoringConfig(
            signal_weights=SIGNAL_WEIGHTS,
            account_multiplier=ACCOUNT_MULTIPLIER,
            similarity_threshold=SIMILARITY_THRESHOLD,
        ),
    )


@router.post("/category-suggestions", response_model=list[CategoryPrediction])
def suggest_categories(
    payload: CategoryPredictionRequest,
    db: Session = Depends(get_db),
    learning_db: Session = Depends(get_learning_db),
) -> list[CategoryPrediction]:
    """Return ranked, explainable category suggestions for a draft transaction."""
    return predict_categories(db, learning_db, payload)


@router.post(
    "/category-learning/events",
    status_code=status.HTTP_204_NO_CONTENT,
)
def create_learning_event(
    payload: CategoryLearningRequest,
    db: Session = Depends(get_db),
) -> None:
    """Record an explicit user correction without exposing the learning database."""
    if db.get(Category, payload.category_id) is None:
        raise HTTPException(status_code=404, detail="Category not found")
    record_learning_event(
        category_id=payload.category_id,
        merchant=payload.merchant,
        description=payload.description,
        account_id=payload.account_id,
        transaction_type=payload.transaction_type,
        amount=payload.amount,
        currency_code=payload.currency_code,
        source=payload.source,
    )
