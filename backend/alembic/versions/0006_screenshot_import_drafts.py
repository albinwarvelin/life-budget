"""Add auditable screenshot import batches and editable draft rows.

Revision ID: 0006_screenshot_import_drafts
Revises: 0005_merge_budget_heads
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_screenshot_import_drafts"
down_revision = "0005_merge_budget_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("stored_path", sa.String(500), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("currency_code", sa.String(3), sa.ForeignKey("currencies.code"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()
        ),
    )
    op.create_index("ix_import_batches_status", "import_batches", ["status"])
    op.create_table(
        "import_draft_rows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("import_batches.id"), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("raw_amount_text", sa.String(80)),
        sa.Column("source_bounds", sa.JSON()),
        sa.Column("transaction_date", sa.Date()),
        sa.Column("merchant", sa.String(160)),
        sa.Column("description", sa.String(240)),
        sa.Column("signed_amount", sa.Numeric(18, 2)),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("predicted_category_id", sa.Integer()),
        sa.Column("predicted_transaction_type", sa.String(15)),
        sa.Column("category_confidence", sa.Float(), nullable=False),
        sa.Column("type_confidence", sa.Float(), nullable=False),
        sa.Column("extraction_confidence", sa.Float(), nullable=False),
        sa.Column("validation_errors", sa.JSON(), nullable=False),
        sa.Column("possible_duplicate", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
    )
    op.create_index("ix_import_draft_rows_batch_id", "import_draft_rows", ["batch_id"])


def downgrade() -> None:
    op.drop_index("ix_import_draft_rows_batch_id", table_name="import_draft_rows")
    op.drop_table("import_draft_rows")
    op.drop_index("ix_import_batches_status", table_name="import_batches")
    op.drop_table("import_batches")
