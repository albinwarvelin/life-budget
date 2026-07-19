"""Backfill word signals and add amount-band context.

Revision ID: 0002_learning_features
Revises: 0001_initial_learning_schema
"""

from collections import defaultdict

import sqlalchemy as sa
from alembic import op

revision = "0002_learning_features"
down_revision = "0001_initial_learning_schema"
branch_labels = None
depends_on = None

WEIGHTS = {
    "merchant": 4.0,
    "merchant_token": 0.5,
    "description": 1.5,
    "description_token": 0.25,
    "combined": 2.0,
}


def _tokens(value: str) -> list[str]:
    return list(dict.fromkeys(token for token in value.split() if len(token) > 1))


def upgrade() -> None:
    op.add_column("category_learning_events", sa.Column("amount_band", sa.String(30)))
    op.add_column("category_learning_events", sa.Column("currency_code", sa.String(3)))
    op.create_index(
        "ix_category_learning_events_amount_band", "category_learning_events", ["amount_band"]
    )

    # Earlier application versions learned full phrases but did not always
    # retain their individual words. Rebuilding from the auditable event table
    # makes all historical single-word evidence available without double-counting.
    connection = op.get_bind()
    events = connection.execute(
        sa.text(
            "SELECT merchant_normalized, description_normalized, category_id, "
            "account_id, transaction_type FROM category_learning_events"
        )
    ).mappings()
    totals: dict[tuple, list[float | int]] = defaultdict(lambda: [0.0, 0])
    for event in events:
        merchant = event["merchant_normalized"] or ""
        description = event["description_normalized"] or ""
        signals = [("merchant", merchant)]
        signals.extend(("merchant_token", token) for token in _tokens(merchant))
        if description:
            signals.append(("description", description))
            signals.extend(("description_token", token) for token in _tokens(description))
            signals.append(("combined", f"{merchant} {description}"))
        scopes = [None, event["account_id"]] if event["account_id"] is not None else [None]
        for pattern_type, pattern_text in signals:
            if not pattern_text:
                continue
            for scope in scopes:
                key = (
                    pattern_type,
                    pattern_text,
                    event["category_id"],
                    scope,
                    event["transaction_type"],
                )
                totals[key][0] += WEIGHTS[pattern_type]
                totals[key][1] += 1
    connection.execute(sa.text("DELETE FROM category_patterns"))
    insert = sa.text(
        "INSERT INTO category_patterns "
        "(pattern_type, pattern_text, category_id, account_id, transaction_type, weight, observations) "
        "VALUES (:pattern_type, :pattern_text, :category_id, :account_id, :transaction_type, "
        ":weight, :observations)"
    )
    for key, values in totals.items():
        connection.execute(
            insert,
            {
                "pattern_type": key[0],
                "pattern_text": key[1],
                "category_id": key[2],
                "account_id": key[3],
                "transaction_type": key[4],
                "weight": values[0],
                "observations": values[1],
            },
        )


def downgrade() -> None:
    op.drop_index("ix_category_learning_events_amount_band", "category_learning_events")
    op.drop_column("category_learning_events", "currency_code")
    op.drop_column("category_learning_events", "amount_band")
