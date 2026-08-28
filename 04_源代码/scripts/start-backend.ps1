$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendRoot = Join-Path $ProjectRoot 'backend'
$PythonPath = Join-Path $BackendRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $PythonPath)) {
    throw "Backend virtual environment not found: $PythonPath"
}

Set-Location -LiteralPath $BackendRoot
& $PythonPath 'run.py'

