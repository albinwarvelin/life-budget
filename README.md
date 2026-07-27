# Life Budget

Local-first personal finance and life budgeting application.

The project is organized as a small monorepo:

- `backend/` — FastAPI API and future SQLAlchemy/Alembic persistence layer.
- `frontend/` — React/Vite user interface.
- `docs/` — product and implementation documentation.

## Development

Copy `.env.example` to `.env` when local configuration is needed. The initial health check is available at `GET /health` after starting the backend.

### Backend

```text
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
alembic upgrade head
alembic -c alembic_learning.ini upgrade head
alembic -c alembic_type_learning.ini upgrade head
alembic -c alembic_description_learning.ini upgrade head
uvicorn app.main:app --reload
```

Run backend checks with:

```text
python -m pytest
ruff check .
ruff format --check .
```

The default financial database is SQLite at `backend/life_budget.db`. The category-learning
service uses a separate SQLite file at `backend/life_budget_learning.db` by default. It stores
only normalized merchant/description signals, category IDs, observations, and weights—not
transaction amounts or account names. Category learning now also stores coarse currency-aware amount
bands, never exact paid amounts. Type learning uses `life_budget_type_learning.db`, while approved
description suggestions use `life_budget_description_learning.db`. These are local SQLite files, not
separate servers.
SQLite is a file, not a separate
server process: Alembic creates the file and tables when you run `alembic upgrade head` from
`backend/`.
Use `alembic current` to inspect the applied revision and `alembic history` to inspect available revisions.
The initial migration seeds only NOK and SEK. Add EUR, USD, or another currency explicitly through
`POST /api/v1/currencies`; it will then become available for accounts and transactions.

### Starting SQLite and the backend

From PowerShell, use:

```powershell
cd life-budget\backend
.\.venv\Scripts\Activate.ps1
alembic upgrade head
alembic -c alembic_learning.ini upgrade head
alembic -c alembic_type_learning.ini upgrade head
alembic -c alembic_description_learning.ini upgrade head
uvicorn app.main:app --reload
```

Keep Uvicorn running while using the API. Visit `http://127.0.0.1:8000/docs` for the interactive
API documentation. The manual transaction endpoints are:

```text
POST   /api/v1/transactions
GET    /api/v1/transactions
PUT    /api/v1/transactions/{transaction_id}
DELETE /api/v1/transactions/{transaction_id}
```

The API writes financial data to `life_budget.db` through SQLAlchemy sessions. The category
prediction endpoints read/write the isolated learning database:

```text
POST /api/v1/category-suggestions
POST /api/v1/category-learning/events
GET  /api/v1/category-learning/model
```

The financial and category-learning SQLite files have separate Alembic histories. Future financial schema changes belong in
`backend/alembic/versions/`; future learning-model changes belong in
`backend/alembic_learning/versions/`.

Transaction-type learning uses a third isolated file, `backend/life_budget_type_learning.db`, and
its own migration history in `backend/alembic_type_learning/`. Run
`alembic -c alembic_type_learning.ini upgrade head` after pulling type-model schema changes.
Description learning uses `backend/life_budget_description_learning.db` and its own migration history
in `backend/alembic_description_learning/`. Run
`alembic -c alembic_description_learning.ini upgrade head` after description-model schema changes.
The backend also checks and applies pending category, type, and description model migrations before
each model database is first used in a process. Running the commands explicitly remains useful because
it surfaces migration problems before the API starts handling requests.

### Screenshot imports

The Transactions page contains an **Import screenshot** button. The browser first shows the selected
image locally; only pressing **Confirm and parse** uploads it. Processing progress is persisted and
polled by the frontend. Parsed rows remain `ImportDraftRow` records until the user edits and approves
them in the review dialog. Approval creates transactions in one financial database commit, then sends
the confirmed merchant/category/type/description values to the three isolated learning stores.

OCR is local and requires the `tesseract` executable. Install Tesseract OCR separately and include the
`eng`, `swe`, and `nor` language data for best results. If the executable is not on `PATH`, set
`TESSERACT_COMMAND` in `.env` to its full path. `TESSERACT_LANGUAGES` defaults to `eng+swe+nor`; the
parser falls back to English if the Scandinavian language packs are unavailable. Screenshots are
limited to PNG, JPEG, or WebP files up to 15 MB and are stored below `uploads/imports/`, which is
ignored by Git.

