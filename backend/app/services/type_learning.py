from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from app.repositories.type_learning import add_type_event, find_type_pattern, list_type_patterns
from app.services.learning_features import amount_band, normalize_text, tokenize
from app.type_learning_db import TypeLearningSessionLocal, ensure_type_learning_schema
from app.type_learning_models import TypeLearningEvent, TypePattern

TYPE_SIGNAL_WEIGHTS = {
    "amount_sign": 3.0,
    "merchant": 2.0,
    "merchant_token": 0.35,
    "category": 3.0,
    "merchant_category": 1.5,
    "amount_band": 0.15,
    "merchant_amount_band": 0.4,
    "category_amount_band": 0.3,
}
TYPE_SIMILARITY_THRESHOLD = 0.78


@dataclass(frozen=True)
class TypePrediction:
    transaction_type: str
    confidence: float
    reason: str


def amount_sign(amount: Decimal) -> str:
    """Keep zero separate because it carries little directional evidence."""
    return "negative" if amount < 0 else "positive" if amount > 0 else "zero"


def _features(
    amount: Decimal, merchant: str, category_id: int | None, currency_code: str | None
) -> list[tuple[str, str, float, int | None]]:
    merchant_key = normalize_text(merchant)
    features = [("amount_sign", amount_sign(amount), TYPE_SIGNAL_WEIGHTS["amount_sign"], None)]
    if merchant_key:
        features.append(("merchant", merchant_key, TYPE_SIGNAL_WEIGHTS["merchant"], None))
        features.extend(
            ("merchant_token", token, TYPE_SIGNAL_WEIGHTS["merchant_token"], None)
            for token in tokenize(merchant_key)
        )
    if category_id is not None:
        category_key = str(category_id)
        features.append(("category", category_key, TYPE_SIGNAL_WEIGHTS["category"], category_id))
        if merchant_key:
            features.append(
                (
                    "merchant_category",
                    f"{merchant_key}|{category_key}",
                    TYPE_SIGNAL_WEIGHTS["merchant_category"],
                    category_id,
                )
            )
    band = amount_band(amount, currency_code)
    if band:
        features.append(("amount_band", band, TYPE_SIGNAL_WEIGHTS["amount_band"], None))
        if merchant_key:
            features.append(
                (
                    "merchant_amount_band",
                    f"{merchant_key}|{band}",
                    TYPE_SIGNAL_WEIGHTS["merchant_amount_band"],
                    None,
                )
            )
        if category_id is not None:
            features.append(
                (
                    "category_amount_band",
                    f"{category_id}|{band}",
                    TYPE_SIGNAL_WEIGHTS["category_amount_band"],
                    category_id,
                )
            )
    return features


def predict_transaction_type(
    db: Session,
    *,
    amount: Decimal,
    merchant: str,
    category_id: int | None,
    currency_code: str | None = None,
) -> TypePrediction:
    """Combine sign priors with learned merchant and category evidence."""
    sign = amount_sign(amount)
    priors = (
        {"expense": 0.65, "transfer": 0.15, "savings": 0.12, "reimbursement": 0.05, "income": 0.03}
        if sign == "negative"
        else {
            "income": 0.42,
            "reimbursement": 0.22,
            "transfer": 0.14,
            "savings": 0.12,
            "expense": 0.10,
        }
    )
    scores = dict(priors)
    strongest: dict[str, tuple[float, str, int]] = {}
    # Feature extraction normalizes and tokenizes merchant text. It depends
    # only on this request, so calculate it once instead of repeating that work
    # for every stored pattern in the model.
    requested_features = _features(amount, merchant, category_id, currency_code)
    for pattern in list_type_patterns(db):
        for feature_type, feature_text, base_weight, feature_category in requested_features:
            if pattern.pattern_type != feature_type or pattern.category_id != feature_category:
                continue
            if feature_type == "merchant_token":
                if feature_text != pattern.pattern_text:
                    continue
                similarity = 1.0
            else:
                similarity = SequenceMatcher(None, feature_text, pattern.pattern_text).ratio()
            if similarity < TYPE_SIMILARITY_THRESHOLD:
                continue
            contribution = base_weight * pattern.weight * similarity
            scores[pattern.transaction_type] += contribution
            if (
                pattern.transaction_type not in strongest
                or contribution > strongest[pattern.transaction_type][0]
            ):
                strongest[pattern.transaction_type] = (
                    contribution,
                    pattern.pattern_type,
                    pattern.observations,
                )
    winner, winner_score = max(scores.items(), key=lambda item: item[1])
    total = sum(scores.values())
    learned = strongest.get(winner)
    reason = (
        f"Learned {learned[1]} evidence from {learned[2]} observation(s), combined with a {sign} amount"
        if learned
        else f"Initial {sign}-amount prior; confirm it so the model can learn"
    )
    return TypePrediction(winner, round(winner_score / total, 4), reason)


def record_type_learning_event(
    *,
    amount: Decimal,
    merchant: str,
    category_id: int | None,
    transaction_type: str,
    currency_code: str | None = None,
    source: str = "screenshot",
) -> None:
    """Update the isolated model only after a user accepts the final draft values."""
    ensure_type_learning_schema()
    with TypeLearningSessionLocal() as db:
        learn_transaction_type(
            db,
            amount=amount,
            merchant=merchant,
            category_id=category_id,
            transaction_type=transaction_type,
            currency_code=currency_code,
            source=source,
        )


def learn_transaction_type(
    db: Session,
    *,
    amount: Decimal,
    merchant: str,
    category_id: int | None,
    transaction_type: str,
    currency_code: str | None = None,
    source: str = "screenshot",
) -> None:
    """Apply one confirmed event to a supplied session for testable learning."""
    add_type_event(
        db,
        TypeLearningEvent(
            amount_sign=amount_sign(amount),
            amount_band=amount_band(amount, currency_code) or None,
            currency_code=currency_code.upper() if currency_code else None,
            merchant_normalized=normalize_text(merchant),
            category_id=category_id,
            transaction_type=transaction_type,
            source=source,
        ),
    )
    for pattern_type, pattern_text, weight, feature_category in _features(
        amount, merchant, category_id, currency_code
    ):
        pattern = find_type_pattern(
            db,
            pattern_type=pattern_type,
            pattern_text=pattern_text,
            category_id=feature_category,
            transaction_type=transaction_type,
        )
        if pattern is None:
            pattern = TypePattern(
                pattern_type=pattern_type,
                pattern_text=pattern_text,
                category_id=feature_category,
                transaction_type=transaction_type,
                weight=0.0,
                observations=0,
            )
            db.add(pattern)
        pattern.weight += weight
        pattern.observations += 1
    db.commit()
