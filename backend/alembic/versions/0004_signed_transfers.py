"""Allow transfer transactions to represent either direction.

Revision ID: 0004_signed_transfers
Revises: 0003_signed_savings
"""

from alembic import op

revision = "0004_signed_transfers"
down_revision = "0003_signed_savings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Permit negative amounts for transfers while keeping other types positive."""
    # SQLite cannot alter a CHECK constraint in place, so Alembic rebuilds the
    # table while preserving its columns and data.
    with op.batch_alter_table("transactions", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_transactions_amount_non_negative", type_="check")
        batch_op.create_check_constraint(
            "ck_transactions_amount_non_negative",
            "amount >= 0 OR transaction_type IN ('savings', 'transfer')",
        )


def downgrade() -> None:
    """Restore the previous rule where only savings could be negative."""
    with op.batch_alter_table("transactions", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_transactions_amount_non_negative", type_="check")
        batch_op.create_check_constraint(
            "ck_transactions_amount_non_negative",
            "amount >= 0 OR transaction_type = 'savings'",
        )
