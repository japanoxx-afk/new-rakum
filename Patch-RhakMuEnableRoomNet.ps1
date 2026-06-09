param(
    [string]$ExePath = "C:\Program Files (x86)\TriggerSoft\RhakMu\Rhakmu.exe",
    [switch]$Revert
)

# ROOT CAUSE FIX (v2, surgical) for the in-game "connecting" stall.
#
# In-game sync needs the host to send RMPK 0x100A (game start) over
# classRoomNetMGR. RMPKSend_* are skipped when RoomNetMGR's send buffer
# (this+4) is null, and RoomNetMGR is never initialized in our flow (the
# menu state that would call RoomNetMGR_Setup never happens). The previous
# team worked around the null with Patch-RhakMuRoomSendGuards (skip the send,
# dropping the 0x100A write) so coordination never happened.
#
# v1 forced RoomNetMGR_Setup at channel-select -> broke the lobby (room-mode
# transition fired at login). v2 is surgical: it only runs at ROOM CREATE.
#
# The create-room reply handler (0x0044CBE0, type 0x0EFF, our reply has
# packet[4]=0 -> case 0 host-setup path) contains a harmless debug-log call at
# VA 0x0044CC88 (16 bytes: push 0x4EEB7C; push 4; call [0x4EB3D0]; add esp,8).
# We overwrite it with:  push 0; mov ecx,0x6DFBD8; call 0x00423300  (+NOPs)
# i.e. RoomNetMGR_Setup, which allocates the RoomNetMGR send buffer right when
# the host creates the room. The lobby/login path is untouched.
#
# It also reverts the 3 RoomSendGuards so RMPKSend runs its ORIGINAL code and
# actually emits 0x100A (safe now that this+4 is allocated).

$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $ExePath)) { throw "File not found: $ExePath" }
$bytes = [IO.File]::ReadAllBytes($ExePath)

function Eq($a,$o,$e){ for($i=0;$i -lt $e.Length;$i++){ if($a[$o+$i] -ne $e[$i]){ return $false } } return $true }
function Put($a,$o,$p){ for($i=0;$i -lt $p.Length;$i++){ $a[$o+$i]=$p[$i] } }

# --- site 1: room-create debug-log -> RoomNetMGR_Setup (file offset 0x4CC88) ---
$rnOff  = 0x4CC88
$rnOrig = [byte[]]@(0x68,0x7C,0xEB,0x4E,0x00,0x6A,0x04,0xFF,0x15,0xD0,0xB3,0x4E,0x00,0x83,0xC4,0x08)
# push 0 ; mov ecx,0x6DFBD8 ; call 0x00423300 ; nop nop nop nop
$rnPatch= [byte[]]@(0x6A,0x00,0xB9,0xD8,0xFB,0x6D,0x00,0xE8,0x6C,0x66,0xFD,0xFF,0x90,0x90,0x90,0x90)

# --- sites 2-4: RoomSendGuards (patched <-> original) ---
$guards = @(
    @{ Off=0x45AEC; Name="RMPKSend_GameStart";
       Patched=[byte[]]@(0x8B,0x45,0xFC,0x83,0x78,0x04,0x00,0x0F,0x84,0xB8,0x00,0x00,0x00,0x90);
       Orig   =[byte[]]@(0x8B,0x45,0xFC,0x8B,0x48,0x04,0x8B,0x51,0x0C,0x66,0xC7,0x02,0x0A,0x10) },
    @{ Off=0x4577C; Name="RMPKSend_GameOption";
       Patched=[byte[]]@(0x8B,0x45,0xFC,0x83,0x78,0x04,0x00,0x0F,0x84,0xD4,0x01,0x00,0x00,0x90);
       Orig   =[byte[]]@(0x8B,0x45,0xFC,0x8B,0x48,0x04,0x8B,0x51,0x0C,0x66,0xC7,0x02,0x11,0x10) },
    @{ Off=0x45BFC; Name="RMPKSend_UserLeft";
       Patched=[byte[]]@(0x8B,0x45,0xFC,0x83,0x78,0x04,0x00,0x0F,0x84,0xBD,0x00,0x00,0x00,0x90);
       Orig   =[byte[]]@(0x8B,0x45,0xFC,0x8B,0x48,0x04,0x8B,0x51,0x0C,0x66,0xC7,0x02,0x08,0x10) }
)

$stamp = Get-Date -Format yyyyMMdd_HHmmss
[IO.File]::WriteAllBytes("$ExePath.bak_roomnet2_$stamp", $bytes)

if ($Revert) {
    if (Eq $bytes $rnOff $rnPatch) { Put $bytes $rnOff $rnOrig; Write-Host "Reverted: room-create debug-log restored" -ForegroundColor Green }
    foreach ($g in $guards) { if (Eq $bytes $g.Off $g.Orig) { Put $bytes $g.Off $g.Patched; Write-Host "Reverted: $($g.Name) guard re-applied" -ForegroundColor Green } }
    [IO.File]::WriteAllBytes($ExePath, $bytes)
    Write-Host "Revert complete."
    return
}

if (Eq $bytes $rnOff $rnPatch) { Write-Host "Already patched: room-create RoomNetMGR_Setup" -ForegroundColor Yellow }
elseif (Eq $bytes $rnOff $rnOrig) { Put $bytes $rnOff $rnPatch; Write-Host "Patched: RoomNetMGR_Setup at room create (@0x0044CC88)" -ForegroundColor Green }
else { $h=($bytes[$rnOff..($rnOff+15)]|%{ "{0:X2}" -f $_ }) -join " "; throw "Unexpected bytes @0x44CC88: $h" }

foreach ($g in $guards) {
    if (Eq $bytes $g.Off $g.Orig) { Write-Host "Already original: $($g.Name)" -ForegroundColor Yellow }
    elseif (Eq $bytes $g.Off $g.Patched) { Put $bytes $g.Off $g.Orig; Write-Host "Restored original send: $($g.Name)" -ForegroundColor Green }
    else { $h=($bytes[$g.Off..($g.Off+13)]|%{ "{0:X2}" -f $_ }) -join " "; throw "Unexpected bytes for $($g.Name): $h" }
}

[IO.File]::WriteAllBytes($ExePath, $bytes)
Write-Host ""
Write-Host "Done. RoomNetMGR is initialized at room create; room-master sends are live." -ForegroundColor Green
Write-Host "Apply on BOTH PCs, restart the game. Lobby/login flow is untouched." -ForegroundColor Cyan
