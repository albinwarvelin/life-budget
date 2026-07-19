"""Merge the localized-category and signed-transfer migration branches.

Revision ID: 0005_merge_budget_heads
Revises: 0004_localized_categories_optional_descriptions, 0004_signed_transfers
"""

# This is a graph-only migration. Both 0004 revisions contain real schema
# changes, so Alembic must apply both before considering the budget database
# history unified again.

revision = "0005_merge_budget_heads"
down_revision = ("0004_localized_categories_optional_descriptions", "0004_signed_transfers")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Mark both completed branches as one shared migration history."""


def downgrade() -> None:
    """Re-expose the two historical branches when rolling back the merge."""
