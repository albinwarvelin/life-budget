"""Store screenshot description predictions and confidence.

Revision ID: 0007_import_description_predictions
Revises: 0006_screenshot_import_drafts
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_import_description_predictions"
down_revision = "0006_screenshot_import_drafts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "import_draft_rows", sa.Column("predicted_description", sa.String(240), nullable=True)
    )
    op.add_column(
        "import_draft_rows",
        sa.Column("description_confidence", sa.Float(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("import_draft_rows", "description_confidence")
    op.drop_column("import_draft_rows", "predicted_description")
