param(
    [string]$ExePath = "C:\Program Files (x86)\TriggerSoft\RhakMu\Rhakmu.exe",
    [switch]$Revert
)

# ROOT CAUSE FIX for the in-game "connecting" stall.
#
# In-game sync needs the host to send RMPK 0x100A (game start) etc. over
# classRoomNetMGR. RMPKSend_* skip the send when RoomNetMGR's send buffer
# (this+4) is null. RoomNetMGR's send buffer is only allocated by
# RoomNetMGR_Setup (0x423300), which the channel-select handler (0x44C0E0,
# type 0x07FF) calls ONLY when the flag [0x6DFCD6]==1. That flag is set to 1
# only by a specific CPannelMgr menu state (0x462AFC), which never happens in
# our flow -> RoomNetMGR is never initialized -> every room-master send is
# skipped -> the guest waits on "connecting" forever.
#
# The previous team's Patch-RhakMuRoomSendGuards worked around the resulting
# null-deref by SKIPPING the sends (which also dropped the 0x100A packet-type
# write), so the room-master coordination never actually happened.
#
# This patch:
#  1) Forces RoomNetMGR_Setup to always run: NOPs the "je" gate at 0x0044C1DF
#     so the channel-select handler allocates the RoomNetMGR send buffer
#     regardless of [0x6DFCD6].
#  2) Reverts the 3 RoomSendGuards so RMPKSend_GameStart/GameOption/UserLeft
#     run their ORIGINAL code (writing the real 0x100A/0x10xx packet type and
#     actually sending). Safe now because (1) guarantees this+4 is allocated.

$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $ExePath)) { throw "File not found: $ExePath" }
$bytes = [IO.File]::ReadAllBytes($ExePath)

function Eq($a,$o,$e){ for($i=0;$i -lt $e.Length;$i++){ if($a[$o+$i] -ne $e[$i]){ return $false } } return $true }
function Put($a,$o,$p){ for($i=0;$i -lt $p.Length;$i++){ $a[$o+$i]=$p[$i] } }

# --- site 1: channel-select RoomNetMGR gate (file offset 0x4C1DF) ---
$gateOff = 0x4C1DF
$gateOrig = [byte[]]@(0x0F,0x84,0x39,0x01,0x00,0x00)   # je 0x44c31e
$gateNop  = [byte[]]@(0x90,0x90,0x90,0x90,0x90,0x90)

# --- sites 2-4: RoomSendGuards (file offsets), patched <-> original ---
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
[IO.File]::WriteAllBytes("$ExePath.bak_roomnet_$stamp", $bytes)

if ($Revert) {
    if (Eq $bytes $gateOff $gateNop) { Put $bytes $gateOff $gateOrig; Write-Host "Reverted: RoomNetMGR gate restored" -ForegroundColor Green }
    foreach ($g in $guards) {
        if (Eq $bytes $g.Off $g.Orig) { Put $bytes $g.Off $g.Patched; Write-Host "Reverted: $($g.Name) guard re-applied" -ForegroundColor Green }
    }
    [IO.File]::WriteAllBytes($ExePath, $bytes)
    Write-Host "Revert complete. Backup: $ExePath.bak_roomnet_$stamp"
    return
}

# Force RoomNetMGR setup
if (Eq $bytes $gateOff $gateNop) { Write-Host "Already patched: RoomNetMGR gate" -ForegroundColor Yellow }
elseif (Eq $bytes $gateOff $gateOrig) { Put $bytes $gateOff $gateNop; Write-Host "Patched: force RoomNetMGR_Setup (NOP gate @0x0044C1DF)" -ForegroundColor Green }
else { $h=($bytes[$gateOff..($gateOff+5)]|%{ "{0:X2}" -f $_ }) -join " "; throw "Unexpected gate bytes: $h" }

# Revert RoomSendGuards -> original
foreach ($g in $guards) {
    if (Eq $bytes $g.Off $g.Orig) { Write-Host "Already original: $($g.Name)" -ForegroundColor Yellow }
    elseif (Eq $bytes $g.Off $g.Patched) { Put $bytes $g.Off $g.Orig; Write-Host "Restored original send: $($g.Name)" -ForegroundColor Green }
    else { $h=($bytes[$g.Off..($g.Off+13)]|%{ "{0:X2}" -f $_ }) -join " "; throw "Unexpected bytes for $($g.Name): $h" }
}

[IO.File]::WriteAllBytes($ExePath, $bytes)
Write-Host ""
Write-Host "Done. RoomNetMGR is now force-initialized and room-master sends are live." -ForegroundColor Green
Write-Host "Backup: $ExePath.bak_roomnet_$stamp"
Write-Host "Apply on BOTH PCs, then restart the game." -ForegroundColor Cyan
