"""Create the isolated category-learning model.

Revision ID: 0001_initial_learning_schema
Revises:
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_learning_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "category_learning_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("merchant_normalized", sa.String(length=160), nullable=False),
        sa.Column("description_normalized", sa.String(length=240), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("transaction_type", sa.String(length=15), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_category_learning_events_merchant_normalized", "category_learning_events", ["merchant_normalized"])
    op.create_index("ix_category_learning_events_category_id", "category_learning_events", ["category_id"])
    op.create_index("ix_category_learning_events_account_id", "category_learning_events", ["account_id"])
    op.create_table(
        "category_patterns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pattern_type", sa.String(length=20), nullable=False),
        sa.Column("pattern_text", sa.String(length=320), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("transaction_type", sa.String(length=15), nullable=True),
        sa.Column("weight", sa.Float(), nullable=False, server_default="0"),
        sa.Column("observations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("pattern_type", "pattern_text", "category_id", "account_id", "transaction_type", name="uq_category_pattern_connection"),
    )
    op.create_index("ix_category_patterns_pattern_type", "category_patterns", ["pattern_type"])
    op.create_index("ix_category_patterns_pattern_text", "category_patterns", ["pattern_text"])
    op.create_index("ix_category_patterns_category_id", "category_patterns", ["category_id"])
    op.create_index("ix_category_patterns_account_id", "category_patterns", ["account_id"])


def downgrade() -> None:
    op.drop_table("category_patterns")
    op.drop_table("category_learning_events")
