"""Preserve reviewed source signs and queue learning with financial commits."""

import sqlalchemy as sa
from alembic import op

revision = "0009_reviewed_learning_outbox"
down_revision = "0008_import_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("source_signed_amount", sa.Numeric(18, 2)))
    op.create_table(
        "learning_outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("transaction_id", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(10), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("delivered", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()
        ),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_learning_outbox_transaction_id", "learning_outbox", ["transaction_id"])
    op.create_index("ix_learning_outbox_delivered", "learning_outbox", ["delivered"])


def downgrade() -> None:
    op.drop_table("learning_outbox")
    with op.batch_alter_table("transactions") as batch:
        batch.drop_column("source_signed_amount")
