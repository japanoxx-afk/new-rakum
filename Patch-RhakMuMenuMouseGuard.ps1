param(
    [string]$ExePath = "C:\Program Files (x86)\TriggerSoft\RhakMu\Rhakmu.exe",
    [switch]$Revert
)

# Post-match return to the lobby crashed in CGameMenu::DrawMenuMouse: it
# dereferences the cursor image manager [0x6E0218] (NULL after post-game
# cleanup) -> ACCESS_VIOLATION. DrawMenuMouse (0x004246C0) is the custom
# menu-cursor renderer, called from exactly one site: CGameMenu::Draw @
# 0x004239F6 (mov ecx,[ebp-4] ; call 0x004246C0).
#
# This installs a NULL-guard using a code cave in the .text tail padding
# (VA 0x004EA6B2, ~2KB of zeroes). The call site is redirected to the cave,
# which calls DrawMenuMouse ONLY when [0x6E0218] != 0. So the cursor draws
# normally in the menus/login, and is skipped (no crash) only when the
# manager is NULL (post-match). Cursor stays visible in normal use.
#
# Call site (8 bytes @ file 0x239F6) -> call <cave> + 3 nop
# Cave (18 bytes @ file 0xEA6B2):
#   cmp dword [0x6E0218],0 ; jz +8 ; mov ecx,[ebp-4] ; call 0x004246C0 ; ret

$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $ExePath)) { throw "File not found: $ExePath" }
$bytes = [IO.File]::ReadAllBytes($ExePath)

$siteOff = 0x239F6
$siteOrig1 = [byte[]]@(0x8B,0x4D,0xFC,0xE8,0xC2,0x0C,0x00,0x00)            # original: mov ecx,[ebp-4]; call 0x4246C0
$siteOrig2 = [byte[]]@(0x8B,0x4D,0xFC,0x90,0x90,0x90,0x90,0x90)            # prior NOP-patch state
$sitePatch = [byte[]]@(0xE8,0xB7,0x6C,0x0C,0x00,0x90,0x90,0x90)            # call 0x4EA6B2 ; nop nop nop

$caveOff = 0xEA6B2
$caveZero = [byte[]]@(0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00)
$caveCode = [byte[]]@(0x83,0x3D,0x18,0x02,0x6E,0x00,0x00, 0x74,0x08, 0x8B,0x4D,0xFC, 0xE8,0xFD,0x9F,0xF3,0xFF, 0xC3)

function Eq($a,$o,$e){ for($i=0;$i -lt $e.Length;$i++){ if($a[$o+$i] -ne $e[$i]){ return $false } } return $true }
function Put($a,$o,$p){ for($i=0;$i -lt $p.Length;$i++){ $a[$o+$i]=$p[$i] } }

if ($Revert) {
    if (Eq $bytes $siteOff $sitePatch) { Put $bytes $siteOff $siteOrig1 }
    Put $bytes $caveOff $caveZero
    [IO.File]::WriteAllBytes($ExePath, $bytes)
    Write-Host "Reverted: DrawMenuMouse call restored, cave cleared." -ForegroundColor Green
    return
}

if (Eq $bytes $siteOff $sitePatch -and (Eq $bytes $caveOff $caveCode)) {
    Write-Host "Already patched: DrawMenuMouse NULL-guard installed." -ForegroundColor Yellow; return
}
if (-not (Eq $bytes $siteOff $siteOrig1) -and -not (Eq $bytes $siteOff $siteOrig2) -and -not (Eq $bytes $siteOff $sitePatch)) {
    $h=($bytes[$siteOff..($siteOff+7)]|%{ "{0:X2}" -f $_ }) -join " "; throw "Unexpected call-site bytes: $h"
}
if (-not (Eq $bytes $caveOff $caveZero) -and -not (Eq $bytes $caveOff $caveCode)) {
    $h=($bytes[$caveOff..($caveOff+17)]|%{ "{0:X2}" -f $_ }) -join " "; throw "Cave region not empty: $h"
}

$stamp = Get-Date -Format yyyyMMdd_HHmmss
[IO.File]::WriteAllBytes("$ExePath.bak_menumouse_$stamp", $bytes)
Put $bytes $caveOff $caveCode
Put $bytes $siteOff $sitePatch
[IO.File]::WriteAllBytes($ExePath, $bytes)
Write-Host "Patched: DrawMenuMouse NULL-guard (cursor shows normally; skipped only when manager is NULL)." -ForegroundColor Green
