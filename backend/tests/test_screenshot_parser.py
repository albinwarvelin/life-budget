"""Synthetic OCR evidence only; never store personal screenshots in fixtures."""

import subprocess
from datetime import date
from decimal import Decimal

import pytest
from PIL import Image

from app.services.screenshot_parser import (
    OCRLine,
    ScreenshotParserError,
    TesseractScreenshotParser,
    parse_transaction_lines,
)


def bank_row(date_text: str, *, top: int = 60, amount: str = "-123,45 kr") -> list[OCRLine]:
    """Simulate separate date, merchant, and amount columns in a bank view."""
    return [
        OCRLine(date_text, 0.96, 20, top, 60, 17),
        OCRLine("Example shop", 0.94, 100, top, 180, 17),
        OCRLine(amount, 0.95, 610, top, 110, 17),
    ]


@pytest.mark.parametrize(
    ("month", "alias"),
    [
        (1, "jan"),
        (1, "januar"),
        (1, "january"),
        (1, "januari"),
        (2, "feb"),
        (2, "februar"),
        (2, "february"),
        (2, "februari"),
        (3, "mar"),
        (3, "mars"),
        (3, "march"),
        (4, "apr"),
        (4, "april"),
        (5, "mai"),
        (5, "may"),
        (5, "maj"),
        (6, "jun"),
        (6, "juni"),
        (6, "june"),
        (7, "jul"),
        (7, "juli"),
        (7, "july"),
        (8, "aug"),
        (8, "august"),
        (8, "augusti"),
        (9, "sep"),
        (9, "sept"),
        (9, "september"),
        (10, "okt"),
        (10, "oct"),
        (10, "oktober"),
        (10, "october"),
        (11, "nov"),
        (11, "november"),
        (12, "des"),
        (12, "dec"),
        (12, "desember"),
        (12, "december"),
    ],
)
@pytest.mark.parametrize("separator", [". ", ".", " "])
@pytest.mark.parametrize("suffix", [".", ""])
def test_every_month_alias_accepts_ocr_spacing_and_punctuation(month, alias, separator, suffix):
    """A new month must not need another parser patch to recognize its dates."""
    lines = bank_row(f"5{separator}{alias.upper()}{suffix}")
    [row] = parse_transaction_lines(lines, "NOK", fallback_year=2026)
    assert row.transaction_date == date(2026, month, 5)
    assert row.merchant == "Example shop"
    assert row.signed_amount == Decimal("-123.45")


def test_september_heading_overrides_remembered_year():
    lines = [OCRLine("Sep. 2025", 0.98, 20, 10, 140, 17), *bank_row("5.sep.")]
    [row] = parse_transaction_lines(lines, "NOK", fallback_year=2026)
    assert row.transaction_date == date(2025, 9, 5)


@pytest.mark.parametrize("date_text", ["5.sep.", "31.sep.", "1-560.", "2026-02-30"])
def test_unresolved_dates_remain_drafts(date_text):
    """An unknown year or malformed date needs review, not silent omission."""
    [row] = parse_transaction_lines(bank_row(date_text), "NOK")
    assert row.transaction_date is None
    assert row.signed_amount == Decimal("-123.45")
    assert date_text in row.raw_text


def test_missing_amount_remains_a_draft():
    [row] = parse_transaction_lines(
        bank_row("5.sep.", amount="unreadable"), "NOK", fallback_year=2026
    )
    assert row.transaction_date == date(2026, 9, 5)
    assert row.signed_amount is None
    assert "unreadable" in row.raw_text


@pytest.mark.parametrize("amount_top", [40, 80])
def test_wrapped_amount_enriches_one_draft_without_adding_another(amount_top):
    lines = bank_row("5.sep.")[:2]
    lines.append(OCRLine("-123,45 kr", 0.95, 610, amount_top, 110, 17))
    [row] = parse_transaction_lines(lines, "NOK", fallback_year=2026)
    assert row.merchant == "Example shop"
    assert row.signed_amount == Decimal("-123.45")


def test_two_line_currency_badge_has_amount_above_date_and_annotation_below():
    lines = bank_row("1.sep.")[:2]
    lines.extend(
        [
            OCRLine("1 234,56 kr", 0.95, 610, 40, 110, 17),
            OCRLine("111,11 EUR", 0.95, 610, 80, 110, 17),
        ]
    )
    [row] = parse_transaction_lines(lines, "NOK", fallback_year=2026)
    assert row.signed_amount == Decimal("1234.56")
    assert row.transaction_date == date(2026, 9, 1)


def test_equal_transactions_at_different_positions_are_not_discarded():
    rows = parse_transaction_lines(
        [*bank_row("5.sep."), *bank_row("5.sep.", top=110)], "NOK", fallback_year=2026
    )
    assert len(rows) == 2
    assert rows[0].transaction_date == rows[1].transaction_date
    assert rows[0].signed_amount == rows[1].signed_amount
    assert rows[0].merchant == rows[1].merchant
    assert rows[0].bounds != rows[1].bounds


@pytest.mark.parametrize("currency", ["EUR", "USD", "GBP", "SEK"])
def test_foreign_annotations_do_not_replace_the_booked_amount(currency):
    # OCR can place both amounts on one visual line. Keep the foreign value as
    # source evidence while selecting the explicitly booked kr amount.
    [row] = parse_transaction_lines(
        bank_row("5.sep.", amount=f"1 234,56 kr 111,11 {currency}"),
        "NOK",
        fallback_year=2026,
    )
    assert row.signed_amount == Decimal("1234.56")
    assert row.currency_code == "NOK"
    assert f"111,11 {currency}" in row.raw_text


def test_foreign_amount_alone_is_not_relabelled_as_account_currency():
    [row] = parse_transaction_lines(
        bank_row("5.sep.", amount="111,11 EUR"), "NOK", fallback_year=2026
    )
    assert row.signed_amount is None
    assert row.currency_code == "NOK"
    assert "111,11 EUR" in row.raw_text


def test_wrapped_foreign_annotation_is_not_another_transaction():
    lines = [*bank_row("5.sep."), OCRLine("11,11 EUR", 0.95, 610, 80, 110, 17)]
    [row] = parse_transaction_lines(lines, "NOK", fallback_year=2026)
    assert row.signed_amount == Decimal("-123.45")


def test_tesseract_failure_has_its_own_error(tmp_path, monkeypatch):
    source = tmp_path / "synthetic.png"
    Image.new("RGB", (200, 100), "white").save(source)
    monkeypatch.setattr(
        "app.services.screenshot_parser._run_with_language_fallback",
        lambda *args: subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="failure"
        ),
    )
    with pytest.raises(ScreenshotParserError, match="Local OCR could not run"):
        TesseractScreenshotParser().parse(source, "NOK")
