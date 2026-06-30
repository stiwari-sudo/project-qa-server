# Starts the local "pgqa" Postgres cluster on port 5544 if it isn't already up.
#
# This cluster lives at %LocalAppData%\pgqa\data and is NOT a Windows service,
# so it does not survive a reboot on its own. A scheduled task runs this script
# at logon; you can also run it by hand: `pwsh scripts/start-db.ps1`.
#
# Safe to run repeatedly: it no-ops if the port is already listening, and
# pg_ctl clears a stale postmaster.pid automatically.
$ErrorActionPreference = 'Stop'

$dataDir = Join-Path $env:LocalAppData 'pgqa\data'
$logFile = Join-Path $env:LocalAppData 'pgqa\pg_ctl.log'
$port = 5544

# Locate pg_ctl from the installed PostgreSQL (prefer the newest major version).
$pgCtl = Get-ChildItem 'C:\Program Files\PostgreSQL' -Directory -ErrorAction SilentlyContinue |
    Sort-Object { [int]($_.Name) } -Descending |
    ForEach-Object { Join-Path $_.FullName 'bin\pg_ctl.exe' } |
    Where-Object { Test-Path $_ } |
    Select-Object -First 1

if (-not $pgCtl) { throw "pg_ctl.exe not found under C:\Program Files\PostgreSQL" }

# Already listening on the port? Nothing to do.
if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
    Write-Host "pgqa already running on port $port"
    exit 0
}

Write-Host "Starting pgqa cluster ($dataDir) on port $port ..."
& $pgCtl -D "$dataDir" -l "$logFile" -o "-p $port" -w start
