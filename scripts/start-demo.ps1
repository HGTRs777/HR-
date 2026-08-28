param([switch]$SkipBuild)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendRoot = Join-Path $ProjectRoot 'backend'
$FrontendRoot = Join-Path $ProjectRoot 'frontend'
$PythonPath = Join-Path $BackendRoot '.venv\Scripts\python.exe'
$NodePath = (Get-Command node.exe -ErrorAction Stop).Source
$VitePath = Join-Path $FrontendRoot 'node_modules\vite\bin\vite.js'
$RuntimeRoot = Join-Path $ProjectRoot '.runtime'
$StatePath = Join-Path $RuntimeRoot 'demo-processes.json'

if (-not (Test-Path -LiteralPath $PythonPath)) { throw "Backend virtual environment not found: $PythonPath" }
if (-not (Test-Path -LiteralPath (Join-Path $FrontendRoot 'node_modules'))) { throw 'Frontend dependencies are not installed.' }
$BackendEnvPath = Join-Path $BackendRoot '.env'
$ConfiguredSecret = $env:SECRET_KEY
if (-not $ConfiguredSecret -and (Test-Path -LiteralPath $BackendEnvPath)) {
    $SecretLine = Get-Content -LiteralPath $BackendEnvPath | Where-Object { $_ -match '^SECRET_KEY=' } | Select-Object -First 1
    if ($SecretLine) { $ConfiguredSecret = $SecretLine.Substring('SECRET_KEY='.Length).Trim() }
}
if (-not $ConfiguredSecret -or $ConfiguredSecret -in @('dev-only-change-me', 'replace-with-a-long-random-value')) {
    throw 'Set a strong SECRET_KEY in backend/.env before production demo startup.'
}
foreach ($port in 5000, 5173) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $port is already in use. Stop the existing process before starting the demo."
    }
}

New-Item -ItemType Directory -Path $RuntimeRoot -Force | Out-Null
Remove-Item -LiteralPath $StatePath -Force -ErrorAction SilentlyContinue

Push-Location $BackendRoot
try { & $PythonPath -m flask --app run.py db upgrade } finally { Pop-Location }
if (-not $SkipBuild) {
    Push-Location $FrontendRoot
    try { npm run build } finally { Pop-Location }
}
if (-not (Test-Path -LiteralPath (Join-Path $FrontendRoot 'dist\index.html'))) {
    throw 'Frontend build output is missing. Run without -SkipBuild once.'
}

$PreviousEnvironment = $env:APP_ENV
$env:APP_ENV = 'production'
$BackendProcess = $null
$FrontendProcess = $null
try {
    $BackendProcess = Start-Process -FilePath $PythonPath -ArgumentList '-m','waitress','--host=127.0.0.1','--port=5000','run:app' -WorkingDirectory $BackendRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $RuntimeRoot 'backend.out.log') -RedirectStandardError (Join-Path $RuntimeRoot 'backend.err.log')
    $FrontendProcess = Start-Process -FilePath $NodePath -ArgumentList $VitePath,'preview','--host','127.0.0.1','--port','5173','--strictPort' -WorkingDirectory $FrontendRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $RuntimeRoot 'frontend.out.log') -RedirectStandardError (Join-Path $RuntimeRoot 'frontend.err.log')

    $BackendReady = $false
    $FrontendReady = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        try { $BackendReady = (Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:5000/api/v1/health' -TimeoutSec 2).StatusCode -eq 200 } catch { $BackendReady = $false }
        try { $FrontendReady = (Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:5173/' -TimeoutSec 2).StatusCode -eq 200 } catch { $FrontendReady = $false }
        if ($BackendReady -and $FrontendReady) { break }
        Start-Sleep -Milliseconds 500
    }
    if (-not ($BackendReady -and $FrontendReady)) { throw 'Demo health check failed. Inspect .runtime/*.err.log.' }

    @{
        backend = @{ pid = $BackendProcess.Id; started_at = $BackendProcess.StartTime.ToUniversalTime().ToString('o') }
        frontend = @{ pid = $FrontendProcess.Id; started_at = $FrontendProcess.StartTime.ToUniversalTime().ToString('o') }
    } | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $StatePath -Encoding UTF8
    Write-Host 'Demo is ready: employee http://127.0.0.1:5173/ | HR http://127.0.0.1:5173/admin | API http://127.0.0.1:5000'
} catch {
    foreach ($ProcessItem in @($BackendProcess, $FrontendProcess)) {
        if ($null -ne $ProcessItem -and -not $ProcessItem.HasExited) { Stop-Process -Id $ProcessItem.Id -Force -ErrorAction SilentlyContinue }
    }
    throw
} finally {
    $env:APP_ENV = $PreviousEnvironment
}
