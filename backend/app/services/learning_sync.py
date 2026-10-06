"""Idempotent projection of reviewed ledger values into the local ML store."""

import logging
from threading import RLock

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import ImportDraftRow, Transaction
from app.models.budget import LearningOutbox
from app.prediction_db import PredictionSessionLocal, ensure_prediction_schema
from app.prediction_models import PredictionState, TrainingExample

logger = logging.getLogger(__name__)
sync_lock = RLock()


def reviewed_direction(transaction: Transaction) -> tuple[str, str]:
    """Prefer the reviewed bank sign, otherwise use the reviewed ledger semantics.

    This fallback is recorded explicitly, not presented as a recovered bank sign.
    Savings/transfer amounts already preserve direction in the current domain.
    """
    if transaction.source_signed_amount is not None:
        amount = transaction.source_signed_amount
        origin = "source"
    else:
        amount = (
            -abs(transaction.amount)
            if transaction.transaction_type == "expense"
            else transaction.amount
        )
        origin = "reviewed_type"
    return ("incoming" if amount > 0 else "outgoing" if amount < 0 else "neutral"), origin


def queue_transaction(db: Session, transaction: Transaction, *, operation: str = "upsert") -> None:
    """Queue without committing: callers include this in the financial transaction."""
    db.flush()
    direction, origin = reviewed_direction(transaction)
    draft = (
        db.get(ImportDraftRow, transaction.import_draft_id) if transaction.import_draft_id else None
    )
    payload = {
        "merchant": transaction.merchant,
        "amount": str(abs(transaction.amount)),
        "currency_code": transaction.currency_code,
        "direction": direction,
        "direction_origin": origin,
        "account_id": transaction.account_id,
        "category_id": transaction.category_id,
        "transaction_type": transaction.transaction_type,
        "description": transaction.description or "",
        # This user explicitly reviews every inserted field. All confirmed
        # labels have full weight; model-generated origin is not a penalty.
        "weight": 1.0,
        "group": f"import:{draft.batch_id}" if draft else f"transaction:{transaction.id}",
        "confirmed_at": (transaction.updated_at.isoformat() if transaction.updated_at else ""),
    }
    db.add(LearningOutbox(transaction_id=transaction.id, operation=operation, payload=payload))


def rebuild_projection(db: Session, learning_db: Session) -> int:
    """Seed from current reviewed transactions, never from old accumulated patterns."""
    transactions = list(
        db.scalars(select(Transaction).order_by(Transaction.created_at, Transaction.id))
    )
    current = {transaction.id for transaction in transactions}
    for transaction in transactions:
        queue_transaction(db, transaction)
    known = set(learning_db.scalars(select(TrainingExample.transaction_id)))
    known.update(
        db.scalars(select(LearningOutbox.transaction_id).where(LearningOutbox.delivered.is_(False)))
    )
    for identifier in known - current:
        db.add(LearningOutbox(transaction_id=identifier, operation="delete", payload={}))
    db.commit()
    state = learning_db.get(PredictionState, 1)
    if state is None:
        state = PredictionState(id=1, initialized=True, dataset_revision=0)
        learning_db.add(state)
    state.initialized = True
    # An older restored ledger may have smaller outbox IDs than its projection.
    # Reset the disposable examples so authoritative restored rows are accepted.
    learning_db.execute(delete(TrainingExample))
    state.dataset_revision = 0
    state.active_snapshot_id = None
    learning_db.commit()
    synchronize(db, learning_db)
    return len(transactions)


def synchronize(db: Session, learning_db: Session) -> None:
    """Deliver ordered revisions; crash/retry cannot duplicate or resurrect examples."""
    with sync_lock:
        state = learning_db.get(PredictionState, 1)
        if state is None or not state.initialized:
            rebuild_projection(db, learning_db)
            state = learning_db.get(PredictionState, 1)
        while True:
            events = list(
                db.scalars(
                    select(LearningOutbox)
                    .where(LearningOutbox.delivered.is_(False))
                    .order_by(LearningOutbox.id)
                    .limit(500)
                )
            )
            if not events:
                return
            for event in events:
                example = learning_db.get(TrainingExample, event.transaction_id)
                if example is None:
                    example = TrainingExample(
                        transaction_id=event.transaction_id, revision=0, active=False, payload={}
                    )
                    learning_db.add(example)
                if event.id > example.revision:
                    example.revision = event.id
                    example.active = event.operation != "delete"
                    example.payload = event.payload
                state.dataset_revision = max(state.dataset_revision, event.id)
            # Commit the receiving side first. A failed acknowledgement simply
            # replays the same revisions, which the check above ignores.
            learning_db.commit()
            for event in events:
                event.delivered = True
            db.commit()


def try_synchronize(db: Session) -> None:
    """An ML outage cannot undo a saved financial record; pending events survive."""
    try:
        ensure_prediction_schema()
        with PredictionSessionLocal() as learning_db:
            synchronize(db, learning_db)
    except Exception:
        db.rollback()
        # Exception text/SQL parameters may contain financial data. Status
        # exposes pending counts, while logs contain only this safe message.
        logger.error("Learning synchronization failed; reviewed updates remain queued")


def pending_count(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(LearningOutbox)
            .where(LearningOutbox.delivered.is_(False))
        )
        or 0
    )
