param(
    [ValidateSet("listen", "send")]
    [string]$Mode = "listen",
    [string]$TargetIp = "",
    [int]$Port = 11223
)

# RhakMu uses DirectPlay8 (WG_IPX.dll -> DP8Peer) P2P on UDP 11223 for the
# actual game. The "start game" signal (RMPK type 0x100A) travels host->guest
# over this DirectPlay8 session, NOT through the lobby server. If this UDP path
# fails between the two PCs, the guest times out after ~13s and leaves the room.
#
# Run this BEFORE testing the game to confirm raw UDP 11223 reachability:
#   On the HOST PC:   .\Test-RhakMuP2P.ps1 -Mode listen
#   On the GUEST PC:  .\Test-RhakMuP2P.ps1 -Mode send -TargetIp <HOST Radmin IP>
# The host should print the bytes it receives; the guest should get a reply.

$ErrorActionPreference = "Stop"

if ($Mode -eq "listen") {
    $ep = [Net.IPEndPoint]::new([Net.IPAddress]::Any, $Port)
    $udp = [Net.Sockets.UdpClient]::new($ep)
    Write-Host "Listening for UDP on 0.0.0.0:$Port ... (Ctrl+C to stop)" -ForegroundColor Green
    Write-Host "Tell the other PC to run:  .\Test-RhakMuP2P.ps1 -Mode send -TargetIp <this PC Radmin IP>" -ForegroundColor Cyan
    while ($true) {
        $remote = [Net.IPEndPoint]::new([Net.IPAddress]::Any, 0)
        $data = $udp.Receive([ref]$remote)
        $text = [Text.Encoding]::ASCII.GetString($data)
        Write-Host "RECV from $($remote.Address):$($remote.Port) -> '$text'" -ForegroundColor Yellow
        $reply = [Text.Encoding]::ASCII.GetBytes("PONG from host")
        [void]$udp.Send($reply, $reply.Length, $remote)
    }
} else {
    if (-not $TargetIp) { throw "Provide -TargetIp <HOST Radmin IP>" }
    $udp = [Net.Sockets.UdpClient]::new()
    $udp.Client.ReceiveTimeout = 4000
    $msg = [Text.Encoding]::ASCII.GetBytes("PING from guest")
    [void]$udp.Send($msg, $msg.Length, $TargetIp, $Port)
    Write-Host "Sent PING to ${TargetIp}:$Port, waiting for reply (4s)..." -ForegroundColor Cyan
    try {
        $remote = [Net.IPEndPoint]::new([Net.IPAddress]::Any, 0)
        $data = $udp.Receive([ref]$remote)
        $text = [Text.Encoding]::ASCII.GetString($data)
        Write-Host "SUCCESS: reply from $($remote.Address) -> '$text'" -ForegroundColor Green
        Write-Host "UDP $Port reachability OK. DirectPlay should be able to connect." -ForegroundColor Green
    } catch {
        Write-Host "FAILED: no reply within 4s. UDP $Port is blocked between the PCs." -ForegroundColor Red
        Write-Host "Fix: open UDP $Port + DirectPlay on both PCs, confirm Radmin VPN connects both ways." -ForegroundColor Red
    }
}
