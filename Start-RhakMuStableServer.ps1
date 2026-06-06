param(
    [string]$Bind = "0.0.0.0",
    [int[]]$TcpPorts = @(11223),
    [int[]]$UdpPorts = @(),
    [string]$LogDir = ".\rhakmu_dummy_logs",
    [ValidateSet("original", "original-plus-sync-ok", "none", "original-plus-accept", "accept-only", "original-plus-stage8", "original-plus-delayed-stage8", "original-plus-variants")]
    [string]$GameStartSyncMode = "original-plus-sync-ok",
    [int]$StartTraceWindowSec = 20,
    [int]$UdpOwnerCheckPort = 11223
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
Write-Host "RoomJoinIdentityMode: host" -ForegroundColor Cyan
Write-Host "GameStartSyncMode: $GameStartSyncMode" -ForegroundColor Cyan
Write-Host "StartTraceWindowSec: $StartTraceWindowSec" -ForegroundColor Cyan
Write-Host "UdpOwnerCheckPort: $UdpOwnerCheckPort" -ForegroundColor Cyan
Write-Host "ChannelUserListReplyMode: members" -ForegroundColor Cyan
Write-Host "TcpPorts: $($TcpPorts -join ', ')" -ForegroundColor Cyan
Write-Host "UdpPorts: $(if ($UdpPorts.Count -gt 0) { $UdpPorts -join ', ' } else { '(none - Rhakmu.exe owns UDP 11223)' })" -ForegroundColor Cyan

$serverArgs = @{
    Bind = $Bind
    TcpPorts = $TcpPorts
    LogDir = $LogDir
    AutoReply = "none"
    RoomJoinIdentityMode = "host"
    GameStartSyncMode = $GameStartSyncMode
    StartTraceWindowSec = $StartTraceWindowSec
    UdpOwnerCheckPort = $UdpOwnerCheckPort
    ChannelUserListReplyMode = "members"
}
if ($UdpPorts.Count -gt 0) {
    $serverArgs.UdpPorts = $UdpPorts
} else {
    $serverArgs.TcpOnly = $true
}

& (Join-Path $root "Start-RhakMuDummyServer.ps1") @serverArgs
