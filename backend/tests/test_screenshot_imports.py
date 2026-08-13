from datetime import date
from decimal import Decimal

from PIL import Image, ImageDraw
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Account, Currency, ImportBatch, ImportDraftRow, Transaction
from app.schemas_imports import ApproveImportRequest, ApprovedImportRow
from app.services.screenshot_imports import (
    _recent_account_import_year,
    approve_screenshot_import,
)
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


def test_parser_uses_norwegian_month_header_for_compact_yearless_rows() -> None:
    lines = [OCRLine("Juli 2026", 0.98, 8, 15, 90, 18)]
    source_rows = [
        ("18. juli", "Reservert: Rema Moholt T", "-189,93 kr"),
        ("17. juli", "Travel Retail Norway AS", "18 580,62 kr"),
        ("16. juli", "Lyse Tele AS Ice", "-95,00 kr"),
        ("11. juli", "Easypark", "-122,11 kr"),
    ]
    for index, (transaction_date, merchant, amount) in enumerate(source_rows):
        top = 60 + index * 52
        lines.extend(
            [
                OCRLine(transaction_date, 0.96, 9, top, 50, 17),
                OCRLine(merchant, 0.94, 98, top, 260, 17),
                OCRLine(amount, 0.95, 610, top, 80, 17),
            ]
        )
        if merchant == "Lyse Tele AS Ice":
            lines.append(OCRLine("Efaktura", 0.91, 98, top + 19, 70, 14))
        if merchant == "Easypark":
            # This exchange-value annotation must not become another row.
            lines.append(OCRLine("-118,06 SEK", 0.90, 615, top + 19, 78, 14))

    rows = parse_transaction_lines(lines, "NOK")

    assert len(rows) == 4
    assert [row.transaction_date for row in rows] == [
        date(2026, 7, 18),
        date(2026, 7, 17),
        date(2026, 7, 16),
        date(2026, 7, 11),
    ]
    assert [row.merchant for row in rows] == [
        "Rema Moholt T",
        "Travel Retail Norway AS",
        "Lyse Tele AS Ice",
        "Easypark",
    ]
    assert [row.signed_amount for row in rows] == [
        Decimal("-189.93"),
        Decimal("18580.62"),
        Decimal("-95.00"),
        Decimal("-122.11"),
    ]
    assert all(row.currency_code == "NOK" for row in rows)


def test_parser_reads_abbreviated_august_dates_in_compact_bank_view() -> None:
    """Rows marked ``aug.`` must inherit the explicit year in the screenshot."""
    lines = [OCRLine("August 2026", 0.98, 8, 15, 100, 18)]
    source_rows = [
        ("8. aug.", "Reservert: Ta Walkthrough", "-383,63 kr"),
        ("7. aug.", "Reservert: Delhaize", "-81,41 kr"),
        ("6. aug.", "Decathlon 0288", "-1 146,46 kr"),
        ("1. aug.", "M Serena Boutique", "-61,90 kr"),
    ]
    for index, (transaction_date, merchant, amount) in enumerate(source_rows):
        top = 60 + index * 52
        lines.extend(
            [
                OCRLine(transaction_date, 0.96, 9, top, 55, 17),
                OCRLine(merchant, 0.94, 83, top, 280, 17),
                OCRLine(amount, 0.95, 660, top, 82, 17),
            ]
        )

    rows = parse_transaction_lines(lines, "NOK")

    assert [row.transaction_date for row in rows] == [
        date(2026, 8, 8),
        date(2026, 8, 7),
        date(2026, 8, 6),
        date(2026, 8, 1),
    ]
    assert [row.signed_amount for row in rows] == [
        Decimal("-383.63"),
        Decimal("-81.41"),
        Decimal("-1146.46"),
        Decimal("-61.90"),
    ]
    assert [row.merchant for row in rows] == [
        "Ta Walkthrough",
        "Delhaize",
        "Decathlon 0288",
        "M Serena Boutique",
    ]


def test_rejected_draft_does_not_require_readable_transaction_fields() -> None:
    """Users must be able to reject the exact rows OCR could not complete."""
    payload = ApproveImportRequest.model_validate(
        {
            "rows": [
                {
                    "draft_id": 42,
                    "accepted": False,
                    "transaction_date": "",
                    "merchant": "",
                    "signed_amount": "",
                    "currency_code": "NOK",
                    "account_id": 2,
                    "transaction_type": "expense",
                    "category_id": None,
                }
            ]
        }
    )

    [rejected] = payload.rows
    assert rejected.accepted is False
    assert rejected.transaction_date is None
    assert rejected.merchant is None
    assert rejected.signed_amount is None


