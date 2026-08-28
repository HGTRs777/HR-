$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$StatePath = Join-Path (Join-Path $ProjectRoot '.runtime') 'local-5000-process.json'
if (-not (Test-Path -LiteralPath $StatePath)) { Write-Host 'No recorded local service was found.'; exit 0 }
$Record = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
$ServerProcess = Get-Process -Id ([int]$Record.pid) -ErrorAction SilentlyContinue
if ($null -ne $ServerProcess) { Stop-Process -Id $ServerProcess.Id -Force; Write-Host "Stopped process $($ServerProcess.Id)." }
[System.IO.File]::Delete($StatePath)
