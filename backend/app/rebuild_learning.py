"""Explicit local rebuild/retirement command; never changes reviewed ledger fields."""

import argparse
from contextlib import closing
import hashlib
import json
import sqlite3
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.config import get_settings
from app.db import SessionLocal
from app.migration_runner import upgrade_database_to_head
from app.models import Transaction
from app.prediction_db import PredictionSessionLocal, ensure_prediction_schema
from app.services.learning_sync import pending_count, rebuild_projection
from app.services.predictions import current_models

LEGACY_NAMES = (
    "life_budget_learning.db",
    "life_budget_type_learning.db",
    "life_budget_description_learning.db",
)


def backup_sqlite(source: Path, destination: Path) -> None:
    """SQLite's backup API includes committed WAL data; refuse to overwrite."""
    if destination.exists():
        raise ValueError("Backup destination already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original:
        with closing(sqlite3.connect(destination)) as backup:
            original.backup(backup)
            if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Backup integrity check failed")


def financial_fingerprint(path: Path, columns: dict | None = None) -> tuple[str, dict]:
    """Hash every pre-existing domain field, excluding migration/outbox metadata.

    Column selection is captured before migration, so adding a nullable
    provenance field is permitted but rewriting any original value is not.
    """
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        if columns is None:
            names = [
                row[0]
                for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
                if not row[0].startswith("sqlite_")
                and row[0] not in {"alembic_version", "learning_outbox"}
            ]
            columns = {
                name: [row[1] for row in db.execute(f'PRAGMA table_info("{name}")')]
                for name in names
            }
        # Names come from trusted schema metadata, not user-supplied SQL.
        records = {
            name: sorted(
                db.execute(
                    "SELECT " + ",".join(f'"{column}"' for column in fields) + f' FROM "{name}"'
                ).fetchall(),
                key=repr,
            )
            for name, fields in columns.items()
        }
        digest = hashlib.sha256(
            json.dumps(records, sort_keys=True, default=str).encode()
        ).hexdigest()
        return digest, columns


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-dir", required=True, type=Path)
    parser.add_argument(
        "--retire-legacy",
        action="store_true",
        help="Archive and remove the three default legacy stores after validation",
    )
    args = parser.parse_args()
    url = make_url(get_settings().database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise ValueError("This backup/rebuild command requires a file SQLite ledger")
    ledger = Path(url.database).resolve()
    if not ledger.is_file():
        raise ValueError("Financial database must exist before rebuilding")
    archive = args.backup_dir.resolve()
    if archive == ledger.parent or archive.is_relative_to(ledger.parent):
        raise ValueError("Choose a backup directory outside the active data directory")
    before, columns = financial_fingerprint(ledger)
    backup_sqlite(ledger, archive / ledger.name)
    prediction_url = make_url(get_settings().prediction_database_url)
    if prediction_url.get_backend_name() == "sqlite" and prediction_url.database:
        prediction_path = Path(prediction_url.database).resolve()
        if prediction_path.is_file():
            backup_sqlite(prediction_path, archive / prediction_path.name)
    legacy = [(ledger.parent / name).resolve() for name in LEGACY_NAMES]
    for path in legacy:
        if path.is_file():
            backup_sqlite(path, archive / path.name)
    upgrade_database_to_head("alembic.ini")
    ensure_prediction_schema()
    with SessionLocal() as db, PredictionSessionLocal() as learning:
        count = rebuild_projection(db, learning)
        snapshot = current_models(db, learning, retrain=True)
        if count != len(list(db.scalars(select(Transaction.id)))) or pending_count(db):
            raise ValueError("Projection validation failed")
        after, _ = financial_fingerprint(ledger, columns)
        if after != before:
            raise ValueError("Original financial values changed; legacy stores retained")
        if args.retire_legacy:
            for path in legacy:
                # Only these explicitly named stores in the resolved data
                # directory may be removed, after their backups are verified.
                if path.parent != ledger.parent or path.name not in LEGACY_NAMES:
                    raise ValueError("Invalid legacy retirement path")
                path.unlink(missing_ok=True)
        print(
            json.dumps(
                {
                    "reviewed_transactions": count,
                    "snapshot_id": snapshot.id,
                    "original_fields_unchanged": True,
                    "backup_directory": str(archive),
                    "legacy_retired": args.retire_legacy,
                    "evaluation": {
                        kind: {
                            key: value
                            for key, value in metrics.items()
                            if key
                            in {
                                "samples",
                                "accuracy",
                                "macro_f1",
                                "log_loss",
                                "baseline_accuracy",
                                "coverage",
                                "suggestion_precision",
                            }
                        }
                        for kind, metrics in snapshot.report["chronological"].items()
                    },
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
