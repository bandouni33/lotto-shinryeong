# Register the Saturday draw-burst observation task (Windows PowerShell)   [ASCII only]
#
# WHY (2026-10-04): the user approved "observe real traffic on Saturday" as the free first step
# before spending money on a VPS. The draw is Saturday ~20:45 KST; the burst arrives right after.
# A background command from the agent session does NOT survive until Saturday, so the run is
# registered as a one-time scheduled task that starts itself that evening.
#
# What it runs (READ-ONLY observer):
#   venv312\Scripts\python.exe -u -X utf8 scratch\observe_live_traffic.py --target cloud
#     --duration 14400  (4 hours)  -> scratch\live_observation_<date>.csv / .json
#   Cloud target: probes HTTP status/latency and counts new session events in the SHARED Turso
#   database (cookie_reachable deltas). It does NOT open a websocket: Cloud rejects anonymous
#   websockets with HTTP 401 (measured 2026-10-04). It writes nothing to the app or the database.
#   Path note: the real page path is /~/+/ - the root / and /_stcore/health answer 303 (measured).
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
# (eas.json이 Cloud를 가리키고 있다). Cloud는 그쪽 CPU/RSS/로그를 볼 수 없고 익명 웹소켓도
# 401로 거부되므로, HTTP 상태·지연과 **공유 Turso의 세션 이벤트 수**를 본다.
# 경로 주의: 실제 페이지 경로는 /~/+/ 다 — 루트 / 와 /_stcore/health 는 303으로 돌려보낸다
# (이걸 빠뜨려 예약 작업이 303만 찔러 0건을 기록할 뻔했다 — 테스트가 잡았다).
$appRoot = "$BaseUrl/~/+/"
$wsUrl = "$($BaseUrl -replace '^https', 'wss')/~/+/_stcore/stream"
$argument = "-u -X utf8 `"$script`" --target $Target " +
    "--health $($appRoot)_stcore/health --page $appRoot " +
    "--url $wsUrl " +
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
