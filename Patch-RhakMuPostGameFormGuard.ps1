param(
    [string]$ExePath = "C:\Program Files (x86)\TriggerSoft\RhakMu\Rhakmu.exe",
    [switch]$Revert
)

# Stabilization: after a match ends, CGameMenu::Menu_GameAfterProcess builds a
# 1024x768 result-screen rect and calls the result-screen setup (sub_422BA0),
# which creates a fullscreen result form. Drawing that form crashes in
# iCARUS16_Put16Image (the fullscreen blit overruns the post-game surface),
# so the game dies at every match end instead of returning to the lobby.
#
# This NOPs the 40-byte result-screen setup block at VA 0x004230E0..0x00423107
# (sub esp,0x10 / build rect / push arg / call sub_422BA0). The post-game then
# skips the result screen and continues its normal scene cleanup back to the
# menu/lobby without the crashing draw. The esp adjustment is removed too, so
# the stack stays balanced.

$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $ExePath)) { throw "File not found: $ExePath" }
$bytes = [IO.File]::ReadAllBytes($ExePath)

$off = 0x230E0
$orig = [byte[]]@(0x83,0xEC,0x10,0x8B,0xCC,0x8B,0x55,0xE8,0x89,0x11,0x8B,0x45,0xEC,0x89,0x41,0x04,0x8B,0x55,0xF0,0x89,0x51,0x08,0x8B,0x45,0xF4,0x89,0x41,0x0C,0x8B,0x4D,0x08,0x51,0x8B,0x4D,0xFC,0xE8,0x98,0xFA,0xFF,0xFF)
$nop = [byte[]]@(); for ($i=0;$i -lt 40;$i++){ $nop += 0x90 }

function Eq($a,$o,$e){ for($i=0;$i -lt $e.Length;$i++){ if($a[$o+$i] -ne $e[$i]){ return $false } } return $true }

$stamp = Get-Date -Format yyyyMMdd_HHmmss
[IO.File]::WriteAllBytes("$ExePath.bak_postgameform_$stamp", $bytes)

if ($Revert) {
    if (Eq $bytes $off $nop) { for($i=0;$i -lt 40;$i++){ $bytes[$off+$i]=$orig[$i] }; [IO.File]::WriteAllBytes($ExePath,$bytes); Write-Host "Reverted: result-screen setup restored." -ForegroundColor Green }
    else { Write-Host "Not patched (already original)." -ForegroundColor Yellow }
    return
}

if (Eq $bytes $off $nop) { Write-Host "Already patched: post-game result-screen setup skipped." -ForegroundColor Yellow; return }
if (-not (Eq $bytes $off $orig)) {
    $h = ($bytes[$off..($off+39)] | ForEach-Object { "{0:X2}" -f $_ }) -join " "
    throw "Unexpected bytes at 0x$('{0:X}' -f $off): $h"
}
for ($i=0;$i -lt 40;$i++){ $bytes[$off+$i]=0x90 }
[IO.File]::WriteAllBytes($ExePath, $bytes)
Write-Host "Patched: skipped post-game result-screen setup (no more end-of-match crash)." -ForegroundColor Green
Write-Host "Apply on BOTH PCs." -ForegroundColor Cyan
