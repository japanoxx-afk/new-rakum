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
        if ($Va -ge $start -and $Va -lt ($start + $size)) {
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

# -----------------------------------------------------------------------
# PATCH: GameStartInit (0x44CBE0) GUEST cases 1 and 2.
#
# ROOT CAUSE: The 1-second countdown timer at 0x4D5B00 gates on
# [0x6e0576] == 2 or 3 before decrementing [0x6dfc74] (battle_state).
# HOST sets [0x6e0576]=3 immediately in GameStartInit case 0, so its
# 5-second countdown runs right away. GUEST never sets [0x6e0576] in
# its cases (1/2/3); it only gets set to 2 when the DP8 callback fires
# at ~18 seconds (after enum + join handshake). By then HOST has already
# entered battle at t=5s and the session is in an irrecoverable state.
#
# FIX: Set [0x6e0576]=3 at the START of GUEST cases 1 and 2, replacing
# the debug-print calls that are present at the top of each case.
# This synchronises the countdown start for both HOST and GUEST.
#
# The debug print bytes:
#   push 0x4eeb6c / push 4 / call [0x4eb3d0] / add esp, 8  (case 1)
#   push 0x4eeb54 / push 4 / call [0x4eb3d0] / add esp, 8  (case 2)
# are replaced with:
#   mov byte ptr [0x6e0576], 3   (7 bytes)
#   nop * 9                      (9 bytes)
# -----------------------------------------------------------------------

$patchBytes = [byte[]]@(
    0xC6, 0x05, 0x76, 0x05, 0x6E, 0x00, 0x03,   # mov byte ptr [0x6e0576], 3
    0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90  # nop * 9
)

$patches = @(
    @{
        Label    = "GameStartInit GUEST case 1"
        VA       = [uint32]0x0044CC9D
        Expected = [byte[]]@(
            0x68, 0x6C, 0xEB, 0x4E, 0x00,             # push 0x4eeb6c
            0x6A, 0x04,                                 # push 4
            0xFF, 0x15, 0xD0, 0xB3, 0x4E, 0x00,        # call [0x4eb3d0]
            0x83, 0xC4, 0x08                            # add esp, 8
        )
    },
    @{
        Label    = "GameStartInit GUEST case 2"
        VA       = [uint32]0x0044CCCD
        Expected = [byte[]]@(
            0x68, 0x54, 0xEB, 0x4E, 0x00,              # push 0x4eeb54
            0x6A, 0x04,                                  # push 4
            0xFF, 0x15, 0xD0, 0xB3, 0x4E, 0x00,         # call [0x4eb3d0]
            0x83, 0xC4, 0x08                             # add esp, 8
        )
    }
)

$needsWrite = $false

foreach ($p in $patches) {
    $offset = Convert-VaToFileOffset $bytes $p.VA
    $current = New-Object byte[] $p.Expected.Length
    [Array]::Copy($bytes, $offset, $current, 0, $current.Length)

    if (Test-BytesEqual $current $patchBytes) {
        Write-Host "Already patched: $($p.Label)" -ForegroundColor Yellow
        continue
    }

    if (-not (Test-BytesEqual $current $p.Expected)) {
        $hex = ($current | ForEach-Object { "{0:X2}" -f $_ }) -join " "
        throw "Unexpected bytes at VA 0x$('{0:X8}' -f $p.VA): $hex"
    }

    [Array]::Copy($patchBytes, 0, $bytes, $offset, $patchBytes.Length)
    Write-Host "Patched: $($p.Label) at VA 0x$('{0:X8}' -f $p.VA)" -ForegroundColor Green
    $needsWrite = $true
}

if ($needsWrite) {
    $backup = "$ExePath.bak_guestp2psync_$(Get-Date -Format yyyyMMdd_HHmmss)"
    [IO.File]::WriteAllBytes($backup, [IO.File]::ReadAllBytes($ExePath))
    [IO.File]::WriteAllBytes($ExePath, $bytes)
    Write-Host "Written. Backup: $backup" -ForegroundColor Cyan
} else {
    Write-Host "No changes needed." -ForegroundColor Yellow
}
