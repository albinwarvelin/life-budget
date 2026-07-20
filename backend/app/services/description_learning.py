import logging
import math
from collections import Counter, defaultdict
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
    list_description_events,
)
from app.services.learning_features import amount_band, normalize_text, tokenize

logger = logging.getLogger(__name__)

# Broad single-field signals intentionally have little authority. Interactions
# become progressively stronger because they identify a narrower situation.
DESCRIPTION_SIGNAL_WEIGHTS = {
    "merchant": 2.4,
    "merchant_token": 0.12,
    "category": 0.2,
    "transaction_type": 0.04,
    "amount_band": 0.05,
    "merchant_category": 3.2,
    "merchant_transaction_type": 1.4,
    "merchant_amount_band": 1.0,
    "merchant_token_category": 0.65,
    # Token interactions let a shared brand word survive location/store-name
    # changes, but remain weaker than their full-merchant equivalents because
    # common words can occur across unrelated merchants.
    "merchant_token_type": 0.18,
    "merchant_token_amount_band": 0.25,
    "merchant_token_category_band": 1.5,
    "category_transaction_type": 0.25,
    "category_amount_band": 0.35,
    "merchant_category_amount_band": 4.2,
}
DESCRIPTION_SIMILARITY_THRESHOLD = 0.78
DESCRIPTION_MIN_CONFIDENCE = 0.4


@dataclass(frozen=True)
class DescriptionFeature:
    pattern_type: str
    pattern_text: str
    weight: float


@dataclass(frozen=True)
class DescriptionContribution:
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


@dataclass(frozen=True)
class DescriptionCandidate:
    description: str
    score: float
    relative_score: float
    contributions: tuple[DescriptionContribution, ...]


@dataclass(frozen=True)
class DescriptionPrediction:
    description: str | None
    confidence: float
    reason: str
    candidates: tuple[DescriptionCandidate, ...] = ()


def _features_from_values(
    *,
    merchant_key: str,
    band: str | None,
    category_id: int | None,
    transaction_type: str | None,
) -> list[DescriptionFeature]:
    """Create single signals and increasingly specific interaction signals."""
    features: list[DescriptionFeature] = []
    category_key = str(category_id) if category_id is not None else None
    merchant_tokens = tokenize(merchant_key) if merchant_key else []
    if merchant_key:
        features.append(
            DescriptionFeature("merchant", merchant_key, DESCRIPTION_SIGNAL_WEIGHTS["merchant"])
        )
        features.extend(
            DescriptionFeature(
                "merchant_token", token, DESCRIPTION_SIGNAL_WEIGHTS["merchant_token"]
            )
            for token in merchant_tokens
        )
    if category_key:
        features.append(
            DescriptionFeature("category", category_key, DESCRIPTION_SIGNAL_WEIGHTS["category"])
        )
    if transaction_type:
        features.append(
            DescriptionFeature(
                "transaction_type",
                transaction_type,
                DESCRIPTION_SIGNAL_WEIGHTS["transaction_type"],
            )
        )
    if band:
        features.append(
            DescriptionFeature("amount_band", band, DESCRIPTION_SIGNAL_WEIGHTS["amount_band"])
        )

    if merchant_key and category_key:
        features.append(
            DescriptionFeature(
                "merchant_category",
                f"{merchant_key}|{category_key}",
                DESCRIPTION_SIGNAL_WEIGHTS["merchant_category"],
            )
        )
        features.extend(
            DescriptionFeature(
                "merchant_token_category",
                f"{token}|{category_key}",
                DESCRIPTION_SIGNAL_WEIGHTS["merchant_token_category"],
            )
            for token in merchant_tokens
        )
    if merchant_key and transaction_type:
        features.append(
            DescriptionFeature(
                "merchant_transaction_type",
                f"{merchant_key}|{transaction_type}",
                DESCRIPTION_SIGNAL_WEIGHTS["merchant_transaction_type"],
            )
        )
        features.extend(
            DescriptionFeature(
                "merchant_token_type",
                f"{token}|{transaction_type}",
                DESCRIPTION_SIGNAL_WEIGHTS["merchant_token_type"],
            )
            for token in merchant_tokens
        )
    if merchant_key and band:
        features.append(
            DescriptionFeature(
                "merchant_amount_band",
                f"{merchant_key}|{band}",
                DESCRIPTION_SIGNAL_WEIGHTS["merchant_amount_band"],
            )
        )
        features.extend(
            DescriptionFeature(
                "merchant_token_amount_band",
                f"{token}|{band}",
                DESCRIPTION_SIGNAL_WEIGHTS["merchant_token_amount_band"],
            )
            for token in merchant_tokens
        )
    if category_key and transaction_type:
        features.append(
            DescriptionFeature(
                "category_transaction_type",
                f"{category_key}|{transaction_type}",
                DESCRIPTION_SIGNAL_WEIGHTS["category_transaction_type"],
            )
        )
    if category_key and band:
        features.append(
            DescriptionFeature(
                "category_amount_band",
                f"{category_key}|{band}",
                DESCRIPTION_SIGNAL_WEIGHTS["category_amount_band"],
            )
        )
    if merchant_key and category_key and band:
        features.append(
            DescriptionFeature(
                "merchant_category_amount_band",
                f"{merchant_key}|{category_key}|{band}",
                DESCRIPTION_SIGNAL_WEIGHTS["merchant_category_amount_band"],
            )
        )
        features.extend(
            DescriptionFeature(
                "merchant_token_category_band",
                f"{token}|{category_key}|{band}",
                DESCRIPTION_SIGNAL_WEIGHTS["merchant_token_category_band"],
            )
            for token in merchant_tokens
        )
    return features


