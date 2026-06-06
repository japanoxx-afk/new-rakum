param(
    [string]$Bind = "0.0.0.0",
    [int[]]$TcpPorts = @(11223),
    [int[]]$UdpPorts = @(11223),
    [string]$LogDir = ".\rhakmu_dummy_logs",
    [int]$DelayedStartStage8Ms = 12000
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
Write-Host "GameStartSyncMode: original-plus-delayed-stage8" -ForegroundColor Cyan
Write-Host "DelayedStartStage8Ms: $DelayedStartStage8Ms" -ForegroundColor Cyan
Write-Host "ChannelUserListReplyMode: members" -ForegroundColor Cyan

& (Join-Path $root "Start-RhakMuDummyServer.ps1") `
    -Bind $Bind `
    -TcpPorts $TcpPorts `
    -UdpPorts $UdpPorts `
    -LogDir $LogDir `
    -AutoReply none `
    -RoomJoinIdentityMode host `
    -GameStartSyncMode original-plus-delayed-stage8 `
    -DelayedStartStage8Ms $DelayedStartStage8Ms `
    -ChannelUserListReplyMode members
