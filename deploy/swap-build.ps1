<#
.SYNOPSIS
  Put a staged interface build in place of the live one, or restore a live build a crash left missing.

.DESCRIPTION
  The interface is built into .next-staging while the old release serves (deploy/install-supervision.ps1). With the
  servers stopped, -Swap makes it .next and keeps the build it replaces as .next-previous. A staged build is whole only
  when it holds VERITY_COMPLETE, which the installer writes after `npm run build` exits 0 (Next's own BUILD_ID is
  written before prerendering, so a killed build can hold one; triage, 2026-10-09). Only a whole build is put in place.

  A swap that fails between its two renames (a folder locked by a scanner or an open handle) puts the replaced build
  back, so the site restarts on the release it had, and the failure is raised. -Recover, run by deploy/supervise.ps1
  before every start of the interface, finishes or undoes a swap a crash interrupted. A folder rename is atomic, so it
  acts only when .next is missing: it takes a whole .next-staging, else .next-previous (the build that served before).
  An existing .next is never touched. Rehearsed 2026-10-09 (docs/FAILURE-ENVELOPE.md).
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
  return (Test-Path (Join-Path $folder "VERITY_COMPLETE"))
}

if ($Recover) {
  if (Test-Path $live) { exit 0 }
  $served = Test-Path (Join-Path $previous "BUILD_ID")  # .next-previous is the build that served until the swap
  foreach ($candidate in @($staging, $previous)) {
    if ((Test-Whole $candidate) -or ($candidate -eq $previous -and $served)) {
      Rename-Item $candidate ".next"
      Write-Output "recovered .next from $(Split-Path $candidate -Leaf)"
      exit 0
    }
  }
  Write-Output "no whole build to recover: .next stays as it is"
  exit 0
}

if ($Swap) {
  if (-not (Test-Whole $staging)) { throw "no whole staged build at $staging (VERITY_COMPLETE missing); nothing was swapped" }
  $stagedId = (Get-Content (Join-Path $staging "BUILD_ID") -Raw).Trim()
  # Clear the slot first, and stop if it will not clear: nothing has moved yet.
  if (Test-Path $previous) { Remove-Item $previous -Recurse -Force }
  if (Test-Path $previous) { throw ".next-previous could not be removed; nothing was swapped" }
  $moved = $false
  try {
    if (Test-Path $live) { Rename-Item $live ".next-previous"; $moved = $true }
    Rename-Item $staging ".next"
  } catch {
    if ($moved -and -not (Test-Path $live)) {
      try { Rename-Item $previous ".next" }  # the site restarts on the build it had
      catch { throw "the swap failed, and putting the previous build back failed too (no .next; the supervisor recovers one at start): $($_.Exception.Message)" }
    }
    throw "the swap failed and the previous build was put back: $($_.Exception.Message)"
  }
  $liveId = (Get-Content (Join-Path $live "BUILD_ID") -Raw).Trim()
  if ($liveId -ne $stagedId) { throw "after the swap .next holds build $liveId, not the staged $stagedId" }
  Write-Output "swapped in build $liveId; the replaced build is .next-previous"
  exit 0
}

throw "pass -Swap or -Recover"
