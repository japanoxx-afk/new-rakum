param(
    [int]$Port = 11223,
    [string]$OutputDir = ".\rhakmu_packet_captures",
    [string]$LogsRoot = ".\logs",
    [string]$LocalIp = "",
    [string]$Label = ""
)

$ErrorActionPreference = "Stop"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-RhakMuLocalIp {
    if (-not [string]::IsNullOrWhiteSpace($LocalIp)) { return $LocalIp.Trim() }

    try {
        $addresses = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
            Where-Object {
                $_.IPAddress -notlike "127.*" -and
                $_.IPAddress -notlike "169.254.*" -and
                $_.IPAddress -ne "0.0.0.0"
            }

        $radmin = $addresses | Where-Object { $_.IPAddress -like "26.*" } | Select-Object -First 1
        if ($null -ne $radmin) { return $radmin.IPAddress }

        $preferred = $addresses | Select-Object -First 1
        if ($null -ne $preferred) { return $preferred.IPAddress }
    } catch {}

    return "unknown-ip"
}

function ConvertTo-SafeName([string]$Text) {
    if ([string]::IsNullOrWhiteSpace($Text)) { return "unknown" }
    return (($Text.Trim() -replace '[\\/:*?"<>|,=\s]+', "_") -replace "_+", "_").Trim("_")
}

if (-not (Test-IsAdministrator)) {
    throw "Run this script from an elevated PowerShell window. pktmon packet capture requires administrator rights."
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $root

$fullOutputDir = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDir)
New-Item -ItemType Directory -Force -Path $fullOutputDir | Out-Null

$resolvedLogsRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($LogsRoot)
New-Item -ItemType Directory -Force -Path $resolvedLogsRoot | Out-Null

$localIpValue = Get-RhakMuLocalIp
$safeIp = ConvertTo-SafeName $localIpValue
$safeLabel = ConvertTo-SafeName $Label
$labelPart = if ([string]::IsNullOrWhiteSpace($Label)) { "" } else { "_$safeLabel" }

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$baseName = "rhakmu_udp_${Port}_${safeIp}${labelPart}_$stamp"
$etlPath = Join-Path $fullOutputDir "$baseName.etl"
$metaPath = Join-Path $fullOutputDir "$baseName.meta.txt"
$statePath = Join-Path $fullOutputDir "active_capture.txt"
$stateJsonPath = Join-Path $fullOutputDir "active_capture.json"

try { pktmon stop | Out-Null } catch {}
pktmon filter remove | Out-Null
pktmon filter add "RhakMu UDP $Port" -t UDP -p $Port | Out-Null
pktmon start --capture --comp nics --pkt-size 0 --file-name $etlPath | Out-Null

@(
    "Started: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff')",
    "Computer: $env:COMPUTERNAME",
    "LocalIp: $localIpValue",
    "Label: $Label",
    "Port: $Port",
    "ETL: $etlPath",
    "LogsRoot: $resolvedLogsRoot",
    "StopCommand: powershell -NoProfile -ExecutionPolicy Bypass -File .\Stop-RhakMuUdpCapture.ps1"
) | Set-Content -LiteralPath $metaPath -Encoding UTF8

$etlPath | Set-Content -LiteralPath $statePath -Encoding UTF8
@{
    Started = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss.fff")
    Computer = $env:COMPUTERNAME
    LocalIp = $localIpValue
    SafeIp = $safeIp
    Label = $Label
    Port = $Port
    OutputDir = $fullOutputDir
    LogsRoot = $resolvedLogsRoot
    BaseName = $baseName
    EtlPath = $etlPath
    MetaPath = $metaPath
} | ConvertTo-Json | Set-Content -LiteralPath $stateJsonPath -Encoding UTF8

Write-Host "RhakMu UDP capture started." -ForegroundColor Green
Write-Host "Port: $Port"
Write-Host "LocalIp: $localIpValue"
Write-Host "ETL: $etlPath"
Write-Host "Git log folder: $(Join-Path $resolvedLogsRoot $safeIp)"
Write-Host ""
Write-Host "Now reproduce the room join timeout. After test2 is removed, run:" -ForegroundColor Yellow
Write-Host "powershell -NoProfile -ExecutionPolicy Bypass -File .\Stop-RhakMuUdpCapture.ps1"
