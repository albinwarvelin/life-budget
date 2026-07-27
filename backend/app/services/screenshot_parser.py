import csv
import io
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageStat

from app.config import get_settings

DATE_PATTERNS = (
    re.compile(
        r"\b(?P<year>20\d{2})[-/.](?P<month>0?[1-9]|1[0-2])[-/.](?P<day>0?[1-9]|[12]\d|3[01])\b"
    ),
    re.compile(
        r"\b(?P<day>0?[1-9]|[12]\d|3[01])[-/.](?P<month>0?[1-9]|1[0-2])[-/.](?P<year>20\d{2})\b"
    ),
)

# Compact Nordic bank views commonly put the year in a month heading and show
# only a localized day/month value on each transaction row. Keep this mapping
# explicit so importing a screenshot never depends on the computer's locale.
MONTH_NAMES = {
    "januar": 1,
    "january": 1,
    "januari": 1,
    "februar": 2,
    "february": 2,
    "februari": 2,
    "mars": 3,
    "march": 3,
    # Norwegian bank statements commonly abbreviate April as ``apr.``. Keep
    # the alias without punctuation because the date expression accepts both
    # the dotted and undotted OCR result.
    "apr": 4,
    "april": 4,
    "mai": 5,
    "may": 5,
    "maj": 5,
    "juni": 6,
    "june": 6,
    "juli": 7,
    "july": 7,
    "august": 8,
    "augusti": 8,
    "september": 9,
    "oktober": 10,
    "october": 10,
    "november": 11,
    "desember": 12,
    "december": 12,
}
_MONTH_ALTERNATION = "|".join(sorted(MONTH_NAMES, key=len, reverse=True))
MONTH_YEAR_PATTERN = re.compile(
    rf"\b(?P<month_name>{_MONTH_ALTERNATION})\s+(?P<year>20\d{{2}})\b",
    re.IGNORECASE,
)
NAMED_DATE_PATTERN = re.compile(
    rf"\b(?P<day>0?[1-9]|[12]\d|3[01])\.?\s+"
    # Put the word boundary before the optional period. A boundary after the
    # period would fail because both the period and following space are
    # non-word characters. Consuming it also keeps ``.`` out of the merchant.
    rf"(?P<month_name>{_MONTH_ALTERNATION})\b\.?",
    re.IGNORECASE,
)
# OCR engines use several dash glyphs for a bank-statement minus sign. A
# detached sign may also be separated from its number by whitespace.
AMOUNT_PATTERN = re.compile(
    r"(?P<amount>[+\-−–—~]?\s*(?:\d{1,3}(?:[ .]\d{3})+|\d+)[,.]\d{2})"
    r"(?:\s*(?P<currency>SEK|NOK|kr|:-))?",
    re.IGNORECASE,
)


class ScreenshotParserError(RuntimeError):
    """A safe parser failure suitable for displaying in import status."""


@dataclass(frozen=True)
class OCRLine:
    text: str
    confidence: float
    left: int
    top: int
    width: int
    height: int

    @property
    def center_y(self) -> float:
        return self.top + self.height / 2


@dataclass(frozen=True)
class ExtractedTransactionRow:
    raw_text: str
    raw_amount_text: str
    transaction_date: date | None
    merchant: str | None
    description: str | None
    signed_amount: Decimal | None
    currency_code: str
    confidence: float
    bounds: dict[str, int]


