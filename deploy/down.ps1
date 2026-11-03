<#
.SYNOPSIS
  Stop the published stack on purpose: tell the supervisors not to restart, then stop the servers.

.DESCRIPTION
  Writes a stop file per supervisor (deploy/supervise.ps1 reads it and exits instead of restarting), stops the
  server each supervisor recorded in its pid file, and still honours the pids.json that deploy/up.ps1 writes for
  the unsupervised local mode. Then whatever still listens on a server's port is stopped when it is this checkout's own
  server (its command line names this checkout and `uvicorn app.main:app` or `next start`), and named and left alone
  when it is anything else. deploy/install-supervision.ps1 removes the stop files when it starts the stack again.
#>
param(
  [int]$ApiPort = 8000,
  [int]$WebPort = 3900
)
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$logs = Join-Path $root "backend\data\logs\deploy"
New-Item -ItemType Directory -Force $logs | Out-Null

# A process is the one recorded only when its pid and its start time both match: Windows gives a dead server's pid to
# the next process that asks, and a record outlives its server after any end the supervisor does not see (a shutdown, a
# sign-out, an ended task). With the pid alone, this killed an unrelated process and its whole tree, and the record,
# never removed, sent every later run to the same pid (stress test, 2026-10-30, ops 6). A record with no start time
# (written before 2026-10-30) is not proof either: it is reported, never acted on. The record is removed in every case.
function Stop-Recorded([string]$name, $id, [string]$token) {
  $process = Get-Process -Id $id -ErrorAction SilentlyContinue
  if (-not $process) { Write-Host "$name (pid $id) was not running"; return }
  try { $started = "$($process.StartTime.ToFileTimeUtc())" } catch { $started = "" }
  if (-not $token -or -not $started -or $started -ne $token) {
    Write-Host "$name record is stale: pid $id is now another process; it was not stopped"
    return
  }
  # A server is a tree (`npm run start`, `next start`): its children are stopped with it.
  & taskkill.exe /PID $id /T /F | Out-Null
  Write-Host "stopped $name (pid $id)"
}

foreach ($name in "api", "web") {
  Set-Content -Path (Join-Path $logs "$name.stop") -Value ("stopped on purpose at " + (Get-Date).ToString("o")) -Encoding utf8
  $pidFile = Join-Path $logs "$name.pid"
  if (Test-Path $pidFile) {
    $id, $token = "$(Get-Content $pidFile -Raw)".Trim() -split "\s+", 2
    if ("$id" -match "^\d+$") { Stop-Recorded "supervised $name" ([int]$id) "$token" } else { Write-Host "supervised $name record is unreadable; nothing was stopped" }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
  }
}

$pidsFile = Join-Path $logs "pids.json"
if (Test-Path $pidsFile) {
  $pids = Get-Content $pidsFile -Raw | ConvertFrom-Json
  foreach ($name in "tunnel", "web", "api") {
    $entry = $pids.$name
    if ($null -eq $entry) { continue }
    if ($entry -is [System.Management.Automation.PSCustomObject]) { Stop-Recorded $name ([int]$entry.pid) "$($entry.started)" } else { Stop-Recorded $name ([int]$entry) "" }
  }
  Remove-Item $pidsFile -Force -Confirm:$false
}

# A server no record names: on 2026-11-02 Windows restarted, the supervisors restarted at logon, and the servers they
# started outlived the stop (a supervisor ended by re-registering its task leaves its servers running), held both ports
# through the next release, and served the previous one. A port's holder is stopped here only when it is this
# checkout's own server; anything else is named, and deploy/ports-free.ps1 then stops the release.
$serverCommand = 'uvicorn app\.main:app|next(\\|/)dist(\\|/)bin(\\|/)next"? start'
foreach ($held in @(@{ name = "api"; port = $ApiPort }, @{ name = "web"; port = $WebPort })) {
  foreach ($listen in @(Get-NetTCPConnection -LocalPort $held.port -State Listen -ErrorAction SilentlyContinue)) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listen.OwningProcess)" -ErrorAction SilentlyContinue
    if (-not $process) { continue }
    $command = "$($process.CommandLine)"
    if ($command.IndexOf($root, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and $command -match $serverCommand) {
      & taskkill.exe /PID $process.ProcessId /T /F | Out-Null
      Write-Host "stopped $($held.name) server holding port $($held.port) (pid $($process.ProcessId)), which no record named"
    } else {
      Write-Host "port $($held.port) is held by pid $($process.ProcessId) ($($process.Name)), not this checkout's server: it was not stopped"
    }
  }
}
