param(
    [switch]$Restore   # re-enable all IPX interfaces
)

# RhakMu's in-game networking uses IPX, tunneled over UDP by ipxwrapper.
# ipxwrapper exposes one virtual IPX interface per host network adapter
# (Radmin VPN, physical LAN, VMware/VirtualBox virtuals, etc). If more than
# one is enabled, the game can bind IPX to the WRONG adapter (e.g. the LAN
# adapter), so its IPX broadcasts/session packets never reach the peer across
# the Radmin VPN -> the match stalls on "connecting".
#
# This enables ONLY the Radmin VPN IPX interface and disables the rest, on this
# PC. Run on BOTH PCs, then fully restart the game.
#   .\Set-RhakMuIpxRadminOnly.ps1            # Radmin-only
#   .\Set-RhakMuIpxRadminOnly.ps1 -Restore   # undo (enable all)

$ErrorActionPreference = "Stop"
$key = "HKCU:\Software\IPXWrapper"
if (-not (Test-Path $key)) { throw "ipxwrapper config not found in registry (run the game once first)." }

# Radmin VPN adapter MAC on this PC, formatted like the registry subkey (xx:xx:..)
$radmin = Get-NetAdapter | Where-Object { $_.InterfaceDescription -match "Radmin" -or $_.Name -match "Radmin" } | Select-Object -First 1
if (-not $radmin) { throw "Radmin VPN adapter not found. Connect Radmin VPN first." }
$radminMac = ($radmin.MacAddress -replace "-", ":").ToUpper()
Write-Host "Radmin VPN MAC: $radminMac" -ForegroundColor Cyan

$subkeys = Get-ChildItem $key -ErrorAction SilentlyContinue
foreach ($sk in $subkeys) {
    $mac = $sk.PSChildName.ToUpper()
    # only touch real per-adapter MAC subkeys (xx:xx:xx:xx:xx:xx)
    if ($mac -notmatch "^[0-9A-F]{2}(:[0-9A-F]{2}){5}$") { continue }
    if ($Restore) {
        Set-ItemProperty -Path $sk.PSPath -Name "enabled" -Value 1 -Type DWord
        Write-Host "enabled  $mac" -ForegroundColor DarkGray
        continue
    }
    if ($mac -eq $radminMac) {
        Set-ItemProperty -Path $sk.PSPath -Name "enabled" -Value 1 -Type DWord
        Write-Host "KEPT enabled (Radmin): $mac" -ForegroundColor Green
    } else {
        Set-ItemProperty -Path $sk.PSPath -Name "enabled" -Value 0 -Type DWord
        Write-Host "disabled $mac" -ForegroundColor Yellow
    }
}

Write-Host ""
if ($Restore) {
    Write-Host "All IPX interfaces re-enabled. Restart the game." -ForegroundColor Cyan
} else {
    Write-Host "Only the Radmin VPN IPX interface is enabled now. Restart the game on BOTH PCs." -ForegroundColor Green
}
