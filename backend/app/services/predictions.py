"""Reviewed-data prediction shared by imports, manual entry, and the tester."""

from collections import Counter
from decimal import Decimal

import numpy as np
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import Category, Transaction
from app.models.budget import LearningOutbox
from app.prediction_db import PredictionSessionLocal, ensure_prediction_schema
from app.prediction_models import ModelSnapshot, PredictionState, TrainingExample
from app.services.learning_sync import pending_count, sync_lock, synchronize
from app.services.prediction_features import normalize_text
from app.services.prediction_settings import MINIMUM_SUPPORT, configuration
from app.services.prediction_training import (
    ALGORITHM_VERSION,
    HEADS,
    Classifier,
    description_probabilities,
    model_probabilities,
    train_models,
)


def current_models(db: Session, learning_db: Session, *, retrain: bool = False) -> ModelSnapshot:
    """Reuse the active model until explicitly retrained; bootstrap on first prediction.

    Updating the ledger projection is cheap and independent of fitting. A model
    may therefore intentionally lag reviewed edits. Status requests never call
    this function. New algorithm versions bootstrap once at prediction/retrain.
    """
    with sync_lock:
        synchronize(db, learning_db)
        state = learning_db.get(PredictionState, 1)
        snapshot = (
            learning_db.get(ModelSnapshot, state.active_snapshot_id)
            if state.active_snapshot_id
            else None
        )
        if snapshot and snapshot.algorithm_version == ALGORITHM_VERSION and not retrain:
            return snapshot
        rows = [
            {**example.payload, "transaction_id": example.transaction_id}
            for example in learning_db.scalars(
                select(TrainingExample).where(TrainingExample.active.is_(True))
            )
        ]
        parameters, report = train_models(rows)
        descriptions: dict[str, Counter] = {}
        for row in rows:
            if row["description"].strip():
                descriptions.setdefault(normalize_text(row["description"]), Counter())[
                    row["description"].strip()
                ] += 1
        parameters["description_labels"] = {
            key: counts.most_common(1)[0][0] for key, counts in descriptions.items()
        }
        parameters["description_labels"]["__empty__"] = "Leave blank"
        parameters["currencies"] = sorted({row["currency_code"] for row in rows})
        snapshot = ModelSnapshot(
            dataset_revision=state.dataset_revision,
            algorithm_version=ALGORITHM_VERSION,
            parameters=parameters,
            report=report,
        )
        learning_db.add(snapshot)
        learning_db.flush()
        state.active_snapshot_id = snapshot.id
        # Retain a small rollback/debug history; large coefficient matrices
        # should not grow the disposable store indefinitely after each edit.
        retained = list(
            learning_db.scalars(select(ModelSnapshot.id).order_by(ModelSnapshot.id.desc()).limit(3))
        )
        learning_db.execute(delete(ModelSnapshot).where(ModelSnapshot.id.not_in(retained)))
        learning_db.commit()
        return snapshot


def observed_row(
    *,
    merchant: str,
    amount: Decimal | None,
    currency_code: str,
    account_id: int | None = None,
    transaction_type: str | None = None,
) -> dict:
    """Bank amount is signed; manual expense magnitude has a known type."""
    signed = -abs(amount) if amount is not None and transaction_type == "expense" else amount
    return {
        "merchant": merchant,
        "amount": str(abs(amount)) if amount is not None else None,
        "currency_code": currency_code.upper(),
        "account_id": account_id,
        "direction": "unknown"
        if signed is None
        else "incoming"
        if signed > 0
        else "outgoing"
        if signed < 0
        else "neutral",
    }


