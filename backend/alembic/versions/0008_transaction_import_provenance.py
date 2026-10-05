"""Link imported transactions to their source rows for stable display ordering.

Revision ID: 0008_import_provenance
Revises: 0007_import_description_predictions
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_import_provenance"
down_revision = "0007_import_description_predictions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Historical rows stay unlinked: matching them by date/amount/merchant
    # would be ambiguous for repeated payments and could invent provenance.
    with op.batch_alter_table("transactions") as batch:
        batch.add_column(sa.Column("import_draft_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_transaction_import_draft",
            "import_draft_rows",
            ["import_draft_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_transactions_import_draft_id", ["import_draft_id"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch:
        batch.drop_index("ix_transactions_import_draft_id")
        batch.drop_constraint("fk_transaction_import_draft", type_="foreignkey")
        batch.drop_column("import_draft_id")
