$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendRoot = Join-Path $ProjectRoot 'backend'
$FrontendRoot = Join-Path $ProjectRoot 'frontend'
$PythonPath = Join-Path $BackendRoot '.venv\Scripts\python.exe'

Set-Location -LiteralPath $BackendRoot
& $PythonPath -m pytest
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $PythonPath -m pip check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $PythonPath -m flask --app run.py db current
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $PythonPath -m flask --app run.py db check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Set-Location -LiteralPath $FrontendRoot
npm run typecheck
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
npm run test:run
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
npm run build
exit $LASTEXITCODE