class TesseractScreenshotParser:
    """Local OCR adapter optimized for repeated bank-statement table rows."""

    def parse(
        self,
        image_path: Path,
        default_currency: str,
        fallback_year: int | None = None,
    ) -> list[ExtractedTransactionRow]:
        settings = get_settings()
        tesseract_command = resolve_tesseract_command(settings.tesseract_command)
        try:
            with tempfile.TemporaryDirectory(prefix="life-budget-ocr-") as temporary_directory:
                prepared_path = Path(temporary_directory) / "prepared.png"
                prepare_screenshot_for_ocr(image_path, prepared_path)
                candidates: list[list[ExtractedTransactionRow]] = []
                # PSM 6 keeps table columns on common visual rows. PSM 11 is a
                # useful fallback for screenshots whose UI spacing causes the
                # table to be segmented into independent sparse blocks.
                for page_segmentation_mode in (6, 11):
                    result = _run_with_language_fallback(
                        tesseract_command,
                        prepared_path,
                        settings.tesseract_languages,
                        page_segmentation_mode,
                    )
                    if result.returncode != 0:
                        continue
                    lines = parse_tesseract_tsv(result.stdout)
                    with Image.open(prepared_path) as prepared_image:
                        candidates.append(
                            parse_transaction_lines(
                                lines,
                                default_currency,
                                prepared_image.convert("L"),
                                fallback_year=fallback_year,
                            )
                        )
        except FileNotFoundError as error:
            raise ScreenshotParserError(
                "Tesseract OCR is not installed or TESSERACT_COMMAND is incorrect"
            ) from error
        except subprocess.TimeoutExpired as error:
            raise ScreenshotParserError("OCR took longer than 90 seconds") from error
        except (OSError, Image.UnidentifiedImageError) as error:
            raise ScreenshotParserError("The uploaded image could not be decoded") from error
        viable = [rows for rows in candidates if rows]
        if not viable:
            raise ScreenshotParserError(
                "No transaction rows with both a date and amount were found"
            )
        # Prefer completeness first, then OCR certainty. This directly avoids
        # choosing a high-confidence pass that happened to miss several rows.
        return max(
            viable,
            key=lambda rows: (
                len(rows),
                sum(row.confidence for row in rows) / max(len(rows), 1),
            ),
        )


def resolve_tesseract_command(configured_command: str) -> str:
    """Find the standard Windows installation when PATH was not refreshed."""
    if shutil.which(configured_command) or Path(configured_command).is_file():
        return configured_command
    if configured_command == "tesseract":
        windows_default = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        if windows_default.is_file():
            return str(windows_default)
    return configured_command


def prepare_screenshot_for_ocr(source: Path, destination: Path) -> None:
    """Normalize dark UI screenshots into a large, high-contrast OCR image."""
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image).convert("L")
        # Bank screenshots commonly use light text on dark gray. Tesseract is
        # more reliable on dark text over white, especially for thin minus signs.
        if ImageStat.Stat(image).mean[0] < 128:
            image = ImageOps.invert(image)
        image = ImageOps.autocontrast(image, cutoff=1)
        scale = max(2, min(3, round(2200 / max(image.width, 1))))
        image = image.resize((image.width * scale, image.height * scale), Image.Resampling.LANCZOS)
        image = ImageEnhance.Contrast(image).enhance(1.35)
        image = image.filter(ImageFilter.UnsharpMask(radius=1.2, percent=160, threshold=2))
        image.save(destination, format="PNG", dpi=(300, 300))


def _run_with_language_fallback(
    command: str, image_path: Path, languages: str, page_segmentation_mode: int
) -> subprocess.CompletedProcess[str]:
    result = _run_tesseract(command, image_path, languages, page_segmentation_mode)
    if result.returncode != 0 and languages != "eng" and "language" in result.stderr.lower():
        return _run_tesseract(command, image_path, "eng", page_segmentation_mode)
    return result


def _run_tesseract(
    command: str, image_path: Path, languages: str, page_segmentation_mode: int
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            command,
            str(image_path),
            "stdout",
            "-l",
            languages,
            "--psm",
            str(page_segmentation_mode),
            "-c",
            "preserve_interword_spaces=1",
            "tsv",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
        check=False,
    )


