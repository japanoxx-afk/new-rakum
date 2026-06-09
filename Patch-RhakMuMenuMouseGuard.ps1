param(
    [string]$ExePath = "C:\Program Files (x86)\TriggerSoft\RhakMu\Rhakmu.exe",
    [switch]$Revert
)

# Stabilization: returning to the menu/lobby after a match crashes in
# CGameMenu::DrawMenuMouse (it dereferences the cursor image manager
# [0x6E0218] in many places; that manager is freed during the post-game
# cleanup and not re-initialized, so [0x6E0218] is NULL -> ACCESS_VIOLATION).
#
# DrawMenuMouse is the custom menu-cursor *renderer* only (click handling and
# cursor position are elsewhere), and it is called from exactly one place:
# CGameMenu::Draw @ VA 0x004239F9  (call 0x004246C0).
#
# This NOPs that 5-byte call. The game no longer draws its own menu cursor
# (the Windows cursor is visible in DDrawCompat borderless mode, and clicks
# still work), and the post-match return to the lobby no longer crashes.
# __thiscall with no stack args, so NOPing the call keeps the stack balanced.

$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $ExePath)) { throw "File not found: $ExePath" }
$bytes = [IO.File]::ReadAllBytes($ExePath)

$off  = 0x239F9
$orig = [byte[]]@(0xE8,0xC2,0x0C,0x00,0x00)   # call 0x004246C0
$nop  = [byte[]]@(0x90,0x90,0x90,0x90,0x90)

function Eq($a,$o,$e){ for($i=0;$i -lt $e.Length;$i++){ if($a[$o+$i] -ne $e[$i]){ return $false } } return $true }

if ($Revert) {
    if (Eq $bytes $off $nop) { for($i=0;$i -lt 5;$i++){ $bytes[$off+$i]=$orig[$i] }; [IO.File]::WriteAllBytes($ExePath,$bytes); Write-Host "Reverted: DrawMenuMouse call restored." -ForegroundColor Green }
    else { Write-Host "Not patched." -ForegroundColor Yellow }
    return
}

if (Eq $bytes $off $nop) { Write-Host "Already patched: DrawMenuMouse call NOPped." -ForegroundColor Yellow; return }
if (-not (Eq $bytes $off $orig)) {
    $h = ($bytes[$off..($off+4)] | ForEach-Object { "{0:X2}" -f $_ }) -join " "
    throw "Unexpected bytes at 0x$('{0:X}' -f $off): $h"
}
$stamp = Get-Date -Format yyyyMMdd_HHmmss
[IO.File]::WriteAllBytes("$ExePath.bak_menumouse_$stamp", $bytes)
for ($i=0;$i -lt 5;$i++){ $bytes[$off+$i]=0x90 }
[IO.File]::WriteAllBytes($ExePath, $bytes)
Write-Host "Patched: NOPped DrawMenuMouse call (no more post-match lobby crash)." -ForegroundColor Green
