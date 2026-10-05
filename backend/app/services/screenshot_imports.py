import logging
from collections import Counter
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.description_learning_db import (
    DescriptionLearningSessionLocal,
    ensure_description_learning_schema,
)
from app.learning_db import LearningSessionLocal, ensure_learning_schema
from app.models import ImportBatch, ImportDraftRow, Transaction
from app.repositories.imports import get_import_batch, replace_import_drafts
from app.schemas import TransactionCreate
from app.schemas_imports import ApproveImportRequest, ApproveImportResponse
from app.schemas_learning import CategoryPredictionRequest
from app.services.category_learning import learn_from_transaction, predict_categories
from app.services.description_learning import (
    predict_description,
    record_description_learning_event,
)
from app.services.screenshot_parser import ScreenshotParserError, TesseractScreenshotParser
from app.services.transactions import validate_transaction
from app.services.type_learning import predict_transaction_type, record_type_learning_event
from app.type_learning_db import TypeLearningSessionLocal, ensure_type_learning_schema

logger = logging.getLogger(__name__)
screenshot_parser = TesseractScreenshotParser()


def process_screenshot_batch(batch_id: int) -> None:
    """Background extraction pipeline with persisted progress for polling clients."""
    with SessionLocal() as db:
        batch = get_import_batch(db, batch_id)
        if batch is None:
            return
        try:
            batch.status = "processing"
            batch.progress = 10
            db.commit()
            fallback_year = _recent_account_import_year(
                db,
                account_id=batch.account_id,
                exclude_batch_id=batch.id,
            )
            extracted_rows = screenshot_parser.parse(
                Path(batch.stored_path),
                batch.currency_code,
                fallback_year=fallback_year,
            )
            # Repeated visual rows remain separate drafts. Flag equal readable
            # values within this image as well as matches against saved records.
            row_identities = Counter(
                (row.transaction_date, row.signed_amount, (row.merchant or "").casefold())
                for row in extracted_rows
                if row.transaction_date is not None
                and row.signed_amount is not None
                and row.merchant
            )
            batch.progress = 40
            db.commit()

            ensure_learning_schema()
            ensure_type_learning_schema()
            ensure_description_learning_schema()
            drafts: list[ImportDraftRow] = []
            with (
                LearningSessionLocal() as category_db,
                TypeLearningSessionLocal() as type_db,
                DescriptionLearningSessionLocal() as description_db,
            ):
                total = max(len(extracted_rows), 1)
                for index, extracted in enumerate(extracted_rows):
                    validation_errors = _validation_errors(extracted)
                    category_id, category_confidence = _predict_category(
                        db,
                        category_db,
                        merchant=extracted.merchant or "Unknown merchant",
                        description=extracted.description,
                        signed_amount=extracted.signed_amount or Decimal("0"),
                        account_id=batch.account_id,
                        currency_code=batch.currency_code,
                    )
                    type_prediction = predict_transaction_type(
                        type_db,
                        amount=extracted.signed_amount or Decimal("0"),
                        merchant=extracted.merchant or "",
                        category_id=category_id,
                        currency_code=batch.currency_code,
                    )
                    description_prediction = predict_description(
                        description_db,
                        merchant=extracted.merchant or "",
                        amount=extracted.signed_amount or Decimal("0"),
                        currency_code=batch.currency_code,
                        category_id=category_id,
                        transaction_type=type_prediction.transaction_type,
                    )
                    suggested_description = (
                        extracted.description or description_prediction.description
                    )
                    duplicate = (
                        _possible_duplicate(
                            db,
                            account_id=batch.account_id,
                            transaction_date=extracted.transaction_date,
                            signed_amount=extracted.signed_amount,
                            merchant=extracted.merchant,
                            transaction_type=type_prediction.transaction_type,
                        )
                        or row_identities[
                            (
                                extracted.transaction_date,
                                extracted.signed_amount,
                                (extracted.merchant or "").casefold(),
                            )
                        ]
                        > 1
                    )
                    drafts.append(
                        ImportDraftRow(
                            row_index=index,
                            raw_text=extracted.raw_text,
                            raw_amount_text=extracted.raw_amount_text,
                            source_bounds=extracted.bounds,
                            transaction_date=extracted.transaction_date,
                            merchant=extracted.merchant,
                            description=suggested_description,
                            predicted_description=description_prediction.description,
                            signed_amount=extracted.signed_amount,
                            # Import currency is owned by the selected account,
                            # never by a foreign amount annotation found by OCR.
                            currency_code=batch.currency_code,
                            account_id=batch.account_id,
                            predicted_category_id=category_id,
                            predicted_transaction_type=type_prediction.transaction_type,
                            category_confidence=category_confidence,
                            type_confidence=type_prediction.confidence,
                            description_confidence=(
                                description_prediction.confidence
                                if description_prediction.description
                                else 0.0
                            ),
                            extraction_confidence=extracted.confidence,
                            validation_errors=validation_errors,
                            possible_duplicate=duplicate,
                        )
                    )
                    batch.progress = 40 + round(50 * (index + 1) / total)
                    db.commit()
            replace_import_drafts(db, batch, drafts)
            batch.status = "review"
            batch.progress = 100
            batch.error_message = None
            db.commit()
        except ScreenshotParserError as error:
            batch.status = "error"
            batch.error_message = str(error)
            batch.progress = 100
            db.commit()
        except Exception:
            logger.exception("Screenshot import batch %s failed", batch_id)
            batch.status = "error"
            batch.error_message = "The screenshot could not be processed"
            batch.progress = 100
            db.commit()