def parse_tesseract_tsv(content: str) -> list[OCRLine]:
    """Reassemble Tesseract words into block lines while retaining geometry."""
    groups: dict[tuple[str, str, str, str], list[dict[str, str]]] = {}
    for word in csv.DictReader(io.StringIO(content), delimiter="\t"):
        text = (word.get("text") or "").strip()
        if not text:
            continue
        key = tuple(
            word.get(part, "0") for part in ("page_num", "block_num", "par_num", "line_num")
        )
        groups.setdefault(key, []).append(word)
    lines: list[OCRLine] = []
    for words in groups.values():
        words.sort(key=lambda word: int(word.get("left") or 0))
        left = min(int(word.get("left") or 0) for word in words)
        top = min(int(word.get("top") or 0) for word in words)
        right = max(int(word.get("left") or 0) + int(word.get("width") or 0) for word in words)
        bottom = max(int(word.get("top") or 0) + int(word.get("height") or 0) for word in words)
        confidences = [max(0.0, float(word.get("conf") or 0)) for word in words]
        lines.append(
            OCRLine(
                text=" ".join(word["text"].strip() for word in words),
                confidence=sum(confidences) / max(len(confidences), 1) / 100,
                left=left,
                top=top,
                width=right - left,
                height=bottom - top,
            )
        )
    return sorted(lines, key=lambda line: (line.center_y, line.left))


def cluster_visual_rows(lines: list[OCRLine]) -> list[list[OCRLine]]:
    """Join OCR fragments by y-coordinate even when Tesseract split columns."""
    rows: list[list[OCRLine]] = []
    for line in sorted(lines, key=lambda item: (item.center_y, item.left)):
        best_row: list[OCRLine] | None = None
        best_distance = float("inf")
        for row in rows[-3:]:
            row_center = sum(item.center_y for item in row) / len(row)
            typical_height = max(1.0, sum(item.height for item in row) / len(row))
            distance = abs(line.center_y - row_center)
            tolerance = max(8.0, min(line.height, typical_height) * 0.72)
            if distance <= tolerance and distance < best_distance:
                best_row = row
                best_distance = distance
        if best_row is None:
            rows.append([line])
        else:
            best_row.append(line)
    for row in rows:
        row.sort(key=lambda item: item.left)
    return rows


def parse_transaction_lines(
    lines: list[OCRLine],
    default_currency: str,
    image: Image.Image | None = None,
    *,
    fallback_year: int | None = None,
) -> list[ExtractedTransactionRow]:
    """Extract transactions from full tables and compact localized month views."""
    rows: list[ExtractedTransactionRow] = []
    seen: set[tuple[date, Decimal, str]] = set()
    visual_rows = cluster_visual_rows(lines)
    month_headers = _month_year_headers(visual_rows)
    for fragments in _transaction_row_candidates(visual_rows):
        row_text = "   ".join(fragment.text for fragment in fragments)
        row_top = min(fragment.top for fragment in fragments)
        inferred_year = _preceding_header_year(month_headers, row_top) or fallback_year
        date_matches = _all_date_matches(row_text, inferred_year=inferred_year)
        amount_matches = list(AMOUNT_PATTERN.finditer(row_text))
        if not date_matches or not amount_matches:
            continue
        parsed_date, first_date_match = date_matches[0]
        amount_match = _account_currency_amount_match(amount_matches, default_currency)
        raw_amount = amount_match.group("amount").strip()
        amount_fragment = _fragment_containing_amount(
            fragments,
            raw_amount=raw_amount,
            currency_hint=amount_match.group("currency") or "",
        )
        signed_amount = parse_signed_decimal(raw_amount)
        if (
            signed_amount is not None
            and not _has_explicit_sign(raw_amount)
            and image is not None
            and amount_fragment is not None
            and _minus_stroke_before_amount(image, amount_fragment)
        ):
            signed_amount = -abs(signed_amount)
            raw_amount = f"-{raw_amount}"

        before_date = _clean_text(row_text[: first_date_match.start()])
        between_dates_and_amount = row_text[first_date_match.end() : amount_match.start()]
        for _, match in date_matches[1:]:
            between_dates_and_amount = between_dates_and_amount.replace(match.group(0), "", 1)
        between_text = _clean_text(between_dates_and_amount)
        if before_date:
            # Desktop statements put merchant before one or more date columns.
            merchant = _clean_merchant(before_date)[:160] or None
            description = between_text[:240] or None
        else:
            # Compact views put date first, making the text before amount the merchant.
            # Pass the uncleaned slice so merchant-specific cleanup can still
            # recognize a leading currency label before generic text cleanup
            # removes that label.
            merchant = _clean_merchant(between_dates_and_amount)[:160] or None
            description = None
        # The screenshot belongs to the selected account. Foreign-currency
        # annotations are useful raw OCR context but must never change the
        # transaction currency persisted for that account.
        currency = default_currency.upper()
        if signed_amount is None:
            continue
        identity = (parsed_date, signed_amount, merchant or "")
        if identity in seen:
            continue
        seen.add(identity)
        rows.append(
            ExtractedTransactionRow(
                raw_text=row_text,
                raw_amount_text=raw_amount,
                transaction_date=parsed_date,
                merchant=merchant,
                description=description,
                signed_amount=signed_amount,
                currency_code=currency,
                confidence=_weighted_confidence(fragments),
                bounds=_union_bounds(fragments),
            )
        )
    return rows


