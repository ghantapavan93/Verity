<#
.SYNOPSIS
  Stop the published stack on purpose: tell the supervisors not to restart, then stop the servers.

.DESCRIPTION
  Writes a stop file per supervisor (deploy/supervise.ps1 reads it and exits instead of restarting), stops the
  server each supervisor recorded in its pid file, and still honours the pids.json that deploy/up.ps1 writes for
  the unsupervised local mode. deploy/install-supervision.ps1 removes the stop files when it starts the stack again.
#>
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$logs = Join-Path $root "backend\data\logs\deploy"
New-Item -ItemType Directory -Force $logs | Out-Null

foreach ($name in "api", "web") {
  Set-Content -Path (Join-Path $logs "$name.stop") -Value ("stopped on purpose at " + (Get-Date).ToString("o")) -Encoding utf8
  $pidFile = Join-Path $logs "$name.pid"
  if (Test-Path $pidFile) {
    $id = [int](Get-Content $pidFile -Raw).Trim()
    if (Get-Process -Id $id -ErrorAction SilentlyContinue) {
      & taskkill.exe /PID $id /T /F | Out-Null
      Write-Host "stopped supervised $name (pid $id); its supervisor exits on the stop file"
    } else {
      Write-Host "supervised $name (pid $id) was not running"
    }
  }
}

$pidsFile = Join-Path $logs "pids.json"
if (Test-Path $pidsFile) {
  $pids = Get-Content $pidsFile -Raw | ConvertFrom-Json
  foreach ($name in "tunnel", "web", "api") {
    $id = $pids.$name
    if ($null -eq $id) { continue }
    if (Get-Process -Id $id -ErrorAction SilentlyContinue) {
      # `npm run start` and `next start` are a tree; stop the children with the parent.
      & taskkill.exe /PID $id /T /F | Out-Null
      Write-Host "stopped $name (pid $id)"
    } else {
      Write-Host "$name (pid $id) was not running"
    }
  }
  Remove-Item $pidsFile -Force -Confirm:$false
}
