from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.learning_models import CategoryLearningEvent, CategoryPattern


def save_learning_event(
    db: Session,
    *,
    merchant_normalized: str,
    description_normalized: str,
    category_id: int,
    account_id: int | None,
    transaction_type: str | None,
    source: str,
) -> CategoryLearningEvent:
    """Append one user-confirmed learning event."""
    event = CategoryLearningEvent(
        merchant_normalized=merchant_normalized,
        description_normalized=description_normalized,
        category_id=category_id,
        account_id=account_id,
        transaction_type=transaction_type,
        source=source,
    )
    db.add(event)
    return event


def get_pattern(
    db: Session,
    *,
    pattern_type: str,
    pattern_text: str,
    category_id: int,
    account_id: int | None,
    transaction_type: str | None,
) -> CategoryPattern | None:
    """Find one weighted input-to-category connection."""
    return db.scalar(
        select(CategoryPattern).where(
            CategoryPattern.pattern_type == pattern_type,
            CategoryPattern.pattern_text == pattern_text,
            CategoryPattern.category_id == category_id,
            CategoryPattern.account_id == account_id,
            CategoryPattern.transaction_type == transaction_type,
        )
    )


def list_patterns(db: Session, *, limit: int = 2000) -> list[CategoryPattern]:
    """Return the strongest learned connections for inspection in the UI."""
    return list(
        db.scalars(
            select(CategoryPattern)
            .order_by(CategoryPattern.weight.desc(), CategoryPattern.id)
            .limit(limit)
        )
    )


def count_learning_events(db: Session) -> int:
    """Return an aggregate count without exposing the event history."""
    return int(db.scalar(select(func.count(CategoryLearningEvent.id))) or 0)


def list_matching_patterns(
    db: Session, *, account_id: int | None, transaction_type: str | None
) -> list[CategoryPattern]:
    """Limit prediction work to global and relevant account/type patterns."""
    return list(
        db.scalars(
            select(CategoryPattern).where(
                or_(CategoryPattern.account_id.is_(None), CategoryPattern.account_id == account_id),
                or_(
                    CategoryPattern.transaction_type.is_(None),
                    CategoryPattern.transaction_type == transaction_type,
                ),
            )
        )
    )
