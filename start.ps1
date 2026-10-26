[CmdletBinding()]
param([ValidateRange(1,65535)][int]$Port = 8090)
$ErrorActionPreference = 'Stop'
$boardPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $boardPython)) { throw 'Run .\install.ps1 first.' }
& $boardPython (Join-Path $PSScriptRoot 'wifi.py') --port $Port --dashboard-only
exit $LASTEXITCODE
