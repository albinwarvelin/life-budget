"""Synthetic regression tests for reviewed-data learning and uncertainty."""

import json
from datetime import date
from decimal import Decimal

import numpy as np
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.database_engine import create_database_engine
from app.models import Account, Category, Currency, Transaction
from app.models.budget import LearningOutbox
from app.prediction_db import PredictionBase
from app.prediction_models import ModelSnapshot, PredictionState, TrainingExample
from app.schemas import TransactionCreate
from app.services.learning_sync import queue_transaction, rebuild_projection, synchronize
from app.services.prediction_features import metadata_features
from app.services.prediction_training import (
    Classifier,
    chronology_split,
    description_probabilities,
    fit_classifier,
    train_models,
)
from app.services.predictions import current_models, observed_row, predict_with_snapshot
from app.services.transactions import create_transaction, remove_transaction, update_transaction


def synthetic_rows():
    rows = []
    for index in range(60):
        kind = index % 3
        rows.append(
            dict(
                transaction_id=index + 1,
                merchant=[
                    f"Person Name {chr(65 + index % 26)}",
                    "Synthetic Employer",
                    "Synthetic Supermarket",
                ][kind],
                amount=["50", "25000", "300"][kind],
                currency_code="NOK",
                direction=["incoming", "incoming", "outgoing"][kind],
                account_id=1,
                transaction_type=["reimbursement", "income", "expense"][kind],
                category_id=kind + 1,
                description=["Shared ride", "Monthly salary", "Food"][kind],
                confirmed_at=f"2026-01-{index // 3 + 1:02}",
                group=f"import:{index // 3}",
                weight=1.0,
            )
        )
    return rows


def sessions():
    main = create_database_engine("sqlite://", poolclass=StaticPool)
    projection = create_database_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(main)
    PredictionBase.metadata.create_all(projection)
    return Session(main, expire_on_commit=False), Session(projection, expire_on_commit=False)


def seed(db):
    db.add(Currency(code="NOK", name="Norwegian krone"))
    db.add(Account(id=1, name="Synthetic bank", account_type="bank", currency_code="NOK"))
    db.add_all(
        [
            Category(id=index, name=name, kind=kind)
            for index, name, kind in [
                (1, "Car", "expense"),
                (2, "Salary", "income"),
                (3, "Groceries", "expense"),
            ]
        ]
    )
    db.commit()


def test_json_coefficients_round_trip_and_generalize_to_unseen_person():
    models, report = train_models(synthetic_rows())
    restored = json.loads(json.dumps(models))
    row = observed_row(
        merchant="Novel Other Person", amount=Decimal("50"), currency_code="NOK", account_id=1
    )
    before = Classifier(models["type"]).probabilities([row])
    after = Classifier(restored["type"]).probabilities([row])
    np.testing.assert_allclose(before, after)
    assert restored["type"]["classes"][int(after.argmax())] == "reimbursement"
    large = {**row, "amount": "25000"}
    large_scores = Classifier(restored["type"]).probabilities([large])
    assert restored["type"]["classes"][int(large_scores.argmax())] == "income"
    assert (
        report["chronological"]["type"]["accuracy"]
        > report["chronological"]["type"]["baseline_accuracy"]
    )
    assert report["unseen_counterparty"] is not None


def test_direct_description_expert_is_independent_of_type_and_category_labels():
    models, _ = train_models(synthetic_rows())
    row = observed_row(
        merchant="Novel Other Person", amount=Decimal("50"), currency_code="NOK", account_id=1
    )
    good = Classifier(models["description"]).probabilities([row])
    # These irrelevant inputs are not observed features of a bank screenshot.
    corrupted = {
        **row,
        "transaction_type": "income",
        "category_id": 2,
        "description": "Monthly salary",
    }
    np.testing.assert_allclose(good, Classifier(models["description"]).probabilities([corrupted]))
    assert models["description"]["classes"][int(good.argmax())] == "shared ride"


