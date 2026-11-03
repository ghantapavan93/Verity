<#
.SYNOPSIS
  Wait until nothing listens on the servers' ports; exit 1, naming each holder, if something still does.

.DESCRIPTION
  deploy/install-supervision.ps1 runs this after deploy/down.ps1 and before it swaps the build or starts a server. On
  2026-11-02 a reboot left servers that no supervisor recorded: the stop step passed them by, the new servers could not
  bind and exited, and the old ones served on, the interface hanging over a swapped build and the API on the previous
  release, while the installer's health check, answered by the old servers, reported success. A port still held here
  means nothing new is started and the build that serves is not touched.
#>
param(
  [int[]]$Ports = @(8000, 3900),
  [int]$Seconds = 30
)
$ErrorActionPreference = "Stop"

function Get-Holders([int[]]$ports) {
  foreach ($port in $ports) {
    foreach ($listen in @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)) {
      $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listen.OwningProcess)" -ErrorAction SilentlyContinue
      $command = if ($process -and $process.CommandLine) { $process.CommandLine } else { "" }
      "port $port is held by pid $($listen.OwningProcess) ($(if ($process) { $process.Name } else { 'gone' })): $($command.Substring(0, [Math]::Min(160, $command.Length)))"
    }
  }
}

# Waited on a Stopwatch, not Get-Date, which a DST change or a clock step moves (deploy/supervise.ps1, Watch-Server).
$waited = [Diagnostics.Stopwatch]::StartNew()
do {
  $held = @(Get-Holders $Ports)
  if ($held.Count -eq 0) { Write-Host "ports $($Ports -join ', ') are free"; exit 0 }
  Start-Sleep -Seconds 1
} while ($waited.Elapsed.TotalSeconds -lt $Seconds)
$held | ForEach-Object { Write-Host $_ }
exit 1
