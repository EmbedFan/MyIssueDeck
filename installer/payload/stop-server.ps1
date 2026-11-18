# Stops the MyIssueDesk server started from this folder. Called by stop-myissuedeck.vbs.
# Only processes whose command line points into this installation are stopped, so
# another IssueDeck running on the same machine (for example from the source
# checkout) is left alone.
$ErrorActionPreference = 'Continue'
$root = $PSScriptRoot
$config = Join-Path $root 'server.toml'
$pidFile = Join-Path $root 'run\server.pid'
$logDir = Join-Path $root 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stopLog = Join-Path $logDir 'start.log'

$port = [int]((Select-String -Path $config -Pattern '^\s*port\s*=\s*(\d+)' | Select-Object -First 1).Matches[0].Groups[1].Value)

$candidates = @()
if (Test-Path $pidFile) { $candidates += [int](Get-Content $pidFile) }
$candidates += @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | ForEach-Object { $_.OwningProcess })

$stopped = 0
foreach ($id in ($candidates | Sort-Object -Unique)) {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$id" -ErrorAction SilentlyContinue
    if ($proc -and $proc.CommandLine -like "*$root*") {
        taskkill /T /F /PID $id | Out-Null
        $stopped++
    }
}
Remove-Item $pidFile -ErrorAction SilentlyContinue

if ($stopped -gt 0) {
    Add-Content $stopLog "$(Get-Date -Format s) Stopped the server on port $port."
    exit 0
}
Add-Content $stopLog "$(Get-Date -Format s) No server from this installation was running on port $port."
exit 4
