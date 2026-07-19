"""Add currency-aware amount magnitude to type events.

Revision ID: 0002_type_amount_features
Revises: 0001_type_learning
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_type_amount_features"
down_revision = "0001_type_learning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("type_learning_events", sa.Column("amount_band", sa.String(30)))
    op.add_column("type_learning_events", sa.Column("currency_code", sa.String(3)))
    op.create_index("ix_type_learning_events_amount_band", "type_learning_events", ["amount_band"])


def downgrade() -> None:
    op.drop_index("ix_type_learning_events_amount_band", "type_learning_events")
    op.drop_column("type_learning_events", "currency_code")
    op.drop_column("type_learning_events", "amount_band")