def ambiguous_description_models():
    """Same observed input, different reviewed category/description relationships."""
    rows = [
        {
            **synthetic_rows()[0],
            "category_id": index % 2 + 1,
            "description": "Shared ride" if index % 2 == 0 else "Club fee",
        }
        for index in range(60)
    ]
    direct = fit_classifier(rows, "description", 4)
    conditional = fit_classifier(rows, "description", 4, condition_category=True)
    conditional["category_support"] = {"1": 30, "2": 30}
    return {"description": direct, "description_category": conditional, "description_blend": 0.5}


def test_description_category_context_improves_ranking_but_has_bounded_influence():
    models = ambiguous_description_models()
    restored = json.loads(json.dumps(models))
    row = observed_row(
        merchant="Person Name A", amount=Decimal("50"), currency_code="NOK", account_id=1
    )
    base = Classifier(models["description"]).probabilities([row])
    scores, labels, weights = description_probabilities(
        restored, [row], category_scores=(np.array([[1.0, 0.0]]), ["1", "2"])
    )
    target = labels.index("shared ride")
    assert scores[0, target] > base[0, target] + 0.15
    assert labels[scores.argmax()] == "shared ride"
    assert weights[0] == 0.5
    np.testing.assert_allclose(scores.sum(axis=1), 1)
    # Even a confidently wrong category cannot replace the entire direct expert.
    wrong, _, _ = description_probabilities(
        models, [row], category_scores=(np.array([[0.0, 1.0]]), ["1", "2"])
    )
    assert np.max(np.abs(wrong - base)) <= 0.5


def test_description_context_falls_back_for_uncertainty_missing_support_and_inactive_categories():
    models = ambiguous_description_models()
    row = observed_row(
        merchant="Person Name A", amount=Decimal("50"), currency_code="NOK", account_id=1
    )
    base = Classifier(models["description"]).probabilities([row])
    for probabilities in (np.array([[0.5, 0.5]]), np.array([[0.5, 0.0]]), np.zeros((1, 2))):
        scores, _, weights = description_probabilities(
            models, [row], category_scores=(probabilities, ["1", "2"])
        )
        np.testing.assert_allclose(scores, base)
        np.testing.assert_allclose(weights, 0)
    models["description_category"]["category_support"] = {"1": 2, "2": 0}
    scores, _, weights = description_probabilities(
        models, [row], category_scores=(np.array([[1.0, 0.0]]), ["1", "2"])
    )
    np.testing.assert_allclose(scores, base)
    np.testing.assert_allclose(weights, 0)


def test_validation_predictions_do_not_read_the_true_held_out_category_or_type():
    # This fixture has enough validation rows to exercise context selection.
    rows = synthetic_rows() + [
        {
            **row,
            "transaction_id": row["transaction_id"] + 60,
            "confirmed_at": "2026-02-" + row["confirmed_at"][-2:],
            "group": row["group"] + ":later",
        }
        for row in synthetic_rows()
    ]
    models, report = train_models(rows)
    _, validation, _ = chronology_split(rows)
    scores, labels, _ = description_probabilities(models, validation)
    corrupted = [
        {
            **row,
            "category_id": 999,
            "transaction_type": "savings",
            "description": "Incorrect target",
        }
        for row in validation
    ]
    other, other_labels, _ = description_probabilities(models, corrupted)
    assert labels == other_labels
    np.testing.assert_allclose(scores, other)
    assert models["description_blend"] in (0.0, 0.25, 0.5)
    selection = report["description_context_selection"]
    assert selection["validation_blend_log_loss"] <= selection["validation_base_log_loss"]
    assert models["category"]["threshold"] == models["description"]["threshold"] == 0.75