def approve_screenshot_import(
    db: Session, batch_id: int, payload: ApproveImportRequest
) -> ApproveImportResponse:
    """Validate every accepted row, commit once, then teach both prediction stores."""
    batch = get_import_batch(db, batch_id)
    if batch is None:
        raise LookupError("Import batch not found")
    if batch.status != "review":
        raise ValueError("Import batch is not ready for approval")
    drafts = {draft.id: draft for draft in batch.drafts}
    if len({row.draft_id for row in payload.rows}) != len(payload.rows):
        raise ValueError("A draft row was submitted more than once")
    if {row.draft_id for row in payload.rows} != set(drafts):
        raise ValueError("Every draft row must be accepted or rejected before completing an import")
    transactions: list[tuple[Transaction, Decimal]] = []
    rejected: list[int] = []
    for approved in payload.rows:
        draft = drafts.get(approved.draft_id)
        if draft is None:
            raise ValueError("A draft row does not belong to this import batch")
        if not approved.accepted:
            draft.status = "rejected"
            rejected.append(draft.id)
            continue
        # The request schema guarantees these values for accepted rows, while
        # leaving them optional for an unreadable row the user rejected.
        if (
            approved.transaction_date is None
            or approved.merchant is None
            or approved.signed_amount is None
        ):
            raise ValueError("Accepted import rows require a date, merchant, and amount")
        stored_amount = (
            approved.signed_amount
            if approved.transaction_type in {"savings", "transfer"}
            else abs(approved.signed_amount)
        )
        transaction_payload = TransactionCreate(
            transaction_date=approved.transaction_date,
            account_id=approved.account_id,
            amount=stored_amount,
            currency_code=approved.currency_code,
            transaction_type=approved.transaction_type,
            description=approved.description,
            merchant=approved.merchant,
            category_id=approved.category_id,
            notes=approved.notes,
            source="screenshot",
        )
        validate_transaction(db, transaction_payload)
        transaction = Transaction(**transaction_payload.model_dump(), import_draft_id=draft.id)
        db.add(transaction)
        draft.status = "accepted"
        transactions.append((transaction, approved.signed_amount))
    batch.status = "completed"
    db.commit()
    for transaction, source_signed_amount in transactions:
        db.refresh(transaction)
        learn_from_transaction(transaction)
        try:
            record_type_learning_event(
                amount=source_signed_amount,
                merchant=transaction.merchant,
                category_id=transaction.category_id,
                transaction_type=transaction.transaction_type,
                currency_code=transaction.currency_code,
            )
        except Exception:
            # A learning-store outage must never roll back accepted finances.
            logger.exception("Could not update transaction-type learning data")
        try:
            record_description_learning_event(
                amount=source_signed_amount,
                merchant=transaction.merchant,
                currency_code=transaction.currency_code,
                category_id=transaction.category_id,
                transaction_type=transaction.transaction_type,
                description=transaction.description,
            )
        except Exception:
            logger.exception("Could not update description-learning data")
    return ApproveImportResponse(
        batch_id=batch.id,
        created_transaction_ids=[transaction.id for transaction, _ in transactions],
        rejected_draft_ids=rejected,
    )


