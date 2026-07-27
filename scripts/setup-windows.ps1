$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
$backendDirectory = Join-Path $projectRoot "backend"
$frontendDirectory = Join-Path $projectRoot "frontend"
$venvDirectory = Join-Path $backendDirectory ".venv"
$venvPython = Join-Path $venvDirectory "Scripts\python.exe"
$pythonLauncher = Get-Command "py.exe" -ErrorAction SilentlyContinue
if ($null -eq $pythonLauncher) {
    $pythonLauncher = Get-Command "python.exe" -ErrorAction SilentlyContinue
}
$npm = Get-Command "npm.cmd" -ErrorAction SilentlyContinue

if ($null -eq $pythonLauncher) {
    throw "Python 3.11 or newer was not found. Install Python and restart PowerShell."
}
if ($null -eq $npm) {
    throw "npm.cmd was not found. Install Node.js and restart PowerShell."
}

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    Push-Location $backendDirectory
    try {
        if ($pythonLauncher.Name -eq "py.exe") {
            & $pythonLauncher.Source -3 -m venv .venv
        }
        else {
            & $pythonLauncher.Source -m venv .venv
        }
    }
    finally {
        Pop-Location
    }
}

Push-Location $backendDirectory
try {
    # Calling the venv interpreter directly makes activation unnecessary and
    # ensures packages are installed into this project, not globally.
    & $venvPython -m pip install -e ".[dev]"
}
finally {
    Pop-Location
}

Push-Location $frontendDirectory
try {
    & $npm.Source ci
}
finally {
    Pop-Location
}

$rootEnv = Join-Path $projectRoot ".env"
$exampleEnv = Join-Path $projectRoot ".env.example"
if (-not (Test-Path -LiteralPath $rootEnv -PathType Leaf)) {
    Copy-Item -LiteralPath $exampleEnv -Destination $rootEnv
    Write-Host "Created .env from .env.example. Review it before using custom settings."
}

Write-Host ""
Write-Host "Setup completed. No virtual-environment activation is required."
Write-Host "Start production: .\scripts\start-production.ps1"
Write-Host "Start through the command wrapper: .\start-life-budget.cmd"
