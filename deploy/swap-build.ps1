<#
.SYNOPSIS
  Put a staged interface build in place of the live one, or restore a live build a crash left missing.

.DESCRIPTION
  The interface is built into .next-staging while the old release serves (deploy/install-supervision.ps1). With the
  servers stopped, -Swap makes it .next and keeps the build it replaces as .next-previous. A build is whole when its
  folder holds BUILD_ID, which Next writes last; only a whole build is ever put in place.

  A swap that fails between its two renames (a folder locked by a scanner or an open handle) puts the replaced build
  back, so the site restarts on the release it had, and the failure is raised. -Recover, run by deploy/supervise.ps1
  before every start of the interface, finishes or undoes a swap a crash interrupted: if .next is missing it takes a
  whole .next-staging, else a whole .next-previous. Rehearsed 2026-10-09 (deploy/README.md).
#>
param(
  [Parameter(Mandatory = $true)][string]$Root,
  [switch]$Swap,
  [switch]$Recover
)
$ErrorActionPreference = "Stop"
$live = Join-Path $Root ".next"
$staging = Join-Path $Root ".next-staging"
$previous = Join-Path $Root ".next-previous"

function Test-Whole([string]$folder) {
  return (Test-Path (Join-Path $folder "BUILD_ID"))
}

if ($Recover) {
  if (Test-Whole $live) { exit 0 }
  foreach ($candidate in @($staging, $previous)) {
    if (Test-Whole $candidate) {
      if (Test-Path $live) { Remove-Item $live -Recurse -Force }  # a partial .next, never served
      Rename-Item $candidate ".next"
      Write-Host "recovered .next from $(Split-Path $candidate -Leaf)"
      exit 0
    }
  }
  Write-Host "no whole build to recover: .next stays as it is"
  exit 0
}

if ($Swap) {
  if (-not (Test-Whole $staging)) { throw "no whole staged build at $staging (BUILD_ID missing); nothing was swapped" }
  $stagedId = (Get-Content (Join-Path $staging "BUILD_ID") -Raw).Trim()
  # Clear the slot first, and stop if it will not clear: nothing has moved yet.
  if (Test-Path $previous) { Remove-Item $previous -Recurse -Force }
  if (Test-Path $previous) { throw ".next-previous could not be removed; nothing was swapped" }
  $moved = $false
  try {
    if (Test-Path $live) { Rename-Item $live ".next-previous"; $moved = $true }
    Rename-Item $staging ".next"
  } catch {
    if ($moved -and -not (Test-Path $live)) { Rename-Item $previous ".next" }  # the site restarts on the build it had
    throw "the swap failed and the previous build was put back: $($_.Exception.Message)"
  }
  $liveId = (Get-Content (Join-Path $live "BUILD_ID") -Raw).Trim()
  if ($liveId -ne $stagedId) { throw "after the swap .next holds build $liveId, not the staged $stagedId" }
  Write-Host "swapped in build $liveId; the replaced build is .next-previous"
  exit 0
}

throw "pass -Swap or -Recover"
