# Architecture

Life Budget is a localhost-only monorepo with a React frontend and FastAPI
backend. Domain and financial rules live in backend services; repositories
contain database queries; route handlers translate HTTP requests and errors.

## Runtime flow

```text
React UI
  -> typed fetch client
  -> FastAPI /api/v1 routes
  -> service validation and workflows
  -> SQLAlchemy repositories/models
  -> local SQLite files
```

Development runs Vite and Uvicorn separately. Production builds Vite once and
FastAPI serves `frontend/dist` with a single-page-application fallback. Concrete
API routes are registered before that fallback.

## Data stores

The stores are intentionally separate:

| Store | Default development file | Contents |
| --- | --- | --- |
| Financial | `life_budget.db` | Accounts, categories, transactions, imports |
| Category learning | `life_budget_learning.db` | Category evidence and events |
| Type learning | `life_budget_type_learning.db` | Transaction-type evidence |
| Description learning | `life_budget_description_learning.db` | Description evidence |

All engines enable SQLite foreign-key enforcement and a ten-second busy timeout.
Production uses one Uvicorn worker to limit write contention.

Money is persisted as fixed-point `Decimal`/`NUMERIC`. Frontend summaries add
integer minor units rather than binary floating-point amounts. Currencies remain
separate throughout storage and summaries.

## Screenshot import

```text
Upload/paste
  -> validate and store local image
  -> background Tesseract OCR
  -> parse rows and generate predictions
  -> persist editable draft rows
  -> user accepts/rejects every row
  -> one financial commit
  -> confirmed values update isolated learners
```

OCR and predictions never create transactions before review. The original OCR
text, extracted values, confidence, and duplicate warning remain visible.

## Security boundary

The current trust model is one person on one computer. The server binds to
`127.0.0.1`; there is no authentication. CORS is not an authentication
mechanism, so do not bind to `0.0.0.0`, port-forward, or expose the app to a
local network or internet.

Uploaded files, screenshots, and database records are sensitive. They are
ignored by Git and should be included in private backups.
