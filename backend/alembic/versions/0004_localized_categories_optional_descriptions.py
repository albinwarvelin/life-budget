"""Add localized category names and make transaction descriptions optional.

Revision ID: 0004_localized_categories_optional_descriptions
Revises: 0003_signed_savings
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_localized_categories_optional_descriptions"
down_revision = "0003_signed_savings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("categories", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("localized_names", sa.JSON(), nullable=True))
    op.execute("UPDATE categories SET localized_names = '{}' WHERE localized_names IS NULL")
    with op.batch_alter_table("categories", recreate="always") as batch_op:
        batch_op.alter_column("localized_names", nullable=False, server_default="{}")
    with op.batch_alter_table("transactions", recreate="always") as batch_op:
        batch_op.alter_column("description", nullable=True)
    # Older databases may contain manually entered rows without a merchant.
    # Preserve those rows while making the field mandatory for new entries.
    op.execute("UPDATE transactions SET merchant = '' WHERE merchant IS NULL")
    with op.batch_alter_table("transactions", recreate="always") as batch_op:
        batch_op.alter_column("merchant", nullable=False)

    # These defaults give a new user useful, bilingual choices without
    # preventing custom categories from being added later.
    seeds = [
        ("Groceries", "expense", '{"en":"Groceries","sv":"Matvaror"}'),
        ("Restaurants", "expense", '{"en":"Restaurants & cafes","sv":"Restauranger och caféer"}'),
        ("Housing", "expense", '{"en":"Housing","sv":"Boende"}'),
        ("Transport", "expense", '{"en":"Transport","sv":"Transport"}'),
        ("Shopping", "expense", '{"en":"Shopping","sv":"Shopping"}'),
        ("Health", "expense", '{"en":"Health","sv":"Hälsa"}'),
        ("Bills", "expense", '{"en":"Bills","sv":"Räkningar"}'),
        ("Entertainment", "expense", '{"en":"Entertainment","sv":"Nöjen"}'),
        ("Salary", "income", '{"en":"Salary","sv":"Lön"}'),
        ("Other income", "income", '{"en":"Other income","sv":"Övrig inkomst"}'),
        ("Reimbursement", "reimbursement", '{"en":"Reimbursement","sv":"Återbetalning"}'),
        ("Savings", "savings", '{"en":"Savings","sv":"Sparande"}'),
    ]
    for name, kind, localized_names in seeds:
        op.execute(
            sa.text(
                "INSERT INTO categories (name, kind, localized_names, is_active) "
                "SELECT :name, :kind, :localized_names, 1 "
                "WHERE NOT EXISTS (SELECT 1 FROM categories WHERE name = :name)"
            ).bindparams(name=name, kind=kind, localized_names=localized_names)
        )


def downgrade() -> None:
    with op.batch_alter_table("transactions", recreate="always") as batch_op:
        batch_op.alter_column("merchant", nullable=True)
        batch_op.alter_column("description", nullable=False)
    with op.batch_alter_table("categories", recreate="always") as batch_op:
        batch_op.drop_column("localized_names")