def _transaction_row_candidates(visual_rows: list[list[OCRLine]]) -> list[list[OCRLine]]:
    """Attach a wrapped amount/info line to the nearest preceding dated row."""
    candidates: list[list[OCRLine]] = []
    for index, fragments in enumerate(visual_rows):
        text = " ".join(fragment.text for fragment in fragments)
        if not AMOUNT_PATTERN.search(text):
            continue
        if _contains_date_text(text):
            candidates.append(fragments)
            continue
        # Some mobile layouts wrap the amount or extra information underneath
        # the date/merchant line. Only merge a close row that has a date and no
        # amount of its own, preventing adjacent complete transactions joining.
        if index > 0:
            previous = visual_rows[index - 1]
            previous_text = " ".join(fragment.text for fragment in previous)
            vertical_gap = min(fragment.top for fragment in fragments) - max(
                fragment.top + fragment.height for fragment in previous
            )
            typical_height = max(
                max(fragment.height for fragment in fragments),
                max(fragment.height for fragment in previous),
            )
            if (
                _contains_date_text(previous_text)
                and not AMOUNT_PATTERN.search(previous_text)
                and vertical_gap <= typical_height * 1.5
            ):
                candidates.append(sorted(previous + fragments, key=lambda item: item.left))
    return candidates


def _all_date_matches(
    value: str, *, inferred_year: int | None = None
) -> list[tuple[date, re.Match[str]]]:
    matches: list[tuple[date, re.Match[str]]] = []
    occupied: set[tuple[int, int]] = set()
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(value):
            if match.span() in occupied:
                continue
            try:
                parsed = date(
                    int(match.group("year")),
                    int(match.group("month")),
                    int(match.group("day")),
                )
            except ValueError:
                continue
            occupied.add(match.span())
            matches.append((parsed, match))
    # A named date is safe only when an explicit year was read from the image.
    # Never substitute the current year for persisted financial data.
    if inferred_year is not None:
        for match in NAMED_DATE_PATTERN.finditer(value):
            if match.span() in occupied:
                continue
            month = MONTH_NAMES[match.group("month_name").lower()]
            try:
                parsed = date(inferred_year, month, int(match.group("day")))
            except ValueError:
                continue
            occupied.add(match.span())
            matches.append((parsed, match))
    return sorted(matches, key=lambda item: item[1].start())


def _contains_date_text(value: str) -> bool:
    """Recognize both complete dates and localized dates that need a header year."""
    return bool(_all_date_matches(value) or NAMED_DATE_PATTERN.search(value))


def _month_year_headers(visual_rows: list[list[OCRLine]]) -> list[tuple[int, int]]:
    """Collect vertical positions and years from headings such as ``Juli 2026``."""
    headers: list[tuple[int, int]] = []
    for fragments in visual_rows:
        text = " ".join(fragment.text for fragment in fragments)
        match = MONTH_YEAR_PATTERN.search(text)
        if match:
            headers.append((min(fragment.top for fragment in fragments), int(match.group("year"))))
    return sorted(headers)


def _preceding_header_year(headers: list[tuple[int, int]], row_top: int) -> int | None:
    """Use the nearest explicit month heading above a compact transaction row."""
    return next((year for top, year in reversed(headers) if top < row_top), None)


