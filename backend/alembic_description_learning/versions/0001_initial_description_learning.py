"""Create the isolated description-learning schema.

Revision ID: 0001_description_learning
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_description_learning"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "description_learning_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("merchant_normalized", sa.String(160), nullable=False),
        sa.Column("amount_band", sa.String(30)),
        sa.Column("currency_code", sa.String(3)),
        sa.Column("category_id", sa.Integer()),
        sa.Column("transaction_type", sa.String(15)),
        sa.Column("description_text", sa.String(240), nullable=False),
        sa.Column("description_normalized", sa.String(240), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()
        ),
    )
    op.create_index(
        "ix_description_learning_events_amount_band", "description_learning_events", ["amount_band"]
    )
    op.create_index(
        "ix_description_learning_events_category_id", "description_learning_events", ["category_id"]
    )
    op.create_index(
        "ix_description_learning_events_transaction_type",
        "description_learning_events",
        ["transaction_type"],
    )
    op.create_index(
        "ix_description_learning_events_description_normalized",
        "description_learning_events",
        ["description_normalized"],
    )
    op.create_table(
        "description_patterns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pattern_type", sa.String(30), nullable=False),
        sa.Column("pattern_text", sa.String(320), nullable=False),
        sa.Column("description_normalized", sa.String(240), nullable=False),
        sa.Column("description_text", sa.String(240), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="0"),
        sa.Column("observations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()
        ),
        sa.UniqueConstraint(
            "pattern_type",
            "pattern_text",
            "description_normalized",
            name="uq_description_pattern_connection",
        ),
    )
    op.create_index(
        "ix_description_patterns_pattern_type", "description_patterns", ["pattern_type"]
    )
    op.create_index(
        "ix_description_patterns_pattern_text", "description_patterns", ["pattern_text"]
    )
    op.create_index(
        "ix_description_patterns_description_normalized",
        "description_patterns",
        ["description_normalized"],
    )


def downgrade() -> None:
    op.drop_table("description_patterns")
    op.drop_table("description_learning_events")
