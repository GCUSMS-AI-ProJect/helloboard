# Windows: install locally; an optional logon task runs as the current user.
[CmdletBinding()]
param([switch]$AutoStart, [ValidateRange(1,65535)][int]$Port = 8090)
$ErrorActionPreference = 'Stop'
$boardRoot = $PSScriptRoot
if ($env:OS -ne 'Windows_NT') { throw 'Use install.sh on Linux.' }
$boardPython = Join-Path $boardRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $boardPython)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv (Join-Path $boardRoot '.venv')
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv (Join-Path $boardRoot '.venv')
    } else { throw 'Install Python 3.10 or later first.' }
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}
& $boardPython -c 'import sys; assert sys.version_info >= (3, 10)'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.10 or later is required.' }
& $boardPython -m pip install -r (Join-Path $boardRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $boardPython -c 'import flask, waitress, yaml, psutil; from host_platform import identity; print(identity())'
if ($LASTEXITCODE -ne 0) { throw 'Startup dependency check failed.' }
if ($AutoStart) {
    $boardIdentity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $boardAction = New-ScheduledTaskAction -Execute $boardPython -Argument ('"{0}" --port {1} --dashboard-only' -f (Join-Path $boardRoot 'wifi.py'), $Port) -WorkingDirectory $boardRoot
    $boardTrigger = New-ScheduledTaskTrigger -AtLogOn -User $boardIdentity
    $boardPrincipal = New-ScheduledTaskPrincipal -UserId $boardIdentity -LogonType Interactive -RunLevel Limited
    $boardSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName 'HelloBoard' -Action $boardAction -Trigger $boardTrigger -Principal $boardPrincipal -Settings $boardSettings -Description 'HelloBoard system dashboard' -Force | Out-Null
    Write-Host 'HelloBoard will start when this Windows account signs in.'
}
Write-Host ('Installed. Run: .\start.ps1 -Port {0}' -f $Port)
