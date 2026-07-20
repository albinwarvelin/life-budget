from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.description_learning_models import DescriptionLearningEvent, DescriptionPattern


def find_description_pattern(
    db: Session, *, pattern_type: str, pattern_text: str, description_normalized: str
) -> DescriptionPattern | None:
    return db.scalar(
        select(DescriptionPattern).where(
            DescriptionPattern.pattern_type == pattern_type,
            DescriptionPattern.pattern_text == pattern_text,
            DescriptionPattern.description_normalized == description_normalized,
        )
    )


def list_description_patterns(db: Session, *, limit: int = 2000) -> list[DescriptionPattern]:
    return list(
        db.scalars(
            select(DescriptionPattern)
            .order_by(DescriptionPattern.weight.desc(), DescriptionPattern.id)
            .limit(limit)
        )
    )


def list_description_events(db: Session, *, limit: int = 5000) -> list[DescriptionLearningEvent]:
    """Return confirmed examples used by the explainable description scorer."""
    return list(
        db.scalars(
            select(DescriptionLearningEvent)
            .order_by(DescriptionLearningEvent.id.desc())
            .limit(limit)
        )
    )


def count_description_events(db: Session) -> int:
    return int(db.scalar(select(func.count(DescriptionLearningEvent.id))) or 0)