def test_predictions_reuse_a_stale_snapshot_until_explicit_retraining(monkeypatch):
    monkeypatch.setattr("app.services.transactions.try_synchronize", lambda db: None)
    db, learning = sessions()
    with db, learning:
        seed(db)
        tx = create_transaction(
            db,
            TransactionCreate(
                transaction_date=date(2026, 1, 1),
                account_id=1,
                amount=Decimal("50"),
                currency_code="NOK",
                merchant="Synthetic Person",
                transaction_type="reimbursement",
                category_id=1,
            ),
        )
        before = current_models(db, learning)
        update_transaction(
            db,
            tx.id,
            TransactionCreate(
                transaction_date=tx.transaction_date,
                account_id=1,
                amount=Decimal("50"),
                currency_code="NOK",
                merchant=tx.merchant,
                transaction_type="income",
                category_id=2,
            ),
        )
        reused = current_models(db, learning)
        assert reused.id == before.id
        assert reused.parameters["category"]["classes"] == ["1"]
        refreshed = current_models(db, learning, retrain=True)
        assert refreshed.id != before.id
        assert refreshed.parameters["category"]["classes"] == ["2"]
        assert len(list(learning.scalars(select(ModelSnapshot)))) == 2


def test_failed_retraining_keeps_the_previous_snapshot_active(monkeypatch):
    db, learning = sessions()
    with db, learning:
        seed(db)
        before = current_models(db, learning)
        monkeypatch.setattr(
            "app.services.predictions.train_models",
            lambda *args: (_ for _ in ()).throw(RuntimeError("Synthetic failure")),
        )
        with pytest.raises(RuntimeError, match="Synthetic failure"):
            current_models(db, learning, retrain=True)
        assert learning.get(PredictionState, 1).active_snapshot_id == before.id
        assert current_models(db, learning).id == before.id


def test_context_is_not_enabled_without_enough_validation_evidence():
    models, report = train_models(synthetic_rows())
    assert report["validation_samples"] < 20
    assert models["description_blend"] == 0
    assert report["description_context"] == "independent"


def test_merchant_amount_features_are_smooth_and_currency_scoped():
    row = observed_row(merchant="Synthetic Person", amount=Decimal("49.99"), currency_code="NOK")
    nearby = {**row, "amount": "50.01"}
    features, other = metadata_features(row), metadata_features(nearby)
    assert (
        max(abs(features[key] - other[key]) for key in features if key.startswith("amount:"))
        < 0.001
    )
    foreign = metadata_features({**row, "currency_code": "EUR"})
    assert not set(key for key in features if key.startswith("amount:")) & set(
        key for key in foreign if key.startswith("amount:")
    )


def test_partition_keeps_imports_together_and_moves_corrections_later():
    rows = synthetic_rows()
    rows[0]["confirmed_at"] = "2026-12-31"
    training, validation, testing = chronology_split(rows)
    groups = [{row["group"] for row in part} for part in (training, validation, testing)]
    assert not groups[0] & groups[1] and not groups[1] & groups[2] and not groups[0] & groups[2]
    assert "import:0" in groups[2]


def test_rebuild_uses_current_ledger_and_full_review_weight(monkeypatch):
    monkeypatch.setattr("app.services.transactions.try_synchronize", lambda db: None)
    with sessions()[0] as db, sessions()[1] as learning:
        seed(db)
        tx = create_transaction(
            db,
            TransactionCreate(
                transaction_date=date(2026, 1, 1),
                account_id=1,
                amount=Decimal("50"),
                currency_code="NOK",
                merchant="Synthetic Person",
                transaction_type="reimbursement",
                category_id=1,
                description="Shared ride",
            ),
        )
        assert rebuild_projection(db, learning) == 1
        assert rebuild_projection(db, learning) == 1
        example = learning.get(TrainingExample, tx.id)
        assert example.payload["weight"] == 1
        assert example.payload["direction_origin"] == "reviewed_type"
        assert len(list(learning.scalars(select(TrainingExample)))) == 1
        payload = TransactionCreate(
            transaction_date=tx.transaction_date,
            account_id=1,
            amount=Decimal("25000"),
            currency_code="NOK",
            merchant=tx.merchant,
            transaction_type="income",
            category_id=2,
            description="Monthly salary",
        )
        update_transaction(db, tx.id, payload)
        synchronize(db, learning)
        assert example.payload["category_id"] == 2
        assert example.payload["description"] == "Monthly salary"
        assert len(list(learning.scalars(select(TrainingExample)))) == 1
        snapshot = current_models(db, learning)
        assert snapshot.parameters["category"]["counts"] == {"2": 1}
        remove_transaction(db, tx.id)
        synchronize(db, learning)
        assert not example.active
        assert current_models(db, learning, retrain=True).parameters["category"]["classes"] == []


