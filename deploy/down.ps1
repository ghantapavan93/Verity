<#
.SYNOPSIS
  Stop what deploy/up.ps1 started: the tunnel, the Next production server and the API.
#>
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$pidsFile = Join-Path $root "backend\data\logs\deploy\pids.json"
if (-not (Test-Path $pidsFile)) { Write-Host "nothing recorded as running ($pidsFile is absent)"; exit 0 }
$pids = Get-Content $pidsFile -Raw | ConvertFrom-Json
foreach ($name in "tunnel", "web", "api") {
  $id = $pids.$name
  if ($null -eq $id) { continue }
  $process = Get-Process -Id $id -ErrorAction SilentlyContinue
  if ($process) {
    # `npm run start` and `next start` are a tree; stop the children with the parent.
    & taskkill.exe /PID $id /T /F | Out-Null
    Write-Host "stopped $name (pid $id)"
  } else {
    Write-Host "$name (pid $id) was not running"
  }
}
Remove-Item $pidsFile -Force -Confirm:$false
