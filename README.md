# Life Budget

Life Budget is a private, local-first personal finance application for manually
tracking accounts and transactions in SEK and NOK. It runs on your own computer:
financial records, uploaded files, screenshots, OCR, and learning-model data are
not sent to an external service.

## Content

- Accounts, categories, and localized English/Swedish category names
- Expense, income, reimbursement, signed savings, and signed transfer entries
- Monthly account/category summaries and derived account balances
- Local transaction attachments
- Screenshot import with local Tesseract OCR and review-before-save
- Explainable category, transaction-type, and description suggestions
- Interactive learning-model explorer

The initial currency catalog contains SEK and NOK. Additional currencies can be
added, but the application never converts or combines different currencies.

## Quick development setup

Requirements:

- Python 3.11 or newer
- Node.js with npm
- Tesseract OCR with `eng`, `swe`, and `nor` language data for screenshot imports

The easiest first-time setup is:

```powershell
.\setup-life-budget.cmd
```

This creates `backend\.venv`, installs backend/frontend dependencies, and creates
`.env` from `.env.example`. It does not activate the environment because the
project scripts call the virtual-environment interpreter directly.

For manual setup, use PowerShell:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
alembic upgrade head
alembic -c alembic_learning.ini upgrade head
alembic -c alembic_type_learning.ini upgrade head
alembic -c alembic_description_learning.ini upgrade head
uvicorn app.main:app --reload
```

In a second PowerShell window:

```powershell
cd frontend
npm ci
npm run dev
```

Open <http://localhost:5173>. API documentation is available at
<http://127.0.0.1:8000/docs>.

See [Development](docs/development.md) for configuration, migrations, testing,
coverage, and troubleshooting.

## Normal local production use

After completing the development installation once, start the built application
from the repository root:

```powershell
.\scripts\start-production.ps1
```

Or double-click/run:

```powershell
.\start-life-budget.cmd
```

The script uses the existing development data directory by default:

```text
backend\\
  life_budget.db
  life_budget_learning.db
  life_budget_type_learning.db
  life_budget_description_learning.db
  uploads\\
```

The script:

1. Creates the development data directories if needed.
2. Runs all four database migration histories.
3. Builds the frontend.
4. Serves the frontend and API together at <http://127.0.0.1:8000>.

It intentionally binds only to localhost because the application has no user
authentication. Read [Production and finalization](docs/production.md) before
moving existing data or relying on the app for daily use.

## Project structure

```text
backend/   FastAPI, SQLAlchemy, Alembic, OCR, and prediction services
frontend/  React, TypeScript, Vite, TanStack Query, and Tailwind CSS
docs/      Architecture and operational documentation
scripts/   Local production launch scripts
```

## Quality checks

```powershell
# Backend
cd backend
python -m pytest
ruff check .
ruff format --check .

# Frontend
cd frontend
npm test
npm run typecheck
npm run build
```

Tests use disposable databases and do not modify your financial or learning data.

## Documentation

- [Architecture and data flow](docs/architecture.md)
- [Development, migrations, and tests](docs/development.md)
- [Production use, backups, updates, and finalization](docs/production.md)
- [Screenshot imports and learning models](docs/imports-and-learning.md)

## Current limitations

- Single local user; no authentication or safe network sharing yet
- No bank connection, automatic synchronization, or exchange-rate conversion
- Account balances are derived from recorded transactions; opening balances are
  not modeled yet
- Screenshot OCR is heuristic and always requires review
- Learning corrections are additive; editing or deleting a historical
  transaction does not yet retract its previous learning event
- Large transaction histories still need API pagination and server-side summary
  endpoints

Never commit databases, screenshots, uploads, exports, `.env` files, or other
personal financial data.