def test_parser_reads_abbreviated_april_dates_in_compact_bank_view() -> None:
    """The Norwegian ``apr.`` abbreviation must inherit April from its heading."""
    lines = [OCRLine("April 2026", 0.98, 10, 15, 95, 18)]
    source_rows = [
        ("29. apr.", "Nok 957,00 Zalando Payments G", "-957,00 kr"),
        ("28. apr.", "REMA", "-219,32 kr"),
        ("25. apr.", "Vegard Gulbrandsen", "530,00 kr"),
        ("23. apr.", "Mats Eidsmo", "50,00 kr"),
    ]
    for index, (transaction_date, merchant, amount) in enumerate(source_rows):
        top = 60 + index * 51
        lines.extend(
            [
                OCRLine(transaction_date, 0.96, 24, top, 60, 17),
                OCRLine(merchant, 0.94, 116, top, 300, 17),
                OCRLine(amount, 0.95, 665, top, 78, 17),
            ]
        )

    rows = parse_transaction_lines(lines, "NOK")

    assert [row.transaction_date for row in rows] == [
        date(2026, 4, 29),
        date(2026, 4, 28),
        date(2026, 4, 25),
        date(2026, 4, 23),
    ]
    assert [row.signed_amount for row in rows] == [
        Decimal("-957.00"),
        Decimal("-219.32"),
        Decimal("530.00"),
        Decimal("50.00"),
    ]
    assert rows[0].merchant == "Zalando Payments G"
    assert "Nok 957,00 Zalando Payments G" in rows[0].raw_text
    assert all(row.currency_code == "NOK" for row in rows)


def test_parser_does_not_guess_year_for_named_dates_without_a_header() -> None:
    lines = [
        OCRLine("18. juli", 0.96, 9, 60, 50, 17),
        OCRLine("Rema Moholt", 0.94, 98, 60, 150, 17),
        OCRLine("-189,93 kr", 0.95, 610, 60, 80, 17),
    ]

    assert parse_transaction_lines(lines, "NOK") == []


def test_parser_uses_remembered_year_when_month_header_is_cropped() -> None:
    lines = [
        OCRLine("18. juli", 0.96, 9, 60, 50, 17),
        OCRLine("Rema Moholt", 0.94, 98, 60, 150, 17),
        OCRLine("-189,93 kr", 0.95, 610, 60, 80, 17),
    ]

    [row] = parse_transaction_lines(lines, "NOK", fallback_year=2026)

    assert row.transaction_date == date(2026, 7, 18)
    assert row.currency_code == "NOK"


def test_parser_prefers_account_currency_amount_over_foreign_annotation() -> None:
    lines = [
        OCRLine("18. juli", 0.96, 9, 60, 50, 17),
        OCRLine("Airbnb", 0.94, 98, 60, 150, 17),
        OCRLine("-980,00 kr", 0.95, 540, 60, 75, 17),
        OCRLine("-941,00 SEK", 0.93, 620, 60, 82, 17),
    ]

    [row] = parse_transaction_lines(lines, "NOK", fallback_year=2026)

    assert row.signed_amount == Decimal("-980.00")
    assert row.raw_amount_text == "-980,00"
    assert row.currency_code == "NOK"
    assert "-941,00 SEK" in row.raw_text


def test_recent_import_year_is_remembered_per_account() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        db.add(Currency(code="NOK", name="Norwegian krone"))
        account = Account(name="Everyday NOK", account_type="bank", currency_code="NOK")
        db.add(account)
        db.flush()
        previous = ImportBatch(
            original_filename="previous.png",
            stored_path="uploads/imports/previous.png",
            content_type="image/png",
            account_id=account.id,
            currency_code="NOK",
            status="completed",
            progress=100,
        )
        previous.drafts.append(
            ImportDraftRow(
                row_index=0,
                raw_text="18. juli Rema -189,93 kr",
                transaction_date=date(2026, 7, 18),
                merchant="Rema",
                signed_amount=Decimal("-189.93"),
                currency_code="NOK",
                account_id=account.id,
                extraction_confidence=0.95,
                validation_errors=[],
            )
        )
        current = ImportBatch(
            original_filename="current.png",
            stored_path="uploads/imports/current.png",
            content_type="image/png",
            account_id=account.id,
            currency_code="NOK",
            status="processing",
            progress=10,
        )
        db.add_all([previous, current])
        db.commit()

        assert (
            _recent_account_import_year(
                db,
                account_id=account.id,
                exclude_batch_id=current.id,
            )
            == 2026
        )


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
