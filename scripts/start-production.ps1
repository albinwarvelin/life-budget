param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8000,
    [string]$DataDirectory = "",
    [switch]$SkipBuild,
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
$backendDirectory = Join-Path $projectRoot "backend"
$frontendDirectory = Join-Path $projectRoot "frontend"
$DataDirectory = if ([string]::IsNullOrWhiteSpace($DataDirectory)) {
    $backendDirectory
}
else {
    $DataDirectory
}
$python = Join-Path $backendDirectory ".venv\Scripts\python.exe"
$npm = Get-Command "npm.cmd" -ErrorAction SilentlyContinue

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Backend virtual environment not found. Complete the setup steps in README.md first."
}
if ($null -eq $npm) {
    throw "npm.cmd was not found. Install Node.js and restart PowerShell."
}
if (-not (Test-Path -LiteralPath (Join-Path $frontendDirectory "node_modules") -PathType Container)) {
    throw "Frontend dependencies are missing. Run 'npm ci' in the frontend directory."
}

$resolvedDataDirectory = [System.IO.Path]::GetFullPath($DataDirectory)
$databaseDirectory = $resolvedDataDirectory
$uploadDirectory = Join-Path $resolvedDataDirectory "uploads"
$null = New-Item -ItemType Directory -Force -Path $databaseDirectory
$null = New-Item -ItemType Directory -Force -Path $uploadDirectory

$legacyDatabase = Join-Path $backendDirectory "life_budget.db"
$productionDatabase = Join-Path $databaseDirectory "life_budget.db"
if (
    (Test-Path -LiteralPath $legacyDatabase -PathType Leaf) -and
    -not (Test-Path -LiteralPath $productionDatabase -PathType Leaf) -and
    $resolvedDataDirectory -ne [System.IO.Path]::GetFullPath($backendDirectory)
) {
    Write-Warning (
        "Existing development data was found in backend. This launcher is using a new " +
        "database because a custom DataDirectory was supplied. Use the default launcher " +
        "or '-DataDirectory .\backend' to use the development data."
    )
}

# SQLAlchemy SQLite URLs use forward slashes, including on Windows.
$databaseUrlDirectory = $databaseDirectory.Replace("\", "/")
$env:DATABASE_URL = "sqlite:///$databaseUrlDirectory/life_budget.db"
$env:LEARNING_DATABASE_URL = "sqlite:///$databaseUrlDirectory/life_budget_learning.db"
$env:TYPE_LEARNING_DATABASE_URL = "sqlite:///$databaseUrlDirectory/life_budget_type_learning.db"
$env:DESCRIPTION_LEARNING_DATABASE_URL = (
    "sqlite:///$databaseUrlDirectory/life_budget_description_learning.db"
)
$env:UPLOAD_DIR = $uploadDirectory

Push-Location $backendDirectory
try {
    # Upgrade every independent SQLite schema before accepting requests. A
    # failed migration stops startup instead of leaving a partly usable app.
    & $python -m alembic upgrade head
    & $python -m alembic -c alembic_learning.ini upgrade head
    & $python -m alembic -c alembic_type_learning.ini upgrade head
    & $python -m alembic -c alembic_description_learning.ini upgrade head
}
finally {
    Pop-Location
}

if (-not $SkipBuild) {
    Push-Location $frontendDirectory
    try {
        # An empty API base makes the production browser use the same Uvicorn
        # origin that serves the frontend, avoiding CORS and port duplication.
        $env:VITE_API_BASE_URL = ""
        & $npm.Source run build
    }
    finally {
        Pop-Location
    }
}

$indexPath = Join-Path $frontendDirectory "dist\index.html"
if (-not (Test-Path -LiteralPath $indexPath -PathType Leaf)) {
    throw "Frontend production build is missing. Run without -SkipBuild once."
}

$env:APP_ENV = "production"
$env:FRONTEND_ORIGIN = "http://127.0.0.1:$Port"

if ($CheckOnly) {
    Write-Host "Production migrations, data paths, dependencies, and frontend build are valid."
    return
}

Write-Host ""
Write-Host "Life Budget is starting at http://127.0.0.1:$Port"
Write-Host "Data directory: $resolvedDataDirectory"
Write-Host "Press Ctrl+C to stop it cleanly."
Write-Host ""

Push-Location $backendDirectory
try {
    # No --reload flag is used in production. One localhost worker avoids
    # SQLite write contention and is sufficient for this single-user app.
    & $python -m uvicorn app.main:app --host 127.0.0.1 --port $Port --workers 1
}
finally {
    Pop-Location
}
