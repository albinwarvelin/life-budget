"""Allow savings transactions and savings categories.

Revision ID: 0003_signed_savings
Revises: 0002_reimbursements_and_attachments
"""

from alembic import op

revision = "0003_signed_savings"
down_revision = "0002_reimbursements_and_attachments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite requires a batch rebuild when a CHECK constraint changes.
    with op.batch_alter_table("categories", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_categories_kind", type_="check")
        batch_op.create_check_constraint(
            "ck_categories_kind", "kind IN ('expense', 'income', 'reimbursement', 'savings')"
        )
    with op.batch_alter_table("transactions", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_transactions_type", type_="check")
        batch_op.create_check_constraint(
            "ck_transactions_type",
            "transaction_type IN ('expense', 'income', 'reimbursement', 'savings', 'transfer')",
        )
        batch_op.drop_constraint("ck_transactions_amount_non_negative", type_="check")
        batch_op.create_check_constraint(
            "ck_transactions_amount_non_negative",
            "amount >= 0 OR transaction_type = 'savings'",
        )


def downgrade() -> None:
    with op.batch_alter_table("transactions", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_transactions_amount_non_negative", type_="check")
        batch_op.create_check_constraint("ck_transactions_amount_non_negative", "amount >= 0")
        batch_op.drop_constraint("ck_transactions_type", type_="check")
        batch_op.create_check_constraint(
            "ck_transactions_type",
            "transaction_type IN ('expense', 'income', 'reimbursement', 'transfer')",
        )
    with op.batch_alter_table("categories", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_categories_kind", type_="check")
        batch_op.create_check_constraint(
            "ck_categories_kind", "kind IN ('expense', 'income', 'reimbursement')"
        )
