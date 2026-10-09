<#
.SYNOPSIS
  Keep one server of the published stack running: start it, wait for it to exit, write what happened, start it again.

.DESCRIPTION
  One supervisor per server (`-Name api` or `-Name web`), started by a Scheduled Task at logon
  (deploy/install-supervision.ps1) or by hand. The server's stdout and stderr go to a stamped file per start under
  backend/data/logs/deploy; every start, exit (with its code and how long the server ran) and restart delay goes to
  <name>.supervisor.log. A server that exits is started again after a delay that doubles from 5 s to 60 s while it
  keeps dying within a minute, and falls back to 5 s once it has run for a minute. A stop file
  (<name>.stop, written by deploy/down.ps1) ends the supervisor instead of restarting.

  On 2026-10-01 the API process ended silently at 02:37 with no log line and no event in Windows' logs; this is the
  smallest thing that turns such an exit into a recorded restart. Deployment only: nothing in the application changes.
#>
param(
  [Parameter(Mandatory = $true)][ValidateSet("api", "web")][string]$Name,
  [string]$Origin = "https://ivo.pavankg.dev",
  [int]$Port = 0,
  # A public demo: every visitor gets a workspace of their own, served from this store, never the owner's (backend/data).
  [string]$PublicDataDir = "",
  [string]$Tag = ""
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$backend = Join-Path $root "backend"
$logs = Join-Path $backend "data\logs\deploy"
New-Item -ItemType Directory -Force $logs | Out-Null
if (-not $Tag) { $Tag = $Name }
if ($Port -eq 0) { $Port = if ($Name -eq "api") { 8000 } else { 3900 } }
$stopFile = Join-Path $logs "$Tag.stop"
$pidFile = Join-Path $logs "$Tag.pid"
$supervisorLog = Join-Path $logs "$Tag.supervisor.log"

function Write-Line([string]$message) {
  Add-Content -Path $supervisorLog -Value ("{0} {1}" -f (Get-Date).ToString("o"), $message) -Encoding utf8
}

if (Test-Path $stopFile) { Write-Line "supervisor not started: stop file present ($stopFile); remove it to allow restarts"; exit 0 }
Write-Line "supervisor started for $Name on port $Port (pid $PID)"

$backoff = 5
while ($true) {
  if (Test-Path $stopFile) { Write-Line "stop file present; supervisor exiting"; break }
  $stamp = (Get-Date).ToString("yyyyMMdd-HHmmss")
  $out = Join-Path $logs "$Tag.$stamp.out.log"
  $err = Join-Path $logs "$Tag.$stamp.err.log"
  if ($Name -eq "api") {
    $env:WORKBENCH_PROVIDER = "ollama"
    $env:WORKBENCH_MODEL = "qwen3:8b"
    $env:WORKBENCH_RETRIEVAL = "bm25"
    $env:WORKBENCH_RETRIEVAL_K = "6"
    $env:WORKBENCH_PROMPT_VERSION = "answer-v2"
    $env:WORKBENCH_CORS_ORIGINS = $Origin
    $env:WORKBENCH_APP_URL = $Origin
    # The gate (backend/app/api/access.py): on when a secret has been made (backend/scripts/access.py secret). The secret
    # and the list of revoked readers live under backend/data, outside the repository, and are read at every start.
    $secretFile = Join-Path $backend "data\access.secret"
    $revokedFile = Join-Path $backend "data\access.revoked"
    $env:WORKBENCH_ACCESS_SECRET = if (Test-Path $secretFile) { (Get-Content $secretFile -Raw).Trim() } else { "" }
    # This API is reachable from the internet through the tunnel: it must never run open. Without a secret of 32+
    # characters the API refuses to start, and the supervisor keeps retrying on its backoff until one is made.
    $env:WORKBENCH_ACCESS_REQUIRED = "1"
    if ($PublicDataDir) {
      # The public store, anonymous sessions on, and a ceiling on the model's day (deploy/README.md, public demo).
      $env:WORKBENCH_DATA_DIR = $PublicDataDir
      $env:WORKBENCH_ANONYMOUS_SESSIONS = "1"
      $env:WORKBENCH_MAX_RUNS_PER_DAY = "200"
    } else {
      Remove-Item Env:WORKBENCH_DATA_DIR, Env:WORKBENCH_ANONYMOUS_SESSIONS, Env:WORKBENCH_MAX_RUNS_PER_DAY -ErrorAction SilentlyContinue
    }
    if ($env:WORKBENCH_ACCESS_SECRET.Length -lt 32) { Write-Line "no access secret at ${secretFile}: the API will refuse to start (WORKBENCH_ACCESS_REQUIRED=1)" }
    $env:WORKBENCH_ACCESS_REVOKED = if (Test-Path $revokedFile) { ((Get-Content $revokedFile) | Where-Object { $_.Trim() } | ForEach-Object { $_.Trim() }) -join "," } else { "" }
    $process = Start-Process -FilePath (Join-Path $backend ".venv\Scripts\python.exe") `
      -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port" `
      -WorkingDirectory $backend -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden -PassThru
  } else {
    # `next start` itself, not `npm run start`: one process, so its exit is the server's exit and its pid is the server's.
    # Loopback only: the tunnel is the only client; before 2026-10-01 the interface also listened on the LAN address.
    $next = Join-Path $root "node_modules\next\dist\bin\next"
    $process = Start-Process -FilePath "node" `
      -ArgumentList "`"$next`"", "start", "-H", "127.0.0.1", "-p", "$Port" `
      -WorkingDirectory $root -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden -PassThru
  }
  $null = $process.Handle  # cache the handle now, or Windows PowerShell cannot read the exit code after the exit
  Set-Content -Path $pidFile -Value $process.Id -Encoding ascii
  Write-Line "started $Name pid $($process.Id) (output $Tag.$stamp.out.log)"
  $began = Get-Date
  $process.WaitForExit()
  $ran = [int]((Get-Date) - $began).TotalSeconds
  Write-Line "exited $Name pid $($process.Id) code $($process.ExitCode) after $ran s"
  Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
  if (Test-Path $stopFile) { Write-Line "stop file present; not restarting"; break }
  Write-Line "restarting $Name in $backoff s"
  Start-Sleep -Seconds $backoff
  # Dying within a minute of starting doubles the wait, up to a minute; a run of a minute or more resets it.
  $backoff = if ($ran -lt 60) { [Math]::Min(60, $backoff * 2) } else { 5 }
}
