from datetime import date

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models import Account, Transaction


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
    statement: Select[tuple[Transaction]] = select(Transaction).order_by(
        Transaction.transaction_date.desc(), Transaction.id.desc()
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


def save_transaction(db: Session, transaction: Transaction) -> Transaction:
    """Insert or update a transaction and return its refreshed database state."""
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


def delete_transaction(db: Session, transaction: Transaction) -> None:
    """Delete a transaction after the service has confirmed it may be deleted."""
    db.delete(transaction)
    db.commit()
