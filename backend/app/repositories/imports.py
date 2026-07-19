from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import ImportBatch, ImportDraftRow


def get_import_batch(db: Session, batch_id: int) -> ImportBatch | None:
    """Load a batch with draft rows for status polling and review."""
    return db.scalar(
        select(ImportBatch)
        .options(selectinload(ImportBatch.drafts))
        .where(ImportBatch.id == batch_id)
    )


def save_import_batch(db: Session, batch: ImportBatch) -> ImportBatch:
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def replace_import_drafts(db: Session, batch: ImportBatch, drafts: list[ImportDraftRow]) -> None:
    """Replace parser output atomically if a batch is intentionally reprocessed."""
    batch.drafts.clear()
    batch.drafts.extend(drafts)
    db.commit()
