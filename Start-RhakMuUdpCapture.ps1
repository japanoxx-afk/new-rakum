param(
    [int]$Port = 11223,
    [string]$OutputDir = ".\rhakmu_packet_captures"
)

$ErrorActionPreference = "Stop"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdministrator)) {
    throw "Run this script from an elevated PowerShell window. pktmon packet capture requires administrator rights."
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $root

$fullOutputDir = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDir)
New-Item -ItemType Directory -Force -Path $fullOutputDir | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$etlPath = Join-Path $fullOutputDir "rhakmu_udp_${Port}_$stamp.etl"
$metaPath = Join-Path $fullOutputDir "rhakmu_udp_${Port}_$stamp.meta.txt"
$statePath = Join-Path $fullOutputDir "active_capture.txt"

try { pktmon stop | Out-Null } catch {}
pktmon filter remove | Out-Null
pktmon filter add "RhakMu UDP $Port" -t UDP -p $Port | Out-Null
pktmon start --capture --comp nics --pkt-size 0 --file-name $etlPath | Out-Null

@(
    "Started: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff')",
    "Computer: $env:COMPUTERNAME",
    "Port: $Port",
    "ETL: $etlPath",
    "StopCommand: powershell -NoProfile -ExecutionPolicy Bypass -File .\Stop-RhakMuUdpCapture.ps1"
) | Set-Content -LiteralPath $metaPath -Encoding UTF8

$etlPath | Set-Content -LiteralPath $statePath -Encoding UTF8

Write-Host "RhakMu UDP capture started." -ForegroundColor Green
Write-Host "Port: $Port"
Write-Host "ETL: $etlPath"
Write-Host ""
Write-Host "Now reproduce the room join timeout. After test2 is removed, run:" -ForegroundColor Yellow
Write-Host "powershell -NoProfile -ExecutionPolicy Bypass -File .\Stop-RhakMuUdpCapture.ps1"
