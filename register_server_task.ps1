# Register LottoShinryeong server auto-recovery tasks (Windows Task Scheduler)   [ASCII only]
#
# Run: powershell -NoProfile -ExecutionPolicy Bypass -File register_server_task.ps1
#
# Registers, without administrator rights, the best that a normal user task can do:
#   * every 5 minutes  -> crash recovery (server back up within 5 minutes)
#   * at logon         -> immediate check (no 5-minute wait after a reboot)
#   Both run as the current user and only while that user is logged on (/it).
#
# For "starts at boot, no logon required" an administrator is needed (Gureum's task):
#   schtasks /create /f /tn LottoShinryeongServer /sc onstart /ru SYSTEM /tr "powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\PC\Desktop\lotto-app\keep_server_up.ps1"
#
# NOTE: keep this file ASCII-only (PowerShell 5.1 reads BOM-less files as ANSI; non-ASCII
# comments corrupt quoting and the script fails to parse).

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$taskName = "LottoShinryeongServer"
$logonName = "$taskName-Logon"
$target = Join-Path $root "keep_server_up.ps1"

if (-not (Test-Path -LiteralPath $target)) {
    Write-Host "ERROR: missing $target - nothing registered"
    exit 1
}

$action = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$target`""

# NOTE: `schtasks /create` returns 0 even when it refuses to create a task, so success is
# judged by querying the task afterwards - not by the exit code (measured 2026-10-04).
function Test-TaskExists([string]$Name) {
    # schtasks writes its "task not found" message to stderr; with $ErrorActionPreference=Stop
    # that becomes a terminating error and kills the whole script (measured 2026-10-04: the
    # logon probe aborted registration so the DDNS task was never created). Query with
    # Continue and judge by exit code only.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $null = & schtasks /query /tn $Name 2>&1
        return ($LASTEXITCODE -eq 0)
    } finally {
        $ErrorActionPreference = $previous
    }
}

Write-Host "== registering =="
schtasks /create /f /tn $taskName /tr $action /sc minute /mo 5 /it | Out-Null
if (Test-TaskExists $taskName) {
    Write-Host ("  OK    {0}  (every 5 minutes - crash recovery)" -f $taskName)
} else {
    Write-Host ("  FAIL  {0}  - not created" -f $taskName)
}

# Logon trigger needs an administrator on this machine (measured 2026-10-04: /sc onlogon is
# silently refused for a normal user). It is a convenience only - the 5-minute task already
# covers a reboot (server returns within 5 minutes of logon).
schtasks /create /f /tn $logonName /tr $action /sc onlogon /it | Out-Null
if (Test-TaskExists $logonName) {
    Write-Host ("  OK    {0}  (at logon - immediate start)" -f $logonName)
} else {
    Write-Host ("  SKIP  {0}  - needs administrator (5-minute task covers this case)" -f $logonName)
}

# DuckDNS updater: keeps the stable hostname pointing at the current public IP.
$ddnsTask = "LottoShinryeongDDNS"
$ddnsScript = Join-Path $root "update_ddns.ps1"
if (Test-Path -LiteralPath $ddnsScript) {
    $ddnsAction = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$ddnsScript`""
    schtasks /create /f /tn $ddnsTask /tr $ddnsAction /sc minute /mo 5 /it | Out-Null
    if (Test-TaskExists $ddnsTask) {
        Write-Host ("  OK    {0}  (every 5 minutes - DDNS update)" -f $ddnsTask)
    } else {
        Write-Host ("  FAIL  {0}  - not created" -f $ddnsTask)
    }
} else {
    Write-Host ("  SKIP  {0}  - update_ddns.ps1 missing" -f $ddnsTask)
}

Write-Host ""
Write-Host "check : schtasks /query /tn $taskName /v /fo LIST"
Write-Host "remove: schtasks /delete /f /tn $taskName ; schtasks /delete /f /tn $logonName ; schtasks /delete /f /tn $ddnsTask"
