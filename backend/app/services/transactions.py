from datetime import date

from sqlalchemy.orm import Session

from app.models import Account, Category, Transaction
from app.services.category_learning import learn_from_transaction
from app.repositories.transactions import (
    delete_transaction,
    get_transaction,
    list_transactions,
    save_transaction,
)
from app.schemas import TransactionCreate


class TransactionValidationError(ValueError):
    """Raised when a transaction violates a financial relationship rule."""


def require_transaction(db: Session, transaction_id: int) -> Transaction:
    """Return a transaction or raise a domain-level not-found error."""
    transaction = get_transaction(db, transaction_id)
    if transaction is None:
        raise LookupError("Transaction not found")
    return transaction


def validate_transaction(db: Session, payload: TransactionCreate) -> None:
    """Check relationships before persistence so route handlers stay thin."""
    if payload.transaction_type not in {"savings", "transfer"} and payload.amount < 0:
        raise TransactionValidationError("Only savings and transfer amounts may be negative")
    account = db.get(Account, payload.account_id)
    if account is None:
        raise TransactionValidationError("account_id does not reference an existing account")
    # Currency is never converted implicitly; an account and its transaction
    # must use exactly the same currency code.
    if account.currency_code != payload.currency_code:
        raise TransactionValidationError("Transaction currency must match account currency")
    if payload.category_id is None:
        return
    category = db.get(Category, payload.category_id)
    if category is None:
        raise TransactionValidationError("category_id does not reference an existing category")
    # Category kinds are labels, not a hard transaction constraint. This lets
    # users reuse or reclassify a category without being blocked by history.


def create_transaction(db: Session, payload: TransactionCreate) -> Transaction:
    """Validate and persist a new manually entered transaction."""
    validate_transaction(db, payload)
    transaction = save_transaction(db, Transaction(**payload.model_dump()))
    learn_from_transaction(transaction)
    return transaction


def find_transactions(
    db: Session,
    *,
    currency_code: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    transaction_type: str | None = None,
    account_id: int | None = None,
) -> list[Transaction]:
    """Return transactions using the repository's stable date/id ordering."""
    return list_transactions(
        db,
        currency_code=currency_code,
        from_date=from_date,
        to_date=to_date,
        transaction_type=transaction_type,
        account_id=account_id,
    )


def update_transaction(db: Session, transaction_id: int, payload: TransactionCreate) -> Transaction:
    """Validate and replace editable fields on an existing transaction."""
    transaction = require_transaction(db, transaction_id)
    validate_transaction(db, payload)
    for key, value in payload.model_dump().items():
        setattr(transaction, key, value)
    transaction = save_transaction(db, transaction)
    learn_from_transaction(transaction)
    return transaction


def remove_transaction(db: Session, transaction_id: int) -> None:
    """Delete one explicitly selected transaction."""
    delete_transaction(db, require_transaction(db, transaction_id))
