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

The default database is SQLite at `backend/life_budget.db`. Run `alembic upgrade head` from
`backend/` after creating the virtual environment and whenever new migrations are added.
Use `alembic current` to inspect the applied revision and `alembic history` to inspect available revisions.
The initial migration seeds only NOK and SEK. Add EUR, USD, or another currency explicitly through
`POST /api/v1/currencies`; it will then become available for accounts and transactions.

### Frontend

```text
cd frontend
npm install
npm run dev
```

Run frontend checks with:

```text
npm run lint
npm run typecheck
npm run build
```

No real financial data, exports, screenshots, databases, secrets, or uploaded media belong in this repository.
