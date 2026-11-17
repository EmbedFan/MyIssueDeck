# Starts the MyIssueDesk server in the background. Called by start-myissuedesk.vbs.
# Exit codes: 0 started, 2 port already in use, 3 server did not start.
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$exe = Join-Path $root '.venv\Scripts\issuedeck.exe'
$config = Join-Path $root 'server.toml'
$pidFile = Join-Path $root 'run\server.pid'
$logDir = Join-Path $root 'logs'
New-Item -ItemType Directory -Force -Path (Join-Path $root 'run'), $logDir | Out-Null
$startLog = Join-Path $logDir 'start.log'

$port = [int]((Select-String -Path $config -Pattern '^\s*port\s*=\s*(\d+)' | Select-Object -First 1).Matches[0].Groups[1].Value)

$busy = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($busy) {
    Add-Content $startLog "$(Get-Date -Format s) Port $port is already in use (PID $($busy.OwningProcess)). Not started."
    exit 2
}

$process = Start-Process -FilePath $exe -ArgumentList 'serve', '--config', 'server.toml' `
    -WorkingDirectory $root -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logDir 'server.out.log') `
    -RedirectStandardError (Join-Path $logDir 'server.err.log') -PassThru
Set-Content -Path $pidFile -Value $process.Id

$ready = $false
for ($i = 0; $i -lt 30 -and -not $ready; $i++) {
    Start-Sleep -Seconds 1
    if ($process.HasExited) { break }
    $ready = [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

if (-not $ready) {
    Add-Content $startLog "$(Get-Date -Format s) The server did not start. See logs\server.err.log."
    exit 3
}
Add-Content $startLog "$(Get-Date -Format s) Started PID $($process.Id) on port $port."
exit 0