def _features(
    *,
    merchant: str,
    amount: Decimal,
    currency_code: str,
    category_id: int | None,
    transaction_type: str | None,
) -> list[DescriptionFeature]:
    return _features_from_values(
        merchant_key=normalize_text(merchant),
        band=amount_band(amount, currency_code),
        category_id=category_id,
        transaction_type=transaction_type,
    )


def _event_features(event: DescriptionLearningEvent) -> list[DescriptionFeature]:
    return _features_from_values(
        merchant_key=event.merchant_normalized,
        band=event.amount_band,
        category_id=event.category_id,
        transaction_type=event.transaction_type,
    )


def _feature_similarity(requested: DescriptionFeature, stored: DescriptionFeature) -> float:
    """Fuzzy-match merchant phrases while requiring exact structured context."""
    if requested.pattern_type != stored.pattern_type:
        return 0.0
    if requested.pattern_type.startswith("merchant_token"):
        return 1.0 if requested.pattern_text == stored.pattern_text else 0.0
    if requested.pattern_type.startswith("merchant"):
        requested_parts = requested.pattern_text.split("|")
        stored_parts = stored.pattern_text.split("|")
        if requested_parts[1:] != stored_parts[1:]:
            return 0.0
        similarity = SequenceMatcher(None, requested_parts[0], stored_parts[0]).ratio()
        return similarity if similarity >= DESCRIPTION_SIMILARITY_THRESHOLD else 0.0
    return 1.0 if requested.pattern_text == stored.pattern_text else 0.0


