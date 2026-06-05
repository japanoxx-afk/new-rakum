param(
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
$statePath = Join-Path $fullOutputDir "active_capture.txt"

if (-not (Test-Path -LiteralPath $statePath)) {
    throw "No active capture state found: $statePath"
}

$etlPath = (Get-Content -LiteralPath $statePath -Raw).Trim()
if ([string]::IsNullOrWhiteSpace($etlPath)) {
    throw "Active capture state is empty: $statePath"
}

pktmon stop | Out-Null

$pcapPath = [IO.Path]::ChangeExtension($etlPath, ".pcapng")
$txtPath = [IO.Path]::ChangeExtension($etlPath, ".txt")

pktmon etl2pcap $etlPath --out $pcapPath | Out-Null
pktmon etl2txt $etlPath --out $txtPath | Out-Null

Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue

Write-Host "RhakMu UDP capture stopped." -ForegroundColor Green
Write-Host "ETL:   $etlPath"
Write-Host "PCAP:  $pcapPath"
Write-Host "TEXT:  $txtPath"
Write-Host ""
Write-Host "Send the .pcapng and .txt files from both PCs." -ForegroundColor Yellow
