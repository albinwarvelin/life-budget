# Production and finalization

Here, “production” means reliable daily local use on one Windows computer. It
does not mean internet hosting or multi-user access.

## One-time finalization checklist

1. Install Python 3.11+, Node.js/npm, and Tesseract with `eng`, `swe`, and `nor`.
2. Run `.\setup-life-budget.cmd`; it creates the virtual environment and installs both modules.
3. Run every backend/frontend quality command from the main README.
4. Decide where the existing data will live.
5. Make and verify a backup before moving data or upgrading migrations.
6. Start with the production script and test account, transaction, attachment,
   screenshot import, locale, and model-explorer workflows.
7. Create a restore drill: restore a backup into a temporary directory and open
   it with `-DataDirectory`.

## Starting the application

From the repository root:

```powershell
.\scripts\start-production.ps1
```

The default data directory is the existing development directory:

```text
backend\\
  life_budget.db
  life_budget_learning.db
  life_budget_type_learning.db
  life_budget_description_learning.db
  uploads\
```

The script runs all migrations, builds the frontend, and starts one localhost
Uvicorn worker at <http://127.0.0.1:8000>. Press Ctrl+C to stop cleanly.

Virtual-environment activation is not required. The scripts invoke
`backend/.venv/Scripts/python.exe` directly. Activation is only useful when you
want to type ad-hoc Python commands manually.

For subsequent starts, skip an unchanged frontend build:

```powershell
.\scripts\start-production.ps1 -SkipBuild
```

Validate migrations, dependencies, paths, and the build without starting a
long-running server:

```powershell
.\scripts\start-production.ps1 -CheckOnly
```

## Optional separate data directory

The normal launcher already uses `backend/`. A separate absolute directory can
still be selected explicitly:

```powershell
.\scripts\start-production.ps1 -DataDirectory C:\\Users\\albin\\LifeBudgetData
```

Do not copy only the `.db` files. Attachment and screenshot paths are stored in
the financial database, so the matching `uploads/` directory must be moved as
part of the same backup set. Relative paths in an existing database also need
to be rewritten before moving the complete installation elsewhere.

## Backups

Stop Life Budget before taking a file-level backup. Copy these as one set:

- All four `.db` files
- The complete `uploads/` directory
- Your `.env` file, if it contains required non-secret path configuration

Example while using `backend/` as the data directory:

```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$destination = Join-Path "$env:USERPROFILE\Documents\LifeBudgetBackups" $stamp
New-Item -ItemType Directory -Force $destination
Copy-Item .\backend\*.db $destination
Copy-Item .\backend\uploads (Join-Path $destination "uploads") -Recurse
```

Keep backups on another device or encrypted backup service. Periodically restore
one into a temporary directory and run:

```powershell
.\scripts\start-production.ps1 -DataDirectory C:\Temp\LifeBudgetRestore
```

## Updating

1. Stop the application.
2. Back up databases and uploads.
3. Update the source.
4. Activate the backend environment and rerun `pip install -e ".[dev]"`.
5. Run `npm ci` in `frontend/`.
6. Run tests and builds.
7. Start normally; the launcher applies pending migrations before Uvicorn.

Never remove old Alembic revisions from an installation that already has a
database.
