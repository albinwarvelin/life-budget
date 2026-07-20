"""Backfill compound merchant-token signals for description predictions.

Revision ID: 0003_description_token_interactions
Revises: 0002_description_interactions
"""

from collections import defaultdict

from alembic import op
import sqlalchemy as sa

revision = "0003_description_token_interactions"
down_revision = "0002_description_interactions"
branch_labels = None
depends_on = None

TOKEN_PATTERN_TYPES = (
    "merchant_token_type",
    "merchant_token_amount_band",
    "merchant_token_category_band",
)


def _tokens(value: str) -> set[str]:
    """Match the runtime tokenizer's useful-word behavior for normalized text."""
    return {token for token in value.split() if len(token) > 1}


def upgrade() -> None:
    """Derive the new token interactions from every historical learning event."""
    connection = op.get_bind()
    events = connection.execute(
        sa.text(
            "SELECT merchant_normalized, amount_band, category_id, "
            "transaction_type, description_normalized, description_text "
            "FROM description_learning_events ORDER BY id"
        )
    ).mappings()

    # The revision introduces these pattern kinds, so clearing only these kinds
    # makes a partially retried migration deterministic without touching older
    # model connections.
    connection.execute(
        sa.text(
            "DELETE FROM description_patterns "
            "WHERE pattern_type IN "
            "('merchant_token_type', 'merchant_token_amount_band', "
            "'merchant_token_category_band')"
        )
    )
    totals: defaultdict[tuple[str, str, str], dict[str, object]] = defaultdict(
        lambda: {"description_text": "", "observations": 0}
    )

    def observe(
        pattern_type: str,
        pattern_text: str,
        description_key: str,
        description_text: str,
    ) -> None:
        """Aggregate by normalized output while retaining its latest display text."""
        key = (pattern_type, pattern_text, description_key)
        totals[key]["description_text"] = description_text
        totals[key]["observations"] = int(totals[key]["observations"]) + 1

    for event in events:
        for token in _tokens(event["merchant_normalized"] or ""):
            transaction_type = event["transaction_type"]
            amount_band = event["amount_band"]
            category_id = event["category_id"]
            description_key = event["description_normalized"]
            description_text = event["description_text"]
            if transaction_type:
                observe(
                    "merchant_token_type",
                    f"{token}|{transaction_type}",
                    description_key,
                    description_text,
                )
            if amount_band:
                observe(
                    "merchant_token_amount_band",
                    f"{token}|{amount_band}",
                    description_key,
                    description_text,
                )
            if category_id is not None and amount_band:
                observe(
                    "merchant_token_category_band",
                    f"{token}|{category_id}|{amount_band}",
                    description_key,
                    description_text,
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
    rows = [
        {
            "pattern_type": pattern_type,
            "pattern_text": pattern_text,
            "description_normalized": description_key,
            "description_text": values["description_text"],
            "weight": float(int(values["observations"])),
            "observations": int(values["observations"]),
        }
        for (pattern_type, pattern_text, description_key), values in totals.items()
    ]
    if rows:
        op.bulk_insert(patterns, rows)


def downgrade() -> None:
    """Remove only the token interactions introduced by this revision."""
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "DELETE FROM description_patterns "
            "WHERE pattern_type IN "
            "('merchant_token_type', 'merchant_token_amount_band', "
            "'merchant_token_category_band')"
        )
    )
