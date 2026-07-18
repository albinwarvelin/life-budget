"""Add reimbursement types and local transaction attachment metadata.

Revision ID: 0002_reimbursements_and_attachments
Revises: 0001_initial_budget_schema
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_reimbursements_and_attachments"
down_revision = "0001_initial_budget_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite needs a batch table rebuild to change CHECK constraints safely.
    with op.batch_alter_table("categories", recreate="always") as batch_op:
        batch_op.alter_column("kind", type_=sa.String(length=15))
        batch_op.drop_constraint("ck_categories_kind", type_="check")
        batch_op.create_check_constraint(
            "ck_categories_kind", "kind IN ('expense', 'income', 'reimbursement')"
        )
    with op.batch_alter_table("transactions", recreate="always") as batch_op:
        batch_op.alter_column("transaction_type", type_=sa.String(length=15))
        batch_op.drop_constraint("ck_transactions_type", type_="check")
        batch_op.create_check_constraint(
            "ck_transactions_type",
            "transaction_type IN ('expense', 'income', 'reimbursement', 'transfer')",
        )
        batch_op.add_column(sa.Column("attachment_filename", sa.String(length=255)))
        batch_op.add_column(sa.Column("attachment_path", sa.String(length=500)))
        batch_op.add_column(sa.Column("attachment_content_type", sa.String(length=120)))
        batch_op.add_column(sa.Column("attachment_size", sa.Integer()))


def downgrade() -> None:
    with op.batch_alter_table("transactions", recreate="always") as batch_op:
        batch_op.drop_column("attachment_size")
        batch_op.drop_column("attachment_content_type")
        batch_op.drop_column("attachment_path")
        batch_op.drop_column("attachment_filename")
        batch_op.drop_constraint("ck_transactions_type", type_="check")
        batch_op.create_check_constraint(
            "ck_transactions_type", "transaction_type IN ('expense', 'income', 'transfer')"
        )
        batch_op.alter_column("transaction_type", type_=sa.String(length=10))
    with op.batch_alter_table("categories", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_categories_kind", type_="check")
        batch_op.create_check_constraint("ck_categories_kind", "kind IN ('expense', 'income')")
        batch_op.alter_column("kind", type_=sa.String(length=10))
