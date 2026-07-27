# Development

## Configuration

Copy `.env.example` to `.env` only when overriding defaults. Backend settings are
loaded from `backend/.env` or the repository-root `.env`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_ENV` | `development` | Enables integrated frontend serving when set to `production` |
| `DATABASE_URL` | `sqlite:///./life_budget.db` | Financial database |
| `LEARNING_DATABASE_URL` | `sqlite:///./life_budget_learning.db` | Category learner |
| `TYPE_LEARNING_DATABASE_URL` | `sqlite:///./life_budget_type_learning.db` | Type learner |
| `DESCRIPTION_LEARNING_DATABASE_URL` | `sqlite:///./life_budget_description_learning.db` | Description learner |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | Allowed development browser origin |
| `UPLOAD_DIR` | `uploads` | Local attachments and imported screenshots |
| `TESSERACT_COMMAND` | `tesseract` | Tesseract executable or absolute path |
| `TESSERACT_LANGUAGES` | `eng+swe+nor` | OCR language packs |
| `VITE_API_BASE_URL` | empty | Optional frontend API origin |

Relative backend paths are resolved from the directory where Uvicorn starts.
Always start development commands from `backend/`. The production script uses
absolute paths instead.

## Databases and migrations

SQLite is embedded and does not need a server process. There are four independent
database files and Alembic histories:

```powershell
cd backend
alembic upgrade head
alembic -c alembic_learning.ini upgrade head
alembic -c alembic_type_learning.ini upgrade head
alembic -c alembic_description_learning.ini upgrade head
```

Inspect them with `alembic current` or the same command plus the relevant `-c`
option. New financial schema revisions belong in `backend/alembic/versions/`;
model-store revisions belong in their corresponding Alembic directories.

Do not delete migration files after a database has been created. Alembic needs
the complete revision chain to understand and upgrade older databases.

## Running development servers

Backend:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

Frontend:

```powershell
cd frontend
npm run dev
```

Vite proxies `/api` and `/health` to the backend. The UI is at
<http://localhost:5173>; OpenAPI is at <http://127.0.0.1:8000/docs>.

## Tests and coverage

Backend:

```powershell
cd backend
python -m pytest
python -m pytest --cov=app --cov-report=term-missing --cov-report=html
ruff check .
ruff format --check .
```

The HTML report is written to `backend/htmlcov/index.html`.

Frontend:

```powershell
cd frontend
npm test
npm run test:coverage
npm run typecheck
npm run build
```

The frontend HTML coverage report is written to
`frontend/coverage/index.html`.

Pytest configures all four stores and uploads under a disposable temporary
directory before importing the application. Test merchants cannot be learned by
your normal prediction databases.

## Common problems

### PowerShell blocks virtual-environment activation

You can run the executables directly without activation:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

### Tesseract is not found

Install Tesseract, restart PowerShell, or set:

```text
TESSERACT_COMMAND=C:\Program Files\Tesseract-OCR\tesseract.exe
```

### A database appears empty

Stop the server and verify the current working directory and database URLs.
Relative SQLite paths can otherwise create a second database in another folder.
