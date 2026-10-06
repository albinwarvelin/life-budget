"""Regularized classifiers with leakage-free chronology and explicit uncertainty."""

from collections import Counter

import numpy as np
from scipy.special import softmax
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import GroupShuffleSplit
from threadpoolctl import threadpool_limits

from app.services.prediction_features import FeaturePipeline, normalize_text
from app.services.prediction_settings import (
    DESCRIPTION_BLEND_CANDIDATES,
    DESCRIPTION_CONTEXT_MIN_ROWS,
    MINIMUM_SUPPORT,
    MINIMUM_VALIDATION_SAMPLES,
    REGULARIZATION_CANDIDATES,
    SUGGESTION_THRESHOLDS,
    TARGET_PRECISION,
    TEMPERATURE_CANDIDATES,
    THRESHOLD_CANDIDATES,
    TRAIN_FRACTION,
    VALIDATION_FRACTION,
    WILSON_Z,
)

ALGORITHM_VERSION = "logistic-v2-category-description"
HEADS = ("type", "category", "description")


def label(row: dict, kind: str) -> str | None:
    if kind == "type":
        return row["transaction_type"]
    if kind == "category":
        return str(row["category_id"]) if row.get("category_id") is not None else None
    # A reviewed empty description is a valid outcome, not missing training
    # data. Learning it prevents filling every similar transaction with text.
    return normalize_text(row["description"]) if row.get("description", "").strip() else "__empty__"


def head_rows(rows: list[dict], kind: str) -> list[dict]:
    return [
        {**row, "conditional_type": row["transaction_type"]} if kind == "category" else row
        for row in rows
        if label(row, kind) is not None
    ]


class Classifier:
    """Inference from JSON coefficients; single-class data is explicitly limited."""

    def __init__(self, parameters: dict):
        self.parameters = parameters
        self.classes = parameters["classes"]
        self.pipeline = FeaturePipeline.from_json(parameters["features"]) if self.classes else None

    def probabilities(self, rows: list[dict]) -> np.ndarray:
        if not rows:
            return np.zeros((0, len(self.classes)))
        if not self.classes:
            return np.zeros((len(rows), 0))
        if len(self.classes) == 1:
            return np.ones((len(rows), 1))
        matrix = self.pipeline.transform(rows)
        logits = (
            matrix @ np.asarray(self.parameters["coefficients"]).T + self.parameters["intercepts"]
        )
        return softmax(logits / self.parameters.get("temperature", 1.0), axis=1)

    def contributions(self, row: dict, target: str) -> list[dict]:
        if len(self.classes) < 2 or target not in self.classes:
            return []
        matrix = self.pipeline.transform([row]).getrow(0)
        coefficients = self.parameters["coefficients"][self.classes.index(target)]
        names = self.pipeline.names()
        terms = [
            {"feature": names[index], "contribution": round(float(coefficients[index] * value), 4)}
            for index, value in zip(matrix.indices, matrix.data, strict=True)
        ]
        return sorted(terms, key=lambda item: abs(item["contribution"]), reverse=True)[:6]


def fit_classifier(
    rows: list[dict], kind: str, regularization: float = 1.0, *, condition_category: bool = False
) -> dict:
    rows = head_rows(rows, kind)
    if condition_category:
        # This expert estimates P(description | observed fields, category).
        # True categories are legitimate conditioning labels during training.
        # Validation and inference instead integrate upstream predictions below.
        rows = [
            {
                **row,
                "conditional_category": str(row["category_id"])
                if row.get("category_id") is not None
                else None,
            }
            for row in rows
        ]
    targets = [label(row, kind) for row in rows]
    counts = Counter(targets)
    classes = sorted(counts)
    values = {
        "classes": classes,
        "counts": dict(counts),
        "regularization": regularization,
        "temperature": 1.0,
        "threshold": 0.75,
        "calibrated": False,
    }
    if not rows:
        return values
    pipeline = FeaturePipeline()
    matrix = pipeline.fit_transform(rows)
    values["features"] = pipeline.to_json()
    if len(classes) == 1:
        # A one-label dataset cannot teach discrimination or establish certainty.
        values.update(coefficients=[], intercepts=[], threshold=1.1)
        return values
    estimator = LogisticRegression(C=regularization, max_iter=1000)
    estimator.fit(matrix, targets, sample_weight=[row.get("weight", 1.0) for row in rows])
    coefficients, intercepts = estimator.coef_, estimator.intercept_
    if len(classes) == 2 and len(coefficients) == 1:
        coefficients = np.vstack([-coefficients[0] / 2, coefficients[0] / 2])
        intercepts = np.array([-intercepts[0] / 2, intercepts[0] / 2])
    values.update(
        classes=estimator.classes_.tolist(),
        coefficients=coefficients.tolist(),
        intercepts=intercepts.tolist(),
    )
    return values


