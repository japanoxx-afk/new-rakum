param(
    [string]$Bind = "0.0.0.0",
    [int[]]$Ports = @(11223),
    [string]$LogDir = ".\rhakmu_dummy_logs",
    [ValidateSet("original", "original-plus-sync-ok", "none", "original-plus-accept", "accept-only", "original-plus-stage8", "original-plus-delayed-stage8", "original-plus-variants")]
    [string]$GameStartSyncMode = "original-plus-sync-ok",
    [int]$StartTraceWindowSec = 20
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $root

Get-CimInstance Win32_Process |
    Where-Object {
        ($_.CommandLine -like "*Start-RhakMuDummyServer.ps1*" -or $_.CommandLine -like "*Start-RhakMuStableServer.ps1*") -and
        $_.ProcessId -ne $PID
    } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

Write-Host "Starting RhakMu stable multiplayer server profile..." -ForegroundColor Green
Write-Host "Ports: $($Ports -join ', ')" -ForegroundColor Cyan
Write-Host "RoomJoinIdentityMode: joiner" -ForegroundColor Cyan
Write-Host "GameStartSyncMode: $GameStartSyncMode" -ForegroundColor Cyan
Write-Host "StartTraceWindowSec: $StartTraceWindowSec" -ForegroundColor Cyan
Write-Host "ChannelUserListReplyMode: members" -ForegroundColor Cyan

& (Join-Path $root "Start-RhakMuDummyServer.ps1") `
    -Bind $Bind `
    -Ports $Ports `
    -SkipUdpPorts @() `
    -LogDir $LogDir `
    -AutoReply none `
    -RoomJoinIdentityMode joiner `
    -GameStartSyncMode $GameStartSyncMode `
    -StartTraceWindowSec $StartTraceWindowSec `
    -ChannelUserListReplyMode members
