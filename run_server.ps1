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
