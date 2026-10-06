# Reviewed-data learning model

Implemented with a separate prediction store and financial migration
`0009_reviewed_learning_outbox`. Source-row ordering remains implemented by
`0008_import_provenance` and is preserved.

## Source of truth and lifecycle

Saved reviewed transactions are the authority. The three old append-only
pattern learners are retired. Training starts from current ledger rows, never
from their skewed weights or accumulated events. One current example exists per
transaction ID. Edits replace it; deletion leaves a tombstone. A revisioned
outbox shares each financial commit, and receiving-side commits precede
acknowledgements. Replays cannot duplicate or resurrect an example. Pending
updates retry on later mutations, predictions and explicit retraining. Status
reads only report them and do not deliver the outbox.

Every stored field was reviewed by this user, so confirmed labels have weight
1.0 regardless of whether they started as a suggestion. Imported source signs
are preserved after approval; legacy direction is explicitly derived from the
reviewed transaction type and counted in evaluation metadata. Existing ledger
values are never rewritten by the rebuild. Financial calculations use Decimal;
floating point is confined to ML arrays and evaluation metrics.

## Features and classifiers

Merchant word TF-IDF and character n-grams handle shared brands and OCR variation.
Indicators encode currency, account and direction. Smooth Gaussian bases of
log(1 + absolute amount), scoped by currency/direction, represent amount without
hard band boundaries. Weak name-shape/business-suffix features interact with
these bases. They contain no personal names, category names or +50 NOK rule.

Regularized logistic regression minimizes cross-entropy plus an L2 penalty.
C is selected from 0.25, 1 and 4 on held-out validation data.

```text
p(type=t | x) = softmax(a_t * features(x) + intercept_t)
p(category=c | x,t) = softmax(b_c * features(x,t) + intercept_c)
p(category=c | x) = sum_t p(type=t | x) * p(category=c | x,t)
p(description=d | x) = softmax(h_d * features(x) + intercept_d)
```

Type does not depend on a predicted category. Category integrates type uncertainty
unless a user chose the type. It may still make errors when type predictions
are wrong, but it avoids the old first-income-match shortcut.

Description uses two experts: a direct classifier of observed fields and a
category-conditioned classifier, both trained on the same reviewed description
labels. True training categories are conditioning labels for the second expert,
not in-sample predicted features in a stacked learner. Validation/test inference
never reads their true category/type; it averages over upstream predictions:

```text
q_context(d | x) = sum_c p(category=c | x) q(d | x, category=c)
certainty = 1 - H(p(category | x)) / log(number of categories)
w = selected_blend * certainty
p(description=d | x) = (1-w) q_direct(d | x) + w q_context(d | x)
```

Blend candidates are 0, 0.25 and 0.5, requiring at least 20 validation rows.
Selection minimizes validation log loss using predicted categories and must
not reduce validation top-one accuracy relative to direct-only predictions.
Otherwise the blend stays zero. Each context category additionally needs three
training examples. Unsupported probability mass contributes direct evidence;
inactive categories retain their mass as unknown uncertainty instead of making
surviving categories artificially certain. A single learned category does not
establish certainty and supplies no context. The effective category contribution
is reported per prediction and cannot exceed 50%. Even a confidently wrong
category cannot entirely replace direct evidence. This reduces error propagation;
it does not eliminate it. The composed probability is not further sharpened by
temperature scaling, preserving the influence bound; a mixed output is marked
uncalibrated rather than borrowing the direct expert's calibration claim.

Description still selects previously reviewed text rather than generating
arbitrary prose. Blank descriptions are valid outcomes. The final description
is never an observed feature. Feature contributions explain the direct expert
only; the mixture weight explains the additional category influence.

scikit-learn, NumPy and SciPy run locally. Snapshots contain JSON vocabularies,
IDF values, coefficients and intercepts; no executable pickle is loaded. Up to
three snapshots are retained. Preprocessing is fitted on training data only.

## Evaluation and uncertainty

Split current examples by confirmation chronology into 60/20/20 percent of
whole import groups. A correction moves its group to its latest confirmation.
SQLite audit timestamps are UTC values stored without a timezone suffix;
transaction dates remain calendar dates. Timestamp ties use transaction IDs.
Fewer than 20 rows or five groups means no chronological metrics. Historical
rows without import provenance remain individual groups; the separate merchant
holdout is useful because near-duplicate names may span those groups.

