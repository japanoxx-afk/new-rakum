param(
    [Parameter(Mandatory = $true)]
    [string]$PeerIp,                 # the OTHER PC's Radmin IP (26.x.x.x)
    [int]$DurationSeconds = 45
)

# Captures the real UDP traffic between this PC and the peer during a game
# start, so we can see whether the DirectPlay8 (DP8Peer) P2P handshake on
# port 11223 actually flows, stalls, or switches to a blocked dynamic port.
#
# Run as Administrator on BOTH PCs at the same time, then immediately:
#   host creates room -> guest joins -> host presses Start.
#
#   .\Capture-RhakMuDP8.ps1 -PeerIp <other PC Radmin IP>

$ErrorActionPreference = "Stop"

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}
if (-not (Test-IsAdmin)) { throw "Run this script from an elevated PowerShell window." }

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$etl = Join-Path $PWD "dp8_$stamp.etl"
$txt = Join-Path $PWD "dp8_$stamp.txt"
$summary = Join-Path $PWD "dp8_$stamp.summary.txt"

Write-Host "Resetting pktmon filters..." -ForegroundColor Cyan
pktmon filter remove | Out-Null
# Filter to packets involving the peer IP (both directions).
pktmon filter add RhakMuPeer -i $PeerIp | Out-Null

Write-Host "Starting capture for $DurationSeconds s. DO THE GAME START NOW." -ForegroundColor Green
Write-Host "  host: create room   guest: join   host: press Start" -ForegroundColor Green
pktmon start --capture --pkt-size 64 --file-name $etl | Out-Null

$end = (Get-Date).AddSeconds($DurationSeconds)
while ((Get-Date) -lt $end) {
    Start-Sleep -Seconds 1
    $left = [int]($end - (Get-Date)).TotalSeconds
    Write-Host "  capturing... $left s left" -NoNewline
    Write-Host "`r" -NoNewline
}
Write-Host ""

Write-Host "Stopping capture..." -ForegroundColor Cyan
pktmon stop | Out-Null
pktmon filter remove | Out-Null

Write-Host "Converting to text..." -ForegroundColor Cyan
pktmon etl2txt $etl -o $txt | Out-Null

# Summarize: count UDP packets per src->dst:port, both directions.
$myIps = (Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" }).IPAddress

$lines = Get-Content $txt -ErrorAction SilentlyContinue
$udp = $lines | Where-Object { $_ -match "UDP" -and $_ -match [Regex]::Escape($PeerIp) }

$counts = @{}
foreach ($l in $udp) {
    if ($l -match '(\d+\.\d+\.\d+\.\d+)\.(\d+)\s*>\s*(\d+\.\d+\.\d+\.\d+)\.(\d+)') {
        $key = "{0}:{1} -> {2}:{3}" -f $Matches[1], $Matches[2], $Matches[3], $Matches[4]
        if ($counts.ContainsKey($key)) { $counts[$key]++ } else { $counts[$key] = 1 }
    }
}

$out = New-Object System.Collections.Generic.List[string]
$out.Add("RhakMu DP8 capture summary  ($stamp)")
$out.Add("This PC IPs : $($myIps -join ', ')")
$out.Add("Peer IP     : $PeerIp")
$out.Add("UDP packets involving peer: $($udp.Count)")
$out.Add("")
$out.Add("Flows (src -> dst:port  count):")
if ($counts.Count -eq 0) {
    $out.Add("  (NONE - no UDP packets exchanged with the peer at all)")
} else {
    foreach ($k in ($counts.Keys | Sort-Object { $counts[$_] } -Descending)) {
        $out.Add(("  {0,-46} {1}" -f $k, $counts[$k]))
    }
}
$out | Set-Content -Path $summary -Encoding UTF8
$out | ForEach-Object { Write-Host $_ }

Write-Host ""
Write-Host "Files:" -ForegroundColor Cyan
Write-Host "  summary: $summary"
Write-Host "  full   : $txt"
Write-Host "Paste the summary here." -ForegroundColor Yellow
