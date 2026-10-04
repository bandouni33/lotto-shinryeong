# Streamlit server restart script (Windows PowerShell)
#
# Usage:
#   .\run_server.ps1
#   .\run_server.ps1 -PublicHost "lotto-example.duckdns.org"
#   .\run_server.ps1 -Port 8501
#
# 2026-10-04: a stale public IP was the default here (210.99.230.83). This line changes
# often (this PC gets its public IP directly from KT over DHCP, lease 2 hours), so it is
# **not** kept as a constant: when empty, the current public IP is detected, and a DDNS
# hostname may be passed instead (recommended - that keeps the address stable).
# Keep this file ASCII-only: PowerShell 5.1 reads BOM-less files as ANSI, and non-ASCII
# characters corrupt quoting so the script fails to parse (measured 2026-10-04).

param(
    [Alias("PublicIp")][string]$PublicHost = "",
    [int]$Port = 8501
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# 2026-10-04: observation log - keep the server stdout (one [dbtrace] line per render with
# script_ms/db_ms/calls) in a file. -u (unbuffered) is REQUIRED: when stdout is redirected to a
# file Python block-buffers it, so lines arrive in late chunks and you cannot see live activity.
# *.log is gitignored. NOTE: this file must stay ASCII-only (see the header above) - a Korean
# comment here was read as cp949 by PS 5.1 and broke quoting (caught by
# tests/test_server_address_fix.py:test_scripts_are_ascii_only on 2026-10-04).
$logFile = Join-Path $PSScriptRoot "server_out.log"

Write-Host "========================================"
Write-Host " Lotto App - Streamlit Server"
Write-Host "========================================"

$lines = netstat -ano | Select-String ":$Port\s"
foreach ($line in $lines) {
    $parts = ($line -split "\s+") | Where-Object { $_ -ne "" }
    if ($parts.Length -ge 5) {
        $procId = $parts[-1]
        if ($procId -match "^\d+$" -and [int]$procId -gt 0) {
            Write-Host "Stopping old process PID=$procId on port $Port"
            Stop-Process -Id ([int]$procId) -Force -ErrorAction SilentlyContinue
        }
    }
}

Start-Sleep -Seconds 1

$envFile = Join-Path $PSScriptRoot ".env"
if (Test-Path $envFile) {
    Get-Content $envFile -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line -match "^([^=]+)=(.*)$") {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            Set-Item -Path "env:$name" -Value $value
        }
    }
    Write-Host "Loaded .env"
} else {
    Write-Host "WARNING: .env not found - copy .env.example to .env and set KAKAO_REST_API_KEY"
}

$kakaoKey = $env:KAKAO_REST_API_KEY
$mockAuth = if ($env:LOTTO_DEV_MOCK_AUTH) { $env:LOTTO_DEV_MOCK_AUTH } else { "1" }
if ($kakaoKey) {
    Write-Host "Kakao OAuth: configured (LOTTO_DEV_MOCK_AUTH=$mockAuth)"
} elseif ($mockAuth -eq "0") {
    Write-Host "WARNING: KAKAO_REST_API_KEY empty and LOTTO_DEV_MOCK_AUTH=0 - login will not work"
} else {
    Write-Host "Kakao OAuth: using dev mock (set KAKAO_REST_API_KEY + LOTTO_DEV_MOCK_AUTH=0 for real login)"
}

if (-not $PublicHost) {
    # Prefer the DDNS hostname from .env.ddns: it survives public IP changes (no router on
    # this line - the address comes from KT DHCP with a 2 hour lease). Raw IP is the fallback.
    $ddnsFile = Join-Path $PSScriptRoot ".env.ddns"
    if (Test-Path -LiteralPath $ddnsFile) {
        foreach ($line in Get-Content -LiteralPath $ddnsFile) {
            $t = $line.Trim()
            if ($t -match "^DUCKDNS_DOMAIN=(.*)$") {
                $PublicHost = ($matches[1].Trim() + ".duckdns.org")
            }
        }
    }
}
if (-not $PublicHost) {
    # No router here: this PC holds the public IP directly, so the NIC's DHCP IPv4 IS the
    # public IP (measured 2026-10-04: NIC address == address seen from outside).
    $PublicHost = (Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.PrefixOrigin -eq "Dhcp" } |
        Select-Object -First 1 -ExpandProperty IPAddress)
}
if (-not $PublicHost) {
    Write-Host "WARNING: could not determine public IP/host - pass -PublicHost"
}

$localUrl = "http://localhost:$Port"
$mobileUrl = if ($PublicHost) { "http://{0}:{1}" -f $PublicHost, $Port } else { "(address unknown)" }

Write-Host ""
Write-Host "Starting server..."
Write-Host "  PC:     $localUrl"
Write-Host "  Mobile: $mobileUrl"
Write-Host ""
Write-Host "Press Ctrl+C to stop."
Write-Host ""

if ($PublicHost) {
    # 2026-10-04: send stdout/stderr to the log file. PowerShell's *>> redirect killed the python
    # process instantly when started without a console (Task Scheduler / watchdog Start-Process
    # -WindowStyle Hidden): the file appeared but stayed empty and the server never came up
    # (measured). cmd's >> redirection works in that context.
    cmd /c "python -u -m streamlit run app.py --server.address 0.0.0.0 --server.port $Port --browser.serverAddress $PublicHost --browser.serverPort $Port >> $logFile 2>&1"
} else {
    # Do not pass an empty -browser.serverAddress (an empty value can break origin checks).
    cmd /c "python -u -m streamlit run app.py --server.address 0.0.0.0 --server.port $Port >> $logFile 2>&1"
}
