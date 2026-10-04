# Register the Saturday draw-burst observation task (Windows PowerShell)   [ASCII only]
#
# WHY (2026-10-04): the user approved "observe real traffic on Saturday" as the free first step
# before spending money on a VPS. The draw is Saturday ~20:45 KST; the burst arrives right after.
# A background command from the agent session does NOT survive until Saturday, so the run is
# registered as a one-time scheduled task that starts itself that evening.
#
# What it runs (READ-ONLY observer):
#   venv312\Scripts\python.exe -u -X utf8 scratch\observe_live_traffic.py
#     --duration 14400  (4 hours)  -> scratch\live_observation_<date>.csv / .json
#   It probes HTTP + one websocket session every 60s, samples the server RSS/CPU, and reads
#   server_out.log for real-user [dbtrace] lines. It writes nothing to the app or the database.
#
# Remove it later with:
#   Unregister-ScheduledTask -TaskName "LottoShinryeongObserve" -Confirm:$false
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File register_observer_task.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File register_observer_task.ps1 -At "2026-10-10T19:30:00"

param(
    [string]$At = "2026-10-10T19:30:00",
    [string]$TaskName = "LottoShinryeongObserve",
    [int]$Hours = 4,
    [string]$Target = "cloud",
    [string]$BaseUrl = "https://lotto-shinryeong.streamlit.app",
    [int]$IntervalSeconds = 120
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$py = Join-Path $root "venv312\Scripts\python.exe"
$script = Join-Path $root "scratch\observe_live_traffic.py"
$stamp = ([datetime]$At).ToString("yyyy-MM-dd")
$csv = "scratch\live_observation_$stamp.csv"
$sum = "scratch\live_observation_$stamp.json"

if (-not (Test-Path -LiteralPath $py)) { Write-Host "ERROR: missing $py"; exit 1 }
if (-not (Test-Path -LiteralPath $script)) { Write-Host "ERROR: missing $script"; exit 1 }

# 2026-10-04(정정): 관측 대상은 **Cloud 앱**이다 — 이 PC 서버는 아무도 쓰지 않는다
# (eas.json이 Cloud를 가리키고 있다). Cloud는 그쪽 CPU/RSS/로그를 볼 수 없으므로
# URL 프로브(HTTP + 웹소켓 렌더 + 대기화면 탐지)와 **공유 Turso에서 세션 수**를 본다.
$argument = "-u -X utf8 `"$script`" --target $Target " +
    "--health $BaseUrl/_stcore/health --page $BaseUrl/ " +
    "--url $($BaseUrl -replace '^https', 'wss')/_stcore/stream " +
    "--interval $IntervalSeconds --duration $($Hours * 3600) --out $csv --summary $sum"
$action = New-ScheduledTaskAction -Execute $py -Argument $argument -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Once -At ([datetime]$At)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours ($Hours + 2))

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Force | Out-Null

# schtasks lied about success once before (see register_server_task.ps1) - verify by reading back.
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) { Write-Host "ERROR: task not found after registration"; exit 1 }
Write-Host ("OK  task      : " + $task.TaskName)
Write-Host ("    state     : " + $task.State)
Write-Host ("    starts at : " + ([datetime]$At).ToString("yyyy-MM-dd HH:mm"))
Write-Host ("    command   : " + $py)
Write-Host ("    args      : " + $argument)
Write-Host ("    csv       : " + $csv)