The parser inverts dark screenshots, enlarges and sharpens text, runs table and sparse-text OCR passes,
then groups columns into rows using their image coordinates. It supports both merchant-first tables and
compact date-first Nordic views. For compact views, a heading such as `Juli 2026` or `April 2026`
supplies the explicit year for rows such as `18. juli` or the abbreviated `29. apr.`. If the heading is cropped, the importer reuses the year from the
most recent dated screenshot import for that same account, then falls back to the account's most
recently created transaction. It never guesses from the current calendar. Amount selection prefers
the selected account's currency over foreign conversion annotations; every draft is forced to the
account currency while the foreign amount remains in raw OCR text. This preserves left-column
merchants, signed outgoing amounts, unsigned positive incoming amounts, and thin minus signs that OCR
occasionally omits. It preserves the raw OCR text and signed source amount,
reports per-row confidence, and flags explainable possible duplicates. Category
prediction uses the existing category model first. The separate type model then combines amount sign,
merchant/full-word signals, low-weight amount magnitude, and the predicted category. If OCR did not
produce a description, a third model suggests one from previous approved descriptions. Its scorer
compares each matching signal's description rate with that description's overall baseline rate, so a
broad correlation such as `expense -> Mat` contributes little unless it is genuinely more specific
than the model-wide bias. Merchant/category/amount interactions carry more weight than isolated type,
category, or amount signals. Exact merchant-token interactions also carry lower-weight evidence, so
a shared brand word such as `ICA` can connect differently named branches without treating a common
word as strongly as the complete merchant phrase. Low-confidence results are withheld. Expenses, income, and
reimbursements are
stored as positive magnitudes after review; savings and transfers retain the reviewed sign.

The manual-entry form requests suggestions one second after merchant, description, amount, account,
currency, or transaction type changes. Saving a categorized transaction records a learning event and
updates weighted whole-phrase, single-word, combined-text, and low-weight amount-band connections.
Suggestions are advisory and must
still be selected or confirmed by the user.

Settings → Learning model opens an interactive, localized explorer. Its graph connects learned
signals to prediction outputs. Switch it among category, transaction-type, and description models;
each selected word, phrase, sign, category, or amount band shows its relative evidence distribution.
The description view also contains a prediction laboratory. It sends merchant, amount, currency,
category, and type to the real read-only prediction endpoint and displays candidate scores plus every
conditional rate, baseline, reliability, similarity, and weighted contribution used in the result.

The route handler receives the
HTTP request, the transaction service enforces financial rules, and the repository performs the
database operation. Transfers are kept as transactions but can be excluded from later spending
and income summaries.

### Frontend

```text
cd frontend
npm install
npm run dev
```

The frontend is available at `http://localhost:5173`. In development, Vite proxies `/api` and
`/health` requests to `http://localhost:8000`, so start the backend in a second terminal first.
The frontend uses React Router for page URLs and TanStack Query for loading, caching, and refreshing
backend data. The current UI includes account setup and manual transaction create/list/edit/delete.
Frontend styling is powered by Tailwind CSS through the Vite plugin.

The Transactions page has two views: Month shows transactions for one selected month, while Overview
shows derived balances for each account and an expandable month → account → category activity view.
Each account/month displays expenses, income, reimbursements, signed savings, signed transfers, and total.
Transfers are included in the total and account balances using their signed amount. A positive transfer increases
the balance represented by that account and a negative transfer decreases it. Savings and transfers are signed:
positive savings means putting funds into savings, while negative savings means taking funds out. Account balances
are currently derived from recorded transactions because no opening balance
has been entered yet.

Accounts can be edited from the Accounts page. Existing transaction currencies are protected, so an
account with transaction history cannot be switched from SEK to NOK (or another currency).
Accounts can also be deleted after confirmation; linked transactions and their local attachments are
removed with the account. Categories can be created, edited, and deleted from Settings; deleting a
category leaves transactions intact but makes them uncategorized.

The Month view uses a navigable month picker with older/newer controls and a history menu. The table
header also contains an Add transaction action for the selected month.
Transactions can have one local file/image attachment, limited to 10 MB.
Leave `VITE_API_BASE_URL` unset for the proxy, or set it in `.env` when connecting to another backend origin.

Run frontend checks with:

```text
npm run lint
npm run typecheck
npm run build
```

### Running tests and viewing coverage

Run frontend tests from `frontend/`:

```powershell
npm test
npm run test:coverage
```

The coverage command prints a summary in the terminal and creates an HTML report at
`frontend/coverage/index.html`; open that file in a browser to inspect files and uncovered lines.

Run backend tests from `backend/`:

```powershell
python -m pytest
python -m pytest --cov=app --cov-report=term-missing --cov-report=html
```

The backend HTML report is created at `backend/htmlcov/index.html`. The automated tests use an
isolated in-memory SQLite database, so they do not modify your application database.

No real financial data, exports, screenshots, databases, secrets, or uploaded media belong in this repository.