Choose regularization, expert temperature and description blend on validation, never on the later
test set. Temperature scaling requires at least 20 validation labels, two
classes, and no unseen validation label. Category tuning uses predicted type
mixtures, not the true held-out type. Automatic type thresholds target a Wilson
95 percent lower precision bound of 0.8, with at least 20 selected validation
examples. If validation cannot support that bound, abstain. Category and
description use the explicitly requested fixed 0.75 review threshold. Their
precision/coverage is measured, not guaranteed to meet the automatic precision
target. With no validation,
the default score threshold is conservative and marked uncalibrated. Every
suggested label additionally requires three reviewed examples; a single-class
head cannot establish certainty and never supplies an automatic suggestion.

Later test data reports accuracy, macro F1, per-label recall, log loss,
top-three accuracy, majority baseline and suggestion precision/coverage.
Direct-only and selected-blend description results use the same untouched test
partition. Blank-description outcomes are excluded from suggestion coverage,
matching the import behavior that leaves those fields empty.
Calibration bins compare mean model score with actual accuracy. A separate
20 percent counterparty holdout fits fresh preprocessing and classifiers with
no shared merchant names; its suggestion thresholds are not evaluated. Its
description report evaluates the direct expert only: blend selection on the
chronological partition could otherwise overlap this separate holdout.

Deployed coefficients refit all reviewed rows after settings are selected.
Reported held-out metrics belong to the earlier evaluation model, not a claim
that the refitted model has been independently tested. Sparse labels and future
months can still behave differently. The old model is not retained at runtime
for a broad before/after benchmark; the confirmed scope-ordering failure and
synthetic regression cases provide targeted regression evidence.

## Experimental model lab and adjustment settings

`/settings/learning` is an experimental explanation page with selectable stages,
the active snapshot's C, temperature and suggestion threshold for each output,
a synthetic softmax playground, the read-only transaction tester and expandable
held-out reports. Status reads never synchronize examples, train or activate a
snapshot. A POST to `/api/v1/learning-models/retrain` explicitly fits current
reviewed data. If fitting fails, the previous active snapshot remains usable.
Reviewed mutations synchronize examples cheaply, while predictions reuse the
active snapshot despite newer data. A missing/incompatible model bootstraps
once on prediction or explicit retraining. Status reports distinct changed
transactions including deletions and undelivered outbox updates. The playground uses invented labels and fixed logits; its
sliders never change production settings, save a transaction or teach the model.
Temperature does not change the winner for fixed logits. A suggestion threshold
changes acceptance, not probabilities. Real category probabilities are a mixture
of conditional predictions, rather than the playground's single softmax.

Developer-adjustable grids and policies live in
`backend/app/services/prediction_settings.py`; the status API exposes these same
values in `configuration`. Current defaults are:

| Setting | Current value | Effect |
| --- | --- | --- |
| C candidates | 0.25, 1, 4 | Inverse L2 regularization strength; smaller C penalizes large coefficients more. Retrain to change coefficients. |
| Temperature candidates | 0.75, 1, 1.5, 2 | Rescale logits; higher temperatures spread probabilities. Select on validation data. |
| Type threshold candidates | 0.5, 0.6, 0.7, 0.8, 0.9 | Selected on validation; no passing candidate disables type suggestions. |
| Category / description thresholds | 0.75 / 0.75 | User-requested review policy, not a validated precision guarantee. |
| Description blend candidates | 0, 0.25, 0.5 | Maximum context influence, further reduced by category uncertainty; selected on validation with at least 20 rows. |
| Minimum label support | 3 | Required reviewed examples for the winning label. |
| Validation evidence | 20 selected rows, Wilson z = 1.96, lower precision bound ≥ 0.8 | Controls how much evidence is needed to enable suggestions. Temperature fitting also needs 20 validation rows. |
| Word / character fragments | Words 1–2, max 2,000; characters 3–5, max 4,000 | Text detail and model size; requires retraining. |
| Amount bases | 13 log-space centres, width 1 | Detail and smoothing across amounts; requires retraining. |
| Chronological partitions | About 60% / 20% / 20% of groups | Training / validation / test allocation, rounded at group boundaries. |

There is no persisted live parameter editor. To change settings, explicitly
rebuild the model and reassess held-out results; do not tune against the test
partition. Feature changes require a new `ALGORITHM_VERSION` so old JSON
snapshots are invalidated before inference. Other settings also need a version
bump or an explicit rebuild to replace a cached snapshot. Merely editing a
constant does not update the already selected parameters. All reviewed rows
currently have weight 1; differentiated suggestion-origin weighting is future
training-policy work, not an available page control.

## References

- [Logistic regression](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html)
- [Calibration](https://scikit-learn.org/stable/modules/calibration.html)
- [Avoiding data leakage](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage)
- [Model persistence](https://scikit-learn.org/stable/model_persistence.html)