def test_replay_after_failed_acknowledgement_cannot_resurrect_deleted_example():
    db, learning = sessions()
    with db, learning:
        seed(db)
        tx = Transaction(
            transaction_date=date(2026, 1, 1),
            account_id=1,
            amount=Decimal("50"),
            source_signed_amount=Decimal("50"),
            currency_code="NOK",
            merchant="Synthetic Person",
            transaction_type="reimbursement",
            category_id=1,
            description="Shared ride",
        )
        db.add(tx)
        queue_transaction(db, tx)
        db.commit()
        rebuild_projection(db, learning)
        queue_transaction(db, tx, operation="delete")
        db.delete(tx)
        db.commit()
        synchronize(db, learning)
        # Simulate losing acknowledgements across a process crash.
        for event in db.scalars(select(LearningOutbox)):
            event.delivered = False
        db.commit()
        synchronize(db, learning)
        assert not learning.get(TrainingExample, tx.id).active
        assert all(event.delivered for event in db.scalars(select(LearningOutbox)))


def test_failure_to_synchronize_does_not_undo_saved_finances(monkeypatch):
    from app.services import learning_sync

    db, _ = sessions()
    with db:
        seed(db)
        monkeypatch.setattr(
            learning_sync,
            "synchronize",
            lambda *args: (_ for _ in ()).throw(RuntimeError("Unavailable")),
        )
        tx = create_transaction(
            db,
            TransactionCreate(
                transaction_date=date(2026, 1, 1),
                account_id=1,
                amount=Decimal("50"),
                currency_code="NOK",
                merchant="Synthetic Person",
                transaction_type="reimbursement",
                category_id=1,
            ),
        )
        assert db.get(Transaction, tx.id) is not None
        assert db.scalar(select(LearningOutbox)).delivered is False


def test_cold_start_abstains_and_unknown_currency_has_no_candidates():
    db, learning = sessions()
    with db, learning:
        seed(db)
        tx = Transaction(
            transaction_date=date(2026, 1, 1),
            account_id=1,
            amount=Decimal("50"),
            currency_code="NOK",
            merchant="Synthetic Person",
            transaction_type="reimbursement",
            category_id=1,
        )
        db.add(tx)
        db.commit()
        snapshot = current_models(db, learning)
        row = observed_row(merchant=tx.merchant, amount=Decimal("50"), currency_code="NOK")
        result = predict_with_snapshot(db, snapshot, row)
        assert all(output["suggestion"] is None for output in result["outputs"].values())
        foreign = predict_with_snapshot(db, snapshot, {**row, "currency_code": "EUR"})
        assert all(output["candidates"] == [] for output in foreign["outputs"].values())


def test_prediction_schema_migration_matches_models(tmp_path, monkeypatch):
    from app.config import get_settings

    database_url = f"sqlite:///{(tmp_path / 'projection.db').as_posix()}"
    settings = get_settings().model_copy(update={"prediction_database_url": database_url})
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    config = Config("alembic_predictions.ini")
    command.upgrade(config, "head")
    command.check(config)
    command.downgrade(config, "base")
    command.upgrade(config, "head")


