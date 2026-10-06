"""Shared local features, with monetary values converted only inside ML arrays."""

import math
import re
import unicodedata
from decimal import Decimal

import numpy as np
from scipy.sparse import hstack
from sklearn.feature_extraction import DictVectorizer
from sklearn.feature_extraction.text import TfidfVectorizer

from app.services.prediction_settings import (
    AMOUNT_CENTERS,
    AMOUNT_WIDTH,
    CHARACTER_FEATURES,
    CHARACTER_NGRAM_RANGE,
    WORD_FEATURES,
    WORD_NGRAM_RANGE,
)


def normalize_text(value: str) -> str:
    value = "".join(
        character
        for character in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip() or "unknown"


def metadata_features(row: dict) -> dict[str, float]:
    """Smooth currency/direction-specific amount bases, including name-shape interactions.

    No personal name or target category is hardcoded. Name shape is a weak,
    uncertain input; companies can share the same shape. Decimal values remain
    unchanged in storage. Floating point is used only to construct ML features.
    """
    merchant = normalize_text(row["merchant"])
    tokens = merchant.split()
    business = bool(set(tokens) & {"as", "ab", "ltd", "inc", "oy", "aps", "gmbh"})
    name_shape = float(
        2 <= len(tokens) <= 4 and all(token.isalpha() for token in tokens) and not business
    )
    currency = row["currency_code"].upper()
    direction = row.get("direction", "unknown")
    features = {
        f"currency={currency}": 1.0,
        f"direction={direction}": 1.0,
        f"account={row.get('account_id')}": 1.0,
        f"merchant={merchant}": 1.0,
        "name_shape": name_shape,
        "business_suffix": float(business),
    }
    if row.get("conditional_type"):
        features[f"type={row['conditional_type']}"] = 1.0
    # Only the conditional description expert receives this category. The
    # independent expert never receives category/type labels or predictions.
    if row.get("conditional_category") is not None:
        features[f"category={row['conditional_category']}"] = 1.0
    if row.get("amount") is not None:
        magnitude = math.log1p(float(abs(Decimal(str(row["amount"])))))
        # Equally spaced log-space centers cover small and large amounts
        # smoothly. There is no discontinuity at 50 or another bank amount.
        for index in range(AMOUNT_CENTERS):
            basis = math.exp(-0.5 * ((magnitude - index) / AMOUNT_WIDTH) ** 2)
            scope = f"{currency}/{direction}"
            features[f"amount:{scope}:{index}"] = basis
            features[f"name_amount:{scope}:{index}"] = basis * name_shape
            if row.get("conditional_type"):
                features[f"type_amount:{row['conditional_type']}:{scope}:{index}"] = basis
            if row.get("conditional_category") is not None:
                features[f"category_amount:{row['conditional_category']}:{scope}:{index}"] = basis
    return features


class FeaturePipeline:
    """Fit preprocessing on training rows only and persist transparent JSON state."""

    def __init__(self):
        self.words = TfidfVectorizer(
            ngram_range=WORD_NGRAM_RANGE,
            max_features=WORD_FEATURES,
            sublinear_tf=True,
            token_pattern=r"(?u)\b\w+\b",
        )
        self.characters = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=CHARACTER_NGRAM_RANGE,
            max_features=CHARACTER_FEATURES,
            sublinear_tf=True,
        )
        self.metadata = DictVectorizer()

    def fit_transform(self, rows: list[dict]):
        texts = [normalize_text(row["merchant"]) for row in rows]
        return hstack(
            [
                self.words.fit_transform(texts),
                self.characters.fit_transform(texts),
                self.metadata.fit_transform([metadata_features(row) for row in rows]),
            ],
            format="csr",
        )

    def transform(self, rows: list[dict]):
        texts = [normalize_text(row["merchant"]) for row in rows]
        return hstack(
            [
                self.words.transform(texts),
                self.characters.transform(texts),
                self.metadata.transform([metadata_features(row) for row in rows]),
            ],
            format="csr",
        )

    def names(self) -> list[str]:
        return (
            [f"word:{value}" for value in self.words.get_feature_names_out()]
            + [f"characters:{value}" for value in self.characters.get_feature_names_out()]
            + list(self.metadata.get_feature_names_out())
        )

    def to_json(self) -> dict:
        return {
            "words": {
                "vocabulary": {key: int(value) for key, value in self.words.vocabulary_.items()},
                "idf": self.words.idf_.tolist(),
            },
            "characters": {
                "vocabulary": {
                    key: int(value) for key, value in self.characters.vocabulary_.items()
                },
                "idf": self.characters.idf_.tolist(),
            },
            "metadata": list(self.metadata.get_feature_names_out()),
        }

    @classmethod
    def from_json(cls, values: dict):
        pipeline = cls()
        for name in ("words", "characters"):
            vectorizer = getattr(pipeline, name)
            vectorizer.vocabulary = values[name]["vocabulary"]
            vectorizer.vocabulary_ = values[name]["vocabulary"]
            vectorizer.fixed_vocabulary_ = True
            vectorizer.idf_ = np.asarray(values[name]["idf"])
        pipeline.metadata.feature_names_ = values["metadata"]
        pipeline.metadata.vocabulary_ = {key: index for index, key in enumerate(values["metadata"])}
        return pipeline