def _predict_category(
    main_db,
    category_db,
    *,
    merchant: str,
    description: str | None,
    signed_amount: Decimal,
    account_id: int,
    currency_code: str,
) -> tuple[int | None, float]:
    """Use the existing model before type prediction, with sign only as a scope hint."""
    type_order = (
        ("expense", "transfer", "savings", "reimbursement", "income")
        if signed_amount < 0
        else ("income", "reimbursement", "transfer", "savings", "expense")
    )
    for transaction_type in type_order:
        suggestions = predict_categories(
            main_db,
            category_db,
            CategoryPredictionRequest(
                merchant=merchant,
                description=description,
                account_id=account_id,
                transaction_type=transaction_type,
                amount=signed_amount,
                currency_code=currency_code,
            ),
        )
        if suggestions:
            return suggestions[0].category_id, suggestions[0].confidence
    return None, 0.0


def _recent_account_import_year(
    db: Session,
    *,
    account_id: int,
    exclude_batch_id: int | None = None,
) -> int | None:
    """Recall the latest persisted import year for one account.

    A previous reviewed import is the best reference because it came through
    the same OCR workflow. A recently created transaction is a fallback for an
    account that has not completed a screenshot import yet. No current-calendar
    guess is made when neither source exists.
    """
    imported_date = db.scalar(
        select(ImportDraftRow.transaction_date)
        .join(ImportBatch, ImportDraftRow.batch_id == ImportBatch.id)
        .where(
            ImportBatch.account_id == account_id,
            ImportBatch.id != exclude_batch_id if exclude_batch_id is not None else True,
            ImportBatch.status.in_(("review", "completed")),
            ImportDraftRow.transaction_date.is_not(None),
        )
        .order_by(ImportBatch.updated_at.desc(), ImportDraftRow.id.desc())
        .limit(1)
    )
    if imported_date is not None:
        return imported_date.year

    transaction_date = db.scalar(
        select(Transaction.transaction_date)
        .where(Transaction.account_id == account_id)
        .order_by(Transaction.created_at.desc(), Transaction.id.desc())
        .limit(1)
    )
    return transaction_date.year if transaction_date is not None else None


def _validation_errors(extracted) -> list[str]:
    errors: list[str] = []
    if extracted.transaction_date is None:
        errors.append("Date could not be read")
    if not extracted.merchant:
        errors.append("Merchant could not be read")
    if extracted.signed_amount is None:
        errors.append("Amount could not be read")
    return errors


def _possible_duplicate(
    db,
    *,
    account_id: int,
    transaction_date,
    signed_amount: Decimal | None,
    merchant: str | None,
    transaction_type: str,
) -> bool:
    if transaction_date is None or signed_amount is None or not merchant:
        return False
    stored_amount = (
        signed_amount if transaction_type in {"savings", "transfer"} else abs(signed_amount)
    )
    return (
        db.scalar(
            select(Transaction.id).where(
                Transaction.account_id == account_id,
                Transaction.transaction_date == transaction_date,
                Transaction.amount == stored_amount,
                func.lower(Transaction.merchant) == merchant.lower(),
            )
        )
        is not None
    )
