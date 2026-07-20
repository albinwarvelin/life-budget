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
    DescriptionPredictionCandidateResponse,
    DescriptionPredictionContributionResponse,
    DescriptionPredictionRequest,
    DescriptionPredictionResponse,
    ExplorerModelResponse,
    ExplorerPattern,
    ExplorerScoringConfig,
    ExplorerTarget,
)
from app.services.category_learning import ACCOUNT_MULTIPLIER, SIGNAL_WEIGHTS, SIMILARITY_THRESHOLD
from app.services.description_learning import (
    DESCRIPTION_MIN_CONFIDENCE,
    DESCRIPTION_SIGNAL_WEIGHTS,
    DESCRIPTION_SIMILARITY_THRESHOLD,
    predict_description,
)
from app.services.type_learning import TYPE_SIGNAL_WEIGHTS, TYPE_SIMILARITY_THRESHOLD
from app.type_learning_db import get_type_learning_db

router = APIRouter()


def _category_signal_labels(
    pattern_type: str,
    pattern_text: str,
    category: Category | None,
) -> tuple[str | None, dict[str, str]]:
    """Return readable labels and never expose internal category IDs."""
    if category is None:
        return None, {}
    names = {
        locale: category.localized_names.get(locale) or category.name for locale in ("en", "sv")
    }
    if pattern_type == "category":
        return category.name, names
    if pattern_type in {"merchant_category", "merchant_token_category"}:
        merchant = pattern_text.rsplit("|", 1)[0]
        return (
            f"{merchant} / {category.name}",
            {locale: f"{merchant} / {name}" for locale, name in names.items()},
        )
    if pattern_type == "category_amount_band":
        amount = pattern_text.split("|", 1)[-1]
        return (
            f"{category.name} / {amount}",
            {locale: f"{name} / {amount}" for locale, name in names.items()},
        )
    if pattern_type == "category_transaction_type":
        transaction_type = pattern_text.split("|", 1)[-1]
        return (
            f"{category.name} / {transaction_type}",
            {locale: f"{name} / {transaction_type}" for locale, name in names.items()},
        )
    if pattern_type in {"merchant_category_amount_band", "merchant_token_category_band"}:
        merchant, _, amount = pattern_text.split("|", 2)
        return (
            f"{merchant} / {category.name} / {amount}",
            {locale: f"{merchant} / {name} / {amount}" for locale, name in names.items()},
        )
    return None, {}


def _description_pattern_category_id(pattern_type: str, pattern_text: str) -> int | None:
    """Read the category feature ID encoded in description-model pattern text."""
    if pattern_type in {"category", "category_amount_band", "category_transaction_type"}:
        category_text = pattern_text.split("|", 1)[0]
    elif pattern_type in {
        "merchant_category",
        "merchant_token_category",
        "merchant_category_amount_band",
        "merchant_token_category_band",
    }:
        parts = pattern_text.split("|")
        category_text = parts[1] if len(parts) > 1 else ""
    else:
        return None
    try:
        return int(category_text)
    except ValueError:
        return None


def _signal_category_id(pattern_type: str, pattern_text: str) -> int | None:
    """Find a category ID used by a signal for display-label lookup only."""
    if pattern_type == "category":
        try:
            return int(pattern_text)
        except ValueError:
            return None
    return _description_pattern_category_id(pattern_type, pattern_text)


@router.get("/learning-models/category", response_model=ExplorerModelResponse)
def category_model(
    limit: int = Query(default=2000, ge=1, le=5000),
    db: Session = Depends(get_db),
    learning_db: Session = Depends(get_learning_db),
) -> ExplorerModelResponse:
    categories = list(db.scalars(select(Category).where(Category.is_active.is_(True))))
    category_map = {category.id: category for category in categories}
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
                display_text=_category_signal_labels(
                    pattern.pattern_type,
                    pattern.pattern_text,
                    category_map.get(
                        _signal_category_id(pattern.pattern_type, pattern.pattern_text)
                    ),
                )[0],
                localized_display_texts=_category_signal_labels(
                    pattern.pattern_type,
                    pattern.pattern_text,
                    category_map.get(
                        _signal_category_id(pattern.pattern_type, pattern.pattern_text)
                    ),
                )[1],
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
    db: Session = Depends(get_db),
    learning_db: Session = Depends(get_type_learning_db),
) -> ExplorerModelResponse:
    patterns = list_type_patterns(learning_db, limit=limit)
    categories = {category.id: category for category in db.scalars(select(Category))}
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
                display_text=_category_signal_labels(
                    pattern.pattern_type,
                    pattern.pattern_text,
                    categories.get(pattern.category_id),
                )[0],
                localized_display_texts=_category_signal_labels(
                    pattern.pattern_type,
                    pattern.pattern_text,
                    categories.get(pattern.category_id),
                )[1],
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
    db: Session = Depends(get_db),
    learning_db: Session = Depends(get_description_learning_db),
) -> ExplorerModelResponse:
    patterns = list_description_patterns(learning_db, limit=limit)
    categories = {category.id: category for category in db.scalars(select(Category))}
    labels = {pattern.description_normalized: pattern.description_text for pattern in patterns}
    return ExplorerModelResponse(
        model_kind="description",
        targets=[ExplorerTarget(key=key, label=label) for key, label in sorted(labels.items())],
        patterns=[
            ExplorerPattern(
                id=pattern.id,
                pattern_type=pattern.pattern_type,
                pattern_text=pattern.pattern_text,
                display_text=_category_signal_labels(
                    pattern.pattern_type,
                    pattern.pattern_text,
                    categories.get(
                        _description_pattern_category_id(pattern.pattern_type, pattern.pattern_text)
                    ),
                )[0],
                localized_display_texts=_category_signal_labels(
                    pattern.pattern_type,
                    pattern.pattern_text,
                    categories.get(
                        _description_pattern_category_id(pattern.pattern_type, pattern.pattern_text)
                    ),
                )[1],
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
            minimum_confidence=DESCRIPTION_MIN_CONFIDENCE,
        ),
    )


@router.post(
    "/learning-models/description/predict",
    response_model=DescriptionPredictionResponse,
)
def test_description_prediction(
    payload: DescriptionPredictionRequest,
    learning_db: Session = Depends(get_description_learning_db),
) -> DescriptionPredictionResponse:
    """Run an explainable prediction without recording a learning event."""
    prediction = predict_description(
        learning_db,
        merchant=payload.merchant,
        amount=payload.amount,
        currency_code=payload.currency_code.upper(),
        category_id=payload.category_id,
        transaction_type=payload.transaction_type,
    )
    return DescriptionPredictionResponse(
        description=prediction.description,
        confidence=prediction.confidence,
        reason=prediction.reason,
        candidates=[
            DescriptionPredictionCandidateResponse(
                description=candidate.description,
                score=candidate.score,
                relative_score=candidate.relative_score,
                contributions=[
                    DescriptionPredictionContributionResponse(**vars(contribution))
                    for contribution in candidate.contributions
                ],
            )
            for candidate in prediction.candidates
        ],
    )
