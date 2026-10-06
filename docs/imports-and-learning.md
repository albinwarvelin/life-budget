# Screenshot imports and learning models

## Local OCR

Screenshot import accepts PNG, JPEG, and WebP files up to 15 MB. The browser
previews the image before upload. Tesseract then runs locally with table and
sparse-text passes; no screenshot is sent to an external OCR provider.

The parser supports full merchant/date/amount tables and compact Nordic layouts.
It handles localized names and abbreviations for every month, including `jun.`,
`aug.`, and `sep.`, and OCR spacing variants such as `5.sep.`. Cropped year
headings use recent account-import context; check the inferred year in review.
If no year is available, the date stays blank for correction instead of using
the current calendar year. The parser also handles
account-currency amounts beside foreign annotations, unsigned incoming/outgoing
columns, and common transaction-text prefixes. Wrapped amount badges can appear
above or below the date. Foreign-currency annotations never substitute for a
missing booked account-currency amount.

Recognizable rows with missing or malformed dates or amounts remain incomplete
drafts with validation errors. Separate rows with identical date, merchant, and
amount are kept and flagged as possible duplicates for review. OCR can still
omit text entirely, so compare the draft count and values with the screenshot.

Every extracted row remains a draft. The user must accept or reject every row
before the batch completes. An incomplete OCR row can be rejected without first
inventing missing transaction values. Accepted expenses, income, and
reimbursements store positive magnitudes; savings and transfers preserve their
reviewed sign. Validation failures identify the affected review row and field.

Approved transactions retain a link to their source draft. Lists show newest
dates first and preserve the screenshot's top-to-bottom order within each date
and import batch, regardless of the order in which approval rows are submitted.
Newer import groups appear first; manual entries keep their insertion-order tie
break. There is no bank transaction time available to order different sources
precisely within a day. Historical transactions created before this link was
introduced keep their prior ordering because source-row matches are ambiguous.

## Reviewed-data predictions

One disposable local prediction store replaces the old three additive stores.
Manual entries and approved imports teach all three classifiers. Edits replace
one example by transaction identity; deletion withdraws it. Learning updates are
queued atomically with the ledger write, so an outage can retry without losing
or duplicating examples. Unapproved drafts and tester inputs are never labels.
If predictions are unavailable, OCR still produces reviewable drafts with a
manual-label warning. A model-store outage cannot undo approved financial saves.

Reviewed examples have full weight, including suggestions that you reviewed
and confirmed. Historical bank signs were not persisted: those rows explicitly
use the reviewed type as a direction fallback. New approvals preserve the final
reviewed signed source amount separately from the ledger magnitude.

Type prediction uses observed merchant, currency, account, direction and smooth
amount features. Category prediction integrates type probabilities rather than
trying income first. Manual category suggestions condition on the chosen type.
Description retains a direct expert based on observed fields and can blend in
a category-conditioned expert. The blend averages over predicted categories,
falls with their uncertainty, and is capped at 50%. Validation with predicted
categories must improve log loss without reducing top-one accuracy to enable
it; otherwise the direct expert remains active. Compact screenshots do not extract
transaction descriptions; the full-table parser can. Generated descriptions
are never used as observed category/type features. Reviewed blank descriptions
are learned as an outcome too.

Low evidence leaves import fields unselected and shows model scores as estimates.
A missing type must be selected before approval. Manual category alternatives
are advisory; an explicit category choice is preserved. All ledger values still
require review and remain exact Decimal values.

Each review row offers **Show alternatives** using its current corrected merchant,
signed amount, currency and account. You can explicitly choose a description
even when the model abstains from filling it automatically. Changing those
observed inputs clears the displayed alternatives. A draft's editable type or
category is not silently treated as confirmed context; these alternatives use
the model's category distribution, not the draft's unconfirmed category value.

## Learning page

Settings -> Learning model shows reviewed-example counts, pending updates and
model versions. Opening or refreshing this page is read-only and never fits a
model. Reviewed edits are synchronized separately and shown as **changed
transactions** waiting for training. **Retrain model** explicitly replaces the
active snapshot. Predictions reuse it until retraining; a missing or incompatible
model can initialize once on its first prediction. Chronological test metrics include accuracy, macro F1, top-three
accuracy, majority baseline, precision/coverage and calibration-bin observations.
Whole import batches stay in one partition. A separate counterparty holdout
checks predictions on names absent from training. Insufficient data is stated
explicitly rather than displaying training accuracy as a test result.

Category and description suggestions use the configured 75% threshold; type
retains validation-based threshold selection. Three reviewed examples per label,
multiple learned labels, currency checks and review-before-save still apply.
The configured threshold is not a guarantee of 75% accuracy or of the automatic
Wilson precision target. A blank description remains a legitimate learned
outcome. The tester shows how much category context affected a description;
its feature contributions describe the direct expert, not the complete blend.

The tester runs the same inference as screenshot import and exposes alternatives,
reviewed support and additive score contributions. Scores are not guaranteed
accuracy. Contributions show associations, not causal explanations; category
contributions illustrate the most likely type, while ranking marginalizes all
possible types. See [Model design](learning-model-design.md) for details and
[Rebuilding and retiring old stores](production.md#rebuild-and-retire-legacy-learning).
