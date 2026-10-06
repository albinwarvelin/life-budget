from datetime import date

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import Account, ImportDraftRow, Transaction


def get_transaction(db: Session, transaction_id: int) -> Transaction | None:
    """Fetch one transaction by primary key without applying business rules."""
    return db.get(Transaction, transaction_id)


def list_transactions(
    db: Session,
    *,
    currency_code: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    transaction_type: str | None = None,
    account_id: int | None = None,
) -> list[Transaction]:
    """Build and execute the transaction list query used by the API."""
    # Keep each import together within a date, positioned by its most recently
    # inserted transaction. Inside that group the bank screenshot's top-to-
    # bottom row order wins over insertion order. Manual and historical rows
    # retain their existing newest-ID-first tie break.
    import_groups = (
        select(
            ImportDraftRow.batch_id.label("batch_id"),
            func.max(Transaction.id).label("latest_transaction_id"),
        )
        .join(Transaction, Transaction.import_draft_id == ImportDraftRow.id)
        .group_by(ImportDraftRow.batch_id)
        .subquery()
    )
    statement: Select[tuple[Transaction]] = (
        select(Transaction)
        .outerjoin(ImportDraftRow, Transaction.import_draft_id == ImportDraftRow.id)
        .outerjoin(import_groups, ImportDraftRow.batch_id == import_groups.c.batch_id)
        .order_by(
            Transaction.transaction_date.desc(),
            func.coalesce(import_groups.c.latest_transaction_id, Transaction.id).desc(),
            ImportDraftRow.row_index.asc(),
            Transaction.id.desc(),
        )
    )
    if currency_code:
        statement = statement.where(Transaction.currency_code == currency_code.upper())
    if from_date:
        statement = statement.where(Transaction.transaction_date >= from_date)
    if to_date:
        statement = statement.where(Transaction.transaction_date <= to_date)
    if transaction_type:
        statement = statement.where(Transaction.transaction_type == transaction_type)
    if account_id:
        statement = statement.where(Transaction.account_id == account_id)
    return list(db.scalars(statement))


def list_accounts_with_balance_history(
    db: Session,
    *,
    currency_code: str | None = None,
    account_id: int | None = None,
) -> list[Account]:
    """Return filtered accounts that own at least one recorded transaction."""
    statement = (
        select(Account)
        .join(Transaction, Transaction.account_id == Account.id)
        .distinct()
        .order_by(Account.name, Account.id)
    )
    if currency_code:
        statement = statement.where(Account.currency_code == currency_code.upper())
    if account_id:
        statement = statement.where(Account.id == account_id)
    return list(db.scalars(statement))


def list_balance_transactions(
    db: Session,
    *,
    account_ids: list[int],
) -> list[Transaction]:
    """Load complete account histories without transaction-type filtering."""
    if not account_ids:
        return []
    statement = (
        select(Transaction)
        .where(Transaction.account_id.in_(account_ids))
        .order_by(Transaction.transaction_date, Transaction.id)
    )
    return list(db.scalars(statement))
