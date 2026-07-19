import re
import unicodedata
from decimal import Decimal


def normalize_text(value: str | None) -> str:
    """Normalize user text without retaining case, punctuation, or accents."""
    if not value:
        return ""
    without_accents = "".join(
        character
        for character in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9]+", " ", without_accents.lower()).strip()


def tokenize(value: str | None) -> list[str]:
    """Return every distinct meaningful word as an independent signal."""
    normalized = normalize_text(value)
    return list(dict.fromkeys(token for token in normalized.split() if len(token) > 1))


def amount_band(amount: Decimal | None, currency_code: str | None) -> str:
    """Place an absolute amount in a currency-aware, explainable magnitude band.

    Magnitude is intentionally coarse. It can gently distinguish a small café
    purchase from a large fuel purchase without overpowering merchant or phrase
    evidence, and SEK amounts are never compared silently with NOK amounts.
    """
    if amount is None or not currency_code:
        return ""
    magnitude = abs(amount)
    boundaries = (
        (Decimal("50"), "0-49"),
        (Decimal("100"), "50-99"),
        (Decimal("250"), "100-249"),
        (Decimal("500"), "250-499"),
        (Decimal("1000"), "500-999"),
        (Decimal("2000"), "1000-1999"),
        (Decimal("5000"), "2000-4999"),
    )
    label = next((name for ceiling, name in boundaries if magnitude < ceiling), "5000+")
    return f"{currency_code.upper()}:{label}"
