param(
    [string]$ExePath = "C:\Program Files (x86)\TriggerSoft\RhakMu\Rhakmu.exe"
)

$ErrorActionPreference = "Stop"

function Convert-VaToFileOffset([byte[]]$Bytes, [uint32]$Va) {
    $pe = [BitConverter]::ToUInt32($Bytes, 0x3C)
    $imageBase = [BitConverter]::ToUInt32($Bytes, $pe + 0x34)
    $sections = [BitConverter]::ToUInt16($Bytes, $pe + 0x06)
    $optSize = [BitConverter]::ToUInt16($Bytes, $pe + 0x14)
    $secOff = $pe + 0x18 + $optSize

    for ($i = 0; $i -lt $sections; $i++) {
        $off = $secOff + ($i * 40)
        $virtualSize = [BitConverter]::ToUInt32($Bytes, $off + 8)
        $virtualAddress = [BitConverter]::ToUInt32($Bytes, $off + 12)
        $rawSize = [BitConverter]::ToUInt32($Bytes, $off + 16)
        $rawPtr = [BitConverter]::ToUInt32($Bytes, $off + 20)
        $start = $imageBase + $virtualAddress
        $size = [Math]::Max($virtualSize, $rawSize)
        $end = $start + $size
        if ($Va -ge $start -and $Va -lt $end) {
            return [int]($rawPtr + ($Va - $start))
        }
    }

    throw ("VA 0x{0:X8} is not inside a PE section" -f $Va)
}

function Test-BytesEqual([byte[]]$A, [byte[]]$B) {
    if ($A.Length -ne $B.Length) { return $false }
    for ($i = 0; $i -lt $A.Length; $i++) {
        if ($A[$i] -ne $B[$i]) { return $false }
    }
    return $true
}

if (-not (Test-Path -LiteralPath $ExePath)) {
    throw "File not found: $ExePath"
}

$bytes = [IO.File]::ReadAllBytes($ExePath)

# TNPacket_ReplyBattleReqReply default branch at VA 0x0044D2E2.
# A host game-start broadcast arrives as FF 0F 07 00 02 00 00:
# packet[4]=2 and packet[5]=0. The stock handler switches on packet[5]-1,
# falls into this default branch, prints a debug string, and returns without
# starting the remote client's countdown. Replace the default debug branch with
# the same local countdown state used by classRoomNetMGR::RMPKRecv_GameStart.
$va = [uint32]0x0044D2E2
$offset = Convert-VaToFileOffset $bytes $va
$expected = [byte[]]@(
    0x68,0x30,0xEC,0x4E,0x00,
    0x6A,0x04,
    0xFF,0x15,0xD0,0xB3,0x4E,0x00,
    0x83,0xC4,0x08,
    0x5F,0x5E,0x5B,0x8B,0xE5,0x5D,0xC3
)
$patch = [byte[]]@(
    # mov byte ptr [0x006DFC74], 5
    0xC6,0x05,0x74,0xFC,0x6D,0x00,0x05,
    # pop edi; pop esi; pop ebx; mov esp, ebp; pop ebp; ret
    0x5F,0x5E,0x5B,0x8B,0xE5,0x5D,0xC3,
    # pad remaining replaced debug-call bytes
    0x90,0x90,0x90,0x90,0x90,0x90,0x90,0x90,0x90
)

$current = New-Object byte[] $expected.Length
[Array]::Copy($bytes, $offset, $current, 0, $current.Length)

if (Test-BytesEqual $current $patch) {
    Write-Host "Already patched: battle start sync default branch" -ForegroundColor Yellow
    return
}

if (-not (Test-BytesEqual $current $expected)) {
    $hex = ($current | ForEach-Object { "{0:X2}" -f $_ }) -join " "
    throw "Unexpected bytes at VA 0x$('{0:X8}' -f $va), file offset 0x$('{0:X}' -f $offset): $hex"
}

$backup = "$ExePath.bak_battlestartsync_$(Get-Date -Format yyyyMMdd_HHmmss)"
[IO.File]::WriteAllBytes($backup, $bytes)

[Array]::Copy($patch, 0, $bytes, $offset, $patch.Length)
[IO.File]::WriteAllBytes($ExePath, $bytes)

Write-Host "Patched TNPacket_ReplyBattleReqReply default branch for remote game-start sync." -ForegroundColor Green
Write-Host "Backup: $backup"
