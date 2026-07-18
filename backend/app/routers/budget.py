from datetime import date
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
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
from app.services.transactions import (
    TransactionValidationError,
    create_transaction as create_transaction_service,
    find_transactions,
    remove_transaction,
    update_transaction as update_transaction_service,
)

router = APIRouter()
"""Domain routes for the first budget vertical slice."""

MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024
ALLOWED_ATTACHMENT_TYPES = {"application/pdf", "text/plain", "text/csv", "application/json"}


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


@router.post(
    "/transactions", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED
)
def create_transaction(payload: TransactionCreate, db: Session = Depends(get_db)) -> Transaction:
    """Persist a validated manual transaction."""
    try:
        return create_transaction_service(db, payload)
    except TransactionValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/transactions", response_model=list[TransactionResponse])
def list_transactions(
    currency_code: str | None = Query(default=None, min_length=3, max_length=3),
    from_date: date | None = None,
    to_date: date | None = None,
    transaction_type: str | None = Query(
        default=None, pattern="^(expense|income|reimbursement|transfer)$"
    ),
    db: Session = Depends(get_db),
) -> list[Transaction]:
    """List transactions with backend-validated date, currency, and type filters."""
    return find_transactions(
        db,
        currency_code=currency_code,
        from_date=from_date,
        to_date=to_date,
        transaction_type=transaction_type,
    )


@router.put("/transactions/{transaction_id}", response_model=TransactionResponse)
def update_transaction(
    transaction_id: int, payload: TransactionCreate, db: Session = Depends(get_db)
) -> Transaction:
    """Replace a transaction after rechecking all financial invariants."""
    try:
        return update_transaction_service(db, transaction_id, payload)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except TransactionValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.delete("/transactions/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)) -> None:
    """Delete a transaction after locating it explicitly."""
    try:
        remove_transaction(db, transaction_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/transactions/{transaction_id}/attachment", response_model=TransactionResponse)
async def attach_transaction_file(
    transaction_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> Transaction:
    """Store one local file/image for a transaction after size/type validation."""
    transaction = db.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    content_type = file.content_type or "application/octet-stream"
    if not (content_type.startswith("image/") or content_type in ALLOWED_ATTACHMENT_TYPES):
        raise HTTPException(status_code=415, detail="Attachment type is not supported")

    content = await file.read(MAX_ATTACHMENT_SIZE + 1)
    if len(content) > MAX_ATTACHMENT_SIZE:
        raise HTTPException(status_code=413, detail="Attachment must be 10 MB or smaller")
    original_name = Path(file.filename or "attachment").name
    upload_directory = Path(get_settings().upload_dir)
    upload_directory.mkdir(parents=True, exist_ok=True)
    stored_path = upload_directory / f"{uuid4().hex}_{original_name}"

    # Remove the previous local file only after the new content has passed validation.
    if transaction.attachment_path:
        previous_path = Path(transaction.attachment_path)
        if previous_path.exists():
            previous_path.unlink()
    stored_path.write_bytes(content)
    transaction.attachment_filename = original_name
    transaction.attachment_path = str(stored_path)
    transaction.attachment_content_type = content_type
    transaction.attachment_size = len(content)
    db.commit()
    db.refresh(transaction)
    return transaction


@router.delete("/transactions/{transaction_id}/attachment", status_code=status.HTTP_204_NO_CONTENT)
def remove_transaction_attachment(transaction_id: int, db: Session = Depends(get_db)) -> None:
    """Remove the local attachment while keeping the transaction itself."""
    transaction = db.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if transaction.attachment_path:
        attachment_path = Path(transaction.attachment_path)
        if attachment_path.exists():
            attachment_path.unlink()
    transaction.attachment_filename = None
    transaction.attachment_path = None
    transaction.attachment_content_type = None
    transaction.attachment_size = None
    db.commit()