def negative_log_likelihood(probabilities, classes, targets):
    indices = {value: index for index, value in enumerate(classes)}
    return (
        float(
            np.mean(
                [
                    -np.log(
                        max(
                            float(probabilities[index, indices[target]])
                            if target in indices
                            else 0.0,
                            1e-15,
                        )
                    )
                    for index, target in enumerate(targets)
                ]
            )
        )
        if targets
        else None
    )


def chronology_split(rows: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Whole imports stay in one partition, including out-of-order bank months."""
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["group"], []).append(row)
    # Corrections move their entire import group to the latest confirmation.
    # Otherwise a revised label could leak into an earlier training partition.
    batches = sorted(
        groups.values(),
        key=lambda batch: max((row["confirmed_at"], row["transaction_id"]) for row in batch),
    )
    if len(batches) < 5 or len(rows) < 20:
        return rows, [], []
    first, second = (
        max(1, int(len(batches) * TRAIN_FRACTION)),
        max(2, int(len(batches) * (TRAIN_FRACTION + VALIDATION_FRACTION))),
    )
    return (
        [row for batch in batches[:first] for row in batch],
        [row for batch in batches[first:second] for row in batch],
        [row for batch in batches[second:] for row in batch],
    )


def predict_category_probabilities(models: dict, rows: list[dict]) -> tuple[np.ndarray, list[str]]:
    """Marginalize type uncertainty instead of choosing the first matching scope."""
    type_model, category_model = Classifier(models["type"]), Classifier(models["category"])
    probabilities = np.zeros((len(rows), len(category_model.classes)))
    type_probabilities = type_model.probabilities(rows)
    for index, transaction_type in enumerate(type_model.classes):
        conditional = category_model.probabilities(
            [{**row, "conditional_type": transaction_type} for row in rows]
        )
        probabilities += type_probabilities[:, index, None] * conditional
    return probabilities, category_model.classes


def description_probabilities(
    models: dict, rows: list[dict], *, category_scores: tuple[np.ndarray, list[str]] | None = None
) -> tuple[np.ndarray, list[str], np.ndarray]:
    """Bounded mixture of direct evidence and a category-conditioned expert.

    Confidence is reduced by normalized category entropy and the probability
    mass of unsupported categories. Even a confidently wrong upstream result
    can change a description probability by at most the selected blend cap.
    No true held-out category/type or description is read from the rows here.
    """
    direct = Classifier(models["description"])
    base = direct.probabilities(rows)
    weights = np.zeros(len(rows))
    context = models.get("description_category")
    blend = models.get("description_blend", 0.0)
    if not rows or not context or not blend or not direct.classes:
        return base, direct.classes, weights
    categories, category_classes = category_scores or predict_category_probabilities(models, rows)
    if not category_classes:
        return base, direct.classes, weights
    expert = Classifier(context)
    # Both experts fit the same description targets, including reviewed blanks.
    if expert.classes != direct.classes:
        raise ValueError("Description experts must share their label vocabulary")
    entropy = -np.sum(categories * np.log(np.maximum(categories, 1e-15)), axis=1)
    # When inactive categories have been excluded, keep their uncertainty as an
    # unknown outcome; filtering them must not make the remainder more certain.
    unknown_mass = np.clip(1 - categories.sum(axis=1), 0, 1)
    entropy -= unknown_mass * np.log(np.maximum(unknown_mass, 1e-15))
    certainty = (
        np.clip(1 - entropy / np.log(len(category_classes)), 0, 1)
        if len(category_classes) > 1
        else np.zeros(len(rows))
    )
    conditional = np.zeros_like(base)
    supported_mass = np.zeros(len(rows))
    for index, category in enumerate(category_classes):
        if context["category_support"].get(category, 0) < MINIMUM_SUPPORT:
            continue
        probability = categories[:, index]
        supported_mass += probability
        conditional += probability[:, None] * expert.probabilities(
            [{**row, "conditional_category": category} for row in rows]
        )
    # Unsupported mass contributes direct evidence instead of inventing context.
    conditional += (1 - supported_mass)[:, None] * base
    weights = float(blend) * certainty
    mixed = (1 - weights[:, None]) * base + weights[:, None] * conditional
    return mixed, direct.classes, weights * supported_mass


def model_probabilities(models: dict, kind: str, rows: list[dict]):
    if kind == "category":
        return predict_category_probabilities(models, rows)
    if kind == "description":
        probabilities, classes, _ = description_probabilities(models, rows)
        return probabilities, classes
    model = Classifier(models[kind])
    return model.probabilities(rows), model.classes


def evaluation(models: dict, rows: list[dict], training: list[dict], *, kinds=HEADS) -> dict:
    report = {}
    for kind in kinds:
        scored = [row for row in rows if label(row, kind) is not None]
        targets = [label(row, kind) for row in scored]
        if not scored or not models[kind]["classes"]:
            report[kind] = {
                "samples": len(scored),
                "accuracy": None,
                "macro_f1": None,
                "log_loss": None,
            }
            continue
        probabilities, classes = model_probabilities(models, kind, scored)
        winners = [classes[index] for index in np.argmax(probabilities, axis=1)]
        confidence = probabilities.max(axis=1)
        selected = np.asarray(
            [
                score >= models[kind]["threshold"]
                and len(classes) > 1
                and models[kind]["counts"].get(winner, 0) >= MINIMUM_SUPPORT
                and not (kind == "description" and winner == "__empty__")
                for score, winner in zip(confidence, winners, strict=True)
            ]
        )
        training_labels = [label(row, kind) for row in training if label(row, kind) is not None]
        baseline = Counter(training_labels).most_common(1)[0][0] if training_labels else None
        bins = []
        for lower in (0.0, 0.2, 0.4, 0.6, 0.8):
            members = [
                index
                for index, value in enumerate(confidence)
                if lower <= value < lower + 0.2 or (lower == 0.8 and value == 1)
            ]
            if members:
                bins.append(
                    {
                        "score": float(np.mean(confidence[members])),
                        "accuracy": float(
                            np.mean([winners[index] == targets[index] for index in members])
                        ),
                        "count": len(members),
                    }
                )
        top_three = np.argsort(probabilities, axis=1)[:, -3:]
        report[kind] = {
            "samples": len(scored),
            "accuracy": float(accuracy_score(targets, winners)),
            "macro_f1": float(f1_score(targets, winners, average="macro", zero_division=0)),
            "log_loss": negative_log_likelihood(probabilities, classes, targets),
            "baseline_accuracy": float(np.mean([target == baseline for target in targets])),
            "top_three_accuracy": float(
                np.mean(
                    [
                        target in [classes[j] for j in top_three[index]]
                        for index, target in enumerate(targets)
                    ]
                )
            ),
            "coverage": float(np.mean(selected)),
            "suggestion_precision": float(
                np.mean(
                    [
                        winner == target
                        for winner, target, accept in zip(winners, targets, selected, strict=True)
                        if accept
                    ]
                )
            )
            if selected.any()
            else None,
            "unseen_counterparties": sum(
                normalize_text(row["merchant"])
                not in {normalize_text(item["merchant"]) for item in training}
                for row in scored
            ),
            "calibration_bins": bins,
            "per_label_recall": {
                target: float(
                    np.mean(
                        [
                            winner == target
                            for winner, actual in zip(winners, targets, strict=True)
                            if actual == target
                        ]
                    )
                )
                for target in sorted(set(targets))
            },
        }
    return report


def choose_description_context(models: dict, training: list[dict], validation: list[dict]) -> dict:
    """Choose a capped blend on validation with actual predicted categories.

    This is conditional modelling, not stacking trained on in-sample category
    predictions. All experts and their feature vocabularies fit training only.
    A separate later test reports generalization without selecting the blend.
    """
    models["description_blend"] = 0.0
    targets = [label(row, "description") for row in validation]
    baseline, classes = model_probabilities(models, "description", validation)
    baseline_loss = negative_log_likelihood(baseline, classes, targets) if classes else None
    summary = {
        "weight": 0.0,
        "validation_base_log_loss": baseline_loss,
        "validation_blend_log_loss": baseline_loss,
    }
    if len(validation) < DESCRIPTION_CONTEXT_MIN_ROWS or len(classes) < 2:
        return summary
    baseline_accuracy = np.mean(
        [
            classes[index] == target
            for index, target in zip(baseline.argmax(axis=1), targets, strict=True)
        ]
    )
    best_loss = baseline_loss
    for regularization in REGULARIZATION_CANDIDATES:
        expert = fit_classifier(training, "description", regularization, condition_category=True)
        expert["category_support"] = dict(
            Counter(
                str(row["category_id"]) for row in training if row.get("category_id") is not None
            )
        )
        for blend in DESCRIPTION_BLEND_CANDIDATES:
            if not blend:
                continue
            candidate = {**models, "description_category": expert, "description_blend": blend}
            probabilities, _, _ = description_probabilities(candidate, validation)
            loss = negative_log_likelihood(probabilities, classes, targets)
            accuracy = np.mean(
                [
                    classes[index] == target
                    for index, target in zip(probabilities.argmax(axis=1), targets, strict=True)
                ]
            )
            # Enable context only for a strict held-out loss improvement without
            # reducing top-one accuracy on that validation partition.
            if loss < best_loss - 1e-6 and accuracy >= baseline_accuracy:
                models["description_category"] = expert
                models["description_blend"] = blend
                best_loss = loss
    if models["description_blend"]:
        # An expert's calibration does not calibrate the whole composition.
        # Keep a convex probability blend so the influence bound survives; do
        # not sharpen the final mixture and amplify a wrong category again.
        models["description"]["calibrated"] = False
        summary.update(weight=models["description_blend"], validation_blend_log_loss=best_loss)
    return summary


def train_models(rows: list[dict]) -> tuple[dict, dict]:
    """Choose C/temperature/threshold on validation; report later untouched imports."""
    training, validation, testing = chronology_split(rows)
    choices = {}
    with threadpool_limits(limits=1):
        for kind in HEADS:
            candidates = [
                fit_classifier(training, kind, value) for value in REGULARIZATION_CANDIDATES
            ]
            validation_rows = [row for row in validation if label(row, kind) is not None]
            targets = [label(row, kind) for row in validation_rows]

            def loss(candidate):
                if not targets or not candidate["classes"]:
                    return float("inf")
                if kind == "category":
                    probabilities, classes = predict_category_probabilities(
                        {**choices, "category": candidate}, validation_rows
                    )
                else:
                    probabilities, classes = (
                        Classifier(candidate).probabilities(validation_rows),
                        candidate["classes"],
                    )
                return negative_log_likelihood(probabilities, classes, targets)

            chosen = min(candidates, key=loss) if targets else candidates[1]
            if (
                len(chosen["classes"]) > 1
                and len(targets) >= MINIMUM_VALIDATION_SAMPLES
                and all(target in chosen["classes"] for target in targets)
            ):
                temperatures = TEMPERATURE_CANDIDATES
                chosen["temperature"] = min(
                    temperatures, key=lambda value: loss({**chosen, "temperature": value})
                )
                chosen["calibrated"] = True
            choices[kind] = chosen
        description_context = choose_description_context(choices, training, validation)
        # User-configured review thresholds are explicit overrides. Automatic
        # type selection still needs the validation precision bound below.
        for kind in HEADS:
            if kind in SUGGESTION_THRESHOLDS:
                choices[kind]["threshold"] = (
                    SUGGESTION_THRESHOLDS[kind] if len(choices[kind]["classes"]) > 1 else 1.1
                )
                continue
            scored = [row for row in validation if label(row, kind) is not None]
            if not scored or not choices[kind]["classes"]:
                continue
            probabilities, classes = model_probabilities(choices, kind, scored)
            targets = [label(row, kind) for row in scored]
            winners = [classes[index] for index in np.argmax(probabilities, axis=1)]
            confidence = probabilities.max(axis=1)

            def precision_lower_bound(value):
                correct = [
                    winner == target
                    for winner, target, score in zip(winners, targets, confidence, strict=True)
                    if score >= value
                ]
                if len(correct) < MINIMUM_VALIDATION_SAMPLES:
                    return 0.0
                # Wilson's 95% lower bound avoids calling five lucky matches
                # reliable. Precision/coverage on later data remains reported.
                n, z = len(correct), WILSON_Z
                p = float(np.mean(correct))
                return (
                    p + z * z / (2 * n) - z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
                ) / (1 + z * z / n)

            thresholds = [
                value
                for value in THRESHOLD_CANDIDATES
                if precision_lower_bound(value) >= TARGET_PRECISION
            ]
            choices[kind]["threshold"] = min(thresholds) if thresholds else 1.1
        report = {
            "chronological": evaluation(choices, testing, training),
            "training_samples": len(training),
            "validation_samples": len(validation),
            "test_samples": len(testing),
            "description_context": "category_mixture"
            if choices["description_blend"]
            else "independent",
            "description_context_reason": "Category influence is entropy-damped and capped; its blend is enabled only after validation improvement using predicted categories.",
            "description_context_selection": description_context,
            "description_comparison": {
                "independent": evaluation(
                    {**choices, "description_blend": 0.0}, testing, training, kinds=("description",)
                )["description"],
                "blended": evaluation(choices, testing, training, kinds=("description",))[
                    "description"
                ],
            },
        }
        report["direction_origins"] = dict(
            Counter(row.get("direction_origin", "source") for row in rows)
        )
        # Counterparty holdout complements chronology: exact names cannot occur
        # on both sides, and no preprocessing is fitted on withheld names.
        merchants = [normalize_text(row["merchant"]) for row in rows]
        report["unseen_counterparty"] = None
        if len(rows) >= 30 and len(set(merchants)) >= 5:
            train_indices, test_indices = next(
                GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42).split(
                    rows, groups=merchants
                )
            )
            unseen_training = [rows[index] for index in train_indices]
            unseen_testing = [rows[index] for index in test_indices]
            unseen_models = {
                kind: fit_classifier(unseen_training, kind, choices[kind]["regularization"])
                for kind in HEADS
            }
            # Do not borrow calibration/thresholds selected using rows that may
            # appear in this separate counterparty test. Report ranking only.
            for kind in HEADS:
                unseen_models[kind]["threshold"] = 1.1
            # The selected blend came from chronological validation, whose rows
            # can overlap this separate merchant holdout. Evaluate direct only
            # here rather than leak blend selection into the merchant test.
            report["unseen_counterparty"] = evaluation(
                unseen_models, unseen_testing, unseen_training
            )
        # Fit the deployed coefficients on all current reviewed rows with the
        # selected settings. Holdout metrics above remain strictly out of sample.
        deployed = {}
        for kind in HEADS:
            fitted = fit_classifier(rows, kind, choices[kind]["regularization"])
            fitted.update(
                {key: choices[kind][key] for key in ("temperature", "threshold", "calibrated")}
            )
            deployed[kind] = fitted
        deployed["description_blend"] = choices["description_blend"]
        if choices["description_blend"]:
            expert = fit_classifier(
                rows,
                "description",
                choices["description_category"]["regularization"],
                condition_category=True,
            )
            expert["category_support"] = dict(
                Counter(
                    str(row["category_id"]) for row in rows if row.get("category_id") is not None
                )
            )
            deployed["description_category"] = expert
    return deployed, report