def predict_with_snapshot(
    db: Session, snapshot: ModelSnapshot, row: dict, *, transaction_type: str | None = None
) -> dict:
    """Description blends observed inputs with bounded, uncertain category context.

    Contributions are associations, not causes. Category contributions show
    the most likely type's conditional score; ranking uses the full mixture.
    """
    models = snapshot.parameters
    categories = {
        str(category.id): category
        for category in db.scalars(select(Category).where(Category.is_active.is_(True)))
    }
    outputs = {}
    # Exclude inactive/deleted categories without pretending the surviving
    # predictions are more certain. Unsupported mass falls back to direct input.
    category_probabilities, category_classes = model_probabilities(models, "category", [row])
    if transaction_type:
        category_probabilities = Classifier(models["category"]).probabilities(
            [{**row, "conditional_type": transaction_type}]
        )
    context_categories = category_probabilities.copy()
    for index, key in enumerate(category_classes):
        if key not in categories:
            context_categories[:, index] = 0
    for kind in HEADS:
        parameters = models[kind]
        context_weight = 0.0
        if kind == "category":
            probabilities, classes = category_probabilities, category_classes
        elif kind == "description":
            probabilities, classes, weights = description_probabilities(
                models, [row], category_scores=(context_categories, category_classes)
            )
            context_weight = float(weights[0])
        else:
            probabilities, classes = model_probabilities(models, kind, [row])
        candidates = []
        if classes and row["currency_code"] in models["currencies"]:
            for index in np.argsort(probabilities[0])[::-1]:
                key = classes[index]
                if kind == "category" and key not in categories:
                    continue
                display = (
                    categories[key].name
                    if kind == "category"
                    else models["description_labels"].get(key, key)
                    if kind == "description"
                    else key
                )
                explanation_row = row
                if kind == "category":
                    type_probabilities, type_classes = model_probabilities(models, "type", [row])
                    most_likely = transaction_type or (
                        type_classes[int(np.argmax(type_probabilities[0]))]
                        if type_classes
                        else None
                    )
                    explanation_row = {**row, "conditional_type": most_likely}
                candidates.append(
                    {
                        "key": key,
                        "label": display,
                        "probability": float(probabilities[0, index]),
                        "support": parameters["counts"][key],
                        "contributions": Classifier(parameters).contributions(explanation_row, key),
                    }
                )
                if len(candidates) == 3:
                    break
        top = candidates[0] if candidates else None
        accepted = bool(
            top
            and len(classes) > 1
            and top["probability"] >= parameters["threshold"]
            and top["support"] >= MINIMUM_SUPPORT
        )
        reason = (
            "Suggestion exceeds the configured threshold; review before saving."
            if accepted
            else "Insufficient evidence for a suggestion; alternatives require review."
        )
        if len(classes) == 1:
            reason = "Only one learned label: the model cannot establish certainty."
        if kind == "description" and top and top["key"] == "__empty__":
            accepted = False
            reason = "Reviewed examples favor leaving the description blank."
        if kind == "description" and context_weight:
            reason += f" Category context contributes {context_weight:.0%}; direct transaction evidence remains part of the score."
        outputs[kind] = {
            "suggestion": top["key"] if accepted else None,
            "confidence": top["probability"] if top else 0.0,
            "calibrated": parameters["calibrated"],
            "reason": reason,
            "context_weight": context_weight,
            "candidates": candidates,
        }
    return {"snapshot_id": snapshot.id, "outputs": outputs}


def predict(db: Session, row: dict, *, transaction_type: str | None = None) -> dict:
    ensure_prediction_schema()
    with PredictionSessionLocal() as learning_db:
        return predict_with_snapshot(
            db, current_models(db, learning_db), row, transaction_type=transaction_type
        )


def model_status(db: Session) -> dict:
    """Read existing metadata only: never synchronize, fit, or create a snapshot."""
    ensure_prediction_schema()
    with PredictionSessionLocal() as learning_db:
        state = learning_db.get(PredictionState, 1)
        snapshot = (
            learning_db.get(ModelSnapshot, state.active_snapshot_id)
            if state and state.active_snapshot_id
            else None
        )
        revision = snapshot.dataset_revision if snapshot else 0
        # Distinct IDs count an edited row once, including deleted rows and
        # events still undelivered after a temporary prediction-store outage.
        changed = set(
            learning_db.scalars(
                select(TrainingExample.transaction_id).where(TrainingExample.revision > revision)
            )
        )
        changed.update(
            db.scalars(
                select(LearningOutbox.transaction_id).where(LearningOutbox.delivered.is_(False))
            )
        )
        return {
            "reviewed_transactions": db.scalar(select(func.count()).select_from(Transaction)) or 0,
            "pending_updates": pending_count(db),
            "updates_since_training": len(changed),
            "needs_retraining": bool(changed)
            or not snapshot
            or snapshot.algorithm_version != ALGORITHM_VERSION,
            "snapshot_id": snapshot.id if snapshot else None,
            "dataset_revision": revision,
            "algorithm": snapshot.algorithm_version if snapshot else None,
            "created_at": snapshot.created_at if snapshot else None,
            "report": snapshot.report if snapshot else None,
            "configuration": configuration(),
            "heads": {
                kind: {
                    "labels": len(snapshot.parameters[kind]["classes"]) if snapshot else 0,
                    "calibrated": snapshot.parameters[kind]["calibrated"] if snapshot else False,
                    "threshold": snapshot.parameters[kind]["threshold"] if snapshot else 1.1,
                    "regularization": snapshot.parameters[kind]["regularization"]
                    if snapshot
                    else 1.0,
                    "temperature": snapshot.parameters[kind]["temperature"] if snapshot else 1.0,
                }
                for kind in HEADS
            },
        }


def retrain_models(db: Session) -> dict:
    """Explicit rebuild; a fitting failure leaves the previous snapshot active."""
    ensure_prediction_schema()
    with PredictionSessionLocal() as learning_db:
        current_models(db, learning_db, retrain=True)
    return model_status(db)