def _account_currency_amount_match(
    matches: list[re.Match[str]], default_currency: str
) -> re.Match[str]:
    """Prefer the booked account-currency amount over conversion annotations."""
    account_currency = default_currency.upper()

    def priority(index_and_match: tuple[int, re.Match[str]]) -> tuple[int, int]:
        index, match = index_and_match
        currency = (match.group("currency") or "").upper()
        if currency == account_currency:
            return 3, index
        if currency in {"", "KR", ":-"}:
            return 2, index
        return 0, index

    return max(enumerate(matches), key=priority)[1]


def _fragment_containing_amount(
    fragments: list[OCRLine], *, raw_amount: str, currency_hint: str
) -> OCRLine | None:
    """Find the OCR fragment for the selected amount, not a foreign annotation."""
    normalized_currency = currency_hint.upper()
    candidates = []
    for fragment in fragments:
        for match in AMOUNT_PATTERN.finditer(fragment.text):
            if match.group("amount").strip() != raw_amount:
                continue
            if (match.group("currency") or "").upper() != normalized_currency:
                continue
            candidates.append(fragment)
    return max(candidates, key=lambda fragment: fragment.left, default=None)


def _minus_stroke_before_amount(image: Image.Image, fragment: OCRLine) -> bool:
    """Recover a thin minus glyph that OCR omitted from an otherwise valid number."""
    search_width = max(8, round(fragment.height * 1.4))
    left = max(0, fragment.left - search_width)
    top = max(0, round(fragment.top + fragment.height * 0.25))
    right = max(left + 1, fragment.left + round(fragment.height * 0.18))
    bottom = min(image.height, round(fragment.top + fragment.height * 0.75))
    pixels = image.crop((left, top, right, bottom)).load()
    width, height = right - left, bottom - top
    required_run = max(4, round(fragment.height * 0.25))
    for y in range(height):
        run = 0
        for x in range(width):
            if pixels[x, y] < 105:
                run += 1
                if run >= required_run:
                    return True
            else:
                run = 0
    return False


def _has_explicit_sign(value: str) -> bool:
    return bool(re.match(r"\s*[+\-−–—~]", value))


def parse_signed_decimal(value: str) -> Decimal | None:
    normalized = value.translate(str.maketrans({"−": "-", "–": "-", "—": "-", "~": "-"}))
    normalized = normalized.replace(" ", "")
    if "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def _clean_text(value: str) -> str:
    value = re.sub(r"\b(?:SEK|NOK|kr)\b|:-", "", value, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", value).strip(" -|·")


def _clean_merchant(value: str) -> str:
    """Remove a compact-view status prefix without changing merchant identity."""
    # Column separators leave leading whitespace when this function receives a
    # raw date-to-amount slice rather than already normalized text.
    value = value.lstrip()
    value = re.sub(r"^reservert\s*:\s*", "", value, flags=re.IGNORECASE)
    # Some compact statements repeat a source amount before the actual
    # merchant (for example ``Nok 957,00 Zalando Payments G``). Restrict this
    # cleanup to a leading currency plus decimal amount so ordinary numbers in
    # merchant names remain untouched. The complete OCR text is still retained
    # on the draft row for review and auditing.
    value = re.sub(
        r"^\s*(?:SEK|NOK|kr)\s+[+\-]?\s*"
        r"(?:\d{1,3}(?:[ .]\d{3})+|\d+)[,.]\d{2}\s+",
        "",
        value,
        flags=re.IGNORECASE,
    )
    return _clean_text(value)


def _weighted_confidence(lines: list[OCRLine]) -> float:
    total_weight = sum(max(len(line.text.strip()), 1) for line in lines)
    confidence = sum(line.confidence * max(len(line.text.strip()), 1) for line in lines) / max(
        total_weight, 1
    )
    return round(confidence, 4)


def _union_bounds(lines: list[OCRLine]) -> dict[str, int]:
    left = min(line.left for line in lines)
    top = min(line.top for line in lines)
    right = max(line.left + line.width for line in lines)
    bottom = max(line.top + line.height for line in lines)
    return {"left": left, "top": top, "width": right - left, "height": bottom - top}
