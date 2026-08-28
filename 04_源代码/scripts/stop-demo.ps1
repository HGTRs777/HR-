$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RuntimeRoot = Join-Path $ProjectRoot '.runtime'
$StatePath = Join-Path $RuntimeRoot 'demo-processes.json'

if (-not (Test-Path -LiteralPath $StatePath)) {
    Write-Host 'No recorded demo processes were found.'
    exit 0
}

$State = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
foreach ($Name in 'backend', 'frontend') {
    $Record = $State.$Name
    if ($null -eq $Record) { continue }
    $ProcessItem = Get-Process -Id ([int]$Record.pid) -ErrorAction SilentlyContinue
    if ($null -eq $ProcessItem) { continue }
    if ($Record.started_at -is [DateTime]) {
        $RecordedStart = $Record.started_at.ToUniversalTime()
    } else {
        $RecordedStart = [DateTimeOffset]::Parse([string]$Record.started_at).UtcDateTime
    }
    $ActualStart = $ProcessItem.StartTime.ToUniversalTime()
    if ([Math]::Abs(($ActualStart - $RecordedStart).TotalSeconds) -gt 2) {
        throw "PID $($Record.pid) was reused; refusing to stop an unrelated process."
    }
    Stop-Process -Id $ProcessItem.Id -Force
    Write-Host "Stopped $Name process $($ProcessItem.Id)."
}
Remove-Item -LiteralPath $StatePath -Force
