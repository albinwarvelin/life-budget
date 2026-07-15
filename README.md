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
uvicorn app.main:app --reload
```

Run backend checks with:

```text
python -m pytest
ruff check .
ruff format --check .
```

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
