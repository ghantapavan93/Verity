<#
.SYNOPSIS
  Register the two supervisors as Scheduled Tasks that start at logon, and start them now.

.DESCRIPTION
  One task per server ("Verity API", "Verity Web"), running deploy/supervise.ps1 under the current user at logon,
  hidden, with no time limit, on battery or not. `-Build` first builds the interface for the public origin, into
  .next-staging, swapped in once the old servers have stopped (.next-previous keeps the last one). Servers
  already running are stopped first (deploy/down.ps1) and their supervisors waited out: a task whose instance is still
  running ignores a new start, and on 2026-10-09 the previous release kept serving over a new build.
  `-Uninstall` writes the stop files, stops both servers and removes the tasks. The connector is already a Windows
  service (cloudflared) and is not touched. The laptop must stay logged in for logon tasks to run.
#>
param(
  [string]$Origin = "https://ivo.pavankg.dev",
  # The run the first screen offers as a finished review (docs/DEMO-PROOF.md); empty means the latest complete run.
  [string]$ProofRun = "e5a20e2283e8416e",
  # A public demo's own store (deploy/README.md): set it, and build with -ProofRun "" (the owner's proof run is not in it).
  [string]$PublicDataDir = "",
  [switch]$Build,
  [switch]$Uninstall
)
$ErrorActionPreference = "Stop"
# A public store never holds the owner's proof run, so -PublicDataDir implies an empty -ProofRun. An empty argument is
# dropped by `powershell -File`, which made the documented command fail (2026-10-09).
if ($PublicDataDir -and -not $PSBoundParameters.ContainsKey("ProofRun")) { $ProofRun = "" }
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$logs = Join-Path $root "backend\data\logs\deploy"
$supervise = Join-Path $root "deploy\supervise.ps1"
$tasks = @{ api = "Verity API"; web = "Verity Web" }

if ($Uninstall) {
  & (Join-Path $root "deploy\down.ps1")
  foreach ($name in $tasks.Values) { Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue }
  Write-Host "supervision removed"
  exit 0
}

# The interface is built beside the one that serves (.next-staging) and swapped in only after the running servers have
# stopped: a build into .next itself replaced files under a running `next start`, and a failed one left a half-written
# .next for the next restart to serve (security workstream, 2026-10-09). A failed build changes nothing that serves.
$staging = Join-Path $root ".next-staging"
if ($Build) {
  $env:NEXT_PUBLIC_API_URL = $Origin
  $env:NEXT_PUBLIC_PROOF_RUN = $ProofRun
  $env:NEXT_PUBLIC_BUILD_SHA = (git -C $root rev-parse HEAD).Trim()  # the commit this build is made from, shown on the Runs surface
  $env:NEXT_DIST_DIR = ".next-staging"
  Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue
  # Next writes the build directory's type paths into tsconfig.json; the file is put back as it was.
  $tsconfig = Join-Path $root "tsconfig.json"
  $tsconfigBytes = [System.IO.File]::ReadAllBytes($tsconfig)
  Push-Location $root
  try {
    & npm run build 2>&1 | Tee-Object -FilePath (Join-Path $logs "build-$((Get-Date).ToString('yyyyMMdd-HHmmss')).log") | Select-Object -Last 2
    if ($LASTEXITCODE -ne 0) {
      Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue
      throw "npm run build failed; the release that serves was not touched"
    }
  } finally {
    [System.IO.File]::WriteAllBytes($tsconfig, $tsconfigBytes)
    Remove-Item Env:NEXT_DIST_DIR -ErrorAction SilentlyContinue
    Pop-Location
  }
}

New-Item -ItemType Directory -Force $logs | Out-Null

# The release being installed is the one that serves: stop what runs now, and wait until each task's instance has
# ended, or Start-ScheduledTask below is ignored (-MultipleInstances IgnoreNew) and the old processes keep serving.
$running = @($tasks.Values | Where-Object { (Get-ScheduledTask -TaskName $_ -ErrorAction SilentlyContinue).State -eq "Running" })
if ($running.Count -gt 0) {
  & (Join-Path $root "deploy\down.ps1")
  $until = (Get-Date).AddSeconds(60)
  while ((Get-Date) -lt $until -and @($running | Where-Object { (Get-ScheduledTask -TaskName $_).State -eq "Running" }).Count -gt 0) { Start-Sleep -Seconds 2 }
  $still = @($running | Where-Object { (Get-ScheduledTask -TaskName $_).State -eq "Running" })
  if ($still.Count -gt 0) { throw "still running after the stop: $($still -join ', '); nothing was restarted" }
}
if ($Build) {
  # Nothing serves now: the staged build becomes .next, and the one it replaces is kept as .next-previous for a rollback.
  $live = Join-Path $root ".next"
  $previous = Join-Path $root ".next-previous"
  Remove-Item $previous -Recurse -Force -ErrorAction SilentlyContinue
  if (Test-Path $live) { Rename-Item $live ".next-previous" }
  Rename-Item $staging ".next"
}
$publicArg = if ($PublicDataDir) { " -PublicDataDir `"$PublicDataDir`"" } else { "" }
foreach ($name in $tasks.Keys) {
  Remove-Item (Join-Path $logs "$name.stop") -Force -ErrorAction SilentlyContinue
  $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$supervise`" -Name $name -Origin $Origin$publicArg"
  $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
  # No execution time limit (the default of three days would end a healthy supervisor); battery makes no difference.
  $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
  Register-ScheduledTask -TaskName $tasks[$name] -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
  Start-ScheduledTask -TaskName $tasks[$name]
  Write-Host "task '$($tasks[$name])' registered at logon and started"
}

$deadline = (Get-Date).AddSeconds(90)
$api = $false; $web = $false
while ((Get-Date) -lt $deadline -and -not ($api -and $web)) {
  Start-Sleep -Seconds 3
  try { $api = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 http://127.0.0.1:8000/api/health).StatusCode -eq 200 } catch { $api = $false }
  try { $web = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 http://127.0.0.1:3900/).StatusCode -eq 200 } catch { $web = $false }
}
Write-Host ("API answering: {0}; interface answering: {1}; supervisor logs under {2}" -f $api, $web, $logs)
if (-not ($api -and $web)) { exit 1 }
