# LottoShinryeong server watchdog / auto-restart (Windows PowerShell)   [ASCII only]
#
# WHY (2026-10-04): the server was started by hand via run_server.ps1, so a crash or reboot
# left it down with nobody to bring it back (measured: nothing was listening on 8501 and
# testers were pointed at a dead address). This script is called by Task Scheduler every
# 5 minutes; if the port is not listening it starts run_server.ps1 hidden. If the server is
# alive it does nothing and exits quietly.
#
# No administrator rights needed (port check + starting a process as the current user).
# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads BOM-less files as the ANSI
# code page, so non-ASCII comments here corrupt quoting and the script fails to parse.
#
# Manual test: powershell -NoProfile -ExecutionPolicy Bypass -File keep_server_up.ps1

param(
    [int]$Port = 8501
)

$ErrorActionPreference = "Continue"
$root = $PSScriptRoot
$log = Join-Path $root "server_keepalive.log"

function Write-Log([string]$Message) {
    try {
        $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Add-Content -Path $log -Value ("{0}  {1}" -f $stamp, $Message) -Encoding UTF8
        if ((Get-Item -LiteralPath $log).Length -gt 1MB) {
            Move-Item -LiteralPath $log -Destination "$log.old" -Force
        }
    } catch {
        # never let logging break the watchdog
    }
}

# Already listening -> nothing to do.
$listening = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
if ($listening) {
    exit 0
}

# Port free but a streamlit process may still be starting up -> skip this round.
$running = Get-CimInstance Win32_Process -Filter "Name like '%python%'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -match "streamlit" -and $_.CommandLine -match "app.py" }
if ($running) {
    Write-Log ("port {0} free but streamlit process present (PID {1}) - skipped" -f $Port, ($running.ProcessId -join ","))
    exit 0
}

Write-Log ("port {0} not listening - starting run_server.ps1" -f $Port)
$script = Join-Path $root "run_server.ps1"
if (-not (Test-Path -LiteralPath $script)) {
    Write-Log ("ERROR: missing {0}" -f $script)
    exit 1
}

Start-Process -FilePath "powershell.exe" `
    -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$script`"") `
    -WindowStyle Hidden
exit 0
