param(
    [switch]$SkipDependencyInstall,
    [switch]$SkipIndexBuild
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendRoot = Join-Path $ProjectRoot 'backend'
$FrontendRoot = Join-Path $ProjectRoot 'frontend'
$PythonPath = Join-Path $BackendRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $PythonPath)) {
    throw "Backend virtual environment not found: $PythonPath. Create it with: python -m venv backend\.venv"
}

if (-not (Test-Path -LiteralPath (Join-Path $BackendRoot '.env'))) {
    Copy-Item -LiteralPath (Join-Path $BackendRoot '.env.example') -Destination (Join-Path $BackendRoot '.env')
    Write-Host 'Created backend/.env. Replace SECRET_KEY and optionally configure DEEPSEEK_API_KEY.'
}
if (-not (Test-Path -LiteralPath (Join-Path $FrontendRoot '.env'))) {
    Copy-Item -LiteralPath (Join-Path $FrontendRoot '.env.example') -Destination (Join-Path $FrontendRoot '.env')
}

if (-not $SkipDependencyInstall) {
    Push-Location $BackendRoot
    try { & $PythonPath -m pip install -r requirements-dev.txt } finally { Pop-Location }
    Push-Location $FrontendRoot
    try { npm install } finally { Pop-Location }
}

Push-Location $BackendRoot
try {
    & $PythonPath -m flask --app run.py db upgrade
    & $PythonPath -m flask --app run.py seed-policies
    & $PythonPath -m flask --app run.py seed-demo-data
    if (-not $SkipIndexBuild) { & $PythonPath -m flask --app run.py build-index }
} finally {
    Pop-Location
}

Push-Location $FrontendRoot
try { npm run build } finally { Pop-Location }

Write-Host 'Demo setup completed. Run scripts\start-demo.ps1 to start both services.'
