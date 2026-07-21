# Streamlit server restart script (Windows PowerShell)
#
# Usage:
#   .\run_server.ps1
#   .\run_server.ps1 -PublicIp "210.99.230.83"

param(
    [string]$PublicIp = "210.99.230.83",
    [int]$Port = 8501
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

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
    Write-Host "WARNING: .env not found — copy .env.example to .env and set KAKAO_REST_API_KEY"
}

$kakaoKey = $env:KAKAO_REST_API_KEY
$mockAuth = if ($env:LOTTO_DEV_MOCK_AUTH) { $env:LOTTO_DEV_MOCK_AUTH } else { "1" }
if ($kakaoKey) {
    Write-Host "Kakao OAuth: configured (LOTTO_DEV_MOCK_AUTH=$mockAuth)"
} elseif ($mockAuth -eq "0") {
    Write-Host "WARNING: KAKAO_REST_API_KEY empty and LOTTO_DEV_MOCK_AUTH=0 — login will not work"
} else {
    Write-Host "Kakao OAuth: using dev mock (set KAKAO_REST_API_KEY + LOTTO_DEV_MOCK_AUTH=0 for real login)"
}

$localUrl = "http://localhost:$Port"
$mobileUrl = "http://{0}:{1}" -f $PublicIp, $Port

Write-Host ""
Write-Host "Starting server..."
Write-Host "  PC:     $localUrl"
Write-Host "  Mobile: $mobileUrl"
Write-Host ""
Write-Host "Press Ctrl+C to stop."
Write-Host ""

python -m streamlit run app.py `
    --server.address 0.0.0.0 `
    --server.port $Port `
    --browser.serverAddress $PublicIp `
    --browser.serverPort $Port
