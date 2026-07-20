"""Rebuild description patterns with interaction signals.

Revision ID: 0002_description_interactions
Revises: 0001_description_learning
"""

from collections import defaultdict

import sqlalchemy as sa
from alembic import op

revision = "0002_description_interactions"
down_revision = "0001_description_learning"
branch_labels = None
depends_on = None


def _tokens(merchant: str) -> list[str]:
    return list(dict.fromkeys(token for token in merchant.split() if len(token) > 1))


def _new_features(event: dict[str, object]) -> list[tuple[str, str]]:
    merchant = str(event["merchant_normalized"] or "")
    band = str(event["amount_band"] or "")
    category = str(event["category_id"]) if event["category_id"] is not None else ""
    transaction_type = str(event["transaction_type"] or "")
    features: list[tuple[str, str]] = []
    if merchant:
        features.append(("merchant", merchant))
        features.extend(("merchant_token", token) for token in _tokens(merchant))
    if category:
        features.append(("category", category))
    if transaction_type:
        features.append(("transaction_type", transaction_type))
    if band:
        features.append(("amount_band", band))
    if merchant and category:
        features.append(("merchant_category", f"{merchant}|{category}"))
        features.extend(
            ("merchant_token_category", f"{token}|{category}") for token in _tokens(merchant)
        )
    if merchant and transaction_type:
        features.append(("merchant_transaction_type", f"{merchant}|{transaction_type}"))
    if merchant and band:
        features.append(("merchant_amount_band", f"{merchant}|{band}"))
    if category and transaction_type:
        features.append(("category_transaction_type", f"{category}|{transaction_type}"))
    if category and band:
        features.append(("category_amount_band", f"{category}|{band}"))
    if merchant and category and band:
        features.append(("merchant_category_amount_band", f"{merchant}|{category}|{band}"))
    return features


def _old_features(event: dict[str, object]) -> list[tuple[str, str]]:
    return [
        feature
        for feature in _new_features(event)
        if feature[0]
        in {
            "merchant",
            "merchant_token",
            "category",
            "transaction_type",
            "amount_band",
            "merchant_amount_band",
            "category_amount_band",
        }
    ]


def _rebuild(feature_builder, old_weights: bool) -> None:
    connection = op.get_bind()
    events = list(
        connection.execute(
            sa.text(
                "SELECT merchant_normalized, amount_band, category_id, transaction_type, "
                "description_text, description_normalized FROM description_learning_events "
                "ORDER BY id"
            )
        ).mappings()
    )
    totals: defaultdict[tuple[str, str, str], dict[str, object]] = defaultdict(
        lambda: {"description_text": "", "observations": 0}
    )
    for event in events:
        for pattern_type, pattern_text in feature_builder(dict(event)):
            key = (pattern_type, pattern_text, str(event["description_normalized"]))
            totals[key]["description_text"] = str(event["description_text"])
            totals[key]["observations"] = int(totals[key]["observations"]) + 1

    previous_weights = {
        "merchant": 3.0,
        "merchant_token": 0.4,
        "category": 2.0,
        "transaction_type": 1.0,
        "amount_band": 0.15,
        "merchant_amount_band": 0.4,
        "category_amount_band": 0.3,
    }
    connection.execute(sa.text("DELETE FROM description_patterns"))
    if not totals:
        return
    rows = []
    for (pattern_type, pattern_text, description_normalized), values in totals.items():
        observations = int(values["observations"])
        rows.append(
            {
                "pattern_type": pattern_type,
                "pattern_text": pattern_text,
                "description_normalized": description_normalized,
                "description_text": values["description_text"],
                "weight": observations * previous_weights.get(pattern_type, 1.0)
                if old_weights
                else float(observations),
                "observations": observations,
            }
        )
    patterns = sa.table(
        "description_patterns",
        sa.column("pattern_type", sa.String),
        sa.column("pattern_text", sa.String),
        sa.column("description_normalized", sa.String),
        sa.column("description_text", sa.String),
        sa.column("weight", sa.Float),
        sa.column("observations", sa.Integer),
    )
    op.bulk_insert(patterns, rows)


def upgrade() -> None:
    _rebuild(_new_features, old_weights=False)


def downgrade() -> None:
    _rebuild(_old_features, old_weights=True)