def test_rebuild_accepts_older_restored_ledger_revisions():
    db, learning = sessions()
    with db, learning:
        seed(db)
        tx = Transaction(
            transaction_date=date(2026, 1, 1),
            account_id=1,
            amount=Decimal("50"),
            currency_code="NOK",
            merchant="Synthetic Person",
            transaction_type="reimbursement",
            category_id=1,
        )
        db.add(tx)
        db.commit()
        learning.add(
            TrainingExample(
                transaction_id=tx.id, revision=10000, active=True, payload={"category_id": 2}
            )
        )
        learning.add(TrainingExample(transaction_id=999, revision=10000, active=True, payload={}))
        learning.commit()
        rebuild_projection(db, learning)
        assert learning.get(TrainingExample, tx.id).payload["category_id"] == 1
        assert not learning.get(TrainingExample, 999).active


def test_sqlite_backup_releases_handles_and_preserves_values(tmp_path):
    import sqlite3
    from contextlib import closing
    from app.rebuild_learning import backup_sqlite, financial_fingerprint

    source, backup = tmp_path / "source.db", tmp_path / "backup.db"
    with closing(sqlite3.connect(source)) as db:
        db.execute("CREATE TABLE examples (id INTEGER PRIMARY KEY, amount TEXT)")
        db.execute("INSERT INTO examples VALUES (1, '50.00')")
        db.commit()
    original, columns = financial_fingerprint(source)
    backup_sqlite(source, backup)
    assert financial_fingerprint(backup, columns)[0] == original
    # Windows refuses this when backup_sqlite leaves a connection open.
    source.unlink()
    assert financial_fingerprint(backup, columns)[0] == original


def test_reviewed_empty_description_is_learned_as_a_valid_outcome():
    rows = synthetic_rows()
    for row in rows:
        if row["transaction_type"] == "reimbursement":
            row["description"] = ""
    models, _ = train_models(rows)
    row = observed_row(
        merchant="Novel Other Person", amount=Decimal("50"), currency_code="NOK", account_id=1
    )
    scores = Classifier(models["description"]).probabilities([row])
    assert models["description"]["classes"][int(scores.argmax())] == "__empty__"


def test_editing_type_preserves_observed_sign_and_signed_edit_changes_it(monkeypatch):
    monkeypatch.setattr("app.services.transactions.try_synchronize", lambda db: None)
    db, learning = sessions()
    with db, learning:
        seed(db)
        tx = Transaction(
            transaction_date=date(2026, 1, 1),
            account_id=1,
            amount=Decimal("50"),
            source_signed_amount=Decimal("50"),
            currency_code="NOK",
            merchant="Synthetic Person",
            transaction_type="income",
            category_id=1,
        )
        db.add(tx)
        db.commit()
        payload = TransactionCreate(
            transaction_date=tx.transaction_date,
            account_id=1,
            amount=Decimal("50"),
            currency_code="NOK",
            merchant=tx.merchant,
            transaction_type="reimbursement",
            category_id=1,
        )
        update_transaction(db, tx.id, payload)
        assert tx.source_signed_amount == Decimal("50")
        assert (
            db.scalars(select(LearningOutbox).order_by(LearningOutbox.id.desc()))
            .first()
            .payload["direction_origin"]
            == "source"
        )
        update_transaction(
            db,
            tx.id,
            payload.model_copy(update={"transaction_type": "transfer", "amount": Decimal("-50")}),
        )
        assert tx.source_signed_amount == Decimal("-50")
        assert tx.amount == Decimal("-50")


def test_duplicate_warning_survives_type_abstention():
    from app.services.screenshot_imports import _possible_duplicate

    db, learning = sessions()
    with db, learning:
        seed(db)
        db.add(
            Transaction(
                transaction_date=date(2026, 1, 1),
                account_id=1,
                amount=Decimal("-50"),
                currency_code="NOK",
                merchant="Synthetic Move",
                transaction_type="transfer",
            )
        )
        db.commit()
        assert _possible_duplicate(
            db,
            account_id=1,
            transaction_date=date(2026, 1, 1),
            signed_amount=Decimal("-50"),
            merchant="Synthetic Move",
            transaction_type=None,
        )
