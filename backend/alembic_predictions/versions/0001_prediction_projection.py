"""Create the replaceable, revisioned prediction projection."""

import sqlalchemy as sa
from alembic import op

revision = "0001_prediction_projection"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "training_examples",
        sa.Column("transaction_id", sa.Integer(), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_table(
        "model_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dataset_revision", sa.Integer(), nullable=False),
        sa.Column("algorithm_version", sa.String(40), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()
        ),
    )
    op.create_index("ix_model_snapshots_dataset_revision", "model_snapshots", ["dataset_revision"])
    op.create_table(
        "prediction_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("initialized", sa.Boolean(), nullable=False),
        sa.Column("dataset_revision", sa.Integer(), nullable=False),
        sa.Column("active_snapshot_id", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("prediction_state")
    op.drop_table("model_snapshots")
    op.drop_table("training_examples")
