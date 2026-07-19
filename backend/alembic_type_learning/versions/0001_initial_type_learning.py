"""Create the isolated transaction-type learning schema.

Revision ID: 0001_type_learning
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_type_learning"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "type_learning_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amount_sign", sa.String(10), nullable=False),
        sa.Column("merchant_normalized", sa.String(160), nullable=False),
        sa.Column("category_id", sa.Integer()),
        sa.Column("transaction_type", sa.String(15), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()
        ),
    )
    op.create_index("ix_type_learning_events_amount_sign", "type_learning_events", ["amount_sign"])
    op.create_index("ix_type_learning_events_category_id", "type_learning_events", ["category_id"])
    op.create_index(
        "ix_type_learning_events_transaction_type", "type_learning_events", ["transaction_type"]
    )
    op.create_table(
        "type_patterns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pattern_type", sa.String(30), nullable=False),
        sa.Column("pattern_text", sa.String(320), nullable=False),
        sa.Column("category_id", sa.Integer()),
        sa.Column("transaction_type", sa.String(15), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("observations", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()
        ),
        sa.UniqueConstraint(
            "pattern_type",
            "pattern_text",
            "category_id",
            "transaction_type",
            name="uq_type_pattern_connection",
        ),
    )
    op.create_index("ix_type_patterns_pattern_type", "type_patterns", ["pattern_type"])
    op.create_index("ix_type_patterns_pattern_text", "type_patterns", ["pattern_text"])
    op.create_index("ix_type_patterns_category_id", "type_patterns", ["category_id"])
    op.create_index("ix_type_patterns_transaction_type", "type_patterns", ["transaction_type"])


def downgrade() -> None:
    op.drop_table("type_patterns")
    op.drop_table("type_learning_events")
