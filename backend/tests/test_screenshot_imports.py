from datetime import date
from decimal import Decimal

from PIL import Image, ImageDraw
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Account, Currency, ImportBatch, ImportDraftRow, Transaction
from app.schemas_imports import ApproveImportRequest, ApprovedImportRow
from app.services.screenshot_imports import approve_screenshot_import
from app.services.screenshot_parser import OCRLine, parse_signed_decimal, parse_transaction_lines
from app.services.type_learning import learn_transaction_type, predict_transaction_type
from app.type_learning_db import TypeLearningBase


def test_parser_rejoins_all_columns_in_a_long_bank_transaction_table() -> None:
    source_rows = [
        ("REMA 1000 MOHOLIT", "2026-07-15", "2026-07-15", "-276,63"),
        ("Swish skickad +46725775629", "2026-07-09", "2026-07-09", "-331,00"),
        ("AIRBNB * HMDJPRH", "2026-07-04", "2026-07-06", "-1 156,34"),
        ("Pris betalning", "2026-07-02", "2026-07-02", "-1,50"),
        ("Europabetalning", "2026-07-02", "2026-07-02", "-8 000,00"),
        ("Övf via internet 838167044342009", "2026-07-01", "2026-07-02", "8 000,00"),
        ("MICROSOFT*PC GAM", "2026-06-23", "2026-06-23", "-135,00"),
        ("Swish mottagen +46769126208", "2026-06-20", "2026-06-22", "62,00"),
        ("OKQ8", "2026-06-17", "2026-06-17", "-37,00"),
        ("Buckaroo *app", "2026-06-17", "2026-06-17", "-200,00"),
        ("TEMPO STRATJARA", "2026-06-16", "2026-06-16", "-57,66"),
        ("COOP SVEG", "2026-06-16", "2026-06-16", "-57,32"),
    ]
    # Simulate Tesseract assigning each visual column to a different OCR
    # block/line. Slight y jitter reflects the supplied screenshot behavior.
    lines: list[OCRLine] = []
    for index, (merchant, transaction_date, booking_date, amount) in enumerate(source_rows):
        top = 50 + index * 41
        lines.extend(
            [
                OCRLine(merchant, 0.91, 15, top, 330, 18),
                OCRLine(transaction_date, 0.96, 404, top + 1, 105, 18),
                OCRLine(booking_date, 0.95, 566, top - 1, 105, 18),
                OCRLine(amount, 0.94, 728, top + 1, 90, 18),
            ]
        )

    rows = parse_transaction_lines(lines, "SEK")

    assert len(rows) == 12
    assert [row.merchant for row in rows] == [source[0] for source in source_rows]
    assert rows[2].signed_amount == Decimal("-1156.34")
    assert rows[5].signed_amount == Decimal("8000.00")
    assert rows[6].signed_amount == Decimal("-135.00")
    assert rows[8].signed_amount == Decimal("-37.00")
    assert parse_signed_decimal("−2 500,75") == Decimal("-2500.75")


def test_parser_recovers_a_minus_sign_omitted_by_ocr() -> None:
    image = Image.new("L", (900, 120), 255)
    ImageDraw.Draw(image).line((700, 58, 720, 58), fill=0, width=3)
    lines = [
        OCRLine("OKQ8", 0.95, 15, 48, 100, 20),
        OCRLine("2026-06-17", 0.95, 404, 48, 110, 20),
        OCRLine("2026-06-17", 0.95, 566, 48, 110, 20),
        # The digit box begins at x=728; the visible minus is just to its left.
        OCRLine("37,00", 0.75, 728, 48, 60, 20),
    ]

    [row] = parse_transaction_lines(lines, "SEK", image)

    assert row.raw_amount_text == "-37,00"
    assert row.signed_amount == Decimal("-37.00")


def test_type_model_learns_sign_merchant_and_predicted_category() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    TypeLearningBase.metadata.create_all(engine)
    with Session(engine) as db:
        before = predict_transaction_type(
            db, amount=Decimal("500"), merchant="Internal move", category_id=8
        )
        assert before.transaction_type == "income"

        for _ in range(3):
            learn_transaction_type(
                db,
                amount=Decimal("500"),
                merchant="Internal move",
                category_id=8,
                transaction_type="transfer",
            )
        after = predict_transaction_type(
            db, amount=Decimal("500"), merchant="Internal move", category_id=8
        )
        assert after.transaction_type == "transfer"
        assert after.confidence > 0.9


def test_approval_preserves_raw_sign_but_stores_expense_magnitude(
    monkeypatch,
) -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    learned: list[Decimal] = []
    learned_descriptions: list[str | None] = []
    monkeypatch.setattr(
        "app.services.screenshot_imports.learn_from_transaction", lambda transaction: None
    )
    monkeypatch.setattr(
        "app.services.screenshot_imports.record_type_learning_event",
        lambda **values: learned.append(values["amount"]),
    )
    monkeypatch.setattr(
        "app.services.screenshot_imports.record_description_learning_event",
        lambda **values: learned_descriptions.append(values["description"]),
    )
    with Session(engine, expire_on_commit=False) as db:
        db.add(Currency(code="SEK", name="Swedish krona"))
        account = Account(name="Everyday", account_type="bank", currency_code="SEK")
        db.add(account)
        db.commit()
        batch = ImportBatch(
            original_filename="synthetic.png",
            stored_path="uploads/imports/synthetic.png",
            content_type="image/png",
            account_id=account.id,
            currency_code="SEK",
            status="review",
            progress=100,
        )
        draft = ImportDraftRow(
            row_index=0,
            raw_text="2026-07-18 ICA -245,50 SEK",
            raw_amount_text="-245,50",
            transaction_date=date(2026, 7, 18),
            merchant="ICA",
            signed_amount=Decimal("-245.50"),
            currency_code="SEK",
            account_id=account.id,
            predicted_transaction_type="expense",
            extraction_confidence=0.95,
            category_confidence=0,
            type_confidence=0.65,
            validation_errors=[],
        )
        batch.drafts.append(draft)
        db.add(batch)
        db.commit()

        result = approve_screenshot_import(
            db,
            batch.id,
            ApproveImportRequest(
                rows=[
                    ApprovedImportRow(
                        draft_id=draft.id,
                        transaction_date=date(2026, 7, 18),
                        merchant="ICA",
                        description="Groceries",
                        signed_amount=Decimal("-245.50"),
                        currency_code="SEK",
                        account_id=account.id,
                        transaction_type="expense",
                    )
                ]
            ),
        )

        transaction = db.scalar(select(Transaction))
        assert result.created_transaction_ids == [transaction.id]
        assert transaction.amount == Decimal("245.50")
        assert transaction.source == "screenshot"
        assert learned == [Decimal("-245.50")]
        assert learned_descriptions == ["Groceries"]
        assert draft.status == "accepted"
