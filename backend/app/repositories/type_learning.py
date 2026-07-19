from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.type_learning_models import TypeLearningEvent, TypePattern


def find_type_pattern(
    db: Session,
    *,
    pattern_type: str,
    pattern_text: str,
    category_id: int | None,
    transaction_type: str,
) -> TypePattern | None:
    """Locate one learned feature connection before incrementing it."""
    return db.scalar(
        select(TypePattern).where(
            TypePattern.pattern_type == pattern_type,
            TypePattern.pattern_text == pattern_text,
            TypePattern.category_id == category_id,
            TypePattern.transaction_type == transaction_type,
        )
    )


def list_type_patterns(db: Session, *, limit: int = 5000) -> list[TypePattern]:
    """Return the small local model for one explainable scoring pass."""
    return list(db.scalars(select(TypePattern).order_by(TypePattern.weight.desc()).limit(limit)))


def count_type_events(db: Session) -> int:
    return int(db.scalar(select(func.count(TypeLearningEvent.id))) or 0)


def add_type_event(db: Session, event: TypeLearningEvent) -> None:
    db.add(event)
