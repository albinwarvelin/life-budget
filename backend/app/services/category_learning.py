import logging
import re
import unicodedata
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.learning_models import CategoryPattern
from app.models import Category, Transaction
from app.repositories.category_learning import (
    get_pattern,
    list_matching_patterns,
    save_learning_event,
)
from app.schemas_learning import CategoryPrediction, CategoryPredictionRequest
from app.learning_db import LearningSessionLocal, ensure_learning_schema

logger = logging.getLogger(__name__)

# These constants make the intentionally simple model inspectable and easy to
# tune. Full-field matches carry more evidence than individual word matches.
SIGNAL_WEIGHTS = {
    "merchant": 4.0,
    "merchant_token": 0.5,
    "description": 1.5,
    "description_token": 0.25,
    "combined": 2.0,
}
ACCOUNT_MULTIPLIER = 1.25
SIMILARITY_THRESHOLD = 0.72


def normalize_text(value: str | None) -> str:
    """Create a stable, privacy-conscious key for matching user-entered text."""
    if not value:
        return ""
    without_accents = "".join(
        character
        for character in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9]+", " ", without_accents.lower()).strip()


def tokenize(value: str | None) -> list[str]:
    """Return distinct words while preserving their first-seen order."""
    normalized = normalize_text(value)
    # Ignore one-character noise, but retain every meaningful word. The
    # distinct list prevents repeated words in one entry from multiplying one
    # learning event unfairly.
    return list(dict.fromkeys(token for token in normalized.split() if len(token) > 1))


def _connections(request: CategoryPredictionRequest) -> list[tuple[str, str, float]]:
    """Build full-field and per-word signals with deliberately different weights."""
    merchant = normalize_text(request.merchant)
    description = normalize_text(request.description)
    signals: list[tuple[str, str, float]] = [("merchant", merchant, SIGNAL_WEIGHTS["merchant"])]
    # Every merchant word contributes evidence. Its small weight prevents a
    # long merchant name from overpowering an exact full-merchant match.
    signals.extend(
        ("merchant_token", token, SIGNAL_WEIGHTS["merchant_token"]) for token in tokenize(merchant)
    )
    if description:
        signals.append(("description", description, SIGNAL_WEIGHTS["description"]))
        signals.extend(
            ("description_token", token, SIGNAL_WEIGHTS["description_token"])
            for token in tokenize(description)
        )
        signals.append(("combined", f"{merchant} {description}", SIGNAL_WEIGHTS["combined"]))
    return signals


def record_learning_event(
    *,
    category_id: int,
    merchant: str,
    description: str | None,
    account_id: int | None,
    transaction_type: str | None,
    source: str = "manual",
) -> None:
    """Persist an event and update the weighted model in the separate database."""
    ensure_learning_schema()
    merchant_normalized = normalize_text(merchant)
    description_normalized = normalize_text(description)
    request = CategoryPredictionRequest(
        merchant=merchant,
        description=description,
        account_id=account_id,
        transaction_type=transaction_type,
    )
    with LearningSessionLocal() as db:
        save_learning_event(
            db,
            merchant_normalized=merchant_normalized,
            description_normalized=description_normalized,
            category_id=category_id,
            account_id=account_id,
            transaction_type=transaction_type,
            source=source,
        )
        for pattern_type, pattern_text, base_weight in _connections(request):
            if not pattern_text:
                continue
            scopes = [account_id] if account_id is None else [None, account_id]
            for scope in scopes:
                pattern = get_pattern(
                    db,
                    pattern_type=pattern_type,
                    pattern_text=pattern_text,
                    category_id=category_id,
                    account_id=scope,
                    transaction_type=transaction_type,
                )
                if pattern is None:
                    pattern = CategoryPattern(
                        pattern_type=pattern_type,
                        pattern_text=pattern_text,
                        category_id=category_id,
                        account_id=scope,
                        transaction_type=transaction_type,
                        weight=0.0,
                        observations=0,
                    )
                    db.add(pattern)
                pattern.weight += base_weight
                pattern.observations += 1
        db.commit()


def learn_from_transaction(transaction: Transaction) -> None:
    """Learn only from categorized transactions explicitly saved by the user."""
    if transaction.category_id is None or not transaction.merchant:
        return
    try:
        record_learning_event(
            category_id=transaction.category_id,
            merchant=transaction.merchant,
            description=transaction.description,
            account_id=transaction.account_id,
            transaction_type=transaction.transaction_type,
            source=transaction.source,
        )
    except Exception:  # Learning must never prevent a financial record from saving.
        logger.exception("Could not update category-learning data")


def predict_categories(
    main_db: Session, learning_db: Session, request: CategoryPredictionRequest
) -> list[CategoryPrediction]:
    """Rank categories from exact history first and fuzzy history second."""
    categories = list(main_db.scalars(select(Category).where(Category.is_active.is_(True))))
    if not categories:
        return []
    category_ids = {category.id for category in categories}
    scores: dict[int, float] = {}
    reasons: dict[int, tuple[float, int, str]] = {}
    patterns = list_matching_patterns(
        learning_db, account_id=request.account_id, transaction_type=request.transaction_type
    )
    signals = _connections(request)
    for pattern in patterns:
        if pattern.category_id not in category_ids:
            continue
        for signal_type, text, base_weight in signals:
            if signal_type != pattern.pattern_type or not text:
                continue
            similarity = SequenceMatcher(None, text, pattern.pattern_text).ratio()
            if similarity < SIMILARITY_THRESHOLD:
                continue
            multiplier = ACCOUNT_MULTIPLIER if pattern.account_id == request.account_id else 1.0
            contribution = base_weight * pattern.weight * similarity * multiplier
            scores[pattern.category_id] = scores.get(pattern.category_id, 0.0) + contribution
            previous = reasons.get(pattern.category_id)
            if previous is None or contribution > previous[0]:
                reasons[pattern.category_id] = (
                    contribution,
                    pattern.observations,
                    pattern.pattern_type,
                )
    total = sum(scores.values())
    if total <= 0:
        return []
    suggestions: list[CategoryPrediction] = []
    for category_id, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)[:5]:
        _, observations, pattern_type = reasons[category_id]
        label = next(category.name for category in categories if category.id == category_id)
        reason = (
            f"{label} matched your previous {pattern_type} pattern "
            f"({observations} observation{'s' if observations != 1 else ''})"
        )
        suggestions.append(
            CategoryPrediction(
                category_id=category_id,
                confidence=round(min(score / total, 1.0), 4),
                reason=reason,
            )
        )
    return suggestions
