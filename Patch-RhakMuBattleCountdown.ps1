param(
    [string]$ExePath = "C:\Program Files (x86)\TriggerSoft\RhakMu\Rhakmu.exe",
    [ValidateRange(5, 60)]
    [int]$Seconds = 20
)

# Patches the battle-start countdown value at 0x44D2E8.
# BattleStartSync writes this byte as part of:
#   mov byte ptr [0x006DFC74], <Seconds>
# The default (BattleStartSync default) is 5.  We increase it to 20 so that
# both HOST and GUEST (with GuestP2PSync applied) enter battle AFTER DP8 has
# had time to connect (~9-18 s).  20 s provides a comfortable margin.

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

if (-not (Test-Path -LiteralPath $ExePath)) { throw "File not found: $ExePath" }
$bytes = [IO.File]::ReadAllBytes($ExePath)

# The countdown byte is at VA 0x44D2E8 = 0x44D2E2 + 6
# (BattleStartSync seedZeroPatch: C6 05 74 FC 6D 00 [05] ...)
# Verify the surrounding context matches the BattleStartSync patch.
$ctxVA  = [uint32]0x44D2E2
$ctxOff = Convert-VaToFileOffset $bytes $ctxVA

# Expected prefix: mov byte ptr [0x6DFC74], <any> = C6 05 74 FC 6D 00 ??
$prefix = [byte[]]@(0xC6, 0x05, 0x74, 0xFC, 0x6D, 0x00)
$ok = $true
for ($i = 0; $i -lt $prefix.Length; $i++) {
    if ($bytes[$ctxOff + $i] -ne $prefix[$i]) { $ok = $false; break }
}
if (-not $ok) {
    $hex = ($bytes[$ctxOff..($ctxOff+6)] | ForEach-Object { "{0:X2}" -f $_ }) -join " "
    throw "BattleStartSync prefix mismatch at 0x$('44D2E2') — not patched? bytes: $hex"
}

$countOff = $ctxOff + 6
$current  = $bytes[$countOff]
$target   = [byte]$Seconds

if ($current -eq $target) {
    Write-Host "Already set: countdown = $Seconds s (no change needed)" -ForegroundColor Yellow
    return
}

Write-Host "Countdown byte at VA 0x44D2E8: current=$current, target=$target ($Seconds s)"

$backup = "$ExePath.bak_countdown_$(Get-Date -Format yyyyMMdd_HHmmss)"
[IO.File]::WriteAllBytes($backup, $bytes)

$bytes[$countOff] = $target
[IO.File]::WriteAllBytes($ExePath, $bytes)
Write-Host "Patched: battle countdown = $Seconds s" -ForegroundColor Green
Write-Host "Backup: $backup"
