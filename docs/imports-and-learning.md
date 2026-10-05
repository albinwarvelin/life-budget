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

## Prediction stores

Three transparent learners are updated only from confirmed values:

- Category prediction uses merchant phrases, individual tokens, description,
  account context, transaction type, and low-weight amount bands.
- Type prediction combines amount sign, merchant evidence, predicted category,
  and low-weight amount magnitude.
- Description prediction compares conditional evidence with each description’s
  overall baseline, suppressing generic correlations.

Whole-merchant compounds carry more weight than token compounds. Token
compounds still allow a shared brand such as `ICA` to transfer evidence between
differently named stores while exact matching and lower weights reduce generic
word collisions.

Suggestions are advisory. Manual entry waits one second after typing stops
before requesting a suggestion. The first suggestion may fill an untouched new
category field, but later predictions do not overwrite an explicit user choice
or an existing transaction’s category.

## Explorer

Settings → Learning model shows category, type, and description connections.
Category IDs are replaced by localized names. The description prediction lab
runs the real read-only scorer and shows conditional probability, baseline,
reliability, similarity, and weighted contribution.

## Known model lifecycle limitation

Learning is currently additive. Editing or deleting a transaction does not
retract the event previously learned from it. Before calling the learning system
final, add stable transaction identifiers to learning events and replace or
tombstone evidence on corrections/deletions.
