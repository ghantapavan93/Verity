<#
.SYNOPSIS
  Start the workbench the way it is published: the API in production settings, the Next production
  build, and the named Cloudflare Tunnel (deploy/README.md).

.DESCRIPTION
  Refuses to start if 8000 or 3900 is already in use. Writes every process's output under
  backend/data/logs/deploy/ and their ids to pids.json there, which deploy/down.ps1 reads.
  Nothing in the application changes: the API reads its settings from the environment, the
  interface bakes the API origin in at build time.

  -Local   no tunnel; the API origin is http://127.0.0.1:8000 and the app URL http://localhost:3900,
           so the production build can be checked on this machine before the tunnel exists.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File deploy\up.ps1
  powershell -ExecutionPolicy Bypass -File deploy\up.ps1 -Local
#>
param(
  [switch]$Local,
  [string]$Hostname = "ivo.pavankg.dev",
  [string]$Tunnel = "ivo-workbench"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$backend = Join-Path $root "backend"
$logs = Join-Path $backend "data\logs\deploy"
New-Item -ItemType Directory -Force $logs | Out-Null
$cloudflared = Join-Path $env:LOCALAPPDATA "Programs\cloudflared\cloudflared.exe"

foreach ($port in 8000, 3900) {
  $busy = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
  if ($busy) { throw "port $port is already in use (pid $($busy[0].OwningProcess)); run deploy\down.ps1 or stop the dev server first" }
}
if (-not $Local -and -not (Test-Path $cloudflared)) { throw "cloudflared not found at $cloudflared" }
if (-not $Local -and -not (Test-Path (Join-Path $env:USERPROFILE ".cloudflared"))) {
  throw "no ~/.cloudflared: run 'cloudflared tunnel login' and 'cloudflared tunnel create $Tunnel' first (deploy\README.md)"
}

$publicOrigin = if ($Local) { "http://localhost:3900" } else { "https://$Hostname" }
$apiOrigin = if ($Local) { "http://127.0.0.1:8000" } else { "https://$Hostname" }

# --- the API, in the settings the measurements were made with
$env:WORKBENCH_PROVIDER = "ollama"
$env:WORKBENCH_MODEL = "qwen3:8b"
$env:WORKBENCH_RETRIEVAL = "bm25"
$env:WORKBENCH_RETRIEVAL_K = "6"
$env:WORKBENCH_PROMPT_VERSION = "answer-v2"
$env:WORKBENCH_CORS_ORIGINS = if ($Local) { "http://localhost:3900,http://127.0.0.1:3900" } else { $publicOrigin }
$env:WORKBENCH_APP_URL = $publicOrigin
$api = Start-Process -FilePath (Join-Path $backend ".venv\Scripts\python.exe") `
  -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
  -WorkingDirectory $backend -WindowStyle Hidden -PassThru `
  -RedirectStandardOutput (Join-Path $logs "api.out.log") -RedirectStandardError (Join-Path $logs "api.err.log")
Write-Host "API starting (pid $($api.Id)) with WORKBENCH_APP_URL=$publicOrigin"

# --- the interface: a production build against the API origin, then the production server
$env:NEXT_PUBLIC_API_URL = $apiOrigin
Push-Location $root
try {
  & npm.cmd run build 2>&1 | Tee-Object -FilePath (Join-Path $logs "build.log") | Select-Object -Last 3
  if ($LASTEXITCODE -ne 0) { Stop-Process -Id $api.Id -Force; throw "npm run build failed (see $logs\build.log)" }
} finally { Pop-Location }
$web = Start-Process -FilePath "npm.cmd" -ArgumentList "run", "start", "--", "-p", "3900" `
  -WorkingDirectory $root -WindowStyle Hidden -PassThru `
  -RedirectStandardOutput (Join-Path $logs "web.out.log") -RedirectStandardError (Join-Path $logs "web.err.log")
Write-Host "Interface starting (pid $($web.Id)) built for NEXT_PUBLIC_API_URL=$apiOrigin"

# --- wait for both to answer
$deadline = (Get-Date).AddSeconds(90)
$apiOk = $false; $webOk = $false
while ((Get-Date) -lt $deadline -and -not ($apiOk -and $webOk)) {
  Start-Sleep -Seconds 2
  try { $apiOk = (Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8000/api/health" -TimeoutSec 5).StatusCode -eq 200 } catch { $apiOk = $false }
  try { $webOk = (Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:3900/" -TimeoutSec 5).StatusCode -eq 200 } catch { $webOk = $false }
}
if (-not ($apiOk -and $webOk)) { throw "the API ($apiOk) or the interface ($webOk) did not answer within 90 s; see $logs" }
$health = (Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8000/api/health").Content
Write-Host "API health: $health"

# --- the tunnel
$pids = @{ api = $api.Id; web = $web.Id; tunnel = $null; started = (Get-Date).ToString("o"); local = [bool]$Local }
if (-not $Local) {
  $cf = Start-Process -FilePath $cloudflared `
    -ArgumentList "tunnel", "--config", (Join-Path $root "deploy\cloudflared.yml"), "run", $Tunnel `
    -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $logs "tunnel.out.log") -RedirectStandardError (Join-Path $logs "tunnel.err.log")
  $pids.tunnel = $cf.Id
  Write-Host "Tunnel '$Tunnel' starting (pid $($cf.Id)); the public URL is https://$Hostname once DNS is routed (deploy\README.md)"
}
$pids | ConvertTo-Json | Out-File -Encoding utf8 (Join-Path $logs "pids.json")
Write-Host "Up. Logs and pids under $logs; stop with deploy\down.ps1"
