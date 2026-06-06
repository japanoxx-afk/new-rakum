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
# Restoring this branch is useful for A/B tests when the host starts alone:
# it removes the client-side forced countdown state and lets us confirm whether
# that patch is bypassing the original peer-readiness checks.
$va = [uint32]0x0044D2E2
$offset = Convert-VaToFileOffset $bytes $va
$original = [byte[]]@(
    0x68,0x30,0xEC,0x4E,0x00,
    0x6A,0x04,
    0xFF,0x15,0xD0,0xB3,0x4E,0x00,
    0x83,0xC4,0x08,
    0x5F,0x5E,0x5B,0x8B,0xE5,0x5D,0xC3
)
$oldPatch = [byte[]]@(
    0xC6,0x05,0x74,0xFC,0x6D,0x00,0x05,
    0x5F,0x5E,0x5B,0x8B,0xE5,0x5D,0xC3,
    0x90,0x90,0x90,0x90,0x90,0x90,0x90,0x90,0x90
)
$seedZeroPatch = [byte[]]@(
    0xC6,0x05,0x74,0xFC,0x6D,0x00,0x05,
    0x33,0xC0,0xA3,0x70,0x09,0x6E,0x00,
    0x5F,0x5E,0x5B,0x8B,0xE5,0x5D,0xC3,
    0x90,0x90
)

$current = New-Object byte[] $original.Length
[Array]::Copy($bytes, $offset, $current, 0, $current.Length)

if (Test-BytesEqual $current $original) {
    Write-Host "Already restored: battle start sync default branch is original." -ForegroundColor Yellow
    return
}

if (-not (Test-BytesEqual $current $oldPatch) -and -not (Test-BytesEqual $current $seedZeroPatch)) {
    $hex = ($current | ForEach-Object { "{0:X2}" -f $_ }) -join " "
    throw "Unexpected bytes at VA 0x$('{0:X8}' -f $va), file offset 0x$('{0:X}' -f $offset): $hex"
}

$backup = "$ExePath.bak_restore_battlestartsync_$(Get-Date -Format yyyyMMdd_HHmmss)"
[IO.File]::WriteAllBytes($backup, $bytes)

[Array]::Copy($original, 0, $bytes, $offset, $original.Length)
[IO.File]::WriteAllBytes($ExePath, $bytes)

Write-Host "Restored TNPacket_ReplyBattleReqReply default branch to original bytes." -ForegroundColor Green
Write-Host "Backup: $backup"
