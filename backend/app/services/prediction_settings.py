"""Training and suggestion policy for the local model.

The learning page reads these same values. They are developer settings, not
live controls: changes require an explicit rebuild and fresh holdout evaluation.
Feature changes also require a new algorithm version to invalidate snapshots.
"""

REGULARIZATION_CANDIDATES = (0.25, 1.0, 4.0)
TEMPERATURE_CANDIDATES = (0.75, 1.0, 1.5, 2.0)
THRESHOLD_CANDIDATES = (0.5, 0.6, 0.7, 0.8, 0.9)
# Explicit review-workflow policy requested by the user. These thresholds are
# evaluated and reported; they do not claim the automatic Wilson precision target.
SUGGESTION_THRESHOLDS = {"category": 0.75, "description": 0.75}
DESCRIPTION_BLEND_CANDIDATES = (0.0, 0.25, 0.5)
DESCRIPTION_CONTEXT_MIN_ROWS = 20
MINIMUM_SUPPORT = 3
MINIMUM_VALIDATION_SAMPLES = 20
TARGET_PRECISION = 0.8
WILSON_Z = 1.96
TRAIN_FRACTION = 0.6
VALIDATION_FRACTION = 0.2
WORD_NGRAM_RANGE = (1, 2)
CHARACTER_NGRAM_RANGE = (3, 5)
WORD_FEATURES = 2000
CHARACTER_FEATURES = 4000
AMOUNT_CENTERS = 13
AMOUNT_WIDTH = 1.0


def configuration() -> dict:
    """Public, data-free configuration; coefficients and training rows stay local."""
    return {
        "regularization_candidates": REGULARIZATION_CANDIDATES,
        "temperature_candidates": TEMPERATURE_CANDIDATES,
        "threshold_candidates": THRESHOLD_CANDIDATES,
        "suggestion_thresholds": SUGGESTION_THRESHOLDS,
        "description_blend_candidates": DESCRIPTION_BLEND_CANDIDATES,
        "description_context_min_rows": DESCRIPTION_CONTEXT_MIN_ROWS,
        "minimum_support": MINIMUM_SUPPORT,
        "minimum_validation_samples": MINIMUM_VALIDATION_SAMPLES,
        "target_precision": TARGET_PRECISION,
        "wilson_z": WILSON_Z,
        "train_fraction": TRAIN_FRACTION,
        "validation_fraction": VALIDATION_FRACTION,
        "word_ngram_range": WORD_NGRAM_RANGE,
        "character_ngram_range": CHARACTER_NGRAM_RANGE,
        "word_features": WORD_FEATURES,
        "character_features": CHARACTER_FEATURES,
        "amount_centers": AMOUNT_CENTERS,
        "amount_width": AMOUNT_WIDTH,
    }