def predict_description(
    db: Session,
    *,
    merchant: str,
    amount: Decimal,
    currency_code: str,
    category_id: int | None,
    transaction_type: str | None,
) -> DescriptionPrediction:
    """Score descriptions using discriminative evidence from confirmed examples.

    A signal contributes only when its conditional description rate exceeds
    that description's overall baseline rate. This suppresses generic priors
    such as ``expense -> Mat`` while retaining narrow interaction evidence.
    """
    events = list_description_events(db)
    if not events:
        return DescriptionPrediction(None, 0.0, "No confirmed description pattern yet")

    requested_features = _features(
        merchant=merchant,
        amount=amount,
        currency_code=currency_code,
        category_id=category_id,
        transaction_type=transaction_type,
    )
    labels = {event.description_normalized: event.description_text for event in events}
    baseline_counts = Counter(event.description_normalized for event in events)
    baseline_total = len(events)
    scores: defaultdict[str, float] = defaultdict(float)
    explanations: defaultdict[str, list[DescriptionContribution]] = defaultdict(list)

    prepared_events = [(event, _event_features(event)) for event in events]
    for requested in requested_features:
        support: defaultdict[str, float] = defaultdict(float)
        observations: Counter[str] = Counter()
        matched_values: defaultdict[str, Counter[str]] = defaultdict(Counter)
        for event, stored_features in prepared_events:
            matches = [
                (stored, _feature_similarity(requested, stored))
                for stored in stored_features
                if stored.pattern_type == requested.pattern_type
            ]
            stored, similarity = max(matches, key=lambda item: item[1], default=(None, 0.0))
            if stored is None or similarity <= 0:
                continue
            key = event.description_normalized
            support[key] += similarity
            observations[key] += 1
            matched_values[key][stored.pattern_text] += similarity

        total_support = sum(support.values())
        if total_support <= 0:
            continue
        reliability = total_support / (total_support + 1.0)
        for key, target_support in support.items():
            conditional = target_support / total_support
            baseline = baseline_counts[key] / baseline_total
            # Convert improvement over baseline into a bounded 0..1 value.
            discrimination = max(0.0, (conditional - baseline) / max(1.0 - baseline, 1e-9))
            contribution = requested.weight * reliability * discrimination
            if contribution <= 0:
                continue
            matched_value = matched_values[key].most_common(1)[0][0]
            average_similarity = target_support / observations[key]
            detail = DescriptionContribution(
                signal_type=requested.pattern_type,
                signal_value=requested.pattern_text,
                matched_value=matched_value,
                description=labels[key],
                observations=observations[key],
                conditional_probability=round(conditional, 4),
                baseline_probability=round(baseline, 4),
                reliability=round(reliability, 4),
                similarity=round(average_similarity, 4),
                contribution=round(contribution, 4),
            )
            scores[key] += contribution
            explanations[key].append(detail)

    if not scores:
        return DescriptionPrediction(
            None,
            0.0,
            "The matching signals were no more specific than the overall description bias",
        )

    total_score = sum(scores.values())
    ordered = sorted(scores, key=scores.get, reverse=True)
    candidates = tuple(
        DescriptionCandidate(
            description=labels[key],
            score=round(scores[key], 4),
            relative_score=round(scores[key] / total_score, 4),
            contributions=tuple(
                sorted(explanations[key], key=lambda item: item.contribution, reverse=True)
            ),
        )
        for key in ordered[:5]
    )
    winner = candidates[0]
    runner_up_score = candidates[1].score if len(candidates) > 1 else 0.0
    margin = max(0.0, (winner.score - runner_up_score) / max(winner.score, 1e-9))
    strength = 1.0 - math.exp(-winner.score / 2.5)
    confidence = round(winner.relative_score * strength * (0.7 + 0.3 * margin), 4)
    strongest = winner.contributions[0]
    accepted = confidence >= DESCRIPTION_MIN_CONFIDENCE
    reason = (
        f"{strongest.signal_type} raised '{winner.description}' from "
        f"{strongest.baseline_probability:.0%} overall to "
        f"{strongest.conditional_probability:.0%} in matching examples"
    )
    if not accepted:
        reason = f"Low-confidence candidate '{winner.description}': {reason}"
    return DescriptionPrediction(
        winner.description if accepted else None,
        confidence,
        reason,
        candidates,
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
    """Store one confirmed example and its explainable feature connections."""
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
    for feature in _features(
        merchant=merchant,
        amount=amount,
        currency_code=currency_code,
        category_id=category_id,
        transaction_type=transaction_type,
    ):
        pattern = find_description_pattern(
            db,
            pattern_type=feature.pattern_type,
            pattern_text=feature.pattern_text,
            description_normalized=description_key,
        )
        if pattern is None:
            pattern = DescriptionPattern(
                pattern_type=feature.pattern_type,
                pattern_text=feature.pattern_text,
                description_normalized=description_key,
                description_text=description_text,
                weight=0.0,
                observations=0,
            )
            db.add(pattern)
        pattern.description_text = description_text
        # Stored graph weight is now an observation count. Scoring weight is
        # applied exactly once by DESCRIPTION_SIGNAL_WEIGHTS during prediction.
        pattern.weight += 1.0
        pattern.observations += 1
    db.commit()
