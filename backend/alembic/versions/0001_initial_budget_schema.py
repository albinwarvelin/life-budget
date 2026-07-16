"""Create the initial budget schema.

Revision ID: 0001_initial_budget_schema
Revises:
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_budget_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "currencies",
        sa.Column("code", sa.String(length=3), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("code"),
    )
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("account_type", sa.String(length=30), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("institution", sa.String(length=120), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["currency_code"], ["currencies.code"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("kind IN ('expense', 'income')", name="ck_categories_kind"),
        sa.ForeignKeyConstraint(["parent_id"], ["categories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("transaction_type", sa.String(length=10), nullable=False),
        sa.Column("description", sa.String(length=240), nullable=False),
        sa.Column("merchant", sa.String(length=160), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False
        ),
        sa.CheckConstraint(
            "transaction_type IN ('expense', 'income', 'transfer')", name="ck_transactions_type"
        ),
        sa.CheckConstraint("amount >= 0", name="ck_transactions_amount_non_negative"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.ForeignKeyConstraint(["currency_code"], ["currencies.code"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transactions_transaction_date", "transactions", ["transaction_date"])
    op.create_index("ix_transactions_account_id", "transactions", ["account_id"])
    op.create_index("ix_transactions_category_id", "transactions", ["category_id"])
    # Keep the first-run currency picker intentionally small. Other currencies
    # remain supported through POST /api/v1/currencies when the user needs them.
    op.bulk_insert(
        sa.table("currencies", sa.column("code", sa.String), sa.column("name", sa.String)),
        [
            {"code": "NOK", "name": "Norwegian krone"},
            {"code": "SEK", "name": "Swedish krona"},
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_category_id", table_name="transactions")
    op.drop_index("ix_transactions_account_id", table_name="transactions")
    op.drop_index("ix_transactions_transaction_date", table_name="transactions")
    op.drop_table("transactions")
    op.drop_table("categories")
    op.drop_table("accounts")
    op.drop_table("currencies")
