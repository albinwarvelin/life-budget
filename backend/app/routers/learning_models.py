from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.description_learning_db import get_description_learning_db
from app.learning_db import get_learning_db
from app.models import Category
from app.repositories.category_learning import count_learning_events, list_patterns
from app.repositories.description_learning import (
    count_description_events,
    list_description_patterns,
)
from app.repositories.type_learning import count_type_events, list_type_patterns
from app.schemas_learning import (
    ExplorerModelResponse,
    ExplorerPattern,
    ExplorerScoringConfig,
    ExplorerTarget,
)
from app.services.category_learning import ACCOUNT_MULTIPLIER, SIGNAL_WEIGHTS, SIMILARITY_THRESHOLD
from app.services.description_learning import (
    DESCRIPTION_SIGNAL_WEIGHTS,
    DESCRIPTION_SIMILARITY_THRESHOLD,
)
from app.services.type_learning import TYPE_SIGNAL_WEIGHTS, TYPE_SIMILARITY_THRESHOLD
from app.type_learning_db import get_type_learning_db

router = APIRouter()


@router.get("/learning-models/category", response_model=ExplorerModelResponse)
def category_model(
    limit: int = Query(default=2000, ge=1, le=5000),
    db: Session = Depends(get_db),
    learning_db: Session = Depends(get_learning_db),
) -> ExplorerModelResponse:
    categories = list(db.scalars(select(Category).where(Category.is_active.is_(True))))
    return ExplorerModelResponse(
        model_kind="category",
        targets=[
            ExplorerTarget(
                key=str(category.id),
                label=category.name,
                localized_names=category.localized_names,
            )
            for category in categories
        ],
        patterns=[
            ExplorerPattern(
                id=pattern.id,
                pattern_type=pattern.pattern_type,
                pattern_text=pattern.pattern_text,
                target_key=str(pattern.category_id),
                weight=pattern.weight,
                observations=pattern.observations,
                account_id=pattern.account_id,
                transaction_type=pattern.transaction_type,
                category_id=pattern.category_id,
            )
            for pattern in list_patterns(learning_db, limit=limit)
        ],
        event_count=count_learning_events(learning_db),
        scoring=ExplorerScoringConfig(
            signal_weights=SIGNAL_WEIGHTS,
            account_multiplier=ACCOUNT_MULTIPLIER,
            similarity_threshold=SIMILARITY_THRESHOLD,
        ),
    )


@router.get("/learning-models/type", response_model=ExplorerModelResponse)
def type_model(
    limit: int = Query(default=2000, ge=1, le=5000),
    learning_db: Session = Depends(get_type_learning_db),
) -> ExplorerModelResponse:
    patterns = list_type_patterns(learning_db, limit=limit)
    target_keys = sorted({pattern.transaction_type for pattern in patterns})
    return ExplorerModelResponse(
        model_kind="type",
        targets=[
            ExplorerTarget(key=key, label=key.replace("_", " ").title()) for key in target_keys
        ],
        patterns=[
            ExplorerPattern(
                id=pattern.id,
                pattern_type=pattern.pattern_type,
                pattern_text=pattern.pattern_text,
                target_key=pattern.transaction_type,
                weight=pattern.weight,
                observations=pattern.observations,
                transaction_type=pattern.transaction_type,
                category_id=pattern.category_id,
            )
            for pattern in patterns
        ],
        event_count=count_type_events(learning_db),
        scoring=ExplorerScoringConfig(
            signal_weights=TYPE_SIGNAL_WEIGHTS,
            similarity_threshold=TYPE_SIMILARITY_THRESHOLD,
        ),
    )


@router.get("/learning-models/description", response_model=ExplorerModelResponse)
def description_model(
    limit: int = Query(default=2000, ge=1, le=5000),
    learning_db: Session = Depends(get_description_learning_db),
) -> ExplorerModelResponse:
    patterns = list_description_patterns(learning_db, limit=limit)
    labels = {pattern.description_normalized: pattern.description_text for pattern in patterns}
    return ExplorerModelResponse(
        model_kind="description",
        targets=[ExplorerTarget(key=key, label=label) for key, label in sorted(labels.items())],
        patterns=[
            ExplorerPattern(
                id=pattern.id,
                pattern_type=pattern.pattern_type,
                pattern_text=pattern.pattern_text,
                target_key=pattern.description_normalized,
                weight=pattern.weight,
                observations=pattern.observations,
            )
            for pattern in patterns
        ],
        event_count=count_description_events(learning_db),
        scoring=ExplorerScoringConfig(
            signal_weights=DESCRIPTION_SIGNAL_WEIGHTS,
            similarity_threshold=DESCRIPTION_SIMILARITY_THRESHOLD,
        ),
    )
