from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Account, Category, Currency, Transaction
from app.schemas import (
    AccountCreate,
    AccountResponse,
    CategoryCreate,
    CategoryResponse,
    CurrencyCreate,
    CurrencyResponse,
    TransactionCreate,
    TransactionResponse,
)

router = APIRouter()
"""Domain routes for the first budget vertical slice."""


@router.post("/currencies", response_model=CurrencyResponse, status_code=status.HTTP_201_CREATED)
def create_currency(payload: CurrencyCreate, db: Session = Depends(get_db)) -> Currency:
    """Add an optional currency, rejecting duplicate ISO-like codes."""
    if db.get(Currency, payload.code):
        raise HTTPException(status_code=409, detail="Currency code already exists")
    currency = Currency(**payload.model_dump())
    db.add(currency)
    db.commit()
    db.refresh(currency)
    return currency


@router.get("/currencies", response_model=list[CurrencyResponse])
def list_currencies(db: Session = Depends(get_db)) -> list[Currency]:
    """Return the currencies currently enabled in the user's catalog."""
    return list(db.scalars(select(Currency).order_by(Currency.code)))


@router.post("/accounts", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(payload: AccountCreate, db: Session = Depends(get_db)) -> Account:
    """Create an account only when its currency has been explicitly enabled."""
    if not db.get(Currency, payload.currency_code):
        raise HTTPException(
            status_code=400, detail="currency_code does not reference an existing currency"
        )
    account = Account(**payload.model_dump())
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.get("/accounts", response_model=list[AccountResponse])
def list_accounts(db: Session = Depends(get_db)) -> list[Account]:
    """Return accounts ordered by display name."""
    return list(db.scalars(select(Account).order_by(Account.name)))


@router.post("/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(payload: CategoryCreate, db: Session = Depends(get_db)) -> Category:
    """Create a category and validate its optional parent relationship."""
    if payload.parent_id is not None and not db.get(Category, payload.parent_id):
        raise HTTPException(
            status_code=400, detail="parent_id does not reference an existing category"
        )
    category = Category(**payload.model_dump())
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.get("/categories", response_model=list[CategoryResponse])
def list_categories(db: Session = Depends(get_db)) -> list[Category]:
    """Return categories ordered by display name."""
    return list(db.scalars(select(Category).order_by(Category.name)))


def _get_transaction_or_404(transaction_id: int, db: Session) -> Transaction:
    """Load a transaction for an edit/delete operation or return a clear 404."""
    transaction = db.get(Transaction, transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return transaction


def _validate_transaction(payload: TransactionCreate, db: Session) -> None:
    """Enforce relationship and currency invariants before writing a transaction."""
    account = db.get(Account, payload.account_id)
    if not account:
        raise HTTPException(
            status_code=400, detail="account_id does not reference an existing account"
        )
    if account.currency_code != payload.currency_code:
        raise HTTPException(
            status_code=400, detail="Transaction currency must match account currency"
        )
    if payload.category_id is not None:
        category = db.get(Category, payload.category_id)
        if not category:
            raise HTTPException(
                status_code=400, detail="category_id does not reference an existing category"
            )
        if payload.transaction_type == "transfer" or category.kind != payload.transaction_type:
            raise HTTPException(
                status_code=400,
                detail="Category kind must match transaction type; transfers have no category",
            )


@router.post(
    "/transactions", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED
)
def create_transaction(payload: TransactionCreate, db: Session = Depends(get_db)) -> Transaction:
    """Persist a validated manual transaction."""
    _validate_transaction(payload, db)
    transaction = Transaction(**payload.model_dump())
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


@router.get("/transactions", response_model=list[TransactionResponse])
def list_transactions(
    currency_code: str | None = Query(default=None, min_length=3, max_length=3),
    from_date: date | None = None,
    to_date: date | None = None,
    transaction_type: str | None = Query(default=None, pattern="^(expense|income|transfer)$"),
    db: Session = Depends(get_db),
) -> list[Transaction]:
    """List transactions with backend-validated date, currency, and type filters."""
    statement = select(Transaction).order_by(
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
    return list(db.scalars(statement))


@router.put("/transactions/{transaction_id}", response_model=TransactionResponse)
def update_transaction(
    transaction_id: int, payload: TransactionCreate, db: Session = Depends(get_db)
) -> Transaction:
    """Replace a transaction after rechecking all financial invariants."""
    transaction = _get_transaction_or_404(transaction_id, db)
    _validate_transaction(payload, db)
    for key, value in payload.model_dump().items():
        setattr(transaction, key, value)
    db.commit()
    db.refresh(transaction)
    return transaction


@router.delete("/transactions/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)) -> None:
    """Delete a transaction after locating it explicitly."""
    transaction = _get_transaction_or_404(transaction_id, db)
    db.delete(transaction)
    db.commit()
