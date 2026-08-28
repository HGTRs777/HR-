$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendRoot = Join-Path $ProjectRoot 'backend'
$PythonPath = Join-Path $BackendRoot '.venv\Scripts\python.exe'
$RuntimeRoot = Join-Path $ProjectRoot '.runtime'

if (Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 5000 is already in use.' }
New-Item -ItemType Directory -Path $RuntimeRoot -Force | Out-Null
$env:APP_ENV = 'production'
$env:SERVE_FRONTEND = 'true'
if (-not $env:SECRET_KEY) {
    $RandomBytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($RandomBytes)
    $env:SECRET_KEY = [Convert]::ToBase64String($RandomBytes)
}

Push-Location $BackendRoot
try { & $PythonPath -m flask --app run.py db upgrade } finally { Pop-Location }

$ServerProcess = Start-Process -FilePath $PythonPath -ArgumentList '-m','waitress','--host=127.0.0.1','--port=5000','run:app' -WorkingDirectory $BackendRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $RuntimeRoot 'local-5000.out.log') -RedirectStandardError (Join-Path $RuntimeRoot 'local-5000.err.log')
@{ pid = $ServerProcess.Id; started_at = $ServerProcess.StartTime.ToUniversalTime().ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $RuntimeRoot 'local-5000-process.json') -Encoding UTF8

$Ready = $false
for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
    try {
        $ApiStatus = (Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:5000/api/v1/health' -TimeoutSec 2).StatusCode
        $WebStatus = (Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:5000/' -TimeoutSec 2).StatusCode
        if ($ApiStatus -eq 200 -and $WebStatus -eq 200) { $Ready = $true; break }
    } catch { }
    Start-Sleep -Milliseconds 500
}
if (-not $Ready) { throw 'Service failed to start. Check .runtime/local-5000.err.log.' }
Write-Host "Website is running at http://127.0.0.1:5000/ (PID $($ServerProcess.Id))."
