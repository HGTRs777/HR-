$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$FrontendRoot = Join-Path $ProjectRoot 'frontend'

if (-not (Test-Path -LiteralPath (Join-Path $FrontendRoot 'node_modules'))) {
    throw 'Frontend dependencies are not installed. Run npm install in frontend first.'
}

Set-Location -LiteralPath $FrontendRoot
npm run dev

