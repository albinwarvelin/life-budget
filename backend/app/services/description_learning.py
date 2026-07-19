import logging
from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from app.description_learning_db import (
    DescriptionLearningSessionLocal,
    ensure_description_learning_schema,
)
from app.description_learning_models import DescriptionLearningEvent, DescriptionPattern
from app.repositories.description_learning import (
    find_description_pattern,
    list_description_patterns,
)
from app.services.learning_features import amount_band, normalize_text, tokenize

logger = logging.getLogger(__name__)

# Description is a free-text output, so merchant/category context dominates.
# Amount magnitude is deliberately weak and can only tip otherwise similar evidence.
DESCRIPTION_SIGNAL_WEIGHTS = {
    "merchant": 3.0,
    "merchant_token": 0.4,
    "category": 2.0,
    "transaction_type": 1.0,
    "amount_band": 0.15,
    "merchant_amount_band": 0.4,
    "category_amount_band": 0.3,
}
DESCRIPTION_SIMILARITY_THRESHOLD = 0.78


@dataclass(frozen=True)
class DescriptionPrediction:
    description: str | None
    confidence: float
    reason: str


def _features(
    *,
    merchant: str,
    amount: Decimal,
    currency_code: str,
    category_id: int | None,
    transaction_type: str | None,
) -> list[tuple[str, str, float]]:
    merchant_key = normalize_text(merchant)
    features: list[tuple[str, str, float]] = []
    if merchant_key:
        features.append(("merchant", merchant_key, DESCRIPTION_SIGNAL_WEIGHTS["merchant"]))
        features.extend(
            ("merchant_token", token, DESCRIPTION_SIGNAL_WEIGHTS["merchant_token"])
            for token in tokenize(merchant_key)
        )
    if category_id is not None:
        features.append(("category", str(category_id), DESCRIPTION_SIGNAL_WEIGHTS["category"]))
    if transaction_type:
        features.append(
            ("transaction_type", transaction_type, DESCRIPTION_SIGNAL_WEIGHTS["transaction_type"])
        )
    band = amount_band(amount, currency_code)
    if band:
        features.append(("amount_band", band, DESCRIPTION_SIGNAL_WEIGHTS["amount_band"]))
        if merchant_key:
            features.append(
                (
                    "merchant_amount_band",
                    f"{merchant_key}|{band}",
                    DESCRIPTION_SIGNAL_WEIGHTS["merchant_amount_band"],
                )
            )
        if category_id is not None:
            features.append(
                (
                    "category_amount_band",
                    f"{category_id}|{band}",
                    DESCRIPTION_SIGNAL_WEIGHTS["category_amount_band"],
                )
            )
    return features


def predict_description(
    db: Session,
    *,
    merchant: str,
    amount: Decimal,
    currency_code: str,
    category_id: int | None,
    transaction_type: str | None,
) -> DescriptionPrediction:
    """Rank previously confirmed descriptions from the current row context."""
    scores: dict[str, float] = {}
    labels: dict[str, str] = {}
    strongest: dict[str, tuple[float, str, int]] = {}
    features = _features(
        merchant=merchant,
        amount=amount,
        currency_code=currency_code,
        category_id=category_id,
        transaction_type=transaction_type,
    )
    for pattern in list_description_patterns(db, limit=5000):
        for feature_type, feature_text, base_weight in features:
            if pattern.pattern_type != feature_type:
                continue
            if feature_type.endswith("_token"):
                if feature_text != pattern.pattern_text:
                    continue
                similarity = 1.0
            else:
                similarity = SequenceMatcher(None, feature_text, pattern.pattern_text).ratio()
                if similarity < DESCRIPTION_SIMILARITY_THRESHOLD:
                    continue
            contribution = base_weight * pattern.weight * similarity
            key = pattern.description_normalized
            scores[key] = scores.get(key, 0.0) + contribution
            labels[key] = pattern.description_text
            if key not in strongest or contribution > strongest[key][0]:
                strongest[key] = (contribution, pattern.pattern_type, pattern.observations)
    if not scores:
        return DescriptionPrediction(None, 0.0, "No confirmed description pattern yet")
    winner, winner_score = max(scores.items(), key=lambda item: item[1])
    total = sum(scores.values())
    _, signal, observations = strongest[winner]
    return DescriptionPrediction(
        labels[winner],
        round(min(winner_score / total, 1.0), 4),
        f"Learned {signal} evidence from {observations} observation(s)",
    )


def record_description_learning_event(
    *,
    merchant: str,
    amount: Decimal,
    currency_code: str,
    category_id: int | None,
    transaction_type: str | None,
    description: str | None,
    source: str = "screenshot",
) -> None:
    """Learn only non-empty descriptions explicitly approved by the user."""
    if not description or not normalize_text(description):
        return
    ensure_description_learning_schema()
    with DescriptionLearningSessionLocal() as db:
        learn_description(
            db,
            merchant=merchant,
            amount=amount,
            currency_code=currency_code,
            category_id=category_id,
            transaction_type=transaction_type,
            description=description,
            source=source,
        )


def learn_description(
    db: Session,
    *,
    merchant: str,
    amount: Decimal,
    currency_code: str,
    category_id: int | None,
    transaction_type: str | None,
    description: str,
    source: str = "screenshot",
) -> None:
    """Apply one confirmed description event to a supplied session."""
    description_text = description.strip()
    description_key = normalize_text(description_text)
    db.add(
        DescriptionLearningEvent(
            merchant_normalized=normalize_text(merchant),
            amount_band=amount_band(amount, currency_code) or None,
            currency_code=currency_code.upper(),
            category_id=category_id,
            transaction_type=transaction_type,
            description_text=description_text,
            description_normalized=description_key,
            source=source,
        )
    )
    for pattern_type, pattern_text, weight in _features(
        merchant=merchant,
        amount=amount,
        currency_code=currency_code,
        category_id=category_id,
        transaction_type=transaction_type,
    ):
        pattern = find_description_pattern(
            db,
            pattern_type=pattern_type,
            pattern_text=pattern_text,
            description_normalized=description_key,
        )
        if pattern is None:
            pattern = DescriptionPattern(
                pattern_type=pattern_type,
                pattern_text=pattern_text,
                description_normalized=description_key,
                description_text=description_text,
                weight=0.0,
                observations=0,
            )
            db.add(pattern)
        # Keep the most recently confirmed capitalization/wording as the label.
        pattern.description_text = description_text
        pattern.weight += weight
        pattern.observations += 1
    db.commit()
