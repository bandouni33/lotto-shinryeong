# DuckDNS updater for the LottoShinryeong PC server   [ASCII only]
#
# WHY: this PC has no router and takes its public IP straight from KT over DHCP (2 hour
# lease), so the address changes and every hardcoded URL eventually dies. DuckDNS keeps a
# stable hostname pointing at whatever the current address is. Task Scheduler runs this
# every 5 minutes.
#
# Config lives in .env.ddns next to this file (gitignored by the ".env.*" rule):
#   DUCKDNS_DOMAIN=lottoshinryeong
#   DUCKDNS_TOKEN=<token>
#
# Manual run: powershell -NoProfile -ExecutionPolicy Bypass -File update_ddns.ps1
# NOTE: keep this file ASCII-only (PowerShell 5.1 reads BOM-less files as ANSI; non-ASCII
# characters corrupt quoting and the script fails to parse - measured 2026-10-04).

param(
    [string]$EnvFile = ""
)

$ErrorActionPreference = "Continue"
$root = $PSScriptRoot
if (-not $EnvFile) { $EnvFile = Join-Path $root ".env.ddns" }
$log = Join-Path $root "ddns_update.log"

function Write-Log([string]$Message) {
    try {
        $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Add-Content -Path $log -Value ("{0}  {1}" -f $stamp, $Message) -Encoding UTF8
        if ((Get-Item -LiteralPath $log).Length -gt 1MB) {
            Move-Item -LiteralPath $log -Destination "$log.old" -Force
        }
    } catch {
        # never let logging break the updater
    }
}

if (-not (Test-Path -LiteralPath $EnvFile)) {
    Write-Log ("missing config: {0}" -f $EnvFile)
    exit 1
}

$cfg = @{}
foreach ($line in Get-Content -LiteralPath $EnvFile) {
    $t = $line.Trim()
    if (-not $t -or $t.StartsWith("#")) { continue }
    if ($t -match "^([^=]+)=(.*)$") { $cfg[$matches[1].Trim()] = $matches[2].Trim() }
}

$domain = $cfg["DUCKDNS_DOMAIN"]
$token = $cfg["DUCKDNS_TOKEN"]
if (-not $domain -or -not $token) {
    Write-Log "config incomplete: DUCKDNS_DOMAIN and DUCKDNS_TOKEN are required"
    exit 1
}

# Current public IP: with no router on this line the NIC's DHCP IPv4 IS the public address.
$ip = (Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.PrefixOrigin -eq "Dhcp" } |
    Select-Object -First 1 -ExpandProperty IPAddress)

$url = "https://www.duckdns.org/update?domains={0}&token={1}&ip={2}" -f $domain, $token, $ip
try {
    $resp = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 30
    # PowerShell 5.1 hands back a byte[] when the response has no charset - stringifying it
    # yields "79 75" instead of "OK" (measured 2026-10-04: the update HAD succeeded but the
    # script reported failure). Decode bytes explicitly.
    $content = $resp.Content
    if ($content -is [byte[]]) {
        $body = [System.Text.Encoding]::ASCII.GetString($content).Trim()
    } else {
        $body = ("" + $content).Trim()
    }
    if ($body -eq "OK") {
        Write-Log ("OK {0}.duckdns.org -> {1}" -f $domain, $ip)
        exit 0
    }
    Write-Log ("unexpected response: {0}" -f $body)
    exit 1
} catch {
    Write-Log ("update failed: {0}" -f $_.Exception.Message)
    exit 1
}
