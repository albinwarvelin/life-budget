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
uvicorn app.main:app --reload
```

Run backend checks with:

```text
python -m pytest
ruff check .
ruff format --check .
```

The default database is SQLite at `backend/life_budget.db`. SQLite is a file, not a separate
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

The API writes to `life_budget.db` through SQLAlchemy sessions. The route handler receives the
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
Each account/month displays expenses, income, reimbursements, signed savings, and total. Transfers are
excluded from those totals. Savings are signed: positive means putting funds into savings and negative
means taking funds out. Account balances are currently derived from recorded transactions because no
opening balance has been entered yet.

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
