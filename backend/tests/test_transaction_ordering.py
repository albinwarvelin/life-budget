"""Verify source ordering using synthetic payments and disposable databases."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, Table, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.database_engine import create_database_engine
from app.db import Base
from app.models import Account, Currency, ImportBatch, ImportDraftRow, Transaction
from app.repositories.transactions import list_transactions
from app.schemas_imports import ApproveImportRequest, ApprovedImportRow
from app.services.screenshot_imports import approve_screenshot_import


def test_approval_preserves_source_order_independent_of_payload_order(monkeypatch):
    engine = create_database_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    # This test covers persistence and display, without teaching any model.
    monkeypatch.setattr("app.services.screenshot_imports.try_synchronize", lambda db: None)
    with Session(engine) as db:
        db.add(Currency(code="NOK", name="Norwegian krone"))
        account = Account(name="Synthetic bank", account_type="bank", currency_code="NOK")
        db.add(account)
        db.flush()

        def manual(merchant):
            row = Transaction(
                transaction_date=date(2026, 9, 5),
                account_id=account.id,
                amount=Decimal("10"),
                currency_code="NOK",
                transaction_type="income",
                merchant=merchant,
                source="manual",
            )
            db.add(row)
            db.flush()
            return row

        manual("Earlier manual")
        batches = []
        for batch_index in range(2):
            batch = ImportBatch(
                original_filename="synthetic.png",
                stored_path="uploads/imports/synthetic.png",
                content_type="image/png",
                account_id=account.id,
                currency_code="NOK",
                status="review",
                progress=100,
            )
            for index, day in enumerate((5, 5, 5, 4)):
                batch.drafts.append(
                    ImportDraftRow(
                        row_index=index,
                        raw_text="synthetic evidence",
                        raw_amount_text="10,00",
                        transaction_date=date(2026, 9, day),
                        merchant=f"Batch {batch_index} row {index}",
                        signed_amount=Decimal("10"),
                        currency_code="NOK",
                        account_id=account.id,
                        extraction_confidence=1,
                        validation_errors=[],
                    )
                )
            db.add(batch)
            db.commit()
            # Deliberately scramble the client payload. Source row 1 is rejected
            # to verify that gaps do not reorder the remaining accepted rows.
            request = ApproveImportRequest(
                rows=[
                    ApprovedImportRow(
                        draft_id=batch.drafts[index].id,
                        accepted=index != 1,
                        transaction_date=batch.drafts[index].transaction_date,
                        merchant=batch.drafts[index].merchant,
                        signed_amount=Decimal("10"),
                        currency_code="NOK",
                        account_id=account.id,
                        transaction_type="income",
                    )
                    for index in (3, 2, 0, 1)
                ]
            )
            result = approve_screenshot_import(db, batch.id, request)
            assert len(result.created_transaction_ids) == 3
            batches.append(batch)
        newest_manual = manual("Later manual")
        db.commit()
        expected = [
            "Later manual",
            "Batch 1 row 0",
            "Batch 1 row 2",
            "Batch 0 row 0",
            "Batch 0 row 2",
            "Earlier manual",
            "Batch 1 row 3",
            "Batch 0 row 3",
        ]
        assert [row.merchant for row in list_transactions(db)] == expected
        assert [
            row.merchant for row in list_transactions(db, from_date=date(2026, 9, 5))
        ] == expected[:6]
        assert list_transactions(db, currency_code="SEK") == []
        # Editing user fields cannot disturb the immutable source-row link.
        newest_manual.notes = "Edited"
        db.commit()
        assert [row.merchant for row in list_transactions(db)] == expected

        linked = db.scalar(select(Transaction).where(Transaction.merchant == "Batch 1 row 0"))
        # Removing extraction evidence must leave its financial record intact.
        db.delete(batches[1].drafts[0])
        db.commit()
        db.refresh(linked)
        assert linked.import_draft_id is None
        assert linked.amount == Decimal("10")
    engine.dispose()


def test_provenance_migration_preserves_existing_transactions(tmp_path, monkeypatch):
    """Upgrade and downgrade real SQLite schema versions without guessing old links."""
    backend = Path(__file__).resolve().parents[1]
    database_url = f"sqlite:///{(tmp_path / 'migration.db').as_posix()}"
    settings = get_settings().model_copy(update={"database_url": database_url})
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    previous = "0007_import_description_predictions"
    command.upgrade(config, previous)
    engine = create_database_engine(database_url)
    metadata = MetaData()
    # Reflect the previous schema because today's ORM already knows the new field.
    accounts = Table("accounts", metadata, autoload_with=engine)
    transactions = Table("transactions", metadata, autoload_with=engine)
    with engine.begin() as connection:
        # The initial migration already seeds NOK and SEK.
        connection.execute(
            accounts.insert().values(
                id=1,
                name="Synthetic bank",
                account_type="bank",
                currency_code="NOK",
                is_active=True,
            )
        )
        connection.execute(
            transactions.insert().values(
                id=1,
                transaction_date=date(2026, 9, 5),
                account_id=1,
                amount=Decimal("50"),
                currency_code="NOK",
                transaction_type="income",
                merchant="Synthetic person",
                source="screenshot",
            )
        )
    command.upgrade(config, "head")
    command.check(config)
    with Session(engine) as db:
        [row] = list_transactions(db)
        assert row.merchant == "Synthetic person"
        assert row.amount == Decimal("50")
        assert row.import_draft_id is None
    command.downgrade(config, previous)
    after = Table("transactions", MetaData(), autoload_with=engine)
    assert "import_draft_id" not in after.c
    with engine.connect() as connection:
        assert connection.scalar(select(after.c.amount)) == Decimal("50")
    engine.dispose()
