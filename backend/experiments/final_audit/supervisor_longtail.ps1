# Phase 22: the supervisor's long tail, on a second instance that cannot touch the published one:
# its own tag (audit), its own port (8020), its own data directory. The published api/web supervisors keep running.
$ErrorActionPreference = "Continue"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$logs = Join-Path $root "backend\data\logs\deploy"
$supervise = Join-Path $root "deploy\supervise.ps1"
$python = Join-Path $root "backend\.venv\Scripts\python.exe"
$data = Join-Path $env:TEMP ("verity-supervisor-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Force $data | Out-Null
$env:WORKBENCH_DATA_DIR = $data
Remove-Item (Join-Path $logs "audit.*") -Force -ErrorAction SilentlyContinue

function Health { try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec 20 http://127.0.0.1:8020/api/health).StatusCode } catch { 0 } }
function WaitHealth([int]$seconds) { $until = (Get-Date).AddSeconds($seconds); while ((Get-Date) -lt $until) { if ((Health) -eq 200) { return $true }; Start-Sleep -Milliseconds 700 }; return $false }
function Log { Get-Content (Join-Path $logs "audit.supervisor.log") -ErrorAction SilentlyContinue | ForEach-Object { "      " + ($_ -replace '^\S+ ', '') } }

"### 1. a stale pid file and an occupied port"
Set-Content (Join-Path $logs "audit.pid") -Value "999999" -Encoding ascii
$squatter = Start-Process -FilePath $python -ArgumentList "-m", "http.server", "8020", "--bind", "127.0.0.1" -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 2
$supervisor = Start-Process -FilePath "powershell.exe" -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$supervise`"", "-Name", "api", "-Port", "8020", "-Tag", "audit" -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 40
"   after 40 s with the port taken by another process:"
Log
"### 2. the port is freed: the next attempt must come up by itself"
Stop-Process -Id $squatter.Id -Force
"   healthy within 90 s: $(WaitHealth 90)"
"### 3. the server is killed: restarted"
$serverPid = [int](Get-Content (Join-Path $logs "audit.pid") -Raw).Trim()
& taskkill.exe /PID $serverPid /T /F | Out-Null
Start-Sleep -Seconds 2
"   healthy again within 60 s: $(WaitHealth 60); pid file now $((Get-Content (Join-Path $logs 'audit.pid') -Raw).Trim()) (was $serverPid)"
"### 4. the supervisor itself is killed: what is left?"
Stop-Process -Id $supervisor.Id -Force
Start-Sleep -Seconds 2
"   server still answering with no supervisor: $((Health) -eq 200)"
$serverPid = [int](Get-Content (Join-Path $logs "audit.pid") -Raw).Trim()
& taskkill.exe /PID $serverPid /T /F | Out-Null
Start-Sleep -Seconds 15
"   15 s after that server is killed, answering: $((Health) -eq 200)  (nothing restarts it: the supervisor is gone)"
"### 5. a stop file: a new supervisor refuses to start"
Set-Content (Join-Path $logs "audit.stop") -Value "stopped on purpose" -Encoding utf8
$again = Start-Process -FilePath "powershell.exe" -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$supervise`"", "-Name", "api", "-Port", "8020", "-Tag", "audit" -WindowStyle Hidden -PassThru -Wait
"   supervisor exit code with the stop file present: $($again.ExitCode); answering: $((Health) -eq 200)"
"### the audit supervisor's whole log"
Log
"### the published stack was not touched"
"   api 8000: $(try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec 20 http://127.0.0.1:8000/api/health).StatusCode } catch { 0 }); web 3900: $(try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec 20 http://127.0.0.1:3900/).StatusCode } catch { 0 })"
Get-ScheduledTask -TaskName "Verity API", "Verity Web" | ForEach-Object { "   task '$($_.TaskName)': $($_.State); restart-on-failure count: $($_.Settings.RestartCount); trigger: $($_.Triggers[0].CimClass.CimClassName)" }
Remove-Item (Join-Path $logs "audit.*") -Force -ErrorAction SilentlyContinue
Remove-Item $data -Recurse -Force -ErrorAction SilentlyContinue
