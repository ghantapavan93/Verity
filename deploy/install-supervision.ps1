<#
.SYNOPSIS
  Register the two supervisors as Scheduled Tasks that start at logon, and start them now.

.DESCRIPTION
  One task per server ("Verity API", "Verity Web"), running deploy/supervise.ps1 under the current user at logon,
  hidden, with no time limit, on battery or not. `-Build` first builds the interface for the public origin.
  `-Uninstall` writes the stop files, stops both servers and removes the tasks. The connector is already a Windows
  service (cloudflared) and is not touched. The laptop must stay logged in for logon tasks to run.
#>
param(
  [string]$Origin = "https://ivo.pavankg.dev",
  # The run the first screen offers as a finished review (docs/DEMO-PROOF.md); empty means the latest complete run.
  [string]$ProofRun = "e5a20e2283e8416e",
  [switch]$Build,
  [switch]$Uninstall
)
$ErrorActionPreference = "Stop"
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

if ($Build) {
  $env:NEXT_PUBLIC_API_URL = $Origin
  $env:NEXT_PUBLIC_PROOF_RUN = $ProofRun
  Push-Location $root
  try {
    & npm run build 2>&1 | Tee-Object -FilePath (Join-Path $logs "build-$((Get-Date).ToString('yyyyMMdd-HHmmss')).log") | Select-Object -Last 2
    if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
  } finally { Pop-Location }
}

New-Item -ItemType Directory -Force $logs | Out-Null
foreach ($name in $tasks.Keys) {
  Remove-Item (Join-Path $logs "$name.stop") -Force -ErrorAction SilentlyContinue
  $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$supervise`" -Name $name -Origin $Origin"
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
